"""
helpers.py — idempotent DDL helpers shared by the migration modules.

SQLite has no `ADD COLUMN IF NOT EXISTS` or `CREATE INDEX IF NOT EXISTS` for
every case we need, so each helper checks the catalog first. The helpers index
`PRAGMA` rows positionally so they work whether or not the caller set
`row_factory`.
"""

from __future__ import annotations

import sqlite3


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """True when `table` exists in the schema."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?;",
        (table,),
    ).fetchone()
    return row is not None


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """True when `table.column` exists. `PRAGMA table_info` row[1] is the name."""
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table});"))


def index_exists(conn: sqlite3.Connection, index: str) -> bool:
    """True when an index (or unique constraint's implicit index) exists."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?;",
        (index,),
    ).fetchone()
    return row is not None


def add_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> bool:
    """
    `ALTER TABLE ... ADD COLUMN` when absent. Returns True if the column was added.

    Note: SQLite forbids adding a `NOT NULL` column without a default, and
    forbids a `REFERENCES` clause on an added column unless its default is NULL.
    Every column added here is nullable, so both rules are satisfied.
    """
    if column_exists(conn, table, column):
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    return True


def create_index(conn: sqlite3.Connection, name: str, target: str) -> bool:
    """`CREATE INDEX` when absent. Returns True if the index was created."""
    if index_exists(conn, name):
        return False
    conn.execute(f"CREATE INDEX {name} ON {target}")
    return True
