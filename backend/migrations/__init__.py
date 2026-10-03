"""
backend/migrations — versioned, idempotent schema migrations.

`PRAGMA user_version` is the source of truth: `run_migrations` applies every
registered migration whose version exceeds the database's current
`user_version`, in ascending order, one transaction each.

To add a migration, drop a module in this package and register it in
`runner.MIGRATIONS`. Never edit a migration that has already shipped — the
version gate means it will not re-run, so an in-place edit silently diverges
from every database that already applied the earlier form.
"""

from .runner import LATEST_VERSION, MIGRATIONS, Migration, run_migrations

__all__ = ["LATEST_VERSION", "MIGRATIONS", "Migration", "run_migrations"]
