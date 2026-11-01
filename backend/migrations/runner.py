"""runner.py — the PRAGMA user_version-keyed migration runner."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Callable, Sequence

from .m0001_goal_tracking import migrate as _m0001
from .m0002_category_identity import migrate as _m0002
from .m0003_per_month_budgets import migrate as _m0003
from .m0004_retire_income_sources import migrate as _m0004
from .m0005_frequency_per_version import migrate as _m0005
from .m0006_goal_ledger import migrate as _m0006


@dataclass(frozen=True)
class Migration:
    """A single, atomic schema upgrade."""

    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]


# Every migration, ascending by version. Append only.
MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "goal tracking: expenses.goal_id, sweep_rules, closed_months", _m0001),
    Migration(2, "category identity: categories table, *_id columns, indexes", _m0002),
    Migration(
        3, "versioned budgets: budget_lines + budget_amounts + month_plans", _m0003
    ),
    Migration(
        4, "retire income_sources: carry the single figure into month_plans", _m0004
    ),
    Migration(5, "frequency per version: budget_amounts.frequency", _m0005),
    Migration(6, "goal ledger: goal_allocations, closed_months close figures", _m0006),
)

LATEST_VERSION: int = max(m.version for m in MIGRATIONS)


def get_user_version(conn: sqlite3.Connection) -> int:
    """Read the database's schema version."""
    return int(conn.execute("PRAGMA user_version;").fetchone()[0])


def pending_migrations(
    conn: sqlite3.Connection,
    migrations: Sequence[Migration] = MIGRATIONS,
) -> list[Migration]:
    """Migrations not yet applied to `conn`, ascending."""
    current = get_user_version(conn)
    return [m for m in migrations if m.version > current]


def _validate(migrations: Sequence[Migration]) -> None:
    versions = [m.version for m in migrations]
    if versions != sorted(set(versions)):
        raise ValueError(
            f"migration versions must be unique and ascending, got {versions}"
        )
    if any(v < 1 for v in versions):
        raise ValueError(f"migration versions must be >= 1, got {versions}")


def run_migrations(
    conn: sqlite3.Connection,
    migrations: Sequence[Migration] = MIGRATIONS,
) -> list[int]:
    """
    Apply every pending migration, ascending by version.

    Each migration runs in its own transaction together with its
    `user_version` bump, so a failure leaves the database on the last complete
    version rather than half-upgraded. Returns the versions applied.

    The connection must have no uncommitted work when called, because
    `BEGIN` cannot nest (SQLite has no savepoint nesting through `BEGIN`).
    """
    _validate(migrations)

    if conn.in_transaction:
        raise RuntimeError(
            "run_migrations() requires a connection with no pending transaction; "
            "commit or roll back first"
        )

    # PRAGMA foreign_keys is a no-op inside a transaction, so set it before BEGIN.
    conn.execute("PRAGMA foreign_keys=ON;")

    applied: list[int] = []
    for migration in pending_migrations(conn, migrations):
        conn.execute("BEGIN;")
        try:
            migration.apply(conn)
            # PRAGMA user_version cannot be parameterised; the value is an int we control.
            conn.execute(f"PRAGMA user_version = {int(migration.version)};")
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise
        applied.append(migration.version)

    return applied
