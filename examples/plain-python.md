# Plain Python Usage

Use the `CqlTrack` class to run migrations programmatically from any Python application.

## Install

```bash
pip install cql-track
```

## Basic Usage

### With YAML Config

```python
from cqltrack import CqlTrack

tracker = CqlTrack("cqltrack.yml")
tracker.init()
tracker.migrate()
tracker.close()
```

### With Inline Config (No YAML)

```python
from cqltrack import CqlTrack

tracker = CqlTrack(
    contact_points=["127.0.0.1"],
    keyspace="my_app",
    replication={"class": "SimpleStrategy", "replication_factor": 1},
    migration_dir="migrations",
)
tracker.init()
tracker.migrate()
tracker.close()
```

### With Context Manager

```python
from cqltrack import CqlTrack

with CqlTrack(keyspace="my_app", migration_dir="migrations") as tracker:
    tracker.init()
    tracker.migrate()
```

Connection is automatically closed when the `with` block exits.

## Configuration Options

All config fields can be passed as keyword arguments:

```python
tracker = CqlTrack(
    contact_points=["10.0.1.1", "10.0.1.2"],
    port=9042,
    keyspace="my_app",
    username="cassandra",
    password="secret",
    consistency="LOCAL_QUORUM",
    replication={
        "class": "NetworkTopologyStrategy",
        "dc1": 3,
        "dc2": 2,
    },
    migration_dir="db/migrations",
    lock_ttl=600,
    schema_agreement_wait=30,
    connect_timeout=10,
    request_timeout=30,
    ssl_enabled=True,
    ssl_ca_certs="/path/to/ca.crt",
    ssl_verify=True,
)
```

### YAML Config with Overrides

Load a YAML file but override specific fields:

```python
tracker = CqlTrack("cqltrack.yml", keyspace="other_keyspace")
```

### Profiles

```python
tracker = CqlTrack("cqltrack.yml", profile="prod")
```

## API Reference

### Migrations

```python
# apply all pending migrations
applied = tracker.migrate()

# apply up to a specific version
applied = tracker.migrate(target=5)

# preview without applying
pending = tracker.migrate(dry_run=True)

# rollback the last N migrations
rolled_back = tracker.rollback(steps=2)

# mark V001-V005 as applied without executing (existing database adoption)
count = tracker.baseline(5)
```

### Status and History

```python
# list of dicts: version, description, status, applied_at, applied_by
status = tracker.status()
for s in status:
    print(f"V{s['version']:03d}  {s['status']}  {s['description']}")

# full history including timing and failed attempts
history = tracker.history()
for h in history:
    print(f"V{h['version']:03d}  {h['status']}  {h['exec_time_ms']}ms")

# list of pending Migration objects
pending = tracker.pending()
print(f"{len(pending)} migration(s) pending")
```

### Validation

```python
# check for modified migration files
mismatches = tracker.validate()
if mismatches:
    for migration, recorded_checksum in mismatches:
        print(f"V{migration.version:03d}: expected {recorded_checksum}, got {migration.checksum}")

# accept file changes by updating stored checksums
fixed = tracker.repair()
print(f"Repaired {fixed} checksum(s)")
```

### Linting

Lint does not require a Cassandra connection:

```python
warnings = tracker.lint()
for w in warnings:
    print(f"{w.severity}: [{w.rule}] {w.message}")
```

### Schema Operations

```python
# export live schema as CQL string
cql = tracker.snapshot()

# compare two keyspaces on the same cluster
diffs = tracker.diff(target_keyspace="my_app_v2")
for d in diffs:
    print(f"{d.kind}  {d.path}  {d.change}")

# compare against a different environment
diffs = tracker.diff(target_profile="staging", config_path="cqltrack.yml")
```

## Error Handling

```python
from cqltrack import CqlTrack, MigrationError, ChecksumMismatch, CqlTrackError

tracker = CqlTrack(keyspace="my_app", migration_dir="migrations")

try:
    tracker.init()
    tracker.migrate()
except ChecksumMismatch as e:
    # an applied migration file was modified
    print(f"Checksum error: {e}")
    print("Run tracker.repair() to accept changes")
except MigrationError as e:
    # a migration failed partway through
    # the failed migration is recorded in history
    # fix the .cql file and call migrate() again
    print(f"Migration failed: {e}")
except CqlTrackError as e:
    # base exception for all cqltrack errors
    print(f"Error: {e}")
finally:
    tracker.close()
```

## Logging

cqltrack uses Python's `logging` module under the logger name `cqltrack`:

```python
import logging
logging.basicConfig(level=logging.INFO)

# now tracker.migrate() will log progress to the console
tracker.migrate()
```

Output:

```
cqltrack: Initialized cqltrack in keyspace 'my_app'
Applying V001  create users table ... OK (275ms)
Applying V002  create orders table ... OK (132ms)
```

To suppress output, set the log level higher:

```python
logging.getLogger("cqltrack").setLevel(logging.WARNING)
```

## Startup Script Example

A common pattern for microservices:

```python
#!/usr/bin/env python3
"""Run migrations before starting the application."""

import logging
import sys

from cqltrack import CqlTrack, MigrationError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

def run_migrations():
    with CqlTrack("cqltrack.yml", profile="prod") as tracker:
        tracker.init()

        pending = tracker.pending()
        if not pending:
            logging.info("No pending migrations")
            return

        logging.info("%d pending migration(s)", len(pending))
        try:
            tracker.migrate()
        except MigrationError as e:
            logging.error("Migration failed: %s", e)
            sys.exit(1)

if __name__ == "__main__":
    run_migrations()
```
