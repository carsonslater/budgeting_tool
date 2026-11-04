"""
tests/test_sweep_baseline.py

The sweep baseline and opening fund balances over HTTP. Nothing closes before the
baseline; openings are entered at the baseline and fixed once a month closes. The
database is a temp file.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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


@pytest.fixture()
def world(client):
    """Food is monthly; Insurance is annual (reserve 100/month). Income 3000 from Jan 2025."""
    client.post(
        "/api/budgets",
        json={
            "month": "2025-01",
            "category": "Food",
            "limit_amount": 400,
            "frequency": "Monthly",
        },
    )
    client.post(
        "/api/budgets",
        json={
            "month": "2025-01",
            "category": "Insurance",
            "limit_amount": 1200,
            "frequency": "Annually",
        },
    )
    client.put("/api/month-plans/2025-01/income", json={"amount": 3000})
    return client


def line_key(client, category):
    rows = client.get("/api/budgets?month=2025-01").json()
    return next(r["line_key"] for r in rows if r["category"] == category)


def set_baseline(client, month="2025-01"):
    resp = client.put("/api/sweeps/baseline", json={"month": month})
    assert resp.status_code == 200, resp.text


class TestBaseline:
    def test_nothing_can_close_before_a_baseline(self, world):
        proposal = world.get("/api/sweeps/proposal", params={"month": "2025-01"}).json()
        assert proposal["approvable"] is False
        assert "baseline" in proposal["blocked_reason"]
        assert (
            world.post(
                "/api/sweeps/2025-01/approve", json={"allocations": []}
            ).status_code
            == 409
        )

    def test_the_baseline_is_set_once(self, world):
        set_baseline(world, "2025-01")
        assert (
            world.put("/api/sweeps/baseline", json={"month": "2025-02"}).status_code
            == 409
        )
        assert world.get("/api/sweeps/baseline").json()["month"] == "2025-01"

    def test_a_month_before_the_baseline_is_refused(self, world):
        set_baseline(world, "2025-02")
        proposal = world.get("/api/sweeps/proposal", params={"month": "2025-01"}).json()
        assert proposal["approvable"] is False
        assert "before the sweep baseline" in proposal["blocked_reason"]
        assert (
            world.post(
                "/api/sweeps/2025-01/approve", json={"allocations": []}
            ).status_code
            == 409
        )

    def test_a_bad_month_is_a_400(self, world):
        assert (
            world.put("/api/sweeps/baseline", json={"month": "January"}).status_code
            == 400
        )


class TestOpenings:
    def test_an_opening_needs_a_baseline(self, world):
        key = line_key(world, "Insurance")
        assert (
            world.post(
                "/api/sweeps/openings", json={"line_key": key, "amount": 500}
            ).status_code
            == 400
        )

    def test_only_an_irregular_line_takes_an_opening(self, world):
        set_baseline(world)
        food = line_key(world, "Food")
        assert (
            world.post(
                "/api/sweeps/openings", json={"line_key": food, "amount": 500}
            ).status_code
            == 400
        )

    def test_a_new_amount_replaces_the_old_and_zero_clears_it(self, world):
        set_baseline(world)
        key = line_key(world, "Insurance")

        assert (
            world.post(
                "/api/sweeps/openings", json={"line_key": key, "amount": 500}
            ).status_code
            == 201
        )
        assert world.get("/api/sweeps/baseline").json()["openings"] == {key: 500.0}

        world.post("/api/sweeps/openings", json={"line_key": key, "amount": 800})
        assert world.get("/api/sweeps/baseline").json()["openings"] == {key: 800.0}

        world.post("/api/sweeps/openings", json={"line_key": key, "amount": 0})
        assert world.get("/api/sweeps/baseline").json()["openings"] == {}

    def test_openings_are_fixed_once_a_month_closes(self, world):
        set_baseline(world)
        key = line_key(world, "Insurance")
        world.post("/api/sweeps/openings", json={"line_key": key, "amount": 500})

        assert (
            world.post(
                "/api/sweeps/2025-01/approve", json={"allocations": []}
            ).status_code
            == 200
        )
        assert (
            world.post(
                "/api/sweeps/openings", json={"line_key": key, "amount": 900}
            ).status_code
            == 409
        )
        assert world.get("/api/sweeps/baseline").json()["openings"] == {key: 500.0}

    def test_the_opening_funds_the_baseline_month(self, world):
        set_baseline(world)
        key = line_key(world, "Insurance")
        world.post("/api/sweeps/openings", json={"line_key": key, "amount": 500})
        world.post(
            "/api/expenses",
            json={
                "date": "2025-01-10",
                "category": "Insurance",
                "amount": 1200,
                "expense_type": "Monthly",
            },
        )

        proposal = world.get("/api/sweeps/proposal", params={"month": "2025-01"}).json()
        fund = next(f for f in proposal["funds"] if f["line_key"] == key)
        # The opening of 500 plus January's reserve of 100 covers 600 of the 1200 bill.
        assert fund["balance_before"] == 500.0
        assert fund["draw"] == 600.0
        assert fund["shortfall"] == 600.0

    def test_the_opening_funds_the_month_after_the_baseline(self, world):
        set_baseline(world)
        key = line_key(world, "Insurance")
        world.post("/api/sweeps/openings", json={"line_key": key, "amount": 500})
        world.post("/api/sweeps/2025-01/approve", json={"allocations": []})

        proposal = world.get("/api/sweeps/proposal", params={"month": "2025-02"}).json()
        fund = next(f for f in proposal["funds"] if f["line_key"] == key)
        # Opening 500 plus January's reserve of 100 (1200 / 12).
        assert fund["balance_before"] == 600.0
