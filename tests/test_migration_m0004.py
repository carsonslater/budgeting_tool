"""m0004 — the legacy income figure is carried into month_plans."""

import sqlite3

import pytest

from migrations.m0004_retire_income_sources import migrate

SCHEMA = """
CREATE TABLE income_sources (id INTEGER PRIMARY KEY, source TEXT, amount REAL);
CREATE TABLE expenses (id INTEGER PRIMARY KEY, date TEXT);
CREATE TABLE budget_amounts (line_key TEXT, effective_month TEXT, amount REAL);
CREATE TABLE month_plans (
    month TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'inherited',
    confirmed_at TEXT,
    expected_income REAL
);
"""


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA)
    yield c
    c.close()


def _plans(conn):
    return dict(
        conn.execute(
            "SELECT month, expected_income FROM month_plans "
            "WHERE expected_income IS NOT NULL"
        ).fetchall()
    )


def _legacy_income(conn, amount):
    conn.execute(
        "INSERT INTO income_sources (source, amount) VALUES ('Monthly', ?)", (amount,)
    )


class TestCarryOver:
    def test_anchors_at_the_earliest_budget_month(self, conn):
        _legacy_income(conn, 6000.0)
        conn.execute("INSERT INTO expenses (date) VALUES ('2026-02-10')")
        conn.execute("INSERT INTO budget_amounts VALUES ('k', '2026-01', 300)")
        migrate(conn)
        assert _plans(conn) == {"2026-01": 6000.0}

    def test_anchors_at_the_earliest_expense_month(self, conn):
        _legacy_income(conn, 6000.0)
        conn.execute("INSERT INTO expenses (date) VALUES ('2025-11-02')")
        conn.execute("INSERT INTO budget_amounts VALUES ('k', '2026-01', 300)")
        migrate(conn)
        assert _plans(conn) == {"2025-11": 6000.0}

    def test_legacy_table_is_left_in_place(self, conn):
        _legacy_income(conn, 6000.0)
        conn.execute("INSERT INTO expenses (date) VALUES ('2026-02-10')")
        migrate(conn)
        assert conn.execute("SELECT COUNT(*) FROM income_sources").fetchone()[0] == 1


class TestNoOp:
    def test_no_legacy_income(self, conn):
        conn.execute("INSERT INTO expenses (date) VALUES ('2026-02-10')")
        migrate(conn)
        assert _plans(conn) == {}

    def test_no_dated_data_to_anchor_to(self, conn):
        _legacy_income(conn, 6000.0)
        migrate(conn)
        assert _plans(conn) == {}

    def test_existing_per_month_income_is_kept(self, conn):
        _legacy_income(conn, 6000.0)
        conn.execute("INSERT INTO expenses (date) VALUES ('2026-02-10')")
        conn.execute(
            "INSERT INTO month_plans (month, expected_income) VALUES ('2026-05', 4200)"
        )
        migrate(conn)
        assert _plans(conn) == {"2026-05": 4200.0}
