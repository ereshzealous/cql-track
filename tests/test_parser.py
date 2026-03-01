import pytest

from cqltrack.parser import (
    compute_checksum,
    parse_filename,
    parse_migration,
    scan_directory,
    split_statements,
)
from cqltrack.exceptions import ParseError


class TestParseFilename:

    def test_basic(self):
        ver, desc = parse_filename("V001__create_users.cql")
        assert ver == 1
        assert desc == "create users"

    def test_multidigit(self):
        ver, desc = parse_filename("V042__add_email_index.cql")
        assert ver == 42
        assert desc == "add email index"

    def test_invalid_name(self):
        with pytest.raises(ParseError):
            parse_filename("not_valid.cql")

    def test_missing_prefix(self):
        with pytest.raises(ParseError):
            parse_filename("001__something.cql")


class TestSplitStatements:

    def test_single_statement(self):
        stmts = split_statements("CREATE TABLE foo (id int PRIMARY KEY);")
        assert len(stmts) == 1
        assert "CREATE TABLE" in stmts[0]

    def test_multiple_statements(self):
        cql = (
            "CREATE TABLE a (id int PRIMARY KEY);\n"
            "CREATE TABLE b (id int PRIMARY KEY);\n"
        )
        stmts = split_statements(cql)
        assert len(stmts) == 2

    def test_comments_stripped(self):
        cql = (
            "-- a comment\n"
            "CREATE TABLE foo (id int PRIMARY KEY);\n"
        )
        stmts = split_statements(cql)
        assert len(stmts) == 1
        assert "--" not in stmts[0]

    def test_inline_comment(self):
        cql = "CREATE TABLE foo (id int PRIMARY KEY); -- inline\n"
        stmts = split_statements(cql)
        assert len(stmts) == 1

    def test_semicolon_in_string(self):
        cql = "INSERT INTO t (v) VALUES ('hello; world');"
        stmts = split_statements(cql)
        assert len(stmts) == 1
        assert "hello; world" in stmts[0]

    def test_escaped_quote(self):
        cql = "INSERT INTO t (v) VALUES ('it''s a test');"
        stmts = split_statements(cql)
        assert len(stmts) == 1
        assert "''" in stmts[0]

    def test_no_trailing_semicolon(self):
        cql = "CREATE TABLE foo (id int PRIMARY KEY)"
        stmts = split_statements(cql)
        assert len(stmts) == 1

    def test_empty_input(self):
        assert split_statements("") == []

    def test_only_comments(self):
        assert split_statements("-- just a comment\n-- another") == []


class TestChecksum:

    def test_deterministic(self):
        assert compute_checksum("hello") == compute_checksum("hello")

    def test_different_content(self):
        assert compute_checksum("aaa") != compute_checksum("bbb")

    def test_whitespace_trimmed(self):
        assert compute_checksum("  hello  ") == compute_checksum("hello")


class TestParseMigration:

    def test_up_and_down(self, tmp_path):
        p = tmp_path / "V001__create_foo.cql"
        p.write_text(
            "CREATE TABLE foo (id int PRIMARY KEY);\n"
            "\n"
            "-- @down\n"
            "DROP TABLE foo;\n"
        )
        m = parse_migration(p)
        assert m.version == 1
        assert m.description == "create foo"
        assert len(m.up_statements) == 1
        assert len(m.down_statements) == 1
        assert "CREATE TABLE" in m.up_statements[0]
        assert "DROP TABLE" in m.down_statements[0]

    def test_no_down(self, tmp_path):
        p = tmp_path / "V005__add_index.cql"
        p.write_text("CREATE INDEX ON foo (bar);\n")
        m = parse_migration(p)
        assert m.down_statements == []

    def test_checksum_stable(self, tmp_path):
        content = "SELECT 1;\n"
        p = tmp_path / "V010__check.cql"
        p.write_text(content)
        a = parse_migration(p).checksum
        b = parse_migration(p).checksum
        assert a == b


class TestScanDirectory:

    def test_sorted_by_version(self, tmp_path):
        (tmp_path / "V003__c.cql").write_text("SELECT 3;")
        (tmp_path / "V001__a.cql").write_text("SELECT 1;")
        (tmp_path / "V002__b.cql").write_text("SELECT 2;")

        migs = scan_directory(tmp_path)
        assert [m.version for m in migs] == [1, 2, 3]

    def test_empty_directory(self, tmp_path):
        assert scan_directory(tmp_path) == []

    def test_duplicate_version(self, tmp_path):
        (tmp_path / "V001__first.cql").write_text("SELECT 1;")
        (tmp_path / "V001__dupe.cql").write_text("SELECT 1;")

        with pytest.raises(ParseError, match="Duplicate"):
            scan_directory(tmp_path)

    def test_skips_non_matching_files(self, tmp_path):
        (tmp_path / "V001__good.cql").write_text("SELECT 1;")
        (tmp_path / "notes.txt").write_text("not a migration")
        (tmp_path / "readme.md").write_text("ignore me")

        migs = scan_directory(tmp_path)
        assert len(migs) == 1
