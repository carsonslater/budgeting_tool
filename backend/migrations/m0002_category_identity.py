"""
m0002_category_identity — category identity, phase 1 (expand only).

Adds a `categories` surrogate-key table plus nullable `*_id` columns on
`budgets` and `expenses`, backfills both from the existing string columns, adds
the indexes that were previously absent, and enriches `closed_months` with the
audit fields a month-close needs.

Expand only: the legacy string columns stay in place and stay authoritative for
reads. Dual-write begins in Phase 2; the strings are dropped in a later
contract migration once every read path resolves IDs.

Uniqueness is (name, kind), not name alone. Five names in the live data are used
as both a category and a subcategory — Auto, Baby Items, Health, Other, Phone
Bill. A name-only unique constraint would collapse each pair into one row with
one id, so a rename by id would silently rename both concepts at once and the
`kind` column would contradict itself.
"""

from __future__ import annotations

import sqlite3

from .helpers import add_column, create_index

KIND_CATEGORY = "category"
KIND_SUBCATEGORY = "subcategory"

# (table, id column) — added nullable; a NULL subcategory_id means "no subcategory".
_ID_COLUMNS: tuple[tuple[str, str], ...] = (
    ("budgets", "category_id"),
    ("budgets", "subcategory_id"),
    ("expenses", "category_id"),
    ("expenses", "subcategory_id"),
)

# (table, string column, kind) — the string columns this migration reads from.
_NAME_SOURCES: tuple[tuple[str, str, str], ...] = (
    ("expenses", "category", KIND_CATEGORY),
    ("expenses", "subcategory", KIND_SUBCATEGORY),
    ("budgets", "category", KIND_CATEGORY),
    ("budgets", "subcategory", KIND_SUBCATEGORY),
)

_INDEXES: tuple[tuple[str, str], ...] = (
    ("idx_expenses_date", "expenses(date)"),
    ("idx_expenses_category", "expenses(category, subcategory)"),
    ("idx_expenses_category_id", "expenses(category_id, subcategory_id)"),
    ("idx_expenses_goal_id", "expenses(goal_id)"),
    ("idx_budgets_category", "budgets(category, subcategory, effective_date)"),
    ("idx_budgets_category_id", "budgets(category_id, effective_date)"),
)

_AUDIT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("closed_at", "TEXT"),
    ("leftover_raw", "REAL"),
    ("leftover_capped", "REAL"),
    ("sweep_note", "TEXT"),
)


def create_categories(conn: sqlite3.Connection) -> None:
    """
    CREATE TABLE categories.

    AUTOINCREMENT (not a bare INTEGER PRIMARY KEY) so a deleted row's id is
    never handed out again — these ids are referenced by historical rows, so
    recycling one would silently re-point history at a different name.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS categories (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT    NOT NULL,
            kind         TEXT    NOT NULL CHECK(kind IN ('category', 'subcategory')),
            created_date TEXT,
            UNIQUE(name, kind)
        )
        """
    )


def add_id_columns(conn: sqlite3.Connection) -> None:
    """ADD COLUMN the nullable `*_id` columns to budgets and expenses."""
    for table, column in _ID_COLUMNS:
        add_column(conn, table, column, "INTEGER REFERENCES categories(id)")


def backfill_names(conn: sqlite3.Connection) -> None:
    """Seed `categories` from the distinct, non-blank names already in use."""
    for table, column, kind in _NAME_SOURCES:
        conn.execute(
            f"""
            INSERT OR IGNORE INTO categories (name, kind, created_date)
            SELECT DISTINCT TRIM({column}), ?, date('now')
            FROM   {table}
            WHERE  TRIM(COALESCE({column}, '')) <> ''
            """,
            (kind,),
        )


def backfill_ids(conn: sqlite3.Connection) -> None:
    """Point every non-blank string column at its `categories` row."""
    for table, column, kind in _NAME_SOURCES:
        conn.execute(
            f"""
            UPDATE {table}
            SET    {column}_id = (
                       SELECT c.id
                       FROM   categories c
                       WHERE  c.name = TRIM({table}.{column}) AND c.kind = ?
                   )
            WHERE  TRIM(COALESCE({column}, '')) <> ''
            """,
            (kind,),
        )


def create_indexes(conn: sqlite3.Connection) -> None:
    """Create the indexes the schema previously lacked entirely."""
    for name, target in _INDEXES:
        create_index(conn, name, target)


def enrich_closed_months(conn: sqlite3.Connection) -> None:
    """Add the audit fields a bare `month_id` PK cannot express."""
    for column, ddl in _AUDIT_COLUMNS:
        add_column(conn, "closed_months", column, ddl)


def migrate(conn: sqlite3.Connection) -> None:
    create_categories(conn)
    add_id_columns(conn)
    backfill_names(conn)
    backfill_ids(conn)
    create_indexes(conn)
    enrich_closed_months(conn)
