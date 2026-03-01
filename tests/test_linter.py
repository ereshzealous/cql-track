from cqltrack.linter import lint_directory


class TestLintRules:

    def _write_migration(self, tmp_path, version, content):
        name = f"V{version:03d}__test.cql"
        (tmp_path / name).write_text(content)

    def test_clean_migration_passes(self, tmp_path):
        self._write_migration(tmp_path, 1, (
            "CREATE TABLE IF NOT EXISTS foo (id int PRIMARY KEY);\n"
            "\n"
            "-- @down\n"
            "DROP TABLE IF EXISTS foo;\n"
        ))
        assert lint_directory(tmp_path) == []

    def test_missing_down_section(self, tmp_path):
        self._write_migration(tmp_path, 1,
            "CREATE TABLE IF NOT EXISTS foo (id int PRIMARY KEY);\n"
        )
        warnings = lint_directory(tmp_path)
        rules = [w.rule for w in warnings]
        assert "no-rollback" in rules

    def test_empty_down_section(self, tmp_path):
        self._write_migration(tmp_path, 1, (
            "CREATE TABLE IF NOT EXISTS foo (id int PRIMARY KEY);\n"
            "\n"
            "-- @down\n"
            "-- nothing here\n"
        ))
        warnings = lint_directory(tmp_path)
        rules = [w.rule for w in warnings]
        assert "empty-rollback" in rules

    def test_drop_without_if_exists(self, tmp_path):
        self._write_migration(tmp_path, 1, (
            "DROP TABLE foo;\n"
            "\n"
            "-- @down\n"
            "SELECT 1;\n"
        ))
        warnings = lint_directory(tmp_path)
        rules = [w.rule for w in warnings]
        assert "drop-no-if-exists" in rules

    def test_drop_with_if_exists_passes(self, tmp_path):
        self._write_migration(tmp_path, 1, (
            "DROP TABLE IF EXISTS foo;\n"
            "\n"
            "-- @down\n"
            "SELECT 1;\n"
        ))
        warnings = lint_directory(tmp_path)
        drop_warnings = [w for w in warnings if w.rule == "drop-no-if-exists"]
        assert drop_warnings == []

    def test_create_without_if_not_exists(self, tmp_path):
        self._write_migration(tmp_path, 1, (
            "CREATE TABLE foo (id int PRIMARY KEY);\n"
            "\n"
            "-- @down\n"
            "DROP TABLE IF EXISTS foo;\n"
        ))
        warnings = lint_directory(tmp_path)
        rules = [w.rule for w in warnings]
        assert "create-no-if-not-exists" in rules

    def test_column_drop_warning(self, tmp_path):
        self._write_migration(tmp_path, 1, (
            "ALTER TABLE users DROP email;\n"
            "\n"
            "-- @down\n"
            "ALTER TABLE users ADD email text;\n"
        ))
        warnings = lint_directory(tmp_path)
        rules = [w.rule for w in warnings]
        assert "column-drop" in rules

    def test_column_drop_in_down_section_not_flagged(self, tmp_path):
        self._write_migration(tmp_path, 1, (
            "ALTER TABLE users ADD phone text;\n"
            "\n"
            "-- @down\n"
            "ALTER TABLE users DROP phone;\n"
        ))
        warnings = lint_directory(tmp_path)
        col_drops = [w for w in warnings if w.rule == "column-drop"]
        assert col_drops == []

    def test_truncate_warning(self, tmp_path):
        self._write_migration(tmp_path, 1, (
            "TRUNCATE TABLE users;\n"
            "\n"
            "-- @down\n"
            "SELECT 1;\n"
        ))
        warnings = lint_directory(tmp_path)
        rules = [w.rule for w in warnings]
        assert "truncate" in rules

    def test_multiple_issues(self, tmp_path):
        self._write_migration(tmp_path, 1, (
            "CREATE TABLE foo (id int PRIMARY KEY);\n"
            "DROP TABLE bar;\n"
        ))
        warnings = lint_directory(tmp_path)
        assert len(warnings) >= 3  # create-no-if, drop-no-if, no-rollback
