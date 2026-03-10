# CQLTrack - A Cassandra Based Schema Versioning Tool

Schema migration tool for Apache Cassandra.

Version-controlled `.cql` files, distributed locking, checksum validation, multi-environment profiles, static analysis, and schema diffing — built on the DataStax Python driver.

## Why cqltrack?

Most migration tools target relational databases. Cassandra is different — DDL is asynchronous, there are no transactions, and clusters span multiple datacenters. cqltrack is purpose-built for these realities:

- **Schema agreement handling** — waits for all nodes to converge between DDL statements
- **Distributed locking** — Lightweight Transactions (LWT) prevent concurrent migration runs across CI workers or deploy nodes
- **Partial failure tracking** — if statement 3 of 5 fails, cqltrack records the failure and lets you fix and retry cleanly
- **Cassandra-native** — supports `NetworkTopologyStrategy`, all consistency levels, LWT serial consistency for locks, and Astra DB

## Features

| | |
|---|---|
| **Migrate & Rollback** | Versioned `.cql` files with `-- @down` rollback sections |
| **Distributed Lock** | LWT-based lock with configurable TTL and auto-expiry |
| **Checksum Validation** | MD5 checksums detect modified migration files |
| **Multi-Environment** | YAML profiles for dev/staging/prod in one config file |
| **Static Analysis** | Linter catches dangerous patterns before they hit your cluster |
| **Schema Diff** | Compare schemas across keyspaces or environments |
| **Schema Snapshot** | Export live schema as CQL |
| **Partial Failure** | Failed migrations are tracked and retryable |
| **Baseline** | Adopt cqltrack on existing databases without re-running history |
| **CI/CD Ready** | `pending` command as a deploy gate, JSON output, exit codes |
| **SSL/TLS** | Full TLS support including mutual TLS with client certificates |
| **Astra DB** | Secure connect bundle support for DataStax Astra |

## Quick Start

```bash
# install
pip install cql-track

# start local Cassandra (optional)
docker compose up -d

# create config
cat > cqltrack.yml <<EOF
cassandra:
  contact_points: [127.0.0.1]
  port: 9042
keyspace:
  name: my_app
  replication:
    class: SimpleStrategy
    replication_factor: 1
migrations:
  directory: migrations
EOF

# initialize keyspace and tracking tables
cqltrack init

# create a migration
cqltrack new create_users_table
```

Edit `migrations/V001__create_users_table.cql`:

```sql
CREATE TABLE IF NOT EXISTS users (
    user_id    UUID,
    email      text,
    name       text,
    created_at timestamp,
    PRIMARY KEY (user_id)
);

-- @down
DROP TABLE IF EXISTS users;
```

```bash
# apply
cqltrack migrate

# check status
cqltrack status
```

## Commands

```
cqltrack init        Create the keyspace and tracking tables
cqltrack migrate     Apply pending migrations
cqltrack rollback    Undo the most recently applied migration(s)
cqltrack status      Show applied and pending migrations
cqltrack history     Full migration history with timing and who applied
cqltrack pending     Exit code 1 if unapplied migrations exist (CI gate)
cqltrack baseline    Mark migrations as applied without executing (adoption)
cqltrack validate    Check that applied files haven't been modified
cqltrack repair      Update recorded checksums to match files on disk
cqltrack new         Scaffold a new migration file
cqltrack lint        Static analysis for dangerous CQL patterns
cqltrack snapshot    Export the live keyspace schema as CQL
cqltrack diff        Compare schemas between environments or keyspaces
cqltrack profiles    List available environment profiles
```

Global options:

```
-c, --config     Path to cqltrack.yml
--profile        Environment profile (dev, staging, prod)
-k, --keyspace   Override target keyspace
--host           Cassandra contact point(s), comma-separated
-p, --port       Cassandra native transport port
--json           Machine-readable JSON output
```

## Configuration

```yaml
cassandra:
  contact_points: [127.0.0.1]
  port: 9042
  auth:
    username: myuser
    password: mypass
  consistency: LOCAL_QUORUM       # default: LOCAL_ONE
  connect_timeout: 10
  request_timeout: 30
  ssl:
    enabled: true
    ca_certs: /path/to/ca.crt
    verify: true
  # secure_connect_bundle: /path/to/astra-bundle.zip

keyspace:
  name: my_app
  replication:
    class: NetworkTopologyStrategy
    dc1: 3
    dc2: 2

migrations:
  directory: migrations

lock:
  ttl: 600

schema:
  agreement_wait: 30

profiles:
  dev:
    keyspace:
      name: myapp_dev
  prod:
    cassandra:
      contact_points: [10.0.2.1, 10.0.2.2, 10.0.2.3]
      consistency: LOCAL_QUORUM
    keyspace:
      name: myapp_prod
```

Config resolution order (last wins):

1. Built-in defaults
2. YAML file values
3. Profile overrides (`--profile prod`)
4. Environment variables (`CQLTRACK_KEYSPACE`, `CQLTRACK_PASSWORD`, etc.)
5. CLI flags (`--keyspace`, `--host`, `--port`)

## Migration File Format

Files follow the naming convention `V<version>__<description>.cql`:

```
migrations/
  V001__create_users_table.cql
  V002__create_orders_table.cql
  V003__add_phone_to_users.cql
```

Each file has an UP section and an optional `-- @down` section for rollback:

```sql
-- UP: applied by `cqltrack migrate`
ALTER TABLE users ADD phone text;

-- @down
-- applied by `cqltrack rollback`
ALTER TABLE users DROP phone;
```

## Linter

The built-in linter catches common mistakes before they hit your cluster:

```bash
$ cqltrack lint
  ERR   V005:3   [drop-no-if-exists]       DROP without IF EXISTS — not idempotent
  WARN  V008:1   [create-no-if-not-exists]  CREATE without IF NOT EXISTS
  ERR   V012:5   [column-drop]             ALTER TABLE DROP — permanently deletes data
```

Rules: `no-rollback`, `empty-rollback`, `drop-no-if-exists`, `create-no-if-not-exists`, `column-drop`, `truncate`, `pk-alter`, `type-change`

## CI/CD

Use `pending` as a deploy gate:

```bash
cqltrack --profile prod pending || exit 1
```

Use `lint` in pre-commit or PR checks:

```bash
cqltrack lint
```

JSON output for tooling:

```bash
cqltrack --json status
cqltrack --json history
cqltrack --json pending
cqltrack --json lint
cqltrack --json diff --target-keyspace other_ks
```

## Docker

```bash
# local Cassandra
docker compose up -d

# run cqltrack in a container
docker build -t cqltrack .
docker run --rm -v $(pwd)/migrations:/workspace/migrations \
  -v $(pwd)/cqltrack.yml:/workspace/cqltrack.yml \
  --network host cqltrack migrate
```

## Requirements

- Python 3.9+
- Apache Cassandra 3.x / 4.x / 5.x, or DataStax Astra DB
- Dependencies: `cassandra-driver`, `click`, `pyyaml`

## Examples

See the [`examples/migrations/`](examples/migrations/) directory for sample migration files demonstrating table creation, schema alterations, and rollback patterns.

## Documentation

See [USAGE.md](USAGE.md) for the complete guide — configuration reference, all commands with examples, SSL/TLS setup, Astra DB, distributed locking internals, partial failure handling, schema agreement, adoption workflow, lint rules, and troubleshooting.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and how to submit changes.

## License

[MIT](LICENSE)
