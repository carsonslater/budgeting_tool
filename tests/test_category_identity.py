"""
tests/test_category_identity.py

The backend identifies a category by id; the name is whatever the `categories`
row says today. Concretely:

    - an expense is filed under `category_id` / `subcategory_id`;
    - once filed, a rename changes what it displays, not where it is attributed;
    - a stale copy of the old name in the denormalized text columns cannot move
      spend to another line or split it in two.

The database is built on a temp path, never `data/budget.db`.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Allow imports from backend/ when running tests from project root
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import budget_store
import database
from main import app
from migrations import run_migrations
from routers.categories import resolve_category_ids


MONTH = "2025-03"


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


def _add_line(category, subcategory, limit, month=MONTH, frequency="Monthly"):
    with database.get_db() as conn:
        budget_store.insert_line(
            conn,
            month,
            category=category,
            subcategory=subcategory,
            limit_amount=limit,
            frequency=frequency,
        )
        conn.commit()


def _add_expense(category, subcategory, amount, day="2025-03-10"):
    """Insert an expense the way every write path does — with ids stamped."""
    with database.get_db() as conn:
        cat_id, sub_id = resolve_category_ids(conn, category, subcategory)
        cur = conn.execute(
            """INSERT INTO expenses
                 (date, description, category, subcategory, amount, payer,
                  expense_type, category_id, subcategory_id)
               VALUES (?, ?, ?, ?, ?, 'Joint', 'Monthly', ?, ?)""",
            (day, f"{category} charge", category, subcategory, amount, cat_id, sub_id),
        )
        conn.commit()
        return cur.lastrowid


def _category_id(name):
    with database.get_db() as conn:
        row = conn.execute(
            "SELECT id FROM categories WHERE name = ? AND kind = 'category'", (name,)
        ).fetchone()
    return row["id"]


def _force_text(expense_id, category, subcategory):
    """Simulate a row whose text copy went stale (the id stays put)."""
    with database.get_db() as conn:
        conn.execute(
            "UPDATE expenses SET category = ?, subcategory = ? WHERE id = ?",
            (category, subcategory, expense_id),
        )
        conn.commit()


def _row(payload, category, subcategory="", partition=None):
    rows = payload if partition is None else payload[partition]
    hits = [
        r
        for r in rows
        if r["category"] == category and r.get("subcategory", "") == subcategory
    ]
    assert len(hits) <= 1, f"duplicate {category}/{subcategory} rows"
    return hits[0] if hits else None


# ── Reads show the name the id points at ─────────────────────────────────────


def test_expense_list_shows_the_current_name(client, db_path):
    expense_id = _add_expense("Food", "Groceries", 75.0)

    rename = client.patch(
        f"/api/categories/{_category_id('Food')}", json={"name": "Eating Out"}
    )
    assert rename.status_code == 200

    [expense] = client.get("/api/expenses").json()
    assert expense["id"] == expense_id
    assert expense["category"] == "Eating Out"
    assert expense["category_id"] == _category_id("Eating Out")


def test_expense_list_resolves_even_when_the_text_is_stale(client, db_path):
    expense_id = _add_expense("Food", "Groceries", 75.0)
    client.patch(f"/api/categories/{_category_id('Food')}", json={"name": "Eating Out"})
    _force_text(expense_id, "Food", "Groceries")

    [expense] = client.get("/api/expenses").json()
    assert expense["category"] == "Eating Out"


def test_category_and_subcategory_lists_follow_renames(client, db_path):
    _add_expense("Food", "Groceries", 10.0)
    client.patch(f"/api/categories/{_category_id('Food')}", json={"name": "Eating Out"})

    assert client.get("/api/expenses/categories").json() == ["Eating Out"]
    assert client.get("/api/expenses/subcategories").json() == ["Groceries"]


# ── Attribution follows the id, not the text ─────────────────────────────────


def test_summary_attributes_by_id_when_the_text_is_stale(client, db_path):
    _add_line("Food", "Groceries", 500.0)
    expense_id = _add_expense("Food", "Groceries", 100.0)

    client.patch(f"/api/categories/{_category_id('Food')}", json={"name": "Eating Out"})
    _force_text(expense_id, "Food", "Groceries")

    row = _row(
        client.get(f"/api/reporting/summary?month={MONTH}").json(),
        "Eating Out",
        "Groceries",
        "monthly",
    )
    assert row is not None
    assert row["spent"] == 100.0

    assert (
        _row(
            client.get(f"/api/reporting/summary?month={MONTH}").json(),
            "Food",
            "Groceries",
            "monthly",
        )
        is None
    )


def test_stale_text_cannot_move_spend_to_another_line(client, db_path):
    """
    The text says "Travel", the id says Food. The spend belongs to Food — the
    old name-matching code would have booked it against Travel.
    """
    _add_line("Food", "Groceries", 500.0)
    _add_line("Travel", "Flights", 500.0)
    expense_id = _add_expense("Food", "Groceries", 120.0)
    _force_text(expense_id, "Travel", "Flights")

    payload = client.get(f"/api/reporting/summary?month={MONTH}").json()

    assert _row(payload, "Food", "Groceries", "monthly")["spent"] == 120.0
    assert _row(payload, "Travel", "Flights", "monthly")["spent"] == 0.0


def test_suggested_attributes_by_id(client, db_path):
    _add_line("Food", "Groceries", 500.0, month="2025-05")
    expense_id = _add_expense("Food", "Groceries", 700.0, day="2025-05-12")
    client.patch(f"/api/categories/{_category_id('Food')}", json={"name": "Eating Out"})
    _force_text(expense_id, "Food", "Groceries")

    suggestions = client.get("/api/budgets/suggested?month=2025-06").json()
    [suggestion] = suggestions

    assert suggestion["category"] == "Eating Out"
    assert suggestion["recent_month_spent"] == 700.0


def test_spending_by_category_groups_by_id(client, db_path):
    first = _add_expense("Food", "Groceries", 30.0)
    _add_expense("Food", "Groceries", 20.0, day="2025-03-11")

    client.patch(f"/api/categories/{_category_id('Food')}", json={"name": "Eating Out"})
    _force_text(first, "Food", "Groceries")

    rows = client.get("/api/reporting/categories").json()

    assert len(rows) == 1, f"rename split the group: {rows}"
    assert rows[0]["category"] == "Eating Out"
    assert rows[0]["total"] == 50.0
    assert rows[0]["transaction_count"] == 2
