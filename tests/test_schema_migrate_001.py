"""
tests/test_schema_migrate_001.py

Tests for schema_migrate_001.py — covers:
  - expenses.goal_id column added correctly
  - sweep_rules table created with correct constraints
  - closed_months table created with correct PK
  - Backfill: Goal expenses get goal_id set and category cleared
  - Backfill idempotency (safe to run twice)
  - Unmatched Goal expenses are preserved (not deleted) and warned
  - Steps are individually idempotent (SKIP path)
"""

import sqlite3
import sys
from pathlib import Path

import pytest

# Allow imports from backend/ when running tests from project root
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from schema_migrate_001 import (
    get_conn,
    step1_add_goal_id_to_expenses,
    step2_create_sweep_rules,
    step3_create_closed_months,
    step4_backfill_goal_expenses,
    _column_exists,
    _table_exists,
)


# ---------------------------------------------------------------------------
# Fixtures — in-memory database with minimal schema matching production
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_conn():
    """
    Returns an in-memory SQLite connection with the baseline schema
    (pre-migration state: no goal_id on expenses, no sweep_rules, no closed_months).
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")

    conn.executescript("""
        CREATE TABLE goals (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            target_amount REAL    NOT NULL DEFAULT 0,
            target_month  TEXT    NOT NULL DEFAULT '2025-01',
            created_date  TEXT    NOT NULL DEFAULT '2025-01-01',
            completed     INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE expenses (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            date         TEXT    NOT NULL DEFAULT '2025-01-01',
            description  TEXT    NOT NULL DEFAULT '',
            category     TEXT    NOT NULL DEFAULT '',
            subcategory  TEXT    NOT NULL DEFAULT '',
            amount       REAL    NOT NULL DEFAULT 0,
            payer        TEXT    NOT NULL DEFAULT '',
            expense_type TEXT    NOT NULL DEFAULT 'Monthly'
        );
    """)
    conn.commit()
    return conn


@pytest.fixture()
def seeded_conn(mem_conn):
    """mem_conn pre-seeded with goals and a mix of expense types."""
    conn = mem_conn

    conn.executemany(
        "INSERT INTO goals (name, target_amount, target_month, created_date) VALUES (?,?,?,?)",
        [
            ("Vacation Fund", 3000.0, "2025-06", "2025-01-01"),
            ("Emergency Fund", 10000.0, "2026-01", "2025-01-01"),
        ],
    )

    conn.executemany(
        "INSERT INTO expenses (date, description, category, amount, expense_type) VALUES (?,?,?,?,?)",
        [
            # Goal expenses — should be backfilled
            ("2025-03-01", "Transfer to savings", "Vacation Fund", 500.0, "Goal"),
            ("2025-04-01", "Emergency top-up",     "Emergency Fund", 200.0, "Goal"),
            # Regular expense — should NOT be touched
            ("2025-03-15", "Groceries",            "Food", 120.0, "Monthly"),
            # Goal expense with no matching goal name
            ("2025-05-01", "Mystery Goal",         "Nonexistent Goal", 50.0, "Goal"),
        ],
    )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Step 1 — ADD COLUMN goal_id
# ---------------------------------------------------------------------------

class TestStep1AddGoalId:
    def test_column_added(self, mem_conn):
        assert not _column_exists(mem_conn, "expenses", "goal_id")
        step1_add_goal_id_to_expenses(mem_conn)
        assert _column_exists(mem_conn, "expenses", "goal_id")

    def test_column_is_nullable(self, mem_conn):
        step1_add_goal_id_to_expenses(mem_conn)
        # Insert without goal_id — should not raise
        mem_conn.execute(
            "INSERT INTO expenses (date, description, amount) VALUES ('2025-01-01', 'Test', 10.0)"
        )
        mem_conn.commit()
        row = mem_conn.execute("SELECT goal_id FROM expenses ORDER BY id DESC LIMIT 1").fetchone()
        assert row["goal_id"] is None

    def test_idempotent_skip(self, mem_conn):
        step1_add_goal_id_to_expenses(mem_conn)
        # Should not raise on second call (column already exists path)
        step1_add_goal_id_to_expenses(mem_conn)
        assert _column_exists(mem_conn, "expenses", "goal_id")


# ---------------------------------------------------------------------------
# Step 2 — CREATE TABLE sweep_rules
# ---------------------------------------------------------------------------

class TestStep2SweepRules:
    def test_table_created(self, mem_conn):
        assert not _table_exists(mem_conn, "sweep_rules")
        step2_create_sweep_rules(mem_conn)
        assert _table_exists(mem_conn, "sweep_rules")

    def test_columns_correct(self, mem_conn):
        step2_create_sweep_rules(mem_conn)
        cols = {r["name"] for r in mem_conn.execute("PRAGMA table_info(sweep_rules);").fetchall()}
        assert cols == {"id", "goal_id", "priority_rank", "allocation_type", "amount"}

    def test_allocation_type_check_constraint(self, mem_conn):
        step2_create_sweep_rules(mem_conn)
        goal_id = mem_conn.execute(
            "INSERT INTO goals (name, target_month, created_date) VALUES ('Test', '2025-01', '2025-01-01')"
        ).lastrowid
        mem_conn.commit()

        # Valid values
        mem_conn.execute(
            "INSERT INTO sweep_rules (goal_id, priority_rank, allocation_type, amount) VALUES (?,?,?,?)",
            (goal_id, 1, "percentage", 50.0),
        )
        mem_conn.execute(
            "INSERT INTO sweep_rules (goal_id, priority_rank, allocation_type, amount) VALUES (?,?,?,?)",
            (goal_id, 2, "fixed", 200.0),
        )
        mem_conn.commit()

        # Invalid value should raise
        with pytest.raises(sqlite3.IntegrityError):
            mem_conn.execute(
                "INSERT INTO sweep_rules (goal_id, priority_rank, allocation_type, amount) VALUES (?,?,?,?)",
                (goal_id, 3, "invalid_type", 100.0),
            )
            mem_conn.commit()

    def test_idempotent_skip(self, mem_conn):
        step2_create_sweep_rules(mem_conn)
        step2_create_sweep_rules(mem_conn)
        assert _table_exists(mem_conn, "sweep_rules")


# ---------------------------------------------------------------------------
# Step 3 — CREATE TABLE closed_months
# ---------------------------------------------------------------------------

class TestStep3ClosedMonths:
    def test_table_created(self, mem_conn):
        assert not _table_exists(mem_conn, "closed_months")
        step3_create_closed_months(mem_conn)
        assert _table_exists(mem_conn, "closed_months")

    def test_primary_key_is_month_id(self, mem_conn):
        step3_create_closed_months(mem_conn)
        pk_cols = [
            r["name"]
            for r in mem_conn.execute("PRAGMA table_info(closed_months);").fetchall()
            if r["pk"] == 1
        ]
        assert pk_cols == ["month_id"]

    def test_duplicate_month_rejected(self, mem_conn):
        step3_create_closed_months(mem_conn)
        mem_conn.execute("INSERT INTO closed_months (month_id) VALUES ('2025-01')")
        mem_conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            mem_conn.execute("INSERT INTO closed_months (month_id) VALUES ('2025-01')")
            mem_conn.commit()

    def test_multiple_distinct_months_allowed(self, mem_conn):
        step3_create_closed_months(mem_conn)
        mem_conn.executemany(
            "INSERT INTO closed_months (month_id) VALUES (?)",
            [("2025-01",), ("2025-02",), ("2025-03",)],
        )
        mem_conn.commit()
        count = mem_conn.execute("SELECT COUNT(*) FROM closed_months").fetchone()[0]
        assert count == 3

    def test_idempotent_skip(self, mem_conn):
        step3_create_closed_months(mem_conn)
        step3_create_closed_months(mem_conn)
        assert _table_exists(mem_conn, "closed_months")


# ---------------------------------------------------------------------------
# Step 4 — Backfill goal_id on 'Goal' expenses
# ---------------------------------------------------------------------------

class TestStep4Backfill:
    @pytest.fixture(autouse=True)
    def _apply_ddl(self, seeded_conn):
        """Run DDL steps so the connection is migration-ready."""
        self.conn = seeded_conn
        step1_add_goal_id_to_expenses(seeded_conn)

    def test_matched_rows_get_goal_id(self):
        step4_backfill_goal_expenses(self.conn)

        vacation_goal_id = self.conn.execute(
            "SELECT id FROM goals WHERE name = 'Vacation Fund'"
        ).fetchone()["id"]

        row = self.conn.execute(
            "SELECT goal_id, category FROM expenses WHERE description = 'Transfer to savings'"
        ).fetchone()
        assert row["goal_id"] == vacation_goal_id

    def test_matched_rows_category_cleared(self):
        step4_backfill_goal_expenses(self.conn)
        row = self.conn.execute(
            "SELECT category FROM expenses WHERE description = 'Emergency top-up'"
        ).fetchone()
        assert row["category"] == ""

    def test_regular_expenses_untouched(self):
        step4_backfill_goal_expenses(self.conn)
        row = self.conn.execute(
            "SELECT goal_id, category FROM expenses WHERE description = 'Groceries'"
        ).fetchone()
        assert row["goal_id"] is None
        assert row["category"] == "Food"

    def test_unmatched_goal_row_preserved(self):
        step4_backfill_goal_expenses(self.conn)
        row = self.conn.execute(
            "SELECT goal_id, category FROM expenses WHERE description = 'Mystery Goal'"
        ).fetchone()
        # Row is NOT deleted — goal_id stays NULL, category stays as-is
        assert row["goal_id"] is None
        assert row["category"] == "Nonexistent Goal"

    def test_idempotent_second_run(self):
        step4_backfill_goal_expenses(self.conn)
        step4_backfill_goal_expenses(self.conn)  # should SKIP — no un-migrated rows left

        vacation_goal_id = self.conn.execute(
            "SELECT id FROM goals WHERE name = 'Vacation Fund'"
        ).fetchone()["id"]
        row = self.conn.execute(
            "SELECT goal_id FROM expenses WHERE description = 'Transfer to savings'"
        ).fetchone()
        assert row["goal_id"] == vacation_goal_id  # still correct, not cleared again

    def test_all_matched_goal_rows_populated(self):
        step4_backfill_goal_expenses(self.conn)
        # Both matched Goal rows should have a non-null goal_id
        rows = self.conn.execute(
            "SELECT goal_id FROM expenses WHERE expense_type = 'Goal' AND description != 'Mystery Goal'"
        ).fetchall()
        assert all(r["goal_id"] is not None for r in rows)
