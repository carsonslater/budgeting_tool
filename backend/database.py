"""
database.py — SQLite connection and schema initialization.

DB path is resolved relative to this file so the server works regardless
of the working directory it is launched from.
"""

import os
import sqlite3
import sys
from pathlib import Path

def get_db_path() -> Path:
    """Resolve the SQLite database path, supporting both development and PyInstaller environments."""
    # Allow explicit override via environment variable
    env_path = os.environ.get("BUDGET_DB_PATH")
    if env_path:
        return Path(env_path)

    # Check if running in a packaged/frozen PyInstaller environment
    if getattr(sys, "frozen", False):
        exe_path = Path(sys.executable)
        # If packaged as a macOS app bundle, sys.executable is deep inside:
        # /path/to/dist/desktop_app.app/Contents/MacOS/desktop_app
        if "Contents/MacOS" in str(exe_path):
            base_dir = exe_path.parent.parent.parent.parent
        else:
            base_dir = exe_path.parent
        return base_dir / "data" / "budget.db"

    # Development mode: resolve relative to this file's directory (backend/)
    return Path(__file__).parent.parent / "data" / "budget.db"


# Always resolve relative to a persistent, stable location
_DB_PATH = get_db_path()


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
