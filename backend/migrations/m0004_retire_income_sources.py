"""
m0004 — retire the single-value income source.

Expected income is per month (``month_plans.expected_income``). The legacy
``income_sources`` table held one figure that applied to every month. This migration
carries that figure into ``month_plans`` as an explicit value at the earliest month the
data covers, so every later month inherits it, which is what the old figure did.

``income_sources`` is left in place (expand-only, like ``budgets``). Nothing reads or
writes it after this version.

It does nothing when there is no legacy income, when a per-month income already exists,
or when the database has no dated data to anchor the value to.  In the last case the
user sets income by hand.
"""

from __future__ import annotations

import sqlite3


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
        ).fetchone()
        is not None
    )


def migrate(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "income_sources"):
        return

    total = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM income_sources"
    ).fetchone()[0]
    if not total:
        return

    already = conn.execute(
        "SELECT 1 FROM month_plans WHERE expected_income IS NOT NULL LIMIT 1"
    ).fetchone()
    if already is not None:
        return

    # Earliest month with any dated expense or budget version.
    anchor = conn.execute(
        """
        SELECT MIN(m) FROM (
            SELECT substr(date, 1, 7) AS m FROM expenses
            UNION ALL
            SELECT effective_month AS m FROM budget_amounts
        )
        """
    ).fetchone()[0]
    if anchor is None:
        return

    conn.execute(
        """
        INSERT INTO month_plans (month, expected_income) VALUES (?, ?)
        ON CONFLICT(month) DO UPDATE SET expected_income = excluded.expected_income
        """,
        (anchor, float(total)),
    )
