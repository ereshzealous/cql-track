# Django Integration

Run Cassandra migrations automatically when your Django application starts.

## Install

```bash
pip install cql-track django
```

## Project Structure

```
my-django-app/
  myproject/
    settings.py
    urls.py
  myapp/
    __init__.py
    apps.py
    views.py
  migrations/
    V001__create_users_table.cql
    V002__create_orders_table.cql
  cqltrack.yml
  manage.py
```

## AppConfig.ready() Pattern

Django's `AppConfig.ready()` runs once when the application starts. This is the right place to run Cassandra migrations.

```python
# myapp/apps.py

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class MyAppConfig(AppConfig):
    name = "myapp"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        """Run Cassandra migrations at startup."""
        from cqltrack import CqlTrack, MigrationError

        try:
            tracker = CqlTrack("cqltrack.yml")
            tracker.init()
            applied = tracker.migrate()
            if applied:
                logger.info(
                    "Applied %d Cassandra migration(s)", len(applied)
                )
            tracker.close()
        except MigrationError as e:
            logger.error("Cassandra migration failed: %s", e)
            raise
```

Register the app config in `__init__.py`:

```python
# myapp/__init__.py

default_app_config = "myapp.apps.MyAppConfig"
```

## With Inline Config

```python
class MyAppConfig(AppConfig):
    name = "myapp"

    def ready(self):
        from django.conf import settings
        from cqltrack import CqlTrack

        tracker = CqlTrack(
            contact_points=settings.CASSANDRA_HOSTS,
            keyspace=settings.CASSANDRA_KEYSPACE,
            username=settings.CASSANDRA_USER,
            password=settings.CASSANDRA_PASSWORD,
            migration_dir="migrations",
        )
        tracker.init()
        tracker.migrate()
        tracker.close()
```

```python
# settings.py

CASSANDRA_HOSTS = ["10.0.1.1", "10.0.1.2"]
CASSANDRA_KEYSPACE = "my_app"
CASSANDRA_USER = "cassandra"
CASSANDRA_PASSWORD = "secret"
```

## With Profiles

Switch environments using Django's settings or environment variables:

```python
import os

class MyAppConfig(AppConfig):
    name = "myapp"

    def ready(self):
        from cqltrack import CqlTrack

        env = os.getenv("DJANGO_ENV", "dev")
        tracker = CqlTrack("cqltrack.yml", profile=env)
        tracker.init()
        tracker.migrate()
        tracker.close()
```

```bash
DJANGO_ENV=prod python manage.py runserver
```

## Avoiding Double Execution

Django's `ready()` can be called twice in development (with the auto-reloader). This is safe because:

- `cqltrack init` uses `IF NOT EXISTS` for all DDL
- `cqltrack migrate` checks what's already applied and only runs pending migrations
- If nothing is pending, `migrate()` returns an empty list immediately

No guard code needed.

## Management Command (Alternative)

If you prefer running migrations explicitly (not at startup), create a management command:

```python
# myapp/management/commands/cqlmigrate.py

from django.core.management.base import BaseCommand

from cqltrack import CqlTrack


class Command(BaseCommand):
    help = "Run Cassandra schema migrations"

    def add_arguments(self, parser):
        parser.add_argument(
            "--profile", default=None,
            help="cqltrack profile (dev, staging, prod)",
        )
        parser.add_argument(
            "--target", type=int, default=None,
            help="Stop at this migration version",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Show pending migrations without applying",
        )

    def handle(self, *args, **options):
        tracker = CqlTrack("cqltrack.yml", profile=options["profile"])
        tracker.init()

        applied = tracker.migrate(
            target=options["target"],
            dry_run=options["dry_run"],
        )

        if applied and not options["dry_run"]:
            self.stdout.write(
                self.style.SUCCESS(f"Applied {len(applied)} migration(s)")
            )

        tracker.close()
```

Usage:

```bash
python manage.py cqlmigrate
python manage.py cqlmigrate --profile prod
python manage.py cqlmigrate --dry-run
python manage.py cqlmigrate --target 5
```

## Multiple Processes (gunicorn)

When running with multiple workers, cqltrack's distributed lock ensures only one process runs migrations:

```bash
gunicorn myproject.wsgi:application --workers 4
```

Each worker's `AppConfig.ready()` will attempt to migrate:
- Worker 1 acquires the lock and runs migrations
- Workers 2, 3, 4 wait for the lock, then see no pending migrations
- All workers start serving requests

## Testing

```python
from django.test import TestCase

from cqltrack import CqlTrack


class MigrationTest(TestCase):
    def test_migrations_applied(self):
        tracker = CqlTrack("cqltrack.yml")
        pending = tracker.pending()
        self.assertEqual(len(pending), 0, "There are pending Cassandra migrations")
        tracker.close()
```

## Notes

- cqltrack manages Cassandra schema only. Django's built-in `migrate` command still handles your relational database (PostgreSQL, SQLite, etc.)
- The two migration systems are independent — Django migrations for your relational DB, cqltrack migrations for Cassandra
- Your Django models don't map to Cassandra tables. Use `cassandra-driver` directly for Cassandra queries in your views and services
