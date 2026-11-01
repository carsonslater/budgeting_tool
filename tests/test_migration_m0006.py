"""m0006 — the goal ledger's constraints and the close-record columns."""

import sqlite3

import pytest

from migrations.m0006_goal_ledger import migrate

SCHEMA = """
CREATE TABLE goals (id INTEGER PRIMARY KEY);
CREATE TABLE budget_lines (line_key TEXT PRIMARY KEY);
CREATE TABLE closed_months (month_id TEXT PRIMARY KEY, closed_at TEXT, leftover_raw REAL,
                            leftover_capped REAL, sweep_note TEXT);
INSERT INTO goals VALUES (1);
INSERT INTO budget_lines VALUES ('k');
"""


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys=ON;")
    c.executescript(SCHEMA)
    migrate(c)
    yield c
    c.close()


def insert(
    conn,
    *,
    goal_id=None,
    line_key=None,
    month="2025-01",
    kind="sweep",
    amount=10.0,
    reverses_id=None,
):
    conn.execute(
        """INSERT INTO goal_allocations (goal_id, line_key, month, kind, amount, reverses_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, '2025-01-01T00:00:00')""",
        (goal_id, line_key, month, kind, amount, reverses_id),
    )


def test_a_goal_sweep_and_a_fund_reserve_are_accepted(conn):
    insert(conn, goal_id=1, kind="sweep", amount=10.0)
    insert(conn, line_key="k", kind="reserve", amount=5.0)
    assert conn.execute("SELECT COUNT(*) FROM goal_allocations").fetchone()[0] == 2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"goal_id": 1, "line_key": "k", "kind": "sweep"},  # two owners
        {"kind": "sweep"},  # no owner
        {"line_key": "k", "kind": "sweep"},  # a sweep belongs to a goal
        {"goal_id": 1, "kind": "reserve"},  # a reserve belongs to a fund
        {"goal_id": 1, "kind": "sweep", "amount": -5.0},  # sweeps are positive
        {"goal_id": 1, "kind": "withdrawal", "amount": 5.0},  # withdrawals are negative
        {"line_key": "k", "kind": "draw", "amount": 5.0},  # draws are negative
        {"goal_id": 1, "kind": "sweep", "amount": 0.0},  # never zero
        {
            "goal_id": 1,
            "kind": "reversal",
            "amount": 5.0,
        },  # a reversal names its target
        {"goal_id": 1, "kind": "sweep", "month": "2025-1"},  # YYYY-MM only
        {"goal_id": 1, "kind": "unknown"},
    ],
)
def test_invalid_rows_are_rejected(conn, kwargs):
    kwargs.setdefault("amount", 10.0)
    with pytest.raises(sqlite3.IntegrityError):
        insert(conn, **kwargs)


def test_a_goal_with_history_cannot_be_deleted(conn):
    insert(conn, goal_id=1)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM goals WHERE id = 1")


def test_closed_months_gains_the_close_figures(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(closed_months)")}
    assert {
        "expected_income",
        "regular_spend",
        "reserve_total",
        "shortfall",
        "swept_total",
    } <= cols
    assert {"leftover_raw", "leftover_capped", "sweep_note", "closed_at"} <= cols


def test_rerunning_the_migration_changes_nothing(conn):
    migrate(conn)
    migrate(conn)
    assert conn.execute("SELECT COUNT(*) FROM goal_allocations").fetchone()[0] == 0
