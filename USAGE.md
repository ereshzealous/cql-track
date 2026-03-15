# cqltrack Usage Guide

Schema migration tool for Apache Cassandra. Version-controlled CQL files, distributed locking, checksums, and multi-environment support.

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
  - [Config File](#config-file)
  - [Environment Variables](#environment-variables)
  - [CLI Overrides](#cli-overrides)
  - [Profiles](#profiles)
  - [Resolution Order](#resolution-order)
- [Migration Files](#migration-files)
  - [Naming Convention](#naming-convention)
  - [File Format](#file-format)
  - [Writing Good Migrations](#writing-good-migrations)
- [Commands](#commands)
  - [init](#init)
  - [migrate](#migrate)
  - [rollback](#rollback)
  - [status](#status)
  - [history](#history)
  - [pending](#pending)
  - [baseline](#baseline)
  - [validate](#validate)
  - [repair](#repair)
  - [new](#new)
  - [lint](#lint)
  - [snapshot](#snapshot)
  - [diff](#diff)
  - [profiles](#profiles-command)
- [JSON Output](#json-output)
- [SSL/TLS](#ssltls)
- [DataStax Astra DB](#datastax-astra-db)
- [Docker](#docker)
- [CI/CD Integration](#cicd-integration)
- [Distributed Locking](#distributed-locking)
- [Partial Failure Handling](#partial-failure-handling)
- [Schema Agreement](#schema-agreement)
- [Adopting cqltrack on an Existing Database](#adopting-cqltrack-on-an-existing-database)
- [Lint Rules](#lint-rules)
- [Troubleshooting](#troubleshooting)

---

## Installation

### From source (development)

```bash
git clone <repo-url> && cd cql-track
pip install -e ".[dev]"
```

### From PyPI (when published)

```bash
pip install cql-track
```

### Verify

```bash
cqltrack --version
```

---

## Quick Start

**1. Start Cassandra** (local development):

```bash
docker compose up -d
```

Wait for the health check to pass (~60 seconds on first start).

**2. Create a config file:**

```bash
cp cqltrack.yml.example cqltrack.yml
```

Edit `cqltrack.yml` — at minimum, set your keyspace name:

```yaml
cassandra:
  contact_points:
    - 127.0.0.1
  port: 9042

keyspace:
  name: my_app
  replication:
    class: SimpleStrategy
    replication_factor: 1
```

**3. Initialize:**

```bash
cqltrack init
```

This creates the keyspace and internal tracking tables (`cqltrack_history`, `cqltrack_lock`).

**4. Create your first migration:**

```bash
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

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

-- @down
DROP INDEX IF EXISTS idx_users_email;
DROP TABLE IF EXISTS users;
```

**5. Apply:**

```bash
cqltrack migrate
```

**6. Check status:**

```bash
cqltrack status
```

---

## Configuration

### Config File

cqltrack looks for `cqltrack.yml` in the current directory by default. Override with `-c`:

```bash
cqltrack -c /etc/cqltrack/production.yml migrate
```

Full configuration reference:

```yaml
cassandra:
  contact_points:
    - 127.0.0.1
  port: 9042
  auth:
    username: myuser
    password: mypass
  consistency: LOCAL_ONE
  connect_timeout: 10       # seconds
  request_timeout: 30       # seconds

  # SSL/TLS (optional)
  ssl:
    enabled: true
    ca_certs: /path/to/ca.crt
    certfile: /path/to/client.crt   # mutual TLS
    keyfile: /path/to/client.key
    verify: true

  # Astra DB (optional — replaces contact_points/port/ssl)
  # secure_connect_bundle: /path/to/secure-connect-mydb.zip

keyspace:
  name: my_app
  replication:
    class: SimpleStrategy
    replication_factor: 1

migrations:
  directory: migrations

lock:
  ttl: 600                  # seconds before stale lock auto-expires

schema:
  agreement_wait: 30        # max seconds to wait for schema agreement
```

#### Replication Strategies

**SimpleStrategy** (development, single datacenter):

```yaml
keyspace:
  name: my_app
  replication:
    class: SimpleStrategy
    replication_factor: 1
```

**NetworkTopologyStrategy** (production, multi-datacenter):

```yaml
keyspace:
  name: my_app
  replication:
    class: NetworkTopologyStrategy
    dc1: 3
    dc2: 2
```

#### Consistency Levels

Valid values for `cassandra.consistency`:

| Level | Use Case |
|-------|----------|
| `ANY` | Fire and forget (writes only) |
| `ONE` | Single replica, fastest reads |
| `LOCAL_ONE` | Like ONE but stays in local DC |
| `QUORUM` | Majority of all replicas |
| `LOCAL_QUORUM` | Majority in local DC (recommended for production) |
| `EACH_QUORUM` | Majority in every DC |
| `ALL` | Every replica must respond |

The distributed lock always uses `SERIAL` consistency regardless of this setting (that's how Lightweight Transactions work).

### Environment Variables

Every config value can be overridden via environment variables:

| Variable | Overrides |
|----------|-----------|
| `CQLTRACK_CONTACT_POINTS` | `cassandra.contact_points` (comma-separated) |
| `CQLTRACK_PORT` | `cassandra.port` |
| `CQLTRACK_KEYSPACE` | `keyspace.name` |
| `CQLTRACK_USERNAME` | `cassandra.auth.username` |
| `CQLTRACK_PASSWORD` | `cassandra.auth.password` |
| `CQLTRACK_CONSISTENCY` | `cassandra.consistency` |
| `CQLTRACK_SECURE_CONNECT_BUNDLE` | `cassandra.secure_connect_bundle` |

Example:

```bash
CQLTRACK_KEYSPACE=staging_db CQLTRACK_CONSISTENCY=LOCAL_QUORUM cqltrack migrate
```

### CLI Overrides

```bash
cqltrack --keyspace other_db status
cqltrack --host 10.0.1.1,10.0.1.2 --port 9042 migrate
cqltrack -c /path/to/config.yml --profile prod status
```

### Profiles

Define multiple environments in a single config file:

```yaml
# base config (shared defaults)
cassandra:
  consistency: LOCAL_ONE

keyspace:
  name: my_app
  replication:
    class: SimpleStrategy
    replication_factor: 1

# per-environment overrides
profiles:
  dev:
    cassandra:
      contact_points:
        - 127.0.0.1
    keyspace:
      name: myapp_dev
      replication:
        class: SimpleStrategy
        replication_factor: 1

  staging:
    cassandra:
      contact_points:
        - 10.0.1.1
        - 10.0.1.2
      consistency: LOCAL_QUORUM
    keyspace:
      name: myapp_staging
      replication:
        class: NetworkTopologyStrategy
        dc1: 2

  prod:
    cassandra:
      contact_points:
        - 10.0.2.1
        - 10.0.2.2
        - 10.0.2.3
      consistency: LOCAL_QUORUM
      auth:
        username: cqltrack_svc
        password: "${CQLTRACK_PASSWORD}"
    keyspace:
      name: myapp_prod
      replication:
        class: NetworkTopologyStrategy
        dc1: 3
        dc2: 3
```

Usage:

```bash
cqltrack --profile dev migrate
cqltrack --profile staging status
cqltrack --profile prod migrate
```

List available profiles:

```bash
cqltrack profiles
```

### Resolution Order

Configuration is merged in this order (last wins):

1. Built-in defaults
2. Top-level YAML values
3. Profile overrides (`--profile dev`)
4. `CQLTRACK_*` environment variables
5. CLI flags (`--keyspace`, `--host`, `--port`)

---

## Migration Files

### Naming Convention

```
V<version>__<description>.cql
```

- `version`: integer, zero-padded (e.g., `001`, `002`, `042`)
- `description`: snake_case, describes the change
- Double underscore `__` separates version from description

Examples:

```
V001__create_users_table.cql
V002__create_orders_table.cql
V003__add_phone_to_users.cql
V010__add_audit_log.cql
```

Files that don't match this pattern are ignored.

### File Format

Each file contains CQL statements for the **up** (apply) direction, optionally followed by `-- @down` for rollback:

```sql
-- Migration: create users table

CREATE TABLE IF NOT EXISTS users (
    user_id    UUID,
    email      text,
    name       text,
    created_at timestamp,
    PRIMARY KEY (user_id)
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

-- @down
DROP INDEX IF EXISTS idx_users_email;
DROP TABLE IF EXISTS users;
```

- Everything before `-- @down` is the **up** section (applied by `cqltrack migrate`)
- Everything after `-- @down` is the **down** section (applied by `cqltrack rollback`)
- The `-- @down` marker is case-insensitive
- Statements are separated by semicolons
- SQL comments (`--`) are stripped during parsing
- String literals with semicolons and escaped quotes (`''`) are handled correctly

### Writing Good Migrations

**Use IF NOT EXISTS / IF EXISTS.** Makes migrations idempotent and safe for retry after partial failure:

```sql
CREATE TABLE IF NOT EXISTS users ( ... );
-- not: CREATE TABLE users ( ... );
```

**One logical change per migration.** Don't combine unrelated table creation with column alterations. If statement 3 of 5 fails, only statements 1-2 will have run.

**Always provide a `@down` section.** Rollback is essential for development and incident recovery. The linter warns if it's missing.

**Don't modify applied migrations.** cqltrack checksums every file. If you change an already-applied migration file, `cqltrack validate` will catch it and `cqltrack migrate` will refuse to run.

**Avoid destructive operations in UP.** `DROP COLUMN`, `TRUNCATE`, and `DROP TABLE` permanently destroy data. The linter flags these as errors.

---

## Commands

### init

Create the keyspace and internal tracking tables.

```bash
cqltrack init
```

This runs:
1. `CREATE KEYSPACE IF NOT EXISTS <keyspace> WITH replication = ...`
2. `CREATE TABLE IF NOT EXISTS cqltrack_history (...)`
3. `CREATE TABLE IF NOT EXISTS cqltrack_lock (...)`

Each DDL statement waits for schema agreement across all nodes before proceeding.

Safe to run multiple times (all statements use `IF NOT EXISTS`).

### migrate

Apply pending migrations in version order.

```bash
# apply all pending
cqltrack migrate

# apply up to a specific version
cqltrack migrate --target 5

# preview without applying
cqltrack migrate --dry-run
```

Before applying, `migrate` checks all checksums. If any applied migration file has been modified, it aborts and tells you to run `validate` or `repair`.

Each migration runs inside a distributed lock to prevent concurrent execution.

### rollback

Undo the most recently applied migration(s).

```bash
# roll back the latest migration
cqltrack rollback --yes

# roll back the last 3 migrations
cqltrack rollback --yes -n 3
```

Requires the migration file to have a `-- @down` section. Fails with a clear error if rollback statements are missing.

### status

Show which migrations have been applied and which are pending.

```bash
cqltrack status
```

Output:

```
Keyspace:   my_app
Migrations: /path/to/migrations

  V001   applied  create users table              2026-03-01 08:08:52
  V002   applied  create orders table             2026-03-01 08:08:52
  V003   applied  add phone to users              2026-03-01 08:08:52
  V004   pending  add order notes
```

### history

Show full migration history including who applied each migration and how long it took.

```bash
cqltrack history
```

Output:

```
Keyspace: my_app

  V001  OK  create users table        2026-03-01 08:08:52    275ms  user@hostname
  V002  OK  create orders table       2026-03-01 08:08:52    134ms  user@hostname
  V003  OK  add phone to users        2026-03-01 08:08:52     94ms  user@hostname
```

Failed migrations show with a `FAILED` marker in red.

### pending

Check if there are unapplied migrations. Exits with code 1 if any exist.

```bash
cqltrack pending
```

Designed for CI gates:

```bash
cqltrack pending || { echo "ERROR: pending migrations exist"; exit 1; }
```

### baseline

Mark existing migrations as applied without executing them. Used when adopting cqltrack on a database that already has tables.

```bash
# mark V001 through V005 as applied
cqltrack baseline 5 --yes
```

This records each migration in the history table with status `applied` and `exec_time_ms: 0`, tagged with `[baseline]` in the `applied_by` field.

### validate

Check that no applied migration files have been modified since they were run.

```bash
cqltrack validate
```

Compares the MD5 checksum of each file on disk against the checksum recorded when it was applied. Exits with code 1 on mismatch.

### repair

Accept changes to migration files by updating the recorded checksums.

```bash
cqltrack repair --yes
```

Use this after intentionally editing an already-applied migration file (e.g., fixing a comment). This updates the stored checksum to match the current file — it does **not** re-run the migration.

### new

Scaffold a new migration file with the next version number.

```bash
cqltrack new add_user_preferences
# creates migrations/V007__add_user_preferences.cql
```

The generated file contains a template with `-- @down` section ready to fill in.

### lint

Static analysis of migration files for dangerous patterns.

```bash
cqltrack lint
```

Output:

```
  ERR   V005:3       [drop-no-if-exists]  DROP without IF EXISTS — not idempotent
  WARN  V005:5       [column-drop]        ALTER TABLE DROP — permanently deletes data
  ERR   V008:2       [truncate]           TRUNCATE deletes all data in the table

3 issue(s) found.
```

Exits with code 1 if any errors are found. See [Lint Rules](#lint-rules) for the full list.

### snapshot

Export the live keyspace schema as CQL.

```bash
# print to stdout
cqltrack snapshot

# save to file
cqltrack snapshot -o schema.cql
```

Uses the DataStax driver's metadata to export the full schema including all tables, indexes, UDTs, and materialized views.

### diff

Compare schemas between two environments or keyspaces.

```bash
# compare two profiles (different clusters)
cqltrack diff --source dev --target staging

# compare two keyspaces on the same cluster
cqltrack diff --source-keyspace my_app --target-keyspace my_app_v2

# mix: profile for source, keyspace override for target
cqltrack diff --target-keyspace my_app_staging
```

Output:

```
Schema diff: my_app <-> my_app_v2

  table       orders                          only in my_app   ...
  column      users.phone                     only in my_app   text
  column      users.status                    only in my_app_v2  text

3 difference(s) found.
```

Exits with code 1 if differences are found. Skips internal `cqltrack_*` tables.

### profiles (command)

List all profiles defined in the config file.

```bash
cqltrack profiles
```

Output:

```
Available profiles:
  dev
  staging
  prod
```

---

## JSON Output

Add `--json` before any read command for machine-parseable output:

```bash
cqltrack --json status
cqltrack --json history
cqltrack --json pending
cqltrack --json lint
cqltrack --json diff --source-keyspace ks1 --target-keyspace ks2
```

The `--json` flag is a **global** option — it goes before the command name.

**status:**

```json
[
  {
    "version": 1,
    "description": "create users table",
    "status": "applied",
    "applied_at": "2026-03-01T08:08:52.028000",
    "applied_by": "user@hostname"
  }
]
```

**history:**

```json
[
  {
    "version": 1,
    "description": "create users table",
    "status": "applied",
    "checksum": "25c5263a77a0c19cac6a2f92167dca3e",
    "applied_at": "2026-03-01T08:08:52.028000",
    "applied_by": "user@hostname",
    "exec_time_ms": 275
  }
]
```

**pending:**

```json
{"pending_count": 2, "versions": [7, 8]}
```

**lint:**

```json
[
  {
    "version": 5,
    "file": "V005__dangerous_changes.cql",
    "line": 3,
    "severity": "error",
    "rule": "drop-no-if-exists",
    "message": "DROP without IF EXISTS — not idempotent"
  }
]
```

**diff:**

```json
[
  {
    "kind": "table",
    "path": "orders",
    "change": "only_in_source",
    "source": "...",
    "target": null
  }
]
```

---

## SSL/TLS

SSL is **disabled by default**. Enable it in `cqltrack.yml`:

```yaml
cassandra:
  contact_points:
    - cassandra.example.com
  ssl:
    enabled: true
    ca_certs: /path/to/ca.crt       # CA certificate to verify server
    verify: true                     # hostname + certificate verification
```

For mutual TLS (client certificates):

```yaml
cassandra:
  ssl:
    enabled: true
    ca_certs: /path/to/ca.crt
    certfile: /path/to/client.crt
    keyfile: /path/to/client.key
    verify: true
```

To disable certificate verification (not recommended for production):

```yaml
cassandra:
  ssl:
    enabled: true
    verify: false
```

Local Docker development does not use SSL — just omit the `ssl` section entirely.

---

## DataStax Astra DB

cqltrack supports Astra DB via the secure connect bundle. This replaces `contact_points`, `port`, and `ssl` entirely:

```yaml
cassandra:
  secure_connect_bundle: /path/to/secure-connect-mydb.zip
  auth:
    username: <client_id>
    password: <client_secret>
```

Or via environment variable:

```bash
CQLTRACK_SECURE_CONNECT_BUNDLE=/path/to/bundle.zip \
CQLTRACK_USERNAME=<client_id> \
CQLTRACK_PASSWORD=<client_secret> \
cqltrack migrate
```

---

## Docker

### Running cqltrack in a container

Build:

```bash
docker build -t cqltrack .
```

Run (mount your migrations and config):

```bash
docker run --rm \
  -v $(pwd)/migrations:/workspace/migrations \
  -v $(pwd)/cqltrack.yml:/workspace/cqltrack.yml \
  --network host \
  cqltrack migrate
```

### Local Cassandra for development

```bash
docker compose up -d
```

This starts Cassandra 4.1 with:
- Port 9042 exposed
- Health check (ready in ~60 seconds)
- Persistent volume `cassandra-data`

Check health:

```bash
docker compose ps    # STATUS should show (healthy)
```

Stop without losing data:

```bash
docker compose stop
```

Stop and wipe data:

```bash
docker compose down -v
```

---

## CI/CD Integration

### GitHub Actions

```yaml
name: Migrations Check
on: [pull_request]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install cql-track

      # lint migration files (no Cassandra needed)
      - name: Lint migrations
        run: cqltrack lint

      # check for pending migrations against staging
      - name: Check pending migrations
        run: cqltrack --profile staging pending
        env:
          CQLTRACK_PASSWORD: ${{ secrets.CASSANDRA_PASSWORD }}
```

### Pre-deploy gate

Add to your deployment pipeline:

```bash
# fail the deploy if there are unapplied migrations
cqltrack --profile prod pending || {
  echo "ERROR: Apply pending migrations before deploying"
  exit 1
}
```

### Apply during deploy

```bash
cqltrack --profile prod migrate
```

### Lint as pre-commit hook

```bash
#!/bin/sh
# .git/hooks/pre-commit
cqltrack lint
```

---

## Distributed Locking

cqltrack uses Cassandra Lightweight Transactions (LWT) to prevent concurrent migration runs across multiple nodes or CI workers.

How it works:

1. `INSERT INTO cqltrack_lock ... IF NOT EXISTS USING TTL <lock_ttl>`
2. If another process holds the lock, retry up to 30 times (2 seconds apart)
3. On completion (or crash), release with `DELETE FROM cqltrack_lock WHERE lock_id = 'migration' IF owner = <owner>`
4. If the process crashes without releasing, the TTL (default: 600 seconds) auto-expires the lock

The lock uses `SERIAL` consistency (full linearizability) regardless of your configured consistency level.

The lock owner is recorded as `<username>@<hostname>-<pid>-<random_hex>` for debugging stuck locks.

Configure the TTL:

```yaml
lock:
  ttl: 600   # seconds, default 600
```

---

## Partial Failure Handling

When a migration fails partway through (e.g., statement 2 of 4 throws an error):

1. **Statements that already ran are NOT rolled back.** Cassandra has no transactions for DDL. If `CREATE TABLE` succeeded but the next `ALTER TABLE` failed, the table exists.

2. **The migration is recorded as `failed`** in `cqltrack_history` with status, timing, and error context.

3. **`cqltrack status` shows it as `pending`** — failed migrations are excluded from the "applied" set, so they're eligible for retry.

4. **`cqltrack history` shows it as `FAILED`** — the full audit trail is preserved.

5. **Fix and retry.** Edit the migration file to fix the error, then run `cqltrack migrate` again. It automatically clears the failed record and re-applies.

This is why idempotent statements (`IF NOT EXISTS`, `IF EXISTS`) matter — the first statement already succeeded, so on retry it needs to be safe to execute again.

---

## Schema Agreement

Cassandra propagates schema changes (DDL) asynchronously across nodes. Running two DDL statements back-to-back can fail if the second node hasn't seen the first change yet.

cqltrack handles this at two levels:

1. **Driver level:** `max_schema_agreement_wait` is set on the Cluster object (default: 30 seconds).

2. **Statement level:** After every DDL statement (`CREATE`, `ALTER`, `DROP`, `TRUNCATE`), cqltrack polls `system.local` and `system.peers` until all nodes report the same `schema_version` UUID.

DML statements (`INSERT`, `UPDATE`, `SELECT`) skip this check.

Configure the timeout:

```yaml
schema:
  agreement_wait: 30   # seconds, default 30
```

---

## Adopting cqltrack on an Existing Database

If your database already has tables from manual CQL or another tool:

**1. Create migration files** that match the current schema:

```bash
cqltrack new create_users_table
cqltrack new create_orders_table
cqltrack new add_indexes
```

Write the CQL that would recreate the existing tables (with `IF NOT EXISTS`).

**2. Initialize cqltrack:**

```bash
cqltrack init
```

**3. Baseline to the current state:**

```bash
cqltrack baseline 3 --yes
```

This marks V001-V003 as applied without executing them. From now on, only new migrations (V004+) will run.

**4. Verify:**

```bash
cqltrack status
# V001-V003: applied
# V004+: pending (if any)
```

---

## Lint Rules

| Rule | Severity | Description |
|------|----------|-------------|
| `no-rollback` | warn | Migration has no `-- @down` section |
| `empty-rollback` | warn | `@down` section exists but contains no statements |
| `drop-no-if-exists` | error | `DROP TABLE/INDEX/KEYSPACE` without `IF EXISTS` |
| `create-no-if-not-exists` | warn | `CREATE TABLE/INDEX/KEYSPACE` without `IF NOT EXISTS` |
| `column-drop` | error | `ALTER TABLE ... DROP` in the UP section (data loss) |
| `truncate` | error | `TRUNCATE` statement (data loss) |
| `pk-alter` | error | Attempt to alter PRIMARY KEY (not supported in Cassandra) |
| `type-change` | warn | `ALTER TABLE ... ALTER ... TYPE` (only compatible types allowed) |

The linter only flags `column-drop` in the UP section — drops in `@down` (rollback) are expected and not flagged.

---

## Troubleshooting

### "Cannot connect to Cassandra"

- Is Cassandra running? `docker compose ps` should show `(healthy)`
- Check `contact_points` and `port` in your config
- First startup takes ~60 seconds. Wait for the health check.

### "Profile 'X' not found"

- Run `cqltrack profiles` to see available profiles
- Check indentation in `cqltrack.yml` — profiles must be nested under the `profiles:` key

### "CHECKSUM MISMATCH"

Someone (or you) edited an already-applied migration file.

- `cqltrack validate` shows which files changed
- If the edit was intentional: `cqltrack repair --yes`
- If not: restore the original file from version control

### "Migration lock is held by ..."

Another process is running migrations, or a previous run crashed.

- Wait for the other process to finish
- If the process crashed, the lock auto-expires after `lock.ttl` seconds (default: 600)
- Check who holds it: `SELECT * FROM cqltrack_lock` in cqlsh

### "V00X has no @down section — cannot roll back"

The migration file doesn't have a `-- @down` marker. Add rollback statements to the file. This won't affect the applied checksum since rollback reads the file at execution time.

### "Schema agreement not reached"

Your cluster nodes are slow to converge on schema changes. This is a warning, not a fatal error. Options:

- Increase `schema.agreement_wait` in config
- Check cluster health — a node might be down or overloaded
- The migration proceeds anyway after the timeout

### Migration failed partway through

```bash
cqltrack history       # shows FAILED with timing
cqltrack status        # shows as pending (ready for retry)
# fix the CQL file
cqltrack migrate       # clears failed record, retries
```

### "Unknown consistency level"

Valid values: `ANY`, `ONE`, `TWO`, `THREE`, `QUORUM`, `ALL`, `LOCAL_ONE`, `LOCAL_QUORUM`, `EACH_QUORUM`. Check spelling and case in your config — cqltrack normalizes to uppercase but the value must match one of these.
