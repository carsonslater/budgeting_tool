"""
tests/test_categories.py

Phase 2 acceptance criteria & feature tests (plan §5 & §9, "Category agility"):

    - GET /api/categories/active?month=YYYY-MM
    - GET /api/categories
    - PATCH /api/categories/{id} (surrogate key rename, defensive dual-write)
    - resolve_category_ids: every write path (create, update, import) carries *_id
    - Rename does NOT clobber a user's manual category edit
    - Import confirm carries surrogate IDs
    - _auto_categorize matches against expense descriptions only (no bare budget names)

The database is built on a temp path, never `data/budget.db`.
"""

import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Allow imports from backend/ when running tests from project root
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import database
from main import app
from migrations import run_migrations
from routers.categories import resolve_category_ids
from routers.import_csv import _auto_categorize


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    """A freshly initialized, fully migrated database on a temp path."""
    path = tmp_path / "test_budget.db"
    monkeypatch.setattr(database, "_DB_PATH", path)
    database.init_db()
    with database.get_db() as conn:
        run_migrations(conn)
    return path


@pytest.fixture()
def client(db_path):
    return TestClient(app)


# ── Active categories endpoint ────────────────────────────────────────────────


def test_active_categories(client, db_path):
    """GET /api/categories/active only returns budget lines active in the target month."""
    with database.get_db() as conn:
        conn.execute(
            """INSERT INTO budgets (category, subcategory, limit_amount, frequency, effective_date)
               VALUES ('Food', 'Groceries', 500, 'Monthly', '2025-01-01')"""
        )
        # Concluded before 2025-03 — must not appear
        conn.execute(
            """INSERT INTO budgets (category, subcategory, limit_amount, frequency, effective_date, conclusion_date)
               VALUES ('OldCategory', 'Sub', 200, 'Monthly', '2024-01-01', '2024-12-31')"""
        )
        conn.commit()

    response = client.get("/api/categories/active?month=2025-03")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["category"] == "Food"
    assert data[0]["subcategory"] == "Groceries"


# ── resolve_category_ids helper ───────────────────────────────────────────────


def test_resolve_category_ids_creates_and_returns(db_path):
    """resolve_category_ids inserts missing rows and returns consistent ids."""
    with database.get_db() as conn:
        cat_id, sub_id = resolve_category_ids(conn, "Food", "Groceries")
        conn.commit()

    assert cat_id is not None
    assert sub_id is not None

    # Same call should return the same ids (idempotent — INSERT OR IGNORE)
    with database.get_db() as conn:
        cat_id2, sub_id2 = resolve_category_ids(conn, "Food", "Groceries")
        conn.commit()

    assert cat_id2 == cat_id
    assert sub_id2 == sub_id


def test_resolve_category_ids_empty_strings(db_path):
    """Empty category/subcategory strings resolve to None, never create a row."""
    with database.get_db() as conn:
        cat_id, sub_id = resolve_category_ids(conn, "", "")
        conn.commit()

    assert cat_id is None
    assert sub_id is None

    with database.get_db() as conn:
        blank_rows = conn.execute("SELECT * FROM categories WHERE name = ''").fetchall()
    assert blank_rows == []


# ── Expense create / update carry surrogate ids ───────────────────────────────


def test_create_expense_carries_category_id(client, db_path):
    """POST /api/expenses writes category_id and subcategory_id on new rows."""
    resp = client.post(
        "/api/expenses",
        json={
            "date": "2025-03-01",
            "description": "Test purchase",
            "category": "Food",
            "subcategory": "Groceries",
            "amount": 50.0,
            "payer": "Joint",
            "expense_type": "Monthly",
        },
    )
    assert resp.status_code == 201

    with database.get_db() as conn:
        row = conn.execute(
            "SELECT category_id, subcategory_id FROM expenses WHERE id = ?",
            (resp.json()["id"],),
        ).fetchone()

    assert row["category_id"] is not None
    assert row["subcategory_id"] is not None


def test_update_expense_refreshes_category_id(client, db_path):
    """PATCH /api/expenses/{id} updates *_id when category changes."""
    create_resp = client.post(
        "/api/expenses",
        json={
            "date": "2025-03-01",
            "description": "Store visit",
            "category": "Food",
            "subcategory": "Groceries",
            "amount": 30.0,
            "payer": "Joint",
            "expense_type": "Monthly",
        },
    )
    expense_id = create_resp.json()["id"]

    patch_resp = client.patch(
        f"/api/expenses/{expense_id}",
        json={
            "category": "Dining",
            "subcategory": "Restaurants",
        },
    )
    assert patch_resp.status_code == 200

    with database.get_db() as conn:
        row = conn.execute(
            "SELECT category, subcategory, category_id, subcategory_id FROM expenses WHERE id = ?",
            (expense_id,),
        ).fetchone()

    assert row["category"] == "Dining"
    assert row["subcategory"] == "Restaurants"
    assert row["category_id"] is not None
    assert row["subcategory_id"] is not None

    # Verify the new ids point at the correct categories rows
    with database.get_db() as conn:
        cat_row = conn.execute(
            "SELECT name FROM categories WHERE id = ?", (row["category_id"],)
        ).fetchone()
        sub_row = conn.execute(
            "SELECT name FROM categories WHERE id = ?", (row["subcategory_id"],)
        ).fetchone()
    assert cat_row["name"] == "Dining"
    assert sub_row["name"] == "Restaurants"


# ── Rename is safe and does NOT clobber user edits ───────────────────────────


def test_rename_by_id_after_create_preserves_attribution(client, db_path):
    """
    Regression: create an expense via POST (id set), rename its category by id,
    assert the expense string is updated.  This traverses the create path where
    the original bug lived.
    """
    create_resp = client.post(
        "/api/expenses",
        json={
            "date": "2025-03-01",
            "description": "Safeway run",
            "category": "Food",
            "subcategory": "Groceries",
            "amount": 75.0,
            "payer": "Joint",
            "expense_type": "Monthly",
        },
    )
    assert create_resp.status_code == 201
    expense_id = create_resp.json()["id"]

    # Retrieve the category_id that was assigned
    with database.get_db() as conn:
        row = conn.execute(
            "SELECT category_id FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
    cat_id = row["category_id"]
    assert cat_id is not None

    # Rename via PATCH /api/categories/{id}
    rename_resp = client.patch(f"/api/categories/{cat_id}", json={"name": "Eating Out"})
    assert rename_resp.status_code == 200

    # The expense string should have been updated
    with database.get_db() as conn:
        after = conn.execute(
            "SELECT category FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
    assert after["category"] == "Eating Out"


def test_rename_does_not_clobber_user_edit(client, db_path):
    """
    The clobber scenario: user manually recategorises an expense to a *different*
    category (string moves away from the original; category_id still points at
    the old row).  Renaming the old category must NOT overwrite the user's string.
    """
    # Create expense with "Food"
    create_resp = client.post(
        "/api/expenses",
        json={
            "date": "2025-04-01",
            "description": "Mystery purchase",
            "category": "Food",
            "subcategory": "Groceries",
            "amount": 25.0,
            "payer": "Joint",
            "expense_type": "Monthly",
        },
    )
    expense_id = create_resp.json()["id"]

    with database.get_db() as conn:
        original_cat_id = conn.execute(
            "SELECT category_id FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()["category_id"]

    # User manually edits the expense to "Dining" / "Restaurants" —
    # the UI sends a PATCH that resolves new ids; original_cat_id no longer
    # matches the string.  Simulate this directly in the DB to isolate the
    # rename guard: set category to something different but leave category_id
    # unchanged, as would happen if a client sent only the string columns.
    with database.get_db() as conn:
        conn.execute(
            "UPDATE expenses SET category = 'Dining', subcategory = 'Restaurants' WHERE id = ?",
            (expense_id,),
        )
        conn.commit()

    # Now rename the original category_id ("Food") to "Eating Out"
    rename_resp = client.patch(
        f"/api/categories/{original_cat_id}", json={"name": "Eating Out"}
    )
    assert rename_resp.status_code == 200

    # The user's string ("Dining") must be untouched
    with database.get_db() as conn:
        after = conn.execute(
            "SELECT category FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
    assert after["category"] == "Dining", (
        f"Rename clobbered user edit: expected 'Dining', got '{after['category']}'"
    )


# ── Import confirm carries surrogate ids ─────────────────────────────────────


def test_import_confirm_carries_category_id(client, db_path):
    """POST /api/import/confirm sets category_id and subcategory_id on imported rows."""
    payload = {
        "rows": [
            {
                "date": "2025-03-15",
                "description": "SAFEWAY #100",
                "amount": 60.0,
                "category": "Food",
                "subcategory": "Groceries",
                "payer": "Joint",
                "expense_type": "Monthly",
                "is_duplicate": False,
                "original_index": 0,
            }
        ]
    }
    resp = client.post("/api/import/confirm", json=payload)
    assert resp.status_code == 200
    assert resp.json()["imported"] == 1

    with database.get_db() as conn:
        row = conn.execute(
            "SELECT category_id, subcategory_id FROM expenses ORDER BY id DESC LIMIT 1"
        ).fetchone()

    assert row["category_id"] is not None, "Import did not set category_id"
    assert row["subcategory_id"] is not None, "Import did not set subcategory_id"


# ── _auto_categorize uses expense descriptions only ──────────────────────────


def test_auto_categorize_expense_descriptions_only(db_path):
    """_auto_categorize returns a match when an expense description exists for an active budget line."""
    with database.get_db() as conn:
        conn.execute(
            """INSERT INTO budgets (category, subcategory, limit_amount, effective_date)
               VALUES ('Food', 'Groceries', 500, '2020-01-01')"""
        )
        conn.execute(
            """INSERT INTO expenses (date, description, category, subcategory, amount, payer, expense_type)
               VALUES ('2025-01-01', 'SAFEWAY STORE #123', 'Food', 'Groceries', 75.0, 'Joint', 'Monthly')"""
        )
        conn.commit()

        cat, sub = _auto_categorize("SAFEWAY #456", conn)

    assert cat == "Food"
    assert sub == "Groceries"


def test_auto_categorize_bare_budget_name_not_a_candidate(db_path):
    """
    Bare budget category names ('Food') must NOT be candidates.
    Without expense description evidence, _auto_categorize should return ('', '').
    """
    with database.get_db() as conn:
        conn.execute(
            """INSERT INTO budgets (category, subcategory, limit_amount, effective_date)
               VALUES ('Food', 'Groceries', 500, '2020-01-01')"""
        )
        # No expenses — only the budget name exists
        conn.commit()

        cat, sub = _auto_categorize("Food purchase", conn)

    # Without expense descriptions to match against, should return ("", "")
    assert cat == ""
    assert sub == ""


def test_auto_categorize_inactive_budget_excluded(db_path):
    """Expenses whose category has no active budget line are not returned."""
    with database.get_db() as conn:
        # No budgets at all — Gym/Fitness is orphaned
        conn.execute(
            """INSERT INTO expenses (date, description, category, subcategory, amount, payer, expense_type)
               VALUES ('2025-01-01', 'PLANET FITNESS', 'Gym', 'Fitness', 20.0, 'Joint', 'Monthly')"""
        )
        conn.commit()

        cat, sub = _auto_categorize("PLANET FITNESS", conn)

    assert cat == ""
    assert sub == ""


# ── list_categories endpoint ──────────────────────────────────────────────────


def test_list_categories(client, db_path):
    """GET /api/categories returns records backfilled by migration or created via write paths."""
    # Creating an expense through the API triggers resolve_category_ids
    client.post(
        "/api/expenses",
        json={
            "date": "2025-03-01",
            "description": "Groceries",
            "category": "Food",
            "subcategory": "Groceries",
            "amount": 50.0,
            "payer": "Joint",
            "expense_type": "Monthly",
        },
    )

    resp = client.get("/api/categories?kind=category")
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()]
    assert "Food" in names


# ── Goal-created budget lines carry surrogate ids ────────────────────────────


def test_goal_create_budget_line_carries_category_ids(client, db_path):
    """
    POST /api/goals with a category mints the `categories` row and stamps
    `category_id` / `subcategory_id` on the synthetic budget line, so a
    rename-by-id reaches it.
    """
    resp = client.post(
        "/api/goals",
        json={
            "name": "Vacation",
            "target_amount": 1200.0,
            "target_month": "2026-06-01",
            "created_date": "2026-01-15",
            "category": "Travel",
            "subcategory": "Flights",
        },
    )
    assert resp.status_code == 201

    with database.get_db() as conn:
        b = conn.execute(
            "SELECT category, category_id, subcategory_id FROM budgets"
        ).fetchone()
        cat_row = conn.execute(
            "SELECT id FROM categories WHERE name = 'Travel' AND kind = 'category'"
        ).fetchone()

    assert b["category"] == "Travel"
    assert cat_row is not None, "goal creation did not mint the 'Travel' category row"
    assert b["category_id"] == cat_row["id"]
    assert b["subcategory_id"] is not None

    # Renaming the category by id must reach the goal-created budget line
    rename = client.patch(
        f"/api/categories/{b['category_id']}", json={"name": "Travel & Leisure"}
    )
    assert rename.status_code == 200
    with database.get_db() as conn:
        after = conn.execute("SELECT category FROM budgets").fetchone()
    assert after["category"] == "Travel & Leisure"


def test_goal_link_budget_line_carries_category_ids(client, db_path):
    """POST /api/goals/links stamps surrogate ids on its budget line."""
    client.post(
        "/api/goals",
        json={
            "name": "Car",
            "target_amount": 6000.0,
            "target_month": "2026-12-01",
            "created_date": "2026-01-01",
        },
    )
    resp = client.post(
        "/api/goals/links",
        json={
            "goal_name": "Car",
            "category": "Auto",
            "subcategory": "Repairs",
            "start_date": "2026-02-01",
        },
    )
    assert resp.status_code == 201

    with database.get_db() as conn:
        b = conn.execute(
            "SELECT category_id, subcategory_id FROM budgets WHERE category = 'Auto'"
        ).fetchone()
    assert b is not None
    assert b["category_id"] is not None
    assert b["subcategory_id"] is not None


# ── Draft-commit budget lines carry surrogate ids ────────────────────────────


def test_draft_commit_budget_lines_carry_category_ids(client, db_path):
    """Committing a draft month stamps surrogate ids on the budgets it creates."""
    with database.get_db() as conn:
        conn.execute(
            """INSERT INTO budgets (category, subcategory, limit_amount, frequency, effective_date)
               VALUES ('Food', 'Groceries', 500, 'Monthly', '2020-01-01')"""
        )
        conn.commit()

    # One draft that changes an existing line, one that adds a brand-new line.
    client.post(
        "/api/budget-drafts",
        json={
            "target_month": "2026-07-01",
            "category": "Food",
            "subcategory": "Groceries",
            "limit_amount": 650.0,
            "frequency": "Monthly",
        },
    )
    client.post(
        "/api/budget-drafts",
        json={
            "target_month": "2026-07-01",
            "category": "Pets",
            "subcategory": "Vet",
            "limit_amount": 100.0,
            "frequency": "Monthly",
        },
    )

    resp = client.post("/api/budget-drafts/2026-07-01/commit")
    assert resp.status_code == 200

    with database.get_db() as conn:
        new_rows = conn.execute(
            """SELECT category, category_id, subcategory_id FROM budgets
               WHERE effective_date = '2026-07-01'"""
        ).fetchall()

    assert {r["category"] for r in new_rows} == {"Food", "Pets"}
    assert all(r["category_id"] is not None for r in new_rows)
    assert all(r["subcategory_id"] is not None for r in new_rows)


# ── Legacy CSV importer stamps surrogate ids ─────────────────────────────────


def test_migrate_script_stamps_category_ids(tmp_path, monkeypatch):
    """migrate.py must resolve surrogate keys for the rows it imports."""
    import migrate

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "budget.db"

    monkeypatch.setattr(migrate, "_DATA_DIR", data_dir)
    monkeypatch.setattr(migrate, "_DB_PATH", db_file)
    monkeypatch.setattr(database, "_DB_PATH", db_file)

    (data_dir / "expenses.csv").write_text(
        "Date,Description,Category,Subcategory,Amount,Payer,ExpenseType\n"
        "2025-01-01,Store,Food,Groceries,10.0,Joint,Monthly\n"
    )
    (data_dir / "category_budget.csv").write_text(
        "Category,Subcategory,Limit,Frequency,EffectiveDate,ConclusionDate\n"
        "Food,Groceries,500,Monthly,2025-01-01,\n"
    )

    migrate.main()

    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    try:
        e = conn.execute("SELECT category_id, subcategory_id FROM expenses").fetchone()
        b = conn.execute("SELECT category_id, subcategory_id FROM budgets").fetchone()
    finally:
        conn.close()

    assert e["category_id"] is not None and e["subcategory_id"] is not None
    assert b["category_id"] is not None and b["subcategory_id"] is not None
