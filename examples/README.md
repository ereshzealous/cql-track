# cqltrack Examples

This directory contains example migration files and integration guides for using cqltrack in different contexts.

## Shared Migrations

The `migrations/` directory contains sample `.cql` files used by all examples below:

```
migrations/
  V001__create_users_table.cql    Create users table with email index
  V002__create_orders_table.cql   Create orders table (clustered by user)
  V003__add_phone_to_users.cql    Add phone column to users
  V004__add_order_notes.cql       Add notes column to orders
  V005__dangerous_changes.cql     Create audit_log table
  V006__add_user_status.cql       Add status column to users
```

Each migration includes a `-- @down` rollback section.

## Integration Guides

| Guide | Description |
|-------|-------------|
| [cli.md](cli.md) | Using cqltrack as a standalone CLI tool |
| [plain-python.md](plain-python.md) | Programmatic usage in any Python application |
| [fastapi.md](fastapi.md) | Running migrations at FastAPI startup via lifespan |
| [django.md](django.md) | Running migrations in Django via AppConfig.ready() |

## Prerequisites

All examples assume:

1. **Cassandra running** on `127.0.0.1:9042` (use `docker compose up -d` from the project root)
2. **cqltrack installed**: `pip install cql-track`

## Quick Start

```bash
# start Cassandra
docker compose up -d

# CLI usage
cqltrack init
cqltrack migrate
cqltrack status

# or programmatically
python -c "
from cqltrack import CqlTrack
with CqlTrack(keyspace='my_app', migration_dir='migrations') as t:
    t.init()
    t.migrate()
    print(t.status())
"
```
