import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from cqltrack.exceptions import ParseError


# V001__create_users_table.cql
_FILENAME_PAT = re.compile(r"^V(\d+)__(.+)\.cql$")

# Marker that splits a file into up / down sections
_DOWN_MARKER = re.compile(r"^\s*--\s*@down\s*$", re.IGNORECASE | re.MULTILINE)


@dataclass
class Migration:
    version: int
    description: str
    path: Path
    checksum: str
    up_statements: list = field(default_factory=list)
    down_statements: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def parse_filename(name):
    """Pull version number and human-readable description from a filename.

    >>> parse_filename("V001__create_users.cql")
    (1, 'create users')
    """
    m = _FILENAME_PAT.match(name)
    if not m:
        raise ParseError(
            f"Bad migration filename: {name}  "
            f"(expected V<number>__<description>.cql)"
        )
    version = int(m.group(1))
    desc = m.group(2).replace("_", " ")
    return version, desc


def split_statements(cql_text):
    """Break a block of CQL into individual statements.

    Handles semicolons inside single-quoted strings and strips ``--``
    line comments so they don't end up in the executed statements.
    """
    stmts = []
    buf = []
    in_string = False
    i = 0
    n = len(cql_text)

    while i < n:
        ch = cql_text[i]

        if in_string:
            buf.append(ch)
            if ch == "'":
                # escaped single-quote ('')
                if i + 1 < n and cql_text[i + 1] == "'":
                    buf.append("'")
                    i += 2
                    continue
                in_string = False
        elif ch == "'":
            in_string = True
            buf.append(ch)
        elif ch == "-" and i + 1 < n and cql_text[i + 1] == "-":
            # consume comment until end of line
            while i < n and cql_text[i] != "\n":
                i += 1
            continue
        elif ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                stmts.append(stmt)
            buf = []
        else:
            buf.append(ch)

        i += 1

    # trailing statement without a semicolon
    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)

    return stmts


def compute_checksum(content):
    """MD5 of the file content — used for drift detection, not security."""
    return hashlib.md5(content.strip().encode("utf-8")).hexdigest()


def parse_migration(path):
    """Read a ``.cql`` file and return a Migration object."""
    path = Path(path)
    version, description = parse_filename(path.name)
    content = path.read_text(encoding="utf-8")
    cs = compute_checksum(content)

    parts = _DOWN_MARKER.split(content, maxsplit=1)
    up_cql = parts[0]
    down_cql = parts[1] if len(parts) > 1 else ""

    return Migration(
        version=version,
        description=description,
        path=path,
        checksum=cs,
        up_statements=split_statements(up_cql),
        down_statements=split_statements(down_cql),
    )


def scan_directory(directory):
    """Find all ``V*.cql`` files in *directory*, sorted by version.

    Raises ParseError on duplicate version numbers.
    """
    directory = Path(directory)
    if not directory.is_dir():
        return []

    migrations = []
    for p in sorted(directory.glob("V*.cql")):
        try:
            migrations.append(parse_migration(p))
        except ParseError:
            continue

    migrations.sort(key=lambda m: m.version)

    # catch duplicates early
    seen = {}
    for m in migrations:
        if m.version in seen:
            raise ParseError(
                f"Duplicate version {m.version}: "
                f"{seen[m.version]} and {m.path.name}"
            )
        seen[m.version] = m.path.name

    return migrations
