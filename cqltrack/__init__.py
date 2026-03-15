__version__ = "1.0.2"

import logging
from pathlib import Path

from cqltrack.config import Config
from cqltrack.exceptions import CqlTrackError, MigrationError, ChecksumMismatch
from cqltrack.session import connect
from cqltrack.migrator import Migrator
from cqltrack.parser import scan_directory, Migration
from cqltrack.linter import lint_directory, LintWarning
from cqltrack.differ import SchemaDiffer, Difference

_log = logging.getLogger("cqltrack")


class CqlTrack:
    """Programmatic API for cqltrack.

    Use this to run migrations at application startup in FastAPI, Django,
    or any Python application.

    Example::

        from cqltrack import CqlTrack

        tracker = CqlTrack("cqltrack.yml", profile="prod")
        tracker.init()
        tracker.migrate()

    Or configure inline without a YAML file::

        tracker = CqlTrack(
            contact_points=["10.0.1.1", "10.0.1.2"],
            keyspace="my_app",
            migration_dir="db/migrations",
        )
        tracker.migrate()
    """

    def __init__(self, config_path=None, *, profile=None, **overrides):
        """Create a CqlTrack instance.

        Args:
            config_path: Path to cqltrack.yml. If None and no overrides
                are given, looks for cqltrack.yml in the current directory.
            profile: Environment profile name (dev, staging, prod).
            **overrides: Inline config. Supported keys: contact_points,
                port, keyspace, username, password, consistency,
                replication, migration_dir, lock_ttl,
                schema_agreement_wait, connect_timeout, request_timeout,
                ssl_enabled, ssl_ca_certs, ssl_certfile, ssl_keyfile,
                ssl_verify, secure_connect_bundle.
        """
        if overrides and config_path is None:
            # pure inline config — no YAML file needed
            self._config = Config(**overrides)
        else:
            self._config = Config.load(config_path, profile=profile)
            # apply any inline overrides on top
            for key, value in overrides.items():
                if hasattr(self._config, key):
                    setattr(self._config, key, value)

        self._session = None
        self._migrator = None

    # -- connection ----------------------------------------------------------

    def _connect(self, use_keyspace=True):
        if self._session is None:
            self._session = connect(self._config, use_keyspace=use_keyspace)
        return self._session

    def _get_migrator(self):
        if self._migrator is None:
            session = self._connect()
            self._migrator = Migrator(session, self._config, log=_log)
        return self._migrator

    # -- commands ------------------------------------------------------------

    def init(self):
        """Create the keyspace and tracking tables.

        Safe to call multiple times (all DDL uses IF NOT EXISTS).
        """
        session = self._connect(use_keyspace=False)
        migrator = Migrator(session, self._config, log=_log)
        migrator.init_tracking()
        self._config.migration_dir.mkdir(parents=True, exist_ok=True)
        self._migrator = migrator
        _log.info("Initialized cqltrack in keyspace '%s'", self._config.keyspace)

    def migrate(self, target=None, dry_run=False):
        """Apply pending migrations.

        Args:
            target: Stop at this version number (inclusive).
            dry_run: If True, return pending migrations without applying.

        Returns:
            List of Migration objects that were applied (or would be applied
            in dry_run mode).

        Raises:
            MigrationError: If a migration fails.
            ChecksumMismatch: If an applied migration file was modified
                (call validate() first to check).
        """
        migrator = self._get_migrator()

        # refuse to run if checksums are off
        mismatches = migrator.validate()
        if mismatches:
            files = [f"V{m.version:03d}" for m, _ in mismatches]
            raise ChecksumMismatch(
                f"Checksum mismatch for: {', '.join(files)}. "
                f"Run validate() to inspect or repair() to accept changes."
            )

        return migrator.migrate(target=target, dry_run=dry_run)

    def rollback(self, steps=1):
        """Undo the N most recently applied migrations.

        Args:
            steps: Number of migrations to roll back.

        Returns:
            List of Migration objects that were rolled back.

        Raises:
            MigrationError: If rollback fails or @down section is missing.
        """
        return self._get_migrator().rollback(steps=steps)

    def baseline(self, version):
        """Mark migrations up to version as applied without executing.

        Use when adopting cqltrack on an existing database.

        Args:
            version: Mark V001 through this version as applied.

        Returns:
            Number of migrations baselined.
        """
        return self._get_migrator().baseline(version)

    def status(self):
        """Get migration status.

        Returns:
            List of dicts with keys: version, description, status
            ('applied' or 'pending'), applied_at, applied_by.
        """
        migrator = self._get_migrator()
        applied = migrator.get_applied()
        all_migs = scan_directory(self._config.migration_dir)

        result = []
        for m in all_migs:
            entry = {
                "version": m.version,
                "description": m.description,
                "status": "applied" if m.version in applied else "pending",
                "applied_at": None,
                "applied_by": None,
            }
            if m.version in applied:
                row = applied[m.version]
                entry["applied_at"] = row.applied_at
                entry["applied_by"] = getattr(row, "applied_by", None)
            result.append(entry)

        return result

    def history(self):
        """Get full migration history including failed attempts.

        Returns:
            List of dicts with keys: version, description, status,
            checksum, applied_at, applied_by, exec_time_ms.
        """
        records = self._get_migrator().get_all_records()
        return [
            {
                "version": r.version,
                "description": getattr(r, "description", ""),
                "status": getattr(r, "status", "applied"),
                "checksum": getattr(r, "checksum", ""),
                "applied_at": r.applied_at,
                "applied_by": getattr(r, "applied_by", ""),
                "exec_time_ms": getattr(r, "exec_time_ms", 0),
            }
            for r in records
        ]

    def pending(self):
        """Get list of pending migrations.

        Returns:
            List of Migration objects that haven't been applied.
        """
        return self._get_migrator().get_pending()

    def validate(self):
        """Check applied migration files for modifications.

        Returns:
            List of (Migration, recorded_checksum) tuples for mismatches.
            Empty list if all checksums match.
        """
        return self._get_migrator().validate()

    def repair(self):
        """Update recorded checksums to match files on disk.

        Returns:
            Number of checksums updated.
        """
        return self._get_migrator().repair()

    def lint(self):
        """Run static analysis on migration files.

        Does not require a Cassandra connection.

        Returns:
            List of LintWarning objects.
        """
        return lint_directory(self._config.migration_dir)

    def snapshot(self):
        """Export the live keyspace schema as CQL.

        Returns:
            CQL string of the full keyspace schema.
        """
        session = self._connect()
        cluster = session.cluster
        cluster.refresh_schema_metadata()
        ks_meta = cluster.metadata.keyspaces.get(self._config.keyspace)
        if ks_meta is None:
            raise CqlTrackError(f"Keyspace '{self._config.keyspace}' not found.")
        return ks_meta.export_as_string()

    def diff(self, target_keyspace=None, target_profile=None,
             source_keyspace=None, config_path=None):
        """Compare schemas between two keyspaces or environments.

        Args:
            target_keyspace: Compare against this keyspace (same cluster).
            target_profile: Compare against a different profile/cluster.
            source_keyspace: Override source keyspace name.
            config_path: Path to config file for target profile.

        Returns:
            List of Difference objects.
        """
        src_session = self._connect()
        src_ks_name = source_keyspace or self._config.keyspace

        cluster = src_session.cluster
        cluster.refresh_schema_metadata()

        src_ks = cluster.metadata.keyspaces.get(src_ks_name)
        if src_ks is None:
            raise CqlTrackError(f"Source keyspace '{src_ks_name}' not found.")

        if target_profile:
            tgt_cfg = Config.load(config_path, profile=target_profile)
            tgt_session = connect(tgt_cfg)
            tgt_cluster = tgt_session.cluster
            tgt_cluster.refresh_schema_metadata()
            tgt_ks_name = tgt_cfg.keyspace
            tgt_ks = tgt_cluster.metadata.keyspaces.get(tgt_ks_name)
        elif target_keyspace:
            tgt_ks_name = target_keyspace
            tgt_ks = cluster.metadata.keyspaces.get(tgt_ks_name)
        else:
            raise CqlTrackError(
                "Need at least target_keyspace or target_profile"
            )

        if tgt_ks is None:
            raise CqlTrackError(f"Target keyspace '{tgt_ks_name}' not found.")

        differ = SchemaDiffer(
            src_ks, tgt_ks,
            src_ks_name, tgt_ks_name,
        )
        return differ.diff()

    def close(self):
        """Close the Cassandra connection."""
        if self._session is not None:
            self._session.cluster.shutdown()
            self._session = None
            self._migrator = None

    # -- context manager -----------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
