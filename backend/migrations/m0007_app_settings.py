"""
m0007_app_settings — a small key-value table for app-level settings.

The first use is ``sweep_baseline``: the first month the goal ledger covers. The migration
writes no rows. The baseline is set once, from the turnover flow, so existing history is
never swept.
"""

from __future__ import annotations

import sqlite3

SETTINGS_DDL = """
CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute(SETTINGS_DDL)
