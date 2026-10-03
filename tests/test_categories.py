"""
tests/test_categories.py

Phase 2 acceptance criteria & feature tests (plan §5 & §9, "Category agility"):

    - GET /api/categories/active?month=YYYY-MM
    - GET /api/categories
    - POST /api/categories
    - PATCH /api/categories/{id} (surrogate key rename, dual-write)
    - _auto_categorize matching against active budget categories only

The database is built on a temp path, never `data/budget.db`.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Allow imports from backend/ when running tests from project root
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import database
from main import app
from migrations import run_migrations
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


def test_active_categories(client, db_path):
    """Verify GET /api/categories/active returns active budget lines for specified month."""
    with database.get_db() as conn:
        # Active budget
        conn.execute(
            """INSERT INTO budgets (category, subcategory, limit_amount, frequency, effective_date)
               VALUES ('Food', 'Groceries', 500, 'Monthly', '2025-01-01')"""
        )
        # Concluded budget (not active in 2025-03)
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


def test_list_and_create_category_records(client, db_path):
    """Verify GET and POST /api/categories."""
    res_create = client.post("/api/categories", json={"name": "Travel", "kind": "category"})
    assert res_create.status_code == 201
    cat_data = res_create.json()
    assert cat_data["name"] == "Travel"
    assert cat_data["kind"] == "category"

    # Duplicate should fail with 409
    res_dup = client.post("/api/categories", json={"name": "Travel", "kind": "category"})
    assert res_dup.status_code == 409

    # List all
    res_list = client.get("/api/categories?kind=category")
    assert res_list.status_code == 200
    all_cats = res_list.json()
    names = [c["name"] for c in all_cats]
    assert "Travel" in names


def test_patch_category_rename_and_dual_write(client, db_path):
    """Verify PATCH /api/categories/{id} updates surrogate record and dual-writes to budgets/expenses."""
    with database.get_db() as conn:
        cur = conn.execute(
            "INSERT INTO categories (name, kind, created_date) VALUES ('Dining Out', 'category', '2025-01-01')"
        )
        cat_id = cur.lastrowid
        conn.execute(
            """INSERT INTO budgets (category, subcategory, limit_amount, effective_date, category_id)
               VALUES ('Dining Out', 'Restaurants', 300, '2025-01-01', ?)""",
            (cat_id,),
        )
        conn.execute(
            """INSERT INTO expenses (date, description, category, subcategory, amount, payer, expense_type, category_id)
               VALUES ('2025-03-01', 'Dinner', 'Dining Out', 'Restaurants', 50, 'Joint', 'Monthly', ?)""",
            (cat_id,),
        )
        conn.commit()

    # Rename via PATCH /api/categories/{id}
    response = client.patch(f"/api/categories/{cat_id}", json={"name": "Eating Out"})
    assert response.status_code == 200
    assert response.json()["name"] == "Eating Out"

    # Check dual-write to budgets and expenses
    with database.get_db() as conn:
        b_row = conn.execute("SELECT category FROM budgets WHERE category_id = ?", (cat_id,)).fetchone()
        assert b_row["category"] == "Eating Out"

        e_row = conn.execute("SELECT category FROM expenses WHERE category_id = ?", (cat_id,)).fetchone()
        assert e_row["category"] == "Eating Out"


def test_auto_categorize_active_budgets_only(db_path):
    """Verify _auto_categorize matches against active budget categories."""
    with database.get_db() as conn:
        # Active budget for Safeway -> (Food, Groceries)
        conn.execute(
            """INSERT INTO budgets (category, subcategory, limit_amount, effective_date)
               VALUES ('Food', 'Groceries', 500, '2020-01-01')"""
        )
        conn.execute(
            """INSERT INTO expenses (date, description, category, subcategory, amount, payer, expense_type)
               VALUES ('2025-01-01', 'SAFEWAY STORE #123', 'Food', 'Groceries', 75.0, 'Joint', 'Monthly')"""
        )
        # Inactive budget -> (Gym, Fitness)
        conn.execute(
            """INSERT INTO expenses (date, description, category, subcategory, amount, payer, expense_type)
               VALUES ('2025-01-01', 'PLANET FITNESS', 'Gym', 'Fitness', 20.0, 'Joint', 'Monthly')"""
        )
        conn.commit()

        # Safeway should match Food/Groceries
        cat, sub = _auto_categorize("SAFEWAY #123", conn)
        assert cat == "Food"
        assert sub == "Groceries"

        # Planet Fitness has no active budget line, so should return ("", "")
        cat_gym, sub_gym = _auto_categorize("PLANET FITNESS", conn)
        assert cat_gym == ""
        assert sub_gym == ""
