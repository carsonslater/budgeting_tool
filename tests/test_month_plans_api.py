"""
tests/test_month_plans_api.py

HTTP behaviour of /api/month-plans: confirmation ("keep as is") and per-month
expected income with apply scopes.  A failed request leaves the database untouched.

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


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "test_budget.db"
    monkeypatch.setattr(database, "_DB_PATH", path)
    database.init_db()
    with database.get_db() as conn:
        run_migrations(conn)
    return path


@pytest.fixture()
def client(db_path):
    return TestClient(app)


def rows(table):
    with database.get_db() as conn:
        return sorted(tuple(r) for r in conn.execute(f"SELECT * FROM {table}"))


def income(client, month):
    return client.get(f"/api/month-plans/{month}").json()["expected_income"]


class TestMonthPlan:
    def test_an_untouched_month(self, client):
        assert client.get("/api/month-plans/2025-03").json() == {
            "month": "2025-03",
            "status": "inherited",
            "confirmed_at": None,
            "expected_income": None,
            "income_set_in": None,
        }

    def test_a_malformed_month_is_a_400(self, client):
        assert client.get("/api/month-plans/2025-13").status_code == 400
        assert client.post("/api/month-plans/March/confirm").status_code == 400
        assert (
            client.put(
                "/api/month-plans/2025-13/income", json={"amount": 1}
            ).status_code
            == 400
        )

    def test_confirm_is_idempotent_and_keeps_the_first_timestamp(self, client):
        first = client.post("/api/month-plans/2025-03/confirm").json()
        second = client.post("/api/month-plans/2025-03/confirm").json()
        assert first["status"] == "confirmed"
        assert second["confirmed_at"] == first["confirmed_at"]
        assert client.get("/api/month-plans/2025-03").json()["status"] == "confirmed"

    def test_confirming_one_month_does_not_confirm_another(self, client):
        client.post("/api/month-plans/2025-03/confirm")
        assert client.get("/api/month-plans/2025-04").json()["status"] == "inherited"

    def test_confirming_writes_nothing_to_the_budget(self, client):
        client.post(
            "/api/budgets",
            json={"month": "2025-01", "category": "Food", "limit_amount": 100},
        )
        lines, amounts = rows("budget_lines"), rows("budget_amounts")
        client.post("/api/month-plans/2025-03/confirm")
        assert rows("budget_lines") == lines
        assert rows("budget_amounts") == amounts


class TestListRange:
    def test_every_month_in_range_is_reported(self, client):
        client.post("/api/month-plans/2025-03/confirm")
        out = client.get("/api/month-plans?start=2025-02&end=2025-04").json()
        assert [(p["month"], p["status"]) for p in out] == [
            ("2025-02", "inherited"),
            ("2025-03", "confirmed"),
            ("2025-04", "inherited"),
        ]

    def test_validation(self, client):
        assert (
            client.get("/api/month-plans?start=2025-05&end=2025-02").status_code == 400
        )
        assert (
            client.get("/api/month-plans?start=2025-13&end=2025-14").status_code == 400
        )
        assert (
            client.get("/api/month-plans?start=2025-01&end=2028-01").status_code == 400
        )
        assert client.get("/api/month-plans?start=2025-01").status_code == 422

    def test_the_longest_allowed_range(self, client):
        out = client.get("/api/month-plans?start=2025-01&end=2027-12").json()
        assert len(out) == 36


class TestIncome:
    def put(self, client, month, amount, **extra):
        return client.put(
            f"/api/month-plans/{month}/income", json={"amount": amount, **extra}
        )

    def test_default_scope_is_until_changed(self, client):
        resp = self.put(client, "2025-03", 5000)
        assert resp.status_code == 200
        assert resp.json()["expected_income"] == 5000
        assert income(client, "2025-02") is None
        assert income(client, "2025-09") == 5000
        assert (
            client.get("/api/month-plans/2025-09").json()["income_set_in"] == "2025-03"
        )

    def test_month_scope(self, client):
        self.put(client, "2025-01", 5000)
        self.put(client, "2025-03", 5500, apply="month")
        assert [income(client, f"2025-0{m}") for m in (2, 3, 4)] == [5000, 5500, 5000]

    def test_through_scope(self, client):
        self.put(client, "2025-01", 5000)
        self.put(client, "2025-03", 5500, apply="through", through="2025-04")
        assert [income(client, f"2025-0{m}") for m in (2, 3, 4, 5)] == [
            5000,
            5500,
            5500,
            5000,
        ]

    def test_income_does_not_confirm_the_month(self, client):
        self.put(client, "2025-03", 5000)
        assert client.get("/api/month-plans/2025-03").json()["status"] == "inherited"

    def test_a_negative_amount_is_rejected_and_writes_nothing(self, client):
        before = rows("month_plans")
        assert self.put(client, "2025-03", -5).status_code == 422
        assert rows("month_plans") == before

    def test_a_bad_scope_is_a_400_and_writes_nothing(self, client):
        before = rows("month_plans")
        assert self.put(client, "2025-03", 5, apply="through").status_code == 400
        assert (
            self.put(
                client, "2025-03", 5, apply="through", through="2025-01"
            ).status_code
            == 400
        )
        assert rows("month_plans") == before
