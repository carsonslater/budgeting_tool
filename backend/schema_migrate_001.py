"""
schema_migrate_001.py — Schema migration: sweep rules & goal tracking fix.

Changes applied (idempotent — safe to re-run):
  1. ADD COLUMN goal_id INTEGER REFERENCES goals(id) ON DELETE SET NULL
     to the existing `expenses` table.
  2. CREATE TABLE sweep_rules  (goal_id FK, priority_rank, allocation_type, amount)
  3. CREATE TABLE closed_months (month_id TEXT PRIMARY KEY — YYYY-MM ledger)
  4. DATA: For every expenses row where expense_type = 'Goal', look up goals.id
     by matching expenses.category == goals.name, write the id into goal_id,
     then clear the category column for those rows.

Usage (from project root or backend/):
    python backend/schema_migrate_001.py
    python schema_migrate_001.py    # if run from backend/
"""

import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path resolution (matches database.py logic for dev mode)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent.parent
_DB_PATH = _ROOT / "data" / "budget.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table});").fetchall()
    return any(r["name"] == column for r in rows)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (table,)
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Migration steps
# ---------------------------------------------------------------------------

def step1_add_goal_id_to_expenses(conn: sqlite3.Connection) -> None:
    """ADD COLUMN goal_id to expenses (skipped if already present)."""
    if _column_exists(conn, "expenses", "goal_id"):
        print("  [SKIP]  expenses.goal_id already exists")
        return

    conn.execute("""
        ALTER TABLE expenses
        ADD COLUMN goal_id INTEGER REFERENCES goals(id) ON DELETE SET NULL
    """)
    conn.commit()
    print("  [OK]    ALTER TABLE expenses ADD COLUMN goal_id")


def step2_create_sweep_rules(conn: sqlite3.Connection) -> None:
    """CREATE TABLE sweep_rules if it does not exist."""
    if _table_exists(conn, "sweep_rules"):
        print("  [SKIP]  sweep_rules already exists")
        return

    conn.execute("""
        CREATE TABLE sweep_rules (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id         INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
            priority_rank   INTEGER NOT NULL DEFAULT 0,
            allocation_type TEXT    NOT NULL CHECK(allocation_type IN ('percentage', 'fixed')),
            amount          REAL    NOT NULL DEFAULT 0
        )
    """)
    conn.commit()
    print("  [OK]    CREATE TABLE sweep_rules")


def step3_create_closed_months(conn: sqlite3.Connection) -> None:
    """CREATE TABLE closed_months if it does not exist."""
    if _table_exists(conn, "closed_months"):
        print("  [SKIP]  closed_months already exists")
        return

    conn.execute("""
        CREATE TABLE closed_months (
            month_id TEXT PRIMARY KEY  -- YYYY-MM format
        )
    """)
    conn.commit()
    print("  [OK]    CREATE TABLE closed_months")


def step4_backfill_goal_expenses(conn: sqlite3.Connection) -> None:
    """
    For rows in expenses where expense_type = 'Goal':
      - Match expenses.category to goals.name (case-insensitive trim)
      - Write the matched goals.id into expenses.goal_id
      - Clear the category column (set to '')

    Rows that already have goal_id populated are left untouched.
    Rows whose category does not match any goal name are reported as warnings.
    """
    # Only look at Goal rows that haven't been migrated yet
    goal_rows = conn.execute("""
        SELECT id, category
        FROM   expenses
        WHERE  expense_type = 'Goal'
          AND  goal_id IS NULL
    """).fetchall()

    if not goal_rows:
        print("  [SKIP]  No un-migrated 'Goal' expense rows found")
        return

    # Build a lookup: lowercase(stripped name) → goal id
    goals = conn.execute("SELECT id, name FROM goals").fetchall()
    goal_lookup: dict[str, int] = {g["name"].strip().lower(): g["id"] for g in goals}

    matched = 0
    unmatched = []

    for row in goal_rows:
        key = (row["category"] or "").strip().lower()
        goal_id = goal_lookup.get(key)

        if goal_id is not None:
            conn.execute(
                "UPDATE expenses SET goal_id = ?, category = '' WHERE id = ?",
                (goal_id, row["id"]),
            )
            matched += 1
        else:
            unmatched.append((row["id"], row["category"]))

    conn.commit()
    print(f"  [OK]    Backfilled goal_id on {matched} expense row(s); category cleared")

    if unmatched:
        print(f"  [WARN]  {len(unmatched)} row(s) could not be matched to a goal name:")
        for eid, cat in unmatched:
            print(f"            expenses.id={eid}  category='{cat}'")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if not _DB_PATH.exists():
        print(f"[ERROR] Database not found at {_DB_PATH}")
        print("        Run `python backend/migrate.py` or `init_db()` first.")
        sys.exit(1)

    print(f"\n── Schema Migration 001 ─────────────────────────────────")
    print(f"   DB: {_DB_PATH}\n")

    conn = get_conn()
    try:
        step1_add_goal_id_to_expenses(conn)
        step2_create_sweep_rules(conn)
        step3_create_closed_months(conn)
        step4_backfill_goal_expenses(conn)
    finally:
        conn.close()

    print(f"\n── Done ─────────────────────────────────────────────────\n")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    main()
