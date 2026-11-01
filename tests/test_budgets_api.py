"""
tests/test_budgets_api.py

HTTP behaviour of /api/budgets on the sparse versioned model:

    - reads never write, and `inherited` is true until the month is confirmed
    - POST / PATCH / DELETE take an apply scope: forward (default), month, through
    - a failed write (400 / 404 / 409) leaves the database untouched — the old
      implementation committed a month table before it noticed the 404

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

TABLES = ("budget_lines", "budget_amounts", "month_plans", "categories")


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


def snapshot():
    with database.get_db() as conn:
        return {
            t: sorted(tuple(r) for r in conn.execute(f"SELECT * FROM {t}"))
            for t in TABLES
        }


def create(
    client,
    month="2025-03",
    category="Food",
    subcategory="Groceries",
    amount=100.0,
    **extra,
):
    resp = client.post(
        "/api/budgets",
        json={
            "month": month,
            "category": category,
            "subcategory": subcategory,
            "limit_amount": amount,
            **extra,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def amount_in(client, key, month):
    rows = client.get(f"/api/budgets?month={month}").json()
    hits = [r for r in rows if r["line_key"] == key]
    return hits[0]["limit_amount"] if hits else None


MONTHS = [f"2025-{m:02d}" for m in range(2, 9)]


# ── Reads ────────────────────────────────────────────────────────────────────


class TestReads:
    def test_an_empty_database_has_no_lines(self, client):
        assert client.get("/api/budgets?month=2025-03").json() == []

    def test_a_line_is_visible_from_its_month_onward(self, client):
        key = create(client, "2025-03")["line_key"]
        assert amount_in(client, key, "2025-02") is None
        assert amount_in(client, key, "2025-03") == 100.0
        assert amount_in(client, key, "2031-01") == 100.0

    def test_reads_never_write(self, client):
        create(client, "2025-03")
        before = snapshot()
        client.get("/api/budgets?month=2025-06")
        client.get("/api/budgets?month=2024-01")
        client.get("/api/budgets/suggested?month=2025-06")
        client.get("/api/categories/active?month=2025-09")
        assert snapshot() == before

    def test_inherited_until_the_month_is_confirmed(self, client):
        create(client, "2025-03")
        [row] = client.get("/api/budgets?month=2025-06").json()
        assert row["inherited"] is True

        assert client.post("/api/month-plans/2025-06/confirm").status_code == 200
        [row] = client.get("/api/budgets?month=2025-06").json()
        assert row["inherited"] is False
        [other] = client.get("/api/budgets?month=2025-07").json()
        assert other["inherited"] is True

    def test_lines_expose_when_their_value_took_effect(self, client):
        key = create(client, "2025-03")["line_key"]
        client.patch(f"/api/budgets/{key}?month=2025-05", json={"limit_amount": 150.0})
        [row] = client.get("/api/budgets?month=2025-06").json()
        assert row["effective_since"] == "2025-05"

    def test_zero_amount_lines_are_hidden(self, client):
        create(client, "2025-03", amount=0.0)
        assert client.get("/api/budgets?month=2025-03").json() == []

    def test_a_malformed_month_is_a_400(self, client):
        assert client.get("/api/budgets?month=2025-13").status_code == 400


# ── POST ─────────────────────────────────────────────────────────────────────


class TestCreate:
    def test_default_scope_is_until_changed(self, client):
        key = create(client, "2025-03")["line_key"]
        assert amount_in(client, key, "2025-09") == 100.0

    def test_response_shape(self, client):
        body = create(client, "2025-03", frequency="Quarterly", amount=300.0)
        assert body["month"] == "2025-03"
        assert body["frequency"] == "Quarterly"
        assert body["limit_amount"] == 300.0
        assert body["category"] == "Food" and body["subcategory"] == "Groceries"
        assert body["category_id"] is not None
        assert body["inherited"] is True

    def test_month_scope(self, client):
        key = create(client, "2025-03", apply="month")["line_key"]
        assert amount_in(client, key, "2025-03") == 100.0
        assert amount_in(client, key, "2025-04") is None

    def test_through_scope(self, client):
        key = create(client, "2025-03", apply="through", through="2025-05")["line_key"]
        assert amount_in(client, key, "2025-05") == 100.0
        assert amount_in(client, key, "2025-06") is None

    def test_through_without_a_month_is_a_400(self, client):
        before = snapshot()
        resp = client.post(
            "/api/budgets",
            json={
                "month": "2025-03",
                "category": "Food",
                "limit_amount": 1,
                "apply": "through",
            },
        )
        assert resp.status_code == 400
        assert snapshot() == before

    def test_through_before_the_month_is_a_400(self, client):
        resp = client.post(
            "/api/budgets",
            json={
                "month": "2025-03",
                "category": "Food",
                "limit_amount": 1,
                "apply": "through",
                "through": "2025-01",
            },
        )
        assert resp.status_code == 400

    def test_an_unknown_apply_mode_is_rejected(self, client):
        resp = client.post(
            "/api/budgets",
            json={
                "month": "2025-03",
                "category": "Food",
                "limit_amount": 1,
                "apply": "sideways",
            },
        )
        assert resp.status_code == 422

    def test_a_duplicate_active_pair_is_a_409_and_writes_nothing(self, client):
        create(client, "2025-03")
        before = snapshot()
        resp = client.post(
            "/api/budgets",
            json={
                "month": "2025-05",
                "category": "Food",
                "subcategory": "Groceries",
                "limit_amount": 5,
            },
        )
        assert resp.status_code == 409
        assert snapshot() == before

    def test_an_invalid_frequency_is_a_400(self, client):
        resp = client.post(
            "/api/budgets",
            json={
                "month": "2025-03",
                "category": "Food",
                "limit_amount": 1,
                "frequency": "Weekly",
            },
        )
        assert resp.status_code == 400

    def test_a_blank_category_is_a_400(self, client):
        before = snapshot()
        resp = client.post(
            "/api/budgets",
            json={"month": "2025-03", "category": "  ", "limit_amount": 1},
        )
        assert resp.status_code == 400
        assert snapshot() == before

    def test_a_malformed_month_is_a_400(self, client):
        resp = client.post(
            "/api/budgets",
            json={"month": "March", "category": "Food", "limit_amount": 1},
        )
        assert resp.status_code == 400

    def test_recreating_an_ended_line_revives_it(self, client):
        key = create(client, "2025-03")["line_key"]
        assert client.delete(f"/api/budgets/{key}?month=2025-05").status_code == 204
        again = create(client, "2025-08", amount=120.0)
        assert again["line_key"] == key
        assert amount_in(client, key, "2025-04") == 100.0
        assert amount_in(client, key, "2025-06") is None
        assert amount_in(client, key, "2025-09") == 120.0


# ── PATCH ────────────────────────────────────────────────────────────────────


class TestUpdate:
    def test_default_scope_is_until_changed(self, client):
        key = create(client, "2025-03")["line_key"]
        resp = client.patch(
            f"/api/budgets/{key}?month=2025-05", json={"limit_amount": 150.0}
        )
        assert resp.status_code == 200
        assert resp.json()["limit_amount"] == 150.0
        assert amount_in(client, key, "2025-04") == 100.0
        assert amount_in(client, key, "2025-05") == 150.0
        assert amount_in(client, key, "2030-01") == 150.0

    def test_month_scope(self, client):
        key = create(client, "2025-03")["line_key"]
        client.patch(
            f"/api/budgets/{key}?month=2025-05&apply=month",
            json={"limit_amount": 150.0},
        )
        got = {m: amount_in(client, key, m) for m in ("2025-04", "2025-05", "2025-06")}
        assert got == {"2025-04": 100.0, "2025-05": 150.0, "2025-06": 100.0}

    def test_through_scope(self, client):
        key = create(client, "2025-03")["line_key"]
        client.patch(
            f"/api/budgets/{key}?month=2025-05&apply=through&through=2025-07",
            json={"limit_amount": 150.0},
        )
        got = {
            m: amount_in(client, key, m)
            for m in ("2025-04", "2025-05", "2025-07", "2025-08")
        }
        assert got == {
            "2025-04": 100.0,
            "2025-05": 150.0,
            "2025-07": 150.0,
            "2025-08": 100.0,
        }

    def test_through_without_a_month_is_a_400_and_writes_nothing(self, client):
        key = create(client, "2025-03")["line_key"]
        before = snapshot()
        resp = client.patch(
            f"/api/budgets/{key}?month=2025-05&apply=through",
            json={"limit_amount": 150.0},
        )
        assert resp.status_code == 400
        assert snapshot() == before

    def test_changing_frequency_and_amount_together(self, client):
        # An annual period opens in January, so the switch is made from January 2026.
        key = create(client, "2025-03")["line_key"]
        resp = client.patch(
            f"/api/budgets/{key}?month=2026-01",
            json={"frequency": "Annually", "limit_amount": 1500.0},
        )
        assert resp.status_code == 200
        assert resp.json()["frequency"] == "Annually"
        assert amount_in(client, key, "2025-12") == pytest.approx(100.0)
        assert amount_in(client, key, "2026-06") == 1500.0

    def test_a_frequency_change_off_a_period_boundary_is_a_400(self, client):
        key = create(client, "2025-03")["line_key"]
        resp = client.patch(
            f"/api/budgets/{key}?month=2025-06",
            json={"frequency": "Annually", "limit_amount": 1500.0},
        )
        assert resp.status_code == 400
        assert "2026-01" in resp.json()["detail"]
        assert amount_in(client, key, "2025-06") == pytest.approx(100.0)

    def test_recategorizing_keeps_the_line_key(self, client):
        key = create(client, "2025-03")["line_key"]
        resp = client.patch(
            f"/api/budgets/{key}?month=2025-04", json={"category": "Eating"}
        )
        assert resp.status_code == 200
        [row] = client.get("/api/budgets?month=2025-03").json()
        assert row["line_key"] == key and row["category"] == "Eating"

    def test_recategorizing_onto_an_occupied_pair_is_a_409(self, client):
        create(client, "2025-03", subcategory="Groceries")
        other = create(client, "2025-03", subcategory="Dining")["line_key"]
        before = snapshot()
        resp = client.patch(
            f"/api/budgets/{other}?month=2025-04", json={"subcategory": "Groceries"}
        )
        assert resp.status_code == 409
        assert snapshot() == before

    def test_an_unknown_line_is_a_404_and_writes_nothing(self, client):
        create(client, "2025-03")
        before = snapshot()
        resp = client.patch(
            "/api/budgets/no-such-key?month=2025-04", json={"limit_amount": 1}
        )
        assert resp.status_code == 404
        assert snapshot() == before

    def test_a_line_not_active_in_the_month_is_a_404_and_writes_nothing(self, client):
        key = create(client, "2025-03")["line_key"]
        before = snapshot()
        resp = client.patch(
            f"/api/budgets/{key}?month=2025-01", json={"limit_amount": 1}
        )
        assert resp.status_code == 404
        assert snapshot() == before

    def test_no_fields_is_a_400(self, client):
        key = create(client, "2025-03")["line_key"]
        assert (
            client.patch(f"/api/budgets/{key}?month=2025-04", json={}).status_code
            == 400
        )

    def test_an_invalid_frequency_is_a_400_and_writes_nothing(self, client):
        key = create(client, "2025-03")["line_key"]
        before = snapshot()
        resp = client.patch(
            f"/api/budgets/{key}?month=2025-04", json={"frequency": "Weekly"}
        )
        assert resp.status_code == 400
        assert snapshot() == before


# ── DELETE ───────────────────────────────────────────────────────────────────


class TestDelete:
    def test_default_scope_ends_the_line(self, client):
        key = create(client, "2025-03")["line_key"]
        assert client.delete(f"/api/budgets/{key}?month=2025-05").status_code == 204
        assert amount_in(client, key, "2025-04") == 100.0
        assert amount_in(client, key, "2025-05") is None
        assert amount_in(client, key, "2030-01") is None

    def test_month_scope(self, client):
        key = create(client, "2025-03")["line_key"]
        client.delete(f"/api/budgets/{key}?month=2025-05&apply=month")
        assert amount_in(client, key, "2025-05") is None
        assert amount_in(client, key, "2025-06") == 100.0

    def test_through_scope(self, client):
        key = create(client, "2025-03")["line_key"]
        client.delete(f"/api/budgets/{key}?month=2025-05&apply=through&through=2025-06")
        assert amount_in(client, key, "2025-06") is None
        assert amount_in(client, key, "2025-07") == 100.0

    def test_an_unknown_line_is_a_404_and_writes_nothing(self, client):
        create(client, "2025-03")
        before = snapshot()
        assert (
            client.delete("/api/budgets/no-such-key?month=2025-04").status_code == 404
        )
        assert snapshot() == before

    def test_an_already_ended_line_is_a_404_and_writes_nothing(self, client):
        key = create(client, "2025-03")["line_key"]
        client.delete(f"/api/budgets/{key}?month=2025-05")
        before = snapshot()
        assert client.delete(f"/api/budgets/{key}?month=2025-08").status_code == 404
        assert snapshot() == before

    def test_a_bad_through_is_a_400_and_writes_nothing(self, client):
        key = create(client, "2025-03")["line_key"]
        before = snapshot()
        resp = client.delete(
            f"/api/budgets/{key}?month=2025-05&apply=through&through=2025-01"
        )
        assert resp.status_code == 400
        assert snapshot() == before
