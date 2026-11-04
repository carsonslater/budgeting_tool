"""
tests/test_turnover.py

The turnover prompt over HTTP: setup asks for a baseline, months close one at a time from
the baseline, and setup is a single write that a bad line cannot half-complete. The
database is a temp file, and "today" is pinned through the ledger function.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import database
import goal_ledger
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
    """Food is monthly; Insurance is annual. Income 3000 from Jan 2025."""
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


def insurance_key(client):
    rows = client.get("/api/budgets?month=2025-01").json()
    return next(r["line_key"] for r in rows if r["category"] == "Insurance")


def status_on(today):
    with database.get_db() as conn:
        return goal_ledger.turnover_status(conn, today=today)


class TestStatus:
    def test_without_a_baseline_the_prompt_is_setup(self, world):
        assert world.get("/api/turnover").json()["state"] == "setup"

    def test_setup_defaults_to_last_month(self, db_path):
        with database.get_db() as conn:
            assert (
                goal_ledger.turnover_status(conn, today="2026-11")["default_month"]
                == "2026-10"
            )

    def test_the_target_is_the_first_unclosed_month_from_the_baseline(self, world):
        world.post("/api/turnover/setup", json={"month": "2025-01", "openings": []})
        status = status_on("2025-03")
        assert status["state"] == "turnover"
        assert status["target"] == "2025-01"
        assert status["confirmed"] is False

    def test_months_are_walked_one_at_a_time(self, world):
        world.post("/api/turnover/setup", json={"month": "2025-01", "openings": []})
        world.post("/api/sweeps/2025-01/approve", json={"allocations": []})
        assert status_on("2025-03")["target"] == "2025-02"

    def test_nothing_is_asked_once_every_ended_month_is_closed(self, world):
        world.post("/api/turnover/setup", json={"month": "2025-02", "openings": []})
        world.post("/api/sweeps/2025-02/approve", json={"allocations": []})
        # Today is March 2025, so February is the last ended month and it is closed.
        assert status_on("2025-03")["state"] == "none"

    def test_a_missing_income_is_flagged(self, client, db_path):
        # No income exists before January 2025, so November 2024 has none.
        client.post("/api/turnover/setup", json={"month": "2024-11", "openings": []})
        status = status_on("2024-12")
        assert status["target"] == "2024-11"
        assert status["income_missing"] is True


class TestSetup:
    def test_setup_writes_the_baseline_and_openings_together(self, world):
        key = insurance_key(world)
        resp = world.post(
            "/api/turnover/setup",
            json={"month": "2025-01", "openings": [{"line_key": key, "amount": 500}]},
        )
        assert resp.status_code == 201
        assert world.get("/api/sweeps/baseline").json() == {
            "month": "2025-01",
            "openings": {key: 500.0},
        }

    def test_a_bad_opening_leaves_no_baseline_behind(self, world):
        resp = world.post(
            "/api/turnover/setup",
            json={
                "month": "2025-01",
                "openings": [{"line_key": "no-such-line", "amount": 500}],
            },
        )
        assert resp.status_code == 400
        assert world.get("/api/sweeps/baseline").json()["month"] is None

    def test_setup_is_refused_once_a_baseline_exists(self, world):
        world.post("/api/turnover/setup", json={"month": "2025-01", "openings": []})
        resp = world.post(
            "/api/turnover/setup", json={"month": "2025-02", "openings": []}
        )
        assert resp.status_code == 409

    def test_a_future_baseline_is_refused(self, world):
        assert (
            world.post(
                "/api/turnover/setup", json={"month": "2099-01", "openings": []}
            ).status_code
            == 400
        )
