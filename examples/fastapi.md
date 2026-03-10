# FastAPI Integration

Run Cassandra migrations automatically when your FastAPI application starts.

## Install

```bash
pip install cql-track fastapi uvicorn
```

## Project Structure

```
my-fastapi-app/
  app/
    __init__.py
    main.py
    routes.py
  migrations/
    V001__create_users_table.cql
    V002__create_orders_table.cql
  cqltrack.yml
  requirements.txt
```

## Lifespan Pattern (Recommended)

FastAPI's [lifespan](https://fastapi.tiangolo.com/advanced/events/) is the right place to run migrations. It runs once at startup, before the app serves any requests.

```python
# app/main.py

from contextlib import asynccontextmanager

from fastapi import FastAPI

from cqltrack import CqlTrack


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run migrations at startup, close connection on shutdown."""
    tracker = CqlTrack("cqltrack.yml")
    tracker.init()
    tracker.migrate()

    # store tracker on app state if you need it in routes
    app.state.cqltrack = tracker

    yield

    tracker.close()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

## With Inline Config

No YAML file needed — configure directly in code:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    tracker = CqlTrack(
        contact_points=["10.0.1.1", "10.0.1.2"],
        keyspace="my_app",
        consistency="LOCAL_QUORUM",
        replication={
            "class": "NetworkTopologyStrategy",
            "dc1": 3,
        },
        migration_dir="migrations",
    )
    tracker.init()
    tracker.migrate()

    yield

    tracker.close()
```

## With Profiles

Use different configs per environment:

```python
import os

@asynccontextmanager
async def lifespan(app: FastAPI):
    env = os.getenv("APP_ENV", "dev")
    tracker = CqlTrack("cqltrack.yml", profile=env)
    tracker.init()
    tracker.migrate()

    yield

    tracker.close()
```

```bash
APP_ENV=prod uvicorn app.main:app
```

## Migration Status Endpoint

Expose migration info for monitoring:

```python
from fastapi import FastAPI, Request


@app.get("/migrations")
async def migrations(request: Request):
    tracker = request.app.state.cqltrack
    return tracker.status()


@app.get("/migrations/pending")
async def pending(request: Request):
    tracker = request.app.state.cqltrack
    pending = tracker.pending()
    return {
        "pending_count": len(pending),
        "versions": [m.version for m in pending],
    }
```

## Error Handling

If a migration fails, the app should not start:

```python
from cqltrack import CqlTrack, MigrationError, CqlTrackError


@asynccontextmanager
async def lifespan(app: FastAPI):
    tracker = CqlTrack("cqltrack.yml")
    try:
        tracker.init()
        tracker.migrate()
    except MigrationError as e:
        # migration failed — do NOT start serving requests
        tracker.close()
        raise RuntimeError(f"Migration failed: {e}") from e
    except CqlTrackError as e:
        tracker.close()
        raise RuntimeError(f"cqltrack error: {e}") from e

    yield

    tracker.close()
```

FastAPI will refuse to start if the lifespan raises an exception. This is the correct behavior — don't serve traffic with a broken schema.

## Docker Entrypoint

```dockerfile
FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Migrations run automatically via the lifespan when the container starts. No separate migration step needed.

## Multiple Workers

When running with multiple workers (`uvicorn --workers 4`), each worker calls the lifespan independently. This is safe because:

- cqltrack acquires a **distributed lock** (LWT) before running migrations
- Only one worker actually runs the migrations
- Other workers wait for the lock, then see no pending migrations

```bash
uvicorn app.main:app --workers 4 --host 0.0.0.0
```

## Testing

Test with `TestClient`:

```python
from fastapi.testclient import TestClient
from app.main import app


def test_health():
    with TestClient(app) as client:
        # lifespan runs migrations before first request
        resp = client.get("/health")
        assert resp.status_code == 200


def test_migrations_applied():
    with TestClient(app) as client:
        resp = client.get("/migrations")
        data = resp.json()
        assert all(m["status"] == "applied" for m in data)
```
