import json
import sys
from datetime import datetime
from pathlib import Path

import click

from cqltrack import __version__
from cqltrack.config import Config
from cqltrack.exceptions import CqlTrackError
from cqltrack.migrator import Migrator
from cqltrack.parser import scan_directory
from cqltrack.session import connect


@click.group()
@click.option(
    "--config", "-c", "config_path", default=None,
    help="Path to cqltrack.yml config file.",
)
@click.option("--profile", default=None, help="Environment profile (dev, staging, prod, ...).")
@click.option("--keyspace", "-k", default=None, help="Override target keyspace.")
@click.option("--host", default=None, help="Cassandra contact point(s), comma-separated.")
@click.option("--port", "-p", type=int, default=None, help="Cassandra native transport port.")
@click.option("--json", "json_out", is_flag=True, default=False, help="Output as JSON.")
@click.version_option(__version__, prog_name="cqltrack")
@click.pass_context
def main(ctx, config_path, profile, keyspace, host, port, json_out):
    """cqltrack - Cassandra schema migrations done right."""
    cfg = Config.load(config_path, profile=profile)
    if keyspace:
        cfg.keyspace = keyspace
    if host:
        cfg.contact_points = host.split(",")
    if port:
        cfg.port = port
    ctx.ensure_object(dict)
    ctx.obj["config"] = cfg
    ctx.obj["json"] = json_out


# ---- init ------------------------------------------------------------------

@main.command()
@click.pass_context
def init(ctx):
    """Create the keyspace and tracking tables."""
    cfg = ctx.obj["config"]
    try:
        session = connect(cfg, use_keyspace=False)
    except Exception as exc:
        raise click.ClickException(f"Cannot connect to Cassandra: {exc}")

    migrator = Migrator(session, cfg)
    migrator.init_tracking()

    cfg.migration_dir.mkdir(parents=True, exist_ok=True)
    click.echo(f"Initialized cqltrack in keyspace '{cfg.keyspace}'.")
    click.echo(f"Migrations directory: {cfg.migration_dir.resolve()}")


# ---- migrate --------------------------------------------------------------

@main.command()
@click.option("--target", "-t", type=int, default=None, help="Stop at this version.")
@click.option("--dry-run", is_flag=True, help="Show pending migrations without applying.")
@click.pass_context
def migrate(ctx, target, dry_run):
    """Apply pending migrations."""
    cfg = ctx.obj["config"]
    try:
        session = connect(cfg)
    except Exception as exc:
        raise click.ClickException(
            f"Cannot connect to Cassandra: {exc}\n"
            f"Have you run 'cqltrack init' yet?"
        )

    migrator = Migrator(session, cfg)

    # refuse to run if any checksums are off
    mismatches = migrator.validate()
    if mismatches:
        for m, recorded in mismatches:
            click.echo(
                f"CHECKSUM MISMATCH  V{m.version:03d}  "
                f"(expected {recorded}, got {m.checksum})",
                err=True,
            )
        click.echo(
            "Aborting. Fix the files or run 'cqltrack repair' to accept changes.",
            err=True,
        )
        sys.exit(1)

    applied = migrator.migrate(target=target, dry_run=dry_run)
    if applied and not dry_run:
        click.echo(f"\nApplied {len(applied)} migration(s).")


# ---- rollback --------------------------------------------------------------

@main.command()
@click.option("--steps", "-n", type=int, default=1, help="How many to roll back.")
@click.confirmation_option(prompt="Roll back migrations — are you sure?")
@click.pass_context
def rollback(ctx, steps):
    """Undo the most recently applied migration(s)."""
    cfg = ctx.obj["config"]
    try:
        session = connect(cfg)
    except Exception as exc:
        raise click.ClickException(f"Cannot connect to Cassandra: {exc}")

    migrator = Migrator(session, cfg)
    try:
        rolled = migrator.rollback(steps=steps)
    except CqlTrackError as exc:
        raise click.ClickException(str(exc))

    if rolled:
        click.echo(f"\nRolled back {len(rolled)} migration(s).")


# ---- baseline --------------------------------------------------------------

@main.command()
@click.argument("version", type=int)
@click.confirmation_option(prompt="Mark migrations as applied without running them?")
@click.pass_context
def baseline(ctx, version):
    """Mark V001 through VERSION as applied without executing.

    Use this when adopting cqltrack on an existing database that
    already has tables from earlier migrations.
    """
    cfg = ctx.obj["config"]
    try:
        session = connect(cfg)
    except Exception as exc:
        raise click.ClickException(f"Cannot connect to Cassandra: {exc}")

    migrator = Migrator(session, cfg)
    count = migrator.baseline(version)
    if count:
        click.echo(f"\nBaselined {count} migration(s) up to V{version:03d}.")
    else:
        click.echo("Nothing to baseline — already up to date.")


# ---- status ----------------------------------------------------------------

@main.command()
@click.pass_context
def status(ctx):
    """Show which migrations have been applied and which are pending."""
    cfg = ctx.obj["config"]
    json_out = ctx.obj["json"]

    try:
        session = connect(cfg)
    except Exception as exc:
        raise click.ClickException(f"Cannot connect to Cassandra: {exc}")

    migrator = Migrator(session, cfg)
    applied = migrator.get_applied()
    all_migs = scan_directory(cfg.migration_dir)

    if json_out:
        data = []
        for m in all_migs:
            entry = {
                "version": m.version,
                "description": m.description,
                "status": "applied" if m.version in applied else "pending",
            }
            if m.version in applied:
                row = applied[m.version]
                entry["applied_at"] = row.applied_at.isoformat() if row.applied_at else None
                entry["applied_by"] = getattr(row, "applied_by", None)
            data.append(entry)
        click.echo(json.dumps(data, indent=2))
        return

    if not all_migs:
        click.echo("No migration files found.")
        return

    click.echo(f"Keyspace:   {cfg.keyspace}")
    click.echo(f"Migrations: {cfg.migration_dir.resolve()}\n")

    for m in all_migs:
        if m.version in applied:
            row = applied[m.version]
            when = row.applied_at.strftime("%Y-%m-%d %H:%M:%S") if row.applied_at else "?"
            marker = click.style("applied", fg="green")
        else:
            when = ""
            marker = click.style("pending", fg="yellow")

        click.echo(f"  V{m.version:03d}  {marker:>17s}  {m.description:<30s}  {when}")


# ---- history ---------------------------------------------------------------

@main.command()
@click.pass_context
def history(ctx):
    """Show full migration history with who applied and duration."""
    cfg = ctx.obj["config"]
    json_out = ctx.obj["json"]

    try:
        session = connect(cfg)
    except Exception as exc:
        raise click.ClickException(f"Cannot connect to Cassandra: {exc}")

    migrator = Migrator(session, cfg)
    records = migrator.get_all_records()

    if json_out:
        data = []
        for r in records:
            data.append({
                "version": r.version,
                "description": getattr(r, "description", ""),
                "status": getattr(r, "status", "applied"),
                "checksum": getattr(r, "checksum", ""),
                "applied_at": r.applied_at.isoformat() if r.applied_at else None,
                "applied_by": getattr(r, "applied_by", ""),
                "exec_time_ms": getattr(r, "exec_time_ms", 0),
            })
        click.echo(json.dumps(data, indent=2))
        return

    if not records:
        click.echo("No migrations have been applied.")
        return

    click.echo(f"Keyspace: {cfg.keyspace}\n")

    for r in records:
        when = r.applied_at.strftime("%Y-%m-%d %H:%M:%S") if r.applied_at else "?"
        who = getattr(r, "applied_by", "?")
        ms = getattr(r, "exec_time_ms", 0) or 0
        status = getattr(r, "status", "applied")
        desc = getattr(r, "description", "")

        if status == "failed":
            marker = click.style("FAILED", fg="red")
        else:
            marker = click.style("OK", fg="green")

        click.echo(
            f"  V{r.version:03d}  {marker}  {desc:<28s}  "
            f"{when}  {ms:>5d}ms  {who}"
        )


# ---- pending ---------------------------------------------------------------

@main.command()
@click.pass_context
def pending(ctx):
    """Exit with code 1 if there are unapplied migrations.

    Useful as a CI gate: cqltrack pending || echo 'BLOCKED'
    """
    cfg = ctx.obj["config"]
    json_out = ctx.obj["json"]

    try:
        session = connect(cfg)
    except Exception as exc:
        raise click.ClickException(f"Cannot connect to Cassandra: {exc}")

    migrator = Migrator(session, cfg)
    pend = migrator.get_pending()

    if json_out:
        click.echo(json.dumps({
            "pending_count": len(pend),
            "versions": [m.version for m in pend],
        }))
    elif pend:
        click.echo(f"{len(pend)} pending migration(s):")
        for m in pend:
            click.echo(f"  V{m.version:03d}  {m.description}")
    else:
        click.echo("No pending migrations.")

    if pend:
        sys.exit(1)


# ---- validate -------------------------------------------------------------

@main.command()
@click.pass_context
def validate(ctx):
    """Check that applied migration files haven't been modified."""
    cfg = ctx.obj["config"]
    try:
        session = connect(cfg)
    except Exception as exc:
        raise click.ClickException(f"Cannot connect to Cassandra: {exc}")

    migrator = Migrator(session, cfg)
    bad = migrator.validate()

    if not bad:
        click.echo("All checksums match.")
        return

    for m, recorded in bad:
        click.echo(f"MISMATCH  V{m.version:03d}  recorded={recorded}  current={m.checksum}")
    sys.exit(1)


# ---- repair ----------------------------------------------------------------

@main.command()
@click.confirmation_option(prompt="This will overwrite recorded checksums. Continue?")
@click.pass_context
def repair(ctx):
    """Update recorded checksums to match the files on disk."""
    cfg = ctx.obj["config"]
    try:
        session = connect(cfg)
    except Exception as exc:
        raise click.ClickException(f"Cannot connect to Cassandra: {exc}")

    migrator = Migrator(session, cfg)
    fixed = migrator.repair()
    if fixed:
        click.echo(f"Repaired {fixed} checksum(s).")
    else:
        click.echo("Nothing to repair.")


# ---- new -------------------------------------------------------------------

@main.command("new")
@click.argument("name")
@click.pass_context
def new_migration(ctx, name):
    """Scaffold a new migration file.

    NAME is a short description like 'create_users_table'.
    """
    cfg = ctx.obj["config"]
    cfg.migration_dir.mkdir(parents=True, exist_ok=True)

    existing = scan_directory(cfg.migration_dir)
    next_ver = max((m.version for m in existing), default=0) + 1

    safe_name = name.strip().lower().replace(" ", "_").replace("-", "_")
    filename = f"V{next_ver:03d}__{safe_name}.cql"
    filepath = cfg.migration_dir / filename

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    filepath.write_text(
        f"-- Migration: {name}\n"
        f"-- Created:   {now}\n"
        f"\n"
        f"-- write your CQL here\n"
        f"\n"
        f"\n"
        f"-- @down\n"
        f"-- rollback statements go here\n",
        encoding="utf-8",
    )

    click.echo(f"Created {filepath}")


# ---- lint ------------------------------------------------------------------

@main.command()
@click.pass_context
def lint(ctx):
    """Static analysis of migration files for common mistakes."""
    from cqltrack.linter import lint_directory

    cfg = ctx.obj["config"]
    json_out = ctx.obj["json"]
    warnings = lint_directory(cfg.migration_dir)

    if json_out:
        data = [
            {"version": w.version, "file": w.filename, "line": w.line,
             "severity": w.severity, "rule": w.rule, "message": w.message}
            for w in warnings
        ]
        click.echo(json.dumps(data, indent=2))
        if any(w.severity == "error" for w in warnings):
            sys.exit(1)
        return

    if not warnings:
        click.echo("All migrations look good.")
        return

    errors = 0
    for w in warnings:
        if w.severity == "error":
            icon = click.style("ERR ", fg="red")
            errors += 1
        else:
            icon = click.style("WARN", fg="yellow")

        loc = f"V{w.version:03d}"
        if w.line:
            loc += f":{w.line}"

        click.echo(f"  {icon}  {loc:<12s}  [{w.rule}]  {w.message}")

    click.echo(f"\n{len(warnings)} issue(s) found.")
    if errors:
        sys.exit(1)


# ---- snapshot --------------------------------------------------------------

@main.command()
@click.option("--output", "-o", default=None, help="Write to file instead of stdout.")
@click.pass_context
def snapshot(ctx, output):
    """Export the live keyspace schema as a CQL file."""
    cfg = ctx.obj["config"]
    try:
        session = connect(cfg)
    except Exception as exc:
        raise click.ClickException(f"Cannot connect to Cassandra: {exc}")

    # the driver metadata gives us the full schema
    cluster = session.cluster
    cluster.refresh_schema_metadata()
    ks_meta = cluster.metadata.keyspaces.get(cfg.keyspace)

    if ks_meta is None:
        raise click.ClickException(f"Keyspace '{cfg.keyspace}' not found.")

    cql = ks_meta.export_as_string()

    if output:
        out_path = Path(output)
        out_path.write_text(cql, encoding="utf-8")
        click.echo(f"Schema snapshot written to {out_path}")
    else:
        click.echo(cql)


# ---- diff ------------------------------------------------------------------

@main.command()
@click.option("--source", "source_profile", default=None,
              help="Source profile name (default: current config).")
@click.option("--target", "target_profile", default=None,
              help="Target profile name.")
@click.option("--source-keyspace", default=None,
              help="Override source keyspace (for same-cluster comparison).")
@click.option("--target-keyspace", default=None,
              help="Override target keyspace (for same-cluster comparison).")
@click.pass_context
def diff(ctx, source_profile, target_profile, source_keyspace, target_keyspace):
    """Compare schemas between two environments or keyspaces.

    \b
    Examples:
      cqltrack diff --source dev --target staging
      cqltrack diff --target-keyspace myapp_staging
      cqltrack diff --source-keyspace myapp_v1 --target-keyspace myapp_v2
    """
    from cqltrack.differ import SchemaDiffer

    config_path = ctx.parent.params.get("config_path")
    json_out = ctx.obj["json"]

    # build source config
    if source_profile:
        src_cfg = Config.load(config_path, profile=source_profile)
    else:
        src_cfg = ctx.obj["config"]
    if source_keyspace:
        src_cfg.keyspace = source_keyspace

    # build target config
    if target_profile:
        tgt_cfg = Config.load(config_path, profile=target_profile)
    elif target_keyspace:
        # same connection settings, different keyspace
        tgt_cfg = Config.load(config_path, profile=source_profile)
        tgt_cfg.keyspace = target_keyspace
    else:
        raise click.ClickException(
            "Need at least --target <profile> or --target-keyspace <name>"
        )

    src_label = source_profile or src_cfg.keyspace
    tgt_label = target_profile or tgt_cfg.keyspace

    # connect and fetch metadata
    try:
        src_session = connect(src_cfg)
    except Exception as exc:
        raise click.ClickException(f"Cannot connect to source: {exc}")

    # if same host + port, reuse connection with different keyspace
    same_cluster = (
        src_cfg.contact_points == tgt_cfg.contact_points
        and src_cfg.port == tgt_cfg.port
    )
    if same_cluster:
        tgt_session = src_session
    else:
        try:
            tgt_session = connect(tgt_cfg)
        except Exception as exc:
            raise click.ClickException(f"Cannot connect to target: {exc}")

    src_cluster = src_session.cluster
    src_cluster.refresh_schema_metadata()
    src_ks = src_cluster.metadata.keyspaces.get(src_cfg.keyspace)
    if src_ks is None:
        raise click.ClickException(f"Source keyspace '{src_cfg.keyspace}' not found.")

    if same_cluster:
        tgt_ks = src_cluster.metadata.keyspaces.get(tgt_cfg.keyspace)
    else:
        tgt_cluster = tgt_session.cluster
        tgt_cluster.refresh_schema_metadata()
        tgt_ks = tgt_cluster.metadata.keyspaces.get(tgt_cfg.keyspace)

    if tgt_ks is None:
        raise click.ClickException(f"Target keyspace '{tgt_cfg.keyspace}' not found.")

    # diff
    differ = SchemaDiffer(src_ks, tgt_ks, src_label, tgt_label)
    diffs = differ.diff()

    if json_out:
        data = [
            {"kind": d.kind, "path": d.path, "change": d.change,
             "source": d.left, "target": d.right}
            for d in diffs
        ]
        click.echo(json.dumps(data, indent=2))
        if diffs:
            sys.exit(1)
        return

    if not diffs:
        click.echo(f"Schemas match: {src_cfg.keyspace} == {tgt_cfg.keyspace}")
        return

    click.echo(f"Schema diff: {src_cfg.keyspace} <-> {tgt_cfg.keyspace}\n")

    for d in diffs:
        kind_str = click.style(f"{d.kind:<10s}", bold=True)

        if d.change == "only_in_source":
            arrow = click.style(f"only in {src_label}", fg="red")
            detail = f"{d.left}"
        elif d.change == "only_in_target":
            arrow = click.style(f"only in {tgt_label}", fg="green")
            detail = f"{d.right}"
        elif d.change == "type_mismatch":
            arrow = click.style("type mismatch", fg="yellow")
            detail = f"{d.left} -> {d.right}"
        else:
            arrow = click.style("differs", fg="yellow")
            detail = f"{d.left} -> {d.right}"

        click.echo(f"  {kind_str}  {d.path:<30s}  {arrow}  {detail}")

    click.echo(f"\n{len(diffs)} difference(s) found.")
    sys.exit(1)


# ---- profiles (info) -------------------------------------------------------

@main.command("profiles")
@click.pass_context
def list_profiles(ctx):
    """List available environment profiles."""
    config_path = ctx.parent.params.get("config_path")
    names = Config.available_profiles(config_path)

    if not names:
        click.echo("No profiles defined in cqltrack.yml.")
        click.echo("Add a 'profiles:' section — see cqltrack.yml.example")
        return

    click.echo("Available profiles:")
    for name in names:
        click.echo(f"  {name}")
