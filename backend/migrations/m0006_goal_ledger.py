"""
m0006_goal_ledger — goal money and annual-bill funds as one append-only ledger.

``goal_allocations`` holds every movement of money that is not a plain expense:

* goal-owned rows (``goal_id`` set): ``sweep`` (positive, from a month-end sweep),
  ``withdrawal`` (negative), ``reversal`` (cancels an earlier row when a month is reopened)
* fund-owned rows (``line_key`` set, one fund per irregular budget line): ``reserve``
  (positive, the monthly equivalent set aside), ``draw`` (negative, a bill paid from the
  fund), ``opening`` (positive, a starting balance), ``reversal``

A balance is the sum of an owner's rows. Nothing is updated or deleted. Both foreign keys
are ``RESTRICT``: ledger history outlives the goal or line it belongs to.

``closed_months`` gains the figures a month-end close records. ``leftover_capped`` (from
m0002) is no longer written; it is kept rather than dropped.
"""

from __future__ import annotations

import sqlite3

from .helpers import add_column, create_index

LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS goal_allocations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id     INTEGER REFERENCES goals(id) ON DELETE RESTRICT,
    line_key    TEXT    REFERENCES budget_lines(line_key) ON DELETE RESTRICT,
    month       TEXT    NOT NULL CHECK (month GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'),
    kind        TEXT    NOT NULL CHECK (kind IN
                    ('sweep', 'withdrawal', 'reserve', 'draw', 'opening', 'reversal')),
    amount      REAL    NOT NULL CHECK (amount <> 0),
    reverses_id INTEGER REFERENCES goal_allocations(id),
    created_at  TEXT    NOT NULL,
    CHECK ((goal_id IS NULL) <> (line_key IS NULL)),
    CHECK (kind NOT IN ('sweep', 'withdrawal') OR goal_id IS NOT NULL),
    CHECK (kind NOT IN ('reserve', 'draw', 'opening') OR line_key IS NOT NULL),
    CHECK (kind <> 'sweep' OR amount > 0),
    CHECK (kind <> 'reserve' OR amount > 0),
    CHECK (kind <> 'opening' OR amount > 0),
    CHECK (kind <> 'withdrawal' OR amount < 0),
    CHECK (kind <> 'draw' OR amount < 0),
    CHECK (kind <> 'reversal' OR reverses_id IS NOT NULL)
)
"""

_CLOSED_MONTH_COLUMNS: tuple[tuple[str, str], ...] = (
    ("expected_income", "REAL"),
    ("regular_spend", "REAL"),
    ("reserve_total", "REAL"),
    ("shortfall", "REAL"),
    ("swept_total", "REAL"),
)


def create_goal_allocations(conn: sqlite3.Connection) -> None:
    conn.execute(LEDGER_DDL)
    create_index(conn, "idx_goal_allocations_goal", "goal_allocations(goal_id)")
    create_index(conn, "idx_goal_allocations_fund", "goal_allocations(line_key, month)")
    create_index(conn, "idx_goal_allocations_month", "goal_allocations(month)")


def enrich_closed_months(conn: sqlite3.Connection) -> None:
    for column, ddl in _CLOSED_MONTH_COLUMNS:
        add_column(conn, "closed_months", column, ddl)


def migrate(conn: sqlite3.Connection) -> None:
    create_goal_allocations(conn)
    enrich_closed_months(conn)
