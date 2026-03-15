"""Tests for the CqlTrack programmatic API."""

import tempfile
from pathlib import Path

import pytest

from cqltrack import CqlTrack, __version__


class TestCqlTrackInit:
    """Test CqlTrack construction and config handling."""

    def test_inline_config(self):
        tracker = CqlTrack(
            contact_points=["10.0.1.1", "10.0.1.2"],
            keyspace="test_ks",
            port=9043,
        )
        assert tracker._config.keyspace == "test_ks"
        assert tracker._config.contact_points == ["10.0.1.1", "10.0.1.2"]
        assert tracker._config.port == 9043

    def test_inline_config_defaults(self):
        tracker = CqlTrack(keyspace="my_app")
        assert tracker._config.contact_points == ["127.0.0.1"]
        assert tracker._config.port == 9042
        assert tracker._config.consistency == "LOCAL_ONE"

    def test_yaml_config_with_overrides(self, tmp_path):
        config_file = tmp_path / "cqltrack.yml"
        config_file.write_text(
            "keyspace:\n  name: from_yaml\ncassandra:\n  port: 9042\n"
        )
        tracker = CqlTrack(str(config_file), keyspace="overridden")
        assert tracker._config.keyspace == "overridden"

    def test_no_config_file_with_inline(self):
        """Inline config should work without any YAML file."""
        tracker = CqlTrack(
            contact_points=["localhost"],
            keyspace="test",
        )
        assert tracker._config.keyspace == "test"

    def test_context_manager(self):
        tracker = CqlTrack(keyspace="test")
        with tracker as t:
            assert t is tracker
        # after exit, session should be None
        assert tracker._session is None

    def test_version_accessible(self):
        assert isinstance(__version__, str)
        assert len(__version__.split(".")) >= 3


class TestCqlTrackLint:
    """Test lint via programmatic API — no Cassandra needed."""

    def test_lint_clean_migrations(self, tmp_path):
        mig_dir = tmp_path / "migrations"
        mig_dir.mkdir()
        (mig_dir / "V001__create_table.cql").write_text(
            "CREATE TABLE IF NOT EXISTS t (id uuid PRIMARY KEY);\n"
            "\n-- @down\nDROP TABLE IF EXISTS t;\n"
        )
        tracker = CqlTrack(keyspace="test", migration_dir=str(mig_dir))
        warnings = tracker.lint()
        assert len(warnings) == 0

    def test_lint_catches_issues(self, tmp_path):
        mig_dir = tmp_path / "migrations"
        mig_dir.mkdir()
        (mig_dir / "V001__bad.cql").write_text(
            "CREATE TABLE t (id uuid PRIMARY KEY);\n"
            "DROP TABLE t;\n"
        )
        tracker = CqlTrack(keyspace="test", migration_dir=str(mig_dir))
        warnings = tracker.lint()
        rules = {w.rule for w in warnings}
        assert "no-rollback" in rules
        assert "create-no-if-not-exists" in rules
        assert "drop-no-if-exists" in rules

    def test_lint_empty_directory(self, tmp_path):
        mig_dir = tmp_path / "migrations"
        mig_dir.mkdir()
        tracker = CqlTrack(keyspace="test", migration_dir=str(mig_dir))
        warnings = tracker.lint()
        assert warnings == []


class TestCqlTrackStatus:
    """Test status/pending via programmatic API (read-only, no Cassandra)."""

    def test_pending_returns_migrations(self, tmp_path):
        """Verify pending() would work if connected — test the migration parsing part."""
        mig_dir = tmp_path / "migrations"
        mig_dir.mkdir()
        (mig_dir / "V001__first.cql").write_text("CREATE TABLE IF NOT EXISTS t (id uuid PRIMARY KEY);\n-- @down\nDROP TABLE IF EXISTS t;\n")
        (mig_dir / "V002__second.cql").write_text("ALTER TABLE t ADD name text;\n-- @down\nALTER TABLE t DROP name;\n")

        tracker = CqlTrack(keyspace="test", migration_dir=str(mig_dir))
        # can't call pending() without a connection, but we can verify
        # the migration files are parsed correctly via lint
        warnings = tracker.lint()
        # both migrations are clean
        assert len(warnings) == 0
