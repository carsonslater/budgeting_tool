"""
m0001_goal_tracking — expenses.goal_id, sweep_rules, closed_months.

Folds the former standalone `backend/schema_migrate_001.py` into the versioned
runner. Every step is guarded, so running it against a database that already
has some (or all) of this is a no-op.

Deliberate change from the original script: its step 4 also cleared `category`
on every 'Goal' expense it matched a goal name for. That discarded the category
a row was filed under and was not reversible, so the backfill here writes
`goal_id` and leaves `category` untouched (09-28 plan, Phase 0).
"""

from __future__ import annotations

import sqlite3

from .helpers import add_column

# Nullable by design: a NULL default is what lets SQLite accept a REFERENCES
# clause on an added column.
GOAL_ID_DDL = "INTEGER REFERENCES goals(id) ON DELETE SET NULL"


def add_goal_id(conn: sqlite3.Connection) -> bool:
    """ADD COLUMN expenses.goal_id. Returns True when it was added."""
    return add_column(conn, "expenses", "goal_id", GOAL_ID_DDL)


def create_sweep_rules(conn: sqlite3.Connection) -> None:
    """CREATE TABLE sweep_rules — how surplus is distributed to goals at month-end."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sweep_rules (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id         INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
            priority_rank   INTEGER NOT NULL DEFAULT 0,
            allocation_type TEXT    NOT NULL CHECK(allocation_type IN ('percentage', 'fixed')),
            amount          REAL    NOT NULL DEFAULT 0
        )
        """
    )


def create_closed_months(conn: sqlite3.Connection) -> None:
    """CREATE TABLE closed_months — the month-close ledger. Enriched by m0002."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS closed_months (
            month_id TEXT PRIMARY KEY  -- YYYY-MM
        )
        """
    )


def backfill_goal_expenses(
    conn: sqlite3.Connection,
) -> tuple[int, list[tuple[int, str]]]:
    """
    Set `goal_id` on 'Goal' expenses by matching `category` to `goals.name`
    (case-insensitive, trimmed). `category` is preserved.

    Returns (matched_count, unmatched_rows) where unmatched_rows is
    [(expenses.id, expenses.category), ...].
    """
    rows = conn.execute(
        """
        SELECT id, category
        FROM   expenses
        WHERE  expense_type = 'Goal'
          AND  goal_id IS NULL
        """
    ).fetchall()

    if not rows:
        return 0, []

    # Positional access throughout: migration code must not depend on the
    # caller having set row_factory.
    lookup = {
        (name or "").strip().lower(): goal_id
        for goal_id, name in conn.execute("SELECT id, name FROM goals").fetchall()
    }

    matched = 0
    unmatched: list[tuple[int, str]] = []

    for expense_id, category in rows:
        goal_id = lookup.get((category or "").strip().lower())
        if goal_id is None:
            unmatched.append((expense_id, category))
            continue
        conn.execute(
            "UPDATE expenses SET goal_id = ? WHERE id = ?", (goal_id, expense_id)
        )
        matched += 1

    return matched, unmatched


def migrate(conn: sqlite3.Connection) -> None:
    add_goal_id(conn)
    create_sweep_rules(conn)
    create_closed_months(conn)
    backfill_goal_expenses(conn)
