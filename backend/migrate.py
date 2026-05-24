"""
migrate.py — One-time migration from legacy CSV files → SQLite.

Usage (from project root or backend/):
    python backend/migrate.py
    python migrate.py          # if run from backend/

Each table is skipped if it already contains rows (idempotent).
"""

import sqlite3
import sys
from pathlib import Path

import pandas as pd

# Resolve paths relative to this file regardless of cwd
_ROOT = Path(__file__).parent.parent
_DATA_DIR = _ROOT / "data"
_DB_PATH = _DATA_DIR / "budget.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def _count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ---------------------------------------------------------------------------
# Per-table migration helpers
# ---------------------------------------------------------------------------

def migrate_expenses(conn: sqlite3.Connection) -> int:
    """Map CSV columns → DB columns and insert."""
    if _count(conn, "expenses") > 0:
        print("  expenses:         SKIPPED (table already has data)")
        return 0

    csv_path = _DATA_DIR / "expenses.csv"
    if not csv_path.exists():
        print("  expenses:         SKIPPED (expenses.csv not found)")
        return 0

    df = pd.read_csv(csv_path)
    # Normalise column names
    df.columns = [c.strip() for c in df.columns]

    col_map = {
        "Date": "date",
        "Description": "description",
        "Category": "category",
        "Subcategory": "subcategory",
        "Amount": "amount",
        "Payer": "payer",
        "ExpenseType": "expense_type",
    }
    df = df.rename(columns=col_map)

    # Fill missing optional cols
    for col in ["description", "category", "subcategory", "payer"]:
        if col in df.columns:
            df[col] = df[col].fillna("")

    if "expense_type" not in df.columns:
        df["expense_type"] = "Monthly"
    else:
        df["expense_type"] = df["expense_type"].fillna("Monthly")

    rows = df[["date", "description", "category", "subcategory",
               "amount", "payer", "expense_type"]].dropna(subset=["date"]).to_dict("records")

    conn.executemany(
        """INSERT INTO expenses (date, description, category, subcategory,
                                  amount, payer, expense_type)
           VALUES (:date, :description, :category, :subcategory,
                   :amount, :payer, :expense_type)""",
        rows,
    )
    conn.commit()
    print(f"  expenses:         {len(rows)} rows inserted")
    return len(rows)


def migrate_budgets(conn: sqlite3.Connection) -> int:
    if _count(conn, "budgets") > 0:
        print("  budgets:          SKIPPED (table already has data)")
        return 0

    csv_path = _DATA_DIR / "category_budget.csv"
    if not csv_path.exists():
        print("  budgets:          SKIPPED (category_budget.csv not found)")
        return 0

    df = pd.read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]

    col_map = {
        "Category":       "category",
        "Subcategory":    "subcategory",
        "Limit":          "limit_amount",
        "Frequency":      "frequency",
        "EffectiveDate":  "effective_date",
        "ConclusionDate": "conclusion_date",
    }
    df = df.rename(columns=col_map)

    df["subcategory"] = df.get("subcategory", pd.Series(dtype=str)).fillna("")
    df["frequency"]   = df.get("frequency",   pd.Series(dtype=str)).fillna("Monthly")
    # Conclusion date may be blank — store as None
    if "conclusion_date" in df.columns:
        df["conclusion_date"] = df["conclusion_date"].where(
            df["conclusion_date"].notna() & (df["conclusion_date"].astype(str).str.strip() != ""),
            other=None,
        )
    else:
        df["conclusion_date"] = None

    rows = df[["category", "subcategory", "limit_amount", "frequency",
               "effective_date", "conclusion_date"]].to_dict("records")

    conn.executemany(
        """INSERT INTO budgets (category, subcategory, limit_amount, frequency,
                                 effective_date, conclusion_date)
           VALUES (:category, :subcategory, :limit_amount, :frequency,
                   :effective_date, :conclusion_date)""",
        rows,
    )
    conn.commit()
    print(f"  budgets:          {len(rows)} rows inserted")
    return len(rows)


def migrate_income(conn: sqlite3.Connection) -> int:
    if _count(conn, "income_sources") > 0:
        print("  income_sources:   SKIPPED (table already has data)")
        return 0

    csv_path = _DATA_DIR / "income_sources.csv"
    if not csv_path.exists():
        print("  income_sources:   SKIPPED (income_sources.csv not found)")
        return 0

    df = pd.read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]
    col_map = {"Source": "source", "Amount": "amount"}
    df = df.rename(columns=col_map)

    rows = df[["source", "amount"]].to_dict("records")
    conn.executemany(
        "INSERT INTO income_sources (source, amount) VALUES (:source, :amount)",
        rows,
    )
    conn.commit()
    print(f"  income_sources:   {len(rows)} rows inserted")
    return len(rows)


def migrate_goals(conn: sqlite3.Connection) -> int:
    if _count(conn, "goals") > 0:
        print("  goals:            SKIPPED (table already has data)")
        return 0

    csv_path = _DATA_DIR / "goals.csv"
    if not csv_path.exists():
        print("  goals:            SKIPPED (goals.csv not found)")
        return 0

    df = pd.read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]

    col_map = {
        "Goal":          "name",
        "TargetAmount":  "target_amount",
        "TargetMonth":   "target_month",
        "CreatedDate":   "created_date",
        "Completed":     "completed",
    }
    df = df.rename(columns=col_map)

    # Boolean → integer
    def _bool_to_int(val) -> int:
        if isinstance(val, bool):
            return int(val)
        if isinstance(val, str):
            return 1 if val.strip().upper() in ("TRUE", "1", "YES") else 0
        return int(bool(val))

    df["completed"] = df["completed"].apply(_bool_to_int)
    df["created_date"] = df["created_date"].fillna("2020-01-01")

    rows = df[["name", "target_amount", "target_month",
               "created_date", "completed"]].to_dict("records")
    conn.executemany(
        """INSERT INTO goals (name, target_amount, target_month, created_date, completed)
           VALUES (:name, :target_amount, :target_month, :created_date, :completed)""",
        rows,
    )
    conn.commit()
    print(f"  goals:            {len(rows)} rows inserted")
    return len(rows)


def migrate_goal_budget_links(conn: sqlite3.Connection) -> int:
    if _count(conn, "goal_budget_links") > 0:
        print("  goal_budget_links: SKIPPED (table already has data)")
        return 0

    csv_path = _DATA_DIR / "goal_budget_links.csv"
    if not csv_path.exists():
        print("  goal_budget_links: SKIPPED (file not found — none to migrate)")
        return 0

    df = pd.read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]

    col_map = {
        "GoalName":   "goal_name",
        "Category":   "category",
        "Subcategory":"subcategory",
        "StartDate":  "start_date",
        "EndDate":    "end_date",
    }
    df = df.rename(columns=col_map)
    df["subcategory"] = df.get("subcategory", pd.Series(dtype=str)).fillna("")
    if "end_date" in df.columns:
        df["end_date"] = df["end_date"].where(
            df["end_date"].notna() & (df["end_date"].astype(str).str.strip() != ""),
            other=None,
        )
    else:
        df["end_date"] = None

    rows = df[["goal_name", "category", "subcategory",
               "start_date", "end_date"]].to_dict("records")
    conn.executemany(
        """INSERT INTO goal_budget_links (goal_name, category, subcategory, start_date, end_date)
           VALUES (:goal_name, :category, :subcategory, :start_date, :end_date)""",
        rows,
    )
    conn.commit()
    print(f"  goal_budget_links: {len(rows)} rows inserted")
    return len(rows)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Ensure DB and tables exist first
    from database import init_db  # noqa: relative import works when run as module
    init_db()

    print("\n── Migration ───────────────────────────────────────────")
    conn = _get_conn()
    total = 0
    total += migrate_expenses(conn)
    total += migrate_budgets(conn)
    total += migrate_income(conn)
    total += migrate_goals(conn)
    total += migrate_goal_budget_links(conn)
    conn.close()
    print(f"────────────────────────────────────────────────────────")
    print(f"  Total rows inserted: {total}\n")


if __name__ == "__main__":
    # Allow running from either project root or backend/
    sys.path.insert(0, str(Path(__file__).parent))
    main()
