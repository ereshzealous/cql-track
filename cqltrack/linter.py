import re
from dataclasses import dataclass

from cqltrack.parser import scan_directory


@dataclass
class LintWarning:
    version: int
    filename: str
    line: int
    severity: str  # "warn" or "error"
    rule: str
    message: str


def lint_directory(migration_dir):
    """Run all lint rules against migration files. Returns list of warnings."""
    migrations = scan_directory(migration_dir)
    warnings = []

    for m in migrations:
        content = m.path.read_text(encoding="utf-8")
        lines = content.splitlines()

        warnings.extend(_check_missing_down(m, content))
        warnings.extend(_check_drop_without_if_exists(m, lines))
        warnings.extend(_check_create_without_if_not_exists(m, lines))
        warnings.extend(_check_column_drop(m, lines))
        warnings.extend(_check_truncate(m, lines))
        warnings.extend(_check_partition_key_change(m, lines))
        warnings.extend(_check_type_change(m, lines))

    return warnings


# ---------------------------------------------------------------------------
# Individual rules
# ---------------------------------------------------------------------------

def _check_missing_down(m, content):
    """Migration has no @down section — rollback impossible."""
    if "-- @down" not in content.lower():
        return [LintWarning(
            version=m.version, filename=m.path.name, line=0,
            severity="warn", rule="no-rollback",
            message="No @down section — rollback will not be possible",
        )]
    # has @down marker but nothing after it
    parts = re.split(r"--\s*@down", content, flags=re.IGNORECASE)
    if len(parts) > 1:
        down_body = parts[1].strip()
        # strip comments from down body
        stripped = "\n".join(
            l for l in down_body.splitlines()
            if l.strip() and not l.strip().startswith("--")
        )
        if not stripped:
            return [LintWarning(
                version=m.version, filename=m.path.name, line=0,
                severity="warn", rule="empty-rollback",
                message="@down section exists but has no statements",
            )]
    return []


def _check_drop_without_if_exists(m, lines):
    """DROP TABLE/INDEX/KEYSPACE without IF EXISTS is not idempotent."""
    out = []
    pat = re.compile(r"^\s*DROP\s+(TABLE|INDEX|KEYSPACE|MATERIALIZED\s+VIEW|TYPE)\s+", re.IGNORECASE)
    safe = re.compile(r"IF\s+EXISTS", re.IGNORECASE)
    for i, line in enumerate(lines, 1):
        if line.strip().startswith("--"):
            continue
        if pat.match(line) and not safe.search(line):
            out.append(LintWarning(
                version=m.version, filename=m.path.name, line=i,
                severity="error", rule="drop-no-if-exists",
                message="DROP without IF EXISTS — not idempotent, will fail on re-run",
            ))
    return out


def _check_create_without_if_not_exists(m, lines):
    """CREATE TABLE/INDEX without IF NOT EXISTS breaks on re-run."""
    out = []
    pat = re.compile(r"^\s*CREATE\s+(TABLE|INDEX|KEYSPACE|MATERIALIZED\s+VIEW|TYPE)\s+", re.IGNORECASE)
    safe = re.compile(r"IF\s+NOT\s+EXISTS", re.IGNORECASE)
    for i, line in enumerate(lines, 1):
        if line.strip().startswith("--"):
            continue
        if pat.match(line) and not safe.search(line):
            out.append(LintWarning(
                version=m.version, filename=m.path.name, line=i,
                severity="warn", rule="create-no-if-not-exists",
                message="CREATE without IF NOT EXISTS — not idempotent",
            ))
    return out


def _check_column_drop(m, lines):
    """ALTER TABLE ... DROP column destroys data permanently."""
    out = []
    pat = re.compile(r"^\s*ALTER\s+TABLE\s+\S+\s+DROP\s+", re.IGNORECASE)
    for i, line in enumerate(lines, 1):
        # stop at the @down boundary — drops in rollback are expected
        if re.match(r"^\s*--\s*@down", line, re.IGNORECASE):
            break
        if line.strip().startswith("--"):
            continue
        if pat.match(line):
            out.append(LintWarning(
                version=m.version, filename=m.path.name, line=i,
                severity="error", rule="column-drop",
                message="ALTER TABLE DROP — this permanently deletes column data",
            ))
    return out


def _check_truncate(m, lines):
    """TRUNCATE wipes all data from a table."""
    out = []
    pat = re.compile(r"^\s*TRUNCATE\s+", re.IGNORECASE)
    for i, line in enumerate(lines, 1):
        if line.strip().startswith("--"):
            continue
        if pat.match(line):
            out.append(LintWarning(
                version=m.version, filename=m.path.name, line=i,
                severity="error", rule="truncate",
                message="TRUNCATE deletes all data in the table",
            ))
    return out


def _check_partition_key_change(m, lines):
    """Catch attempts to alter primary/partition key (not supported in C*)."""
    out = []
    # you can't actually alter a PK in Cassandra, but people try
    # and the error is confusing — better to catch early
    content = "\n".join(lines)
    if re.search(r"ALTER\s+TABLE\s+\S+\s+.*PRIMARY\s+KEY", content, re.IGNORECASE):
        out.append(LintWarning(
            version=m.version, filename=m.path.name, line=0,
            severity="error", rule="pk-alter",
            message="Cannot alter PRIMARY KEY in Cassandra — you need to recreate the table",
        ))
    return out


def _check_type_change(m, lines):
    """ALTER TABLE ... ALTER column TYPE — very limited in Cassandra."""
    out = []
    pat = re.compile(r"^\s*ALTER\s+TABLE\s+\S+\s+ALTER\s+\S+\s+TYPE\s+", re.IGNORECASE)
    for i, line in enumerate(lines, 1):
        if line.strip().startswith("--"):
            continue
        if pat.match(line):
            out.append(LintWarning(
                version=m.version, filename=m.path.name, line=i,
                severity="warn", rule="type-change",
                message="Column type changes are only allowed between compatible types (e.g. int -> bigint)",
            ))
    return out
