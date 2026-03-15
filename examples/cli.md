# CLI Usage

cqltrack is primarily a command-line tool. This guide covers the full CLI workflow.

## Setup

```bash
pip install cql-track
```

Create a config file `cqltrack.yml` in your project root:

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

migrations:
  directory: migrations
```

## Initialize

Create the keyspace and tracking tables:

```bash
cqltrack init
```

```
Initialized cqltrack in keyspace 'my_app'.
Migrations directory: /path/to/migrations
```

## Create Migrations

Scaffold a new migration file:

```bash
cqltrack new create_users_table
```

This creates `migrations/V001__create_users_table.cql` with a template. Edit it with your CQL:

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

## Apply Migrations

```bash
# apply all pending
cqltrack migrate

# apply up to a specific version
cqltrack migrate --target 3

# preview without applying
cqltrack migrate --dry-run
```

```
Applying V001  create users table ... OK (275ms)
Applying V002  create orders table ... OK (132ms)
Applying V003  add phone to users ... OK (105ms)

Applied 3 migration(s).
```

## Check Status

```bash
cqltrack status
```

```
Keyspace:   my_app
Migrations: /path/to/migrations

  V001   applied  create users table              2026-03-10 19:20:06
  V002   applied  create orders table             2026-03-10 19:20:07
  V003   applied  add phone to users              2026-03-10 19:20:07
  V004   pending  add order notes
```

## View History

```bash
cqltrack history
```

```
Keyspace: my_app

  V001  OK  create users table        2026-03-10 19:20:06    275ms  user@hostname
  V002  OK  create orders table       2026-03-10 19:20:07    132ms  user@hostname
  V003  OK  add phone to users        2026-03-10 19:20:07    105ms  user@hostname
```

## Rollback

```bash
# undo the last migration
cqltrack rollback --yes

# undo the last 3
cqltrack rollback --yes -n 3
```

## Lint Migrations

Check for dangerous patterns without running anything:

```bash
cqltrack lint
```

```
  ERR   V005:3   [drop-no-if-exists]   DROP without IF EXISTS — not idempotent
  WARN  V008:1   [create-no-if-not-exists]  CREATE without IF NOT EXISTS

2 issue(s) found.
```

## Validate Checksums

Detect if someone modified an already-applied migration file:

```bash
cqltrack validate
```

If a mismatch is found, either restore the file or accept the change:

```bash
cqltrack repair --yes
```

## Schema Snapshot

Export the live schema:

```bash
cqltrack snapshot -o schema.cql
```

## Schema Diff

Compare two keyspaces:

```bash
cqltrack diff --source-keyspace my_app --target-keyspace my_app_v2
```

## JSON Output

Any read command supports JSON for scripting and CI:

```bash
cqltrack --json status
cqltrack --json history
cqltrack --json pending
cqltrack --json lint
```

## Multi-Environment Profiles

```yaml
# cqltrack.yml
profiles:
  dev:
    cassandra:
      contact_points: [127.0.0.1]
    keyspace:
      name: myapp_dev
  prod:
    cassandra:
      contact_points: [10.0.2.1, 10.0.2.2]
      consistency: LOCAL_QUORUM
    keyspace:
      name: myapp_prod
```

```bash
cqltrack --profile dev migrate
cqltrack --profile prod status
```

## CI/CD

Use as a deploy gate:

```bash
cqltrack --profile prod pending || exit 1
cqltrack --profile prod migrate
```

## Baseline (Existing Database)

Adopt cqltrack on a database that already has tables:

```bash
cqltrack init
cqltrack baseline 3 --yes    # marks V001-V003 as applied without executing
cqltrack migrate              # only runs V004+
```
