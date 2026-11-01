"""m0005 — each version row carries the frequency of its line."""

import sqlite3

import pytest

from migrations.m0005_frequency_per_version import migrate

SCHEMA = """
CREATE TABLE budget_lines (line_key TEXT PRIMARY KEY, frequency TEXT NOT NULL);
CREATE TABLE budget_amounts (
    line_key TEXT,
    effective_month TEXT,
    amount REAL,
    PRIMARY KEY (line_key, effective_month)
);
"""


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA)
    yield c
    c.close()


def test_existing_versions_take_the_lines_current_frequency(conn):
    conn.execute("INSERT INTO budget_lines VALUES ('k', 'Quarterly')")
    conn.executemany(
        "INSERT INTO budget_amounts VALUES ('k', ?, ?)",
        [("2025-01", 300.0), ("2025-06", 450.0), ("2025-09", None)],
    )
    migrate(conn)
    rows = conn.execute(
        "SELECT effective_month, amount, frequency FROM budget_amounts ORDER BY effective_month"
    ).fetchall()
    assert rows == [
        ("2025-01", 300.0, "Quarterly"),
        ("2025-06", 450.0, "Quarterly"),
        ("2025-09", None, None),
    ]


def test_an_unknown_frequency_is_rejected_by_the_column(conn):
    conn.execute("INSERT INTO budget_lines VALUES ('k', 'Monthly')")
    migrate(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO budget_amounts VALUES ('k', '2025-01', 1.0, 'Weekly')")
