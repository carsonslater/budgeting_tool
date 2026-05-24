"""
database.py — SQLite connection and schema initialization.

DB path is resolved relative to this file so the server works regardless
of the working directory it is launched from.
"""

import sqlite3
from pathlib import Path

# Always resolve relative to this file's location (backend/)
_DB_PATH = Path(__file__).parent.parent / "data" / "budget.db"


def get_db() -> sqlite3.Connection:
    """Return a new SQLite connection with row_factory set to Row."""
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    """Create all tables (idempotent — uses IF NOT EXISTS)."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS expenses (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                date         TEXT    NOT NULL,
                description  TEXT    NOT NULL DEFAULT '',
                category     TEXT    NOT NULL DEFAULT '',
                subcategory  TEXT    NOT NULL DEFAULT '',
                amount       REAL    NOT NULL DEFAULT 0,
                payer        TEXT    NOT NULL DEFAULT '',
                expense_type TEXT    NOT NULL DEFAULT 'Monthly'
            );

            CREATE TABLE IF NOT EXISTS budgets (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                category        TEXT    NOT NULL,
                subcategory     TEXT    NOT NULL DEFAULT '',
                limit_amount    REAL    NOT NULL DEFAULT 0,
                frequency       TEXT    NOT NULL DEFAULT 'Monthly',
                effective_date  TEXT    NOT NULL,
                conclusion_date TEXT
            );

            CREATE TABLE IF NOT EXISTS income_sources (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT    NOT NULL,
                amount REAL    NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS goals (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT    NOT NULL,
                target_amount REAL    NOT NULL DEFAULT 0,
                target_month  TEXT    NOT NULL,
                created_date  TEXT    NOT NULL,
                completed     INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS goal_budget_links (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_name   TEXT    NOT NULL,
                category    TEXT    NOT NULL,
                subcategory TEXT    NOT NULL DEFAULT '',
                start_date  TEXT    NOT NULL,
                end_date    TEXT
            );
        """)
        conn.commit()

    print(f"[database] Initialized DB at {_DB_PATH}")
