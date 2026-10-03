"""
tests/test_migrations.py

Tests for backend/migrations/ — the PRAGMA user_version-keyed runner.

Replaces tests/test_schema_migrate_001.py. The standalone script that test
covered was folded into migration version 1, so the suite now drives the runner
end to end instead of individual step functions.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

# Allow imports from backend/ when running tests from project root
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from migrations import LATEST_VERSION, MIGRATIONS, Migration, run_migrations
from migrations.helpers import column_exists, index_exists, table_exists
from migrations.runner import get_user_version


# ---------------------------------------------------------------------------
# Baseline schema — the pre-migration shape
# ---------------------------------------------------------------------------
# Matches the live DB at user_version = 0: no expenses.goal_id, no sweep_rules
# or closed_months, no categories, no *_id columns, and no indexes at all.

BASELINE_DDL = """
CREATE TABLE goals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    target_amount REAL    NOT NULL DEFAULT 0,
    target_month  TEXT    NOT NULL,
    created_date  TEXT    NOT NULL,
    completed     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE expenses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT    NOT NULL,
    description  TEXT    NOT NULL DEFAULT '',
    category     TEXT    NOT NULL DEFAULT '',
    subcategory  TEXT    NOT NULL DEFAULT '',
    amount       REAL    NOT NULL DEFAULT 0,
    payer        TEXT    NOT NULL DEFAULT '',
    expense_type TEXT    NOT NULL DEFAULT 'Monthly'
);

CREATE TABLE budgets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT    NOT NULL,
    subcategory     TEXT    NOT NULL DEFAULT '',
    limit_amount    REAL    NOT NULL DEFAULT 0,
    frequency       TEXT    NOT NULL DEFAULT 'Monthly',
    effective_date  TEXT    NOT NULL,
    conclusion_date TEXT
);

CREATE TABLE income_sources (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT    NOT NULL,
    amount REAL    NOT NULL DEFAULT 0
);

CREATE TABLE goal_budget_links (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_name   TEXT    NOT NULL,
    category    TEXT    NOT NULL,
    subcategory TEXT    NOT NULL DEFAULT '',
    start_date  TEXT    NOT NULL,
    end_date    TEXT
);

CREATE TABLE budget_drafts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    target_month    TEXT    NOT NULL,
    category        TEXT    NOT NULL,
    subcategory     TEXT    NOT NULL DEFAULT '',
    limit_amount    REAL    NOT NULL DEFAULT 0,
    frequency       TEXT    NOT NULL DEFAULT 'Monthly'
);
"""


@pytest.fixture()
def conn():
    """Connection holding the baseline schema at user_version = 0."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(BASELINE_DDL)
    c.commit()
    return c


@pytest.fixture()
def seeded(conn):
    """Baseline schema plus rows that exercise both migrations."""
    conn.executemany(
        "INSERT INTO goals (name, target_amount, target_month, created_date) VALUES (?,?,?,?)",
        [
            ("Vacation Fund", 3000.0, "2025-06-01", "2025-01-01"),
            ("Emergency Fund", 10000.0, "2026-01-01", "2025-01-01"),
        ],
    )
    conn.executemany(
        """INSERT INTO expenses (date, description, category, subcategory, amount, payer, expense_type)
           VALUES (?,?,?,?,?,?,?)""",
        [
            # Goal rows — backfill targets
            (
                "2025-03-01",
                "Transfer to savings",
                "Vacation Fund",
                "",
                500.0,
                "Joint",
                "Goal",
            ),
            (
                "2025-04-01",
                "Emergency top-up",
                "Emergency Fund",
                "",
                200.0,
                "Joint",
                "Goal",
            ),
            # Goal row with no matching goal name — must be preserved
            (
                "2025-05-01",
                "Mystery Goal",
                "Nonexistent Goal",
                "",
                50.0,
                "Joint",
                "Goal",
            ),
            # Regular rows — must be untouched
            ("2025-03-15", "Groceries", "Food", "Groceries", 120.0, "Joint", "Monthly"),
            (
                "2025-06-01",
                "Auto repair",
                "Auto",
                "Maintenance",
                300.0,
                "Carson",
                "Monthly",
            ),
            # Blank subcategory — must stay unbackfilled
            ("2025-06-02", "Misc", "Other", "", 10.0, "Chloe", "Monthly"),
        ],
    )
    conn.executemany(
        """INSERT INTO budgets (category, subcategory, limit_amount, frequency, effective_date, conclusion_date)
           VALUES (?,?,?,?,?,?)""",
        [
            # 'Auto' is a category here ...
            ("Auto", "", 200.0, "Monthly", "2025-01-01", None),
            # ... and a subcategory here. Exercises UNIQUE(name, kind).
            ("Food", "Auto", 400.0, "Monthly", "2025-01-01", None),
            ("Travel", "Flights", 1200.0, "Annually", "2025-01-01", None),
        ],
    )
    conn.commit()
    return conn


@pytest.fixture()
def migrated(seeded):
    """Seeded connection with every migration applied."""
    run_migrations(seeded)
    return seeded


# ---------------------------------------------------------------------------
# The runner
# ---------------------------------------------------------------------------


class TestRunner:
    def test_registry_versions_are_unique_and_ascending(self):
        versions = [m.version for m in MIGRATIONS]
        assert versions == sorted(set(versions))
        assert LATEST_VERSION == versions[-1]

    def test_contract_version_is_two(self):
        assert LATEST_VERSION == 2

    def test_applies_every_version_from_zero(self, conn):
        assert run_migrations(conn) == [1, 2]
        assert get_user_version(conn) == LATEST_VERSION

    def test_second_run_is_a_noop(self, migrated):
        assert run_migrations(migrated) == []
        assert get_user_version(migrated) == LATEST_VERSION

    def test_skips_already_applied_versions(self, conn):
        # Pretend version 1 is done; only 2 should run.
        run_migrations(conn, MIGRATIONS[:1])
        assert get_user_version(conn) == 1
        assert run_migrations(conn) == [2]

    def test_rejects_a_connection_with_pending_work(self, conn):
        conn.execute(
            "INSERT INTO goals (name, target_month, created_date) VALUES ('x','2025-01-01','2025-01-01')"
        )
        assert conn.in_transaction
        with pytest.raises(RuntimeError, match="no pending transaction"):
            run_migrations(conn)

    def test_rejects_non_ascending_registry(self, conn):
        bad = (
            Migration(2, "second", lambda c: None),
            Migration(1, "first", lambda c: None),
        )
        with pytest.raises(ValueError, match="unique and ascending"):
            run_migrations(conn, bad)

    def test_failed_migration_rolls_back_completely(self, conn):
        def boom(c):
            c.execute("CREATE TABLE leftovers (id INTEGER)")
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            run_migrations(conn, (Migration(1, "boom", boom),))

        # Neither the migration's DDL nor the version bump survive.
        assert not table_exists(conn, "leftovers")
        assert get_user_version(conn) == 0


# ---------------------------------------------------------------------------
# Migration 1 — goal tracking
# ---------------------------------------------------------------------------


class TestMigration1:
    def test_goal_id_added_and_nullable(self, migrated):
        assert column_exists(migrated, "expenses", "goal_id")
        migrated.execute(
            "INSERT INTO expenses (date, description, amount) VALUES ('2025-01-01','New',1.0)"
        )
        row = migrated.execute(
            "SELECT goal_id FROM expenses WHERE description = 'New'"
        ).fetchone()
        assert row[0] is None

    def test_sweep_rules_created_with_constraints(self, migrated):
        assert table_exists(migrated, "sweep_rules")
        cols = {r[1] for r in migrated.execute("PRAGMA table_info(sweep_rules);")}
        assert cols == {"id", "goal_id", "priority_rank", "allocation_type", "amount"}

        goal_id = migrated.execute(
            "SELECT id FROM goals ORDER BY id LIMIT 1"
        ).fetchone()[0]
        migrated.execute(
            "INSERT INTO sweep_rules (goal_id, priority_rank, allocation_type, amount) VALUES (?,?,?,?)",
            (goal_id, 1, "percentage", 50.0),
        )
        migrated.execute(
            "INSERT INTO sweep_rules (goal_id, priority_rank, allocation_type, amount) VALUES (?,?,?,?)",
            (goal_id, 2, "fixed", 200.0),
        )
        with pytest.raises(sqlite3.IntegrityError):
            migrated.execute(
                "INSERT INTO sweep_rules (goal_id, priority_rank, allocation_type, amount) VALUES (?,?,?,?)",
                (goal_id, 3, "invalid", 10.0),
            )

    def test_closed_months_created_with_month_id_pk(self, migrated):
        assert table_exists(migrated, "closed_months")
        pk = [
            r[1]
            for r in migrated.execute("PRAGMA table_info(closed_months);")
            if r[5] == 1
        ]
        assert pk == ["month_id"]

    def test_backfill_sets_goal_id(self, migrated):
        vacation_id = migrated.execute(
            "SELECT id FROM goals WHERE name = 'Vacation Fund'"
        ).fetchone()[0]
        row = migrated.execute(
            "SELECT goal_id FROM expenses WHERE description = 'Transfer to savings'"
        ).fetchone()
        assert row[0] == vacation_id

    def test_backfill_preserves_category(self, migrated):
        """The destructive `category = ''` write from the old script is gone."""
        row = migrated.execute(
            "SELECT category FROM expenses WHERE description = 'Transfer to savings'"
        ).fetchone()
        assert row[0] == "Vacation Fund"

    def test_unmatched_goal_row_is_preserved(self, migrated):
        row = migrated.execute(
            "SELECT goal_id, category FROM expenses WHERE description = 'Mystery Goal'"
        ).fetchone()
        assert row[0] is None
        assert row[1] == "Nonexistent Goal"

    def test_regular_expenses_untouched(self, migrated):
        row = migrated.execute(
            "SELECT goal_id, category FROM expenses WHERE description = 'Groceries'"
        ).fetchone()
        assert row[0] is None
        assert row[1] == "Food"

    def test_backfill_is_idempotent(self, seeded):
        from migrations.m0001_goal_tracking import add_goal_id, backfill_goal_expenses

        add_goal_id(seeded)  # the function under test assumes the column exists
        first_matched, first_unmatched = backfill_goal_expenses(seeded)
        assert first_matched == 2
        assert len(first_unmatched) == 1

        # Nothing left to match. The unmatched row is still *reported* rather
        # than silently absorbed or dropped.
        second_matched, second_unmatched = backfill_goal_expenses(seeded)
        assert second_matched == 0
        assert second_unmatched == first_unmatched


# ---------------------------------------------------------------------------
# Migration 2 — category identity (expand only)
# ---------------------------------------------------------------------------

NAME_SOURCES = (
    ("expenses", "category", "category"),
    ("expenses", "subcategory", "subcategory"),
    ("budgets", "category", "category"),
    ("budgets", "subcategory", "subcategory"),
)


class TestMigration2:
    def test_categories_table_shape(self, migrated):
        assert table_exists(migrated, "categories")
        cols = {r[1] for r in migrated.execute("PRAGMA table_info(categories);")}
        assert cols == {"id", "name", "kind", "created_date"}

    def test_same_name_allowed_across_kinds(self, migrated):
        """'Auto' is both a category and a subcategory in the live data."""
        rows = migrated.execute(
            "SELECT kind FROM categories WHERE name = 'Auto' ORDER BY kind"
        ).fetchall()
        assert [r[0] for r in rows] == ["category", "subcategory"]
        assert len({r[0] for r in rows}) == 2

    def test_duplicate_name_and_kind_rejected(self, migrated):
        with pytest.raises(sqlite3.IntegrityError):
            migrated.execute(
                "INSERT INTO categories (name, kind, created_date) VALUES ('Auto','category','2025-01-01')"
            )

    def test_kind_is_constrained(self, migrated):
        with pytest.raises(sqlite3.IntegrityError):
            migrated.execute(
                "INSERT INTO categories (name, kind, created_date) VALUES ('Nope','nonsense','2025-01-01')"
            )

    def test_id_columns_added_and_nullable(self, migrated):
        for table, column in (
            ("budgets", "category_id"),
            ("budgets", "subcategory_id"),
            ("expenses", "category_id"),
            ("expenses", "subcategory_id"),
        ):
            assert column_exists(migrated, table, column)

    def test_names_backfilled_from_every_source(self, migrated):
        expected = set()
        for table, column, kind in NAME_SOURCES:
            for (value,) in migrated.execute(
                f"SELECT DISTINCT TRIM({column}) FROM {table} WHERE TRIM(COALESCE({column},'')) <> ''"
            ):
                expected.add((value, kind))
        actual = {
            (n, k) for n, k in migrated.execute("SELECT name, kind FROM categories")
        }
        assert actual == expected

    def test_blank_values_create_no_category_rows(self, migrated):
        names = {r[0] for r in migrated.execute("SELECT name FROM categories")}
        assert "" not in names

    def test_every_non_blank_value_resolves_to_the_right_kind(self, migrated):
        for table, column, kind in NAME_SOURCES:
            rows = migrated.execute(
                f"SELECT {column} AS v, {column}_id AS cid FROM {table}"
            ).fetchall()
            for value, cid in rows:
                if not (value or "").strip():
                    assert cid is None, f"{table}.{column} blank but id set"
                    continue
                assert cid is not None, f"{table}.{column}='{value}' was not backfilled"
                name, resolved_kind = migrated.execute(
                    "SELECT name, kind FROM categories WHERE id = ?", (cid,)
                ).fetchone()
                assert name == value.strip()
                assert resolved_kind == kind

    def test_indexes_created(self, migrated):
        for name in (
            "idx_expenses_date",
            "idx_expenses_category",
            "idx_expenses_category_id",
            "idx_expenses_goal_id",
            "idx_budgets_category",
            "idx_budgets_category_id",
        ):
            assert index_exists(migrated, name), f"missing index {name}"

    def test_closed_months_audit_columns_added(self, migrated):
        cols = {r[1] for r in migrated.execute("PRAGMA table_info(closed_months);")}
        assert {"closed_at", "leftover_raw", "leftover_capped", "sweep_note"} <= cols

    def test_legacy_string_columns_survive_for_now(self, migrated):
        """Expand-only: reads still depend on the strings until the contract step."""
        assert column_exists(migrated, "expenses", "category")
        assert column_exists(migrated, "budgets", "category")
