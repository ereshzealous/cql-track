import os
import socket
import time
from datetime import datetime

import click

from cqltrack.lock import MigrationLock
from cqltrack.parser import scan_directory
from cqltrack.exceptions import MigrationError


HISTORY_TABLE = "cqltrack_history"
LOCK_TABLE = "cqltrack_lock"

# statements that change schema and need agreement across nodes
_DDL_KEYWORDS = ("CREATE", "ALTER", "DROP", "TRUNCATE")

# migration was recorded but failed partway through
FAILED_STATUS = "failed"
APPLIED_STATUS = "applied"


class Migrator:

    def __init__(self, session, config):
        self.session = session
        self.config = config

    # -- bootstrap -----------------------------------------------------------

    def init_tracking(self):
        """Create the keyspace and internal tracking tables.

        Each DDL statement is followed by a schema-agreement wait so the
        next statement sees a consistent view across all nodes.
        """
        repl_str = _replication_cql(self.config.replication)

        self._execute_ddl(
            f"CREATE KEYSPACE IF NOT EXISTS {self.config.keyspace} "
            f"WITH replication = {repl_str}"
        )

        self.session.set_keyspace(self.config.keyspace)

        self._execute_ddl(f"""
            CREATE TABLE IF NOT EXISTS {HISTORY_TABLE} (
                version      int PRIMARY KEY,
                description  text,
                checksum     text,
                status       text,
                applied_at   timestamp,
                applied_by   text,
                exec_time_ms int
            )
        """)

        self._execute_ddl(f"""
            CREATE TABLE IF NOT EXISTS {LOCK_TABLE} (
                lock_id     text PRIMARY KEY,
                owner       text,
                acquired_at timestamp
            ) WITH default_time_to_live = {self.config.lock_ttl}
        """)

    # -- queries -------------------------------------------------------------

    def get_applied(self):
        """Return a dict of version -> row for every successfully applied migration."""
        rows = self.session.execute(f"SELECT * FROM {HISTORY_TABLE}")
        return {
            row.version: row for row in rows
            if getattr(row, "status", APPLIED_STATUS) != FAILED_STATUS
        }

    def get_all_records(self):
        """Return every row from the history table, including failed ones."""
        rows = self.session.execute(f"SELECT * FROM {HISTORY_TABLE}")
        return sorted(rows, key=lambda r: r.version)

    def get_pending(self):
        applied = self.get_applied()
        on_disk = scan_directory(self.config.migration_dir)
        return [m for m in on_disk if m.version not in applied]

    # -- actions -------------------------------------------------------------

    def migrate(self, target=None, dry_run=False):
        """Apply pending migrations, optionally up to *target* version."""
        pending = self.get_pending()
        if target is not None:
            pending = [m for m in pending if m.version <= target]

        if not pending:
            click.echo("Nothing to migrate. Already up to date.")
            return []

        if dry_run:
            click.echo("Dry run - would apply:")
            for m in pending:
                click.echo(f"  V{m.version:03d}  {m.description}")
            return pending

        applied = []
        with MigrationLock(self.session, ttl=self.config.lock_ttl):
            for m in pending:
                # clean up any previous failed attempt for this version
                self._clear_failed(m.version)
                self._apply_one(m)
                applied.append(m)
        return applied

    def rollback(self, steps=1):
        """Undo the N most recently applied migrations."""
        applied = self.get_applied()
        if not applied:
            click.echo("Nothing to roll back.")
            return []

        on_disk = scan_directory(self.config.migration_dir)
        by_version = {m.version: m for m in on_disk}

        targets = sorted(applied.keys(), reverse=True)[:steps]

        rolled = []
        with MigrationLock(self.session, ttl=self.config.lock_ttl):
            for ver in targets:
                if ver not in by_version:
                    raise MigrationError(
                        f"File for V{ver:03d} not found on disk — cannot roll back."
                    )
                m = by_version[ver]
                if not m.down_statements:
                    raise MigrationError(
                        f"V{ver:03d} has no @down section — cannot roll back."
                    )
                self._rollback_one(m)
                rolled.append(m)
        return rolled

    def baseline(self, version):
        """Mark migrations up to *version* as applied without executing them.

        Used when adopting cqltrack on a database that already has tables.
        """
        on_disk = scan_directory(self.config.migration_dir)
        applied = self.get_applied()
        count = 0

        for m in on_disk:
            if m.version > version:
                break
            if m.version in applied:
                continue
            self.session.execute(
                f"INSERT INTO {HISTORY_TABLE} "
                f"(version, description, checksum, status, applied_at, applied_by, exec_time_ms) "
                f"VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    m.version,
                    m.description,
                    m.checksum,
                    APPLIED_STATUS,
                    datetime.utcnow(),
                    _caller_id() + " [baseline]",
                    0,
                ),
            )
            click.echo(f"  Baselined V{m.version:03d}  {m.description}")
            count += 1

        return count

    def validate(self):
        """Compare on-disk checksums against what was recorded.

        Returns a list of (migration, recorded_checksum) tuples for
        every mismatch found.
        """
        applied = self.get_applied()
        on_disk = scan_directory(self.config.migration_dir)
        bad = []
        for m in on_disk:
            if m.version in applied:
                recorded = applied[m.version].checksum
                if recorded != m.checksum:
                    bad.append((m, recorded))
        return bad

    def repair(self):
        """Re-record checksums so they match the current files on disk."""
        applied = self.get_applied()
        on_disk = scan_directory(self.config.migration_dir)
        fixed = 0
        for m in on_disk:
            if m.version in applied and applied[m.version].checksum != m.checksum:
                self.session.execute(
                    f"UPDATE {HISTORY_TABLE} SET checksum = %s WHERE version = %s",
                    (m.checksum, m.version),
                )
                click.echo(f"  Updated checksum for V{m.version:03d}")
                fixed += 1
        return fixed

    # -- internal ------------------------------------------------------------

    def _execute_ddl(self, stmt):
        """Run a DDL statement and wait for all nodes to agree on the schema."""
        self.session.execute(stmt)
        self._wait_for_schema_agreement()

    def _wait_for_schema_agreement(self):
        """Poll until every node in the cluster sees the same schema version.

        Queries system.local and system.peers directly — this is exactly
        what the driver does internally but we do it ourselves so we
        can control the timeout and retry between back-to-back DDL
        statements (CREATE TABLE followed by CREATE INDEX, etc.).
        """
        deadline = time.time() + self.config.schema_agreement_wait
        while time.time() < deadline:
            if self._schemas_agree():
                return
            time.sleep(0.5)
        click.echo(
            "WARNING: schema agreement not reached within "
            f"{self.config.schema_agreement_wait}s — proceeding anyway",
            err=True,
        )

    def _schemas_agree(self):
        """True when every live node reports the same schema_version UUID."""
        versions = set()
        for row in self.session.execute("SELECT schema_version FROM system.local"):
            versions.add(row.schema_version)
        for row in self.session.execute("SELECT schema_version FROM system.peers"):
            if row.schema_version is not None:
                versions.add(row.schema_version)
        return len(versions) <= 1

    def _clear_failed(self, version):
        """Remove a previous failed record so the migration can be retried."""
        rows = self.session.execute(
            f"SELECT version, status FROM {HISTORY_TABLE} WHERE version = %s",
            (version,),
        )
        row = rows.one() if rows else None
        if row and getattr(row, "status", None) == FAILED_STATUS:
            self.session.execute(
                f"DELETE FROM {HISTORY_TABLE} WHERE version = %s",
                (version,),
            )

    def _apply_one(self, migration):
        click.echo(
            f"Applying V{migration.version:03d}  {migration.description} ... ",
            nl=False,
        )
        t0 = time.time()
        try:
            for stmt in migration.up_statements:
                self.session.execute(stmt)
                # only wait for agreement after schema-changing statements,
                # skip for plain DML (INSERT, UPDATE, SELECT, etc.)
                if _is_ddl(stmt):
                    self._wait_for_schema_agreement()
        except Exception as exc:
            click.echo("FAILED")
            elapsed_ms = int((time.time() - t0) * 1000)
            # record the failure so we know this version is in a broken state
            self._record_migration(migration, elapsed_ms, FAILED_STATUS)
            raise MigrationError(
                f"V{migration.version:03d} failed: {exc}\n"
                f"This migration is marked as 'failed' in the history table.\n"
                f"Fix the issue, then re-run 'cqltrack migrate' to retry."
            ) from exc

        elapsed_ms = int((time.time() - t0) * 1000)
        self._record_migration(migration, elapsed_ms, APPLIED_STATUS)
        click.echo(f"OK ({elapsed_ms}ms)")

    def _record_migration(self, migration, elapsed_ms, status):
        self.session.execute(
            f"INSERT INTO {HISTORY_TABLE} "
            f"(version, description, checksum, status, applied_at, applied_by, exec_time_ms) "
            f"VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                migration.version,
                migration.description,
                migration.checksum,
                status,
                datetime.utcnow(),
                _caller_id(),
                elapsed_ms,
            ),
        )

    def _rollback_one(self, migration):
        click.echo(
            f"Rolling back V{migration.version:03d}  {migration.description} ... ",
            nl=False,
        )
        t0 = time.time()
        try:
            for stmt in migration.down_statements:
                self.session.execute(stmt)
                if _is_ddl(stmt):
                    self._wait_for_schema_agreement()
        except Exception as exc:
            click.echo("FAILED")
            raise MigrationError(
                f"Rollback V{migration.version:03d} failed: {exc}"
            ) from exc

        self.session.execute(
            f"DELETE FROM {HISTORY_TABLE} WHERE version = %s",
            (migration.version,),
        )
        elapsed_ms = int((time.time() - t0) * 1000)
        click.echo(f"OK ({elapsed_ms}ms)")


# ---------------------------------------------------------------------------
# module-level helpers
# ---------------------------------------------------------------------------

def _is_ddl(stmt):
    """Check if a CQL statement is a schema change (DDL)."""
    first_word = stmt.strip().split()[0].upper() if stmt.strip() else ""
    return first_word in _DDL_KEYWORDS


def _replication_cql(repl):
    """Format a Python dict as a CQL map literal for CREATE KEYSPACE."""
    pairs = ", ".join(f"'{k}': '{v}'" for k, v in repl.items())
    return "{" + pairs + "}"


def _caller_id():
    return f"{os.getenv('USER', 'unknown')}@{socket.gethostname()}"
