"""
tests/test_sweeps_api.py

End-to-end month-end sweep over HTTP: rules, proposal, approve, reopen, withdrawals,
goal balances, and the delete guard. The database is a temp file.
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


def ledger_rows():
    with database.get_db() as conn:
        return conn.execute("SELECT COUNT(*) FROM goal_allocations").fetchone()[0]


def make_goal(client, name, target):
    return client.post(
        "/api/goals",
        json={
            "name": name,
            "target_amount": target,
            "target_month": "2030-12-01",
            "created_date": "2025-01-01",
        },
    ).json()["id"]


@pytest.fixture()
def world(client):
    """Food is a monthly line; Insurance is an annual line (reserve 100/month).

    Jan 2025: income 3000, food 350, no insurance bill -> leftover 2550.
    Feb 2025: income 3000 (inherited), food 0, insurance bill 1200.
    """
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
    client.put("/api/sweeps/baseline", json={"month": "2025-01"})
    client.post(
        "/api/expenses",
        json={
            "date": "2025-01-10",
            "category": "Food",
            "amount": 350,
            "expense_type": "Monthly",
        },
    )
    client.post(
        "/api/expenses",
        json={
            "date": "2025-02-10",
            "category": "Insurance",
            "amount": 1200,
            "expense_type": "Monthly",
        },
    )
    vacation = make_goal(client, "Vacation", 1000)
    car = make_goal(client, "Car", 2000)
    client.post(
        "/api/sweeps/rules",
        json={
            "goal_id": vacation,
            "priority_rank": 1,
            "allocation_type": "fixed",
            "amount": 300,
        },
    )
    client.post(
        "/api/sweeps/rules",
        json={
            "goal_id": car,
            "priority_rank": 2,
            "allocation_type": "percentage",
            "amount": 50,
        },
    )
    return {"vacation": vacation, "car": car}


def approve_from_proposal(client, month):
    p = client.get("/api/sweeps/proposal", params={"month": month}).json()
    body = {
        "allocations": [
            {"goal_id": g["goal_id"], "amount": g["amount"]} for g in p["goals"]
        ]
    }
    return client.post(f"/api/sweeps/{month}/approve", json=body)


def goal_balance(client, goal_id):
    return next(
        g["balance"] for g in client.get("/api/goals").json() if g["id"] == goal_id
    )


class TestRules:
    def test_percentage_rules_cannot_exceed_one_hundred(self, client, world):
        goal = make_goal(client, "Extra", 500)
        r = client.post(
            "/api/sweeps/rules",
            json={
                "goal_id": goal,
                "priority_rank": 9,
                "allocation_type": "percentage",
                "amount": 60,
            },
        )
        assert r.status_code == 400
        assert "at most 100" in r.json()["detail"]

    def test_priority_ranks_are_unique(self, client, world):
        goal = make_goal(client, "Dup", 500)
        r = client.post(
            "/api/sweeps/rules",
            json={
                "goal_id": goal,
                "priority_rank": 1,
                "allocation_type": "fixed",
                "amount": 10,
            },
        )
        assert r.status_code == 400

    def test_an_unknown_goal_is_a_404(self, client, world):
        r = client.post(
            "/api/sweeps/rules",
            json={
                "goal_id": 99999,
                "priority_rank": 5,
                "allocation_type": "fixed",
                "amount": 10,
            },
        )
        assert r.status_code == 404

    def test_a_rule_can_be_updated_and_deleted(self, client, world):
        rule_id = client.get("/api/sweeps/rules").json()[0]["id"]
        r = client.patch(f"/api/sweeps/rules/{rule_id}", json={"amount": 350})
        assert r.json()["amount"] == 350
        assert client.delete(f"/api/sweeps/rules/{rule_id}").status_code == 204
        assert (
            client.patch(f"/api/sweeps/rules/{rule_id}", json={"amount": 1}).status_code
            == 404
        )


class TestProposal:
    def test_leftover_and_split_for_a_month(self, client, world):
        p = client.get("/api/sweeps/proposal", params={"month": "2025-01"}).json()
        assert p["income"] == 3000
        assert p["regular_spend"] == 350
        assert p["reserve_total"] == 100
        assert p["leftover"] == 2550
        amounts = {g["name"]: g["amount"] for g in p["goals"]}
        assert amounts == {"Car": 1125.0, "Vacation": 300.0}
        assert p["unallocated"] == 1125
        assert p["approvable"] is True

    def test_the_proposal_writes_nothing(self, client, world):
        before = ledger_rows()
        client.get("/api/sweeps/proposal", params={"month": "2025-01"})
        assert ledger_rows() == before

    def test_a_month_without_income_cannot_be_proposed(self, client, world):
        r = client.get("/api/sweeps/proposal", params={"month": "2024-06"})
        assert r.status_code == 400
        assert "expected income" in r.json()["detail"]

    def test_completed_goals_receive_nothing(self, client, world):
        client.patch(f"/api/goals/{world['car']}", json={"completed": 1})
        p = client.get("/api/sweeps/proposal", params={"month": "2025-01"}).json()
        assert [g["name"] for g in p["goals"]] == ["Vacation"]
        assert p["unallocated"] == 2250


class TestApprove:
    def test_a_stale_amount_is_rejected_and_writes_nothing(self, client, world):
        before = ledger_rows()
        r = client.post(
            "/api/sweeps/2025-01/approve",
            json={"allocations": [{"goal_id": world["vacation"], "amount": 999}]},
        )
        assert r.status_code == 409
        assert ledger_rows() == before

    def test_approving_writes_the_split_and_closes_the_month(self, client, world):
        r = client.post(
            "/api/sweeps/2025-01/approve",
            json={
                "allocations": [
                    {"goal_id": world["vacation"], "amount": 300},
                    {"goal_id": world["car"], "amount": 1125},
                ]
            },
        )
        assert r.status_code == 200
        assert goal_balance(client, world["vacation"]) == 300
        assert goal_balance(client, world["car"]) == 1125
        closed = client.get("/api/sweeps/closed").json()
        assert closed[0]["month_id"] == "2025-01"
        assert closed[0]["swept_total"] == 1425

    def test_approving_twice_is_refused(self, client, world):
        body = {
            "allocations": [
                {"goal_id": world["vacation"], "amount": 300},
                {"goal_id": world["car"], "amount": 1125},
            ]
        }
        client.post("/api/sweeps/2025-01/approve", json=body)
        assert client.post("/api/sweeps/2025-01/approve", json=body).status_code == 409

    def test_the_current_month_cannot_be_swept(self, client, world):
        import datetime

        this_month = datetime.date.today().strftime("%Y-%m")
        client.put(f"/api/month-plans/{this_month}/income", json={"amount": 3000})
        r = client.post(f"/api/sweeps/{this_month}/approve", json={"allocations": []})
        assert r.status_code == 409
        assert "has not ended" in r.json()["detail"]

    def test_months_must_close_in_sequence(self, client, world):
        client.post(
            "/api/sweeps/2025-01/approve",
            json={
                "allocations": [
                    {"goal_id": world["vacation"], "amount": 300},
                    {"goal_id": world["car"], "amount": 1125},
                ]
            },
        )
        client.put("/api/month-plans/2025-03/income", json={"amount": 3000})
        r = client.post("/api/sweeps/2025-03/approve", json={"allocations": []})
        assert r.status_code == 409
        assert "2025-02 must be closed" in r.json()["detail"]


class TestFundsAcrossMonths:
    def approve_jan(self, client, world):
        client.post(
            "/api/sweeps/2025-01/approve",
            json={
                "allocations": [
                    {"goal_id": world["vacation"], "amount": 300},
                    {"goal_id": world["car"], "amount": 1125},
                ]
            },
        )

    def test_a_bill_is_drawn_from_the_fund_and_the_rest_is_a_shortfall(
        self, client, world
    ):
        self.approve_jan(client, world)
        p = client.get("/api/sweeps/proposal", params={"month": "2025-02"}).json()
        fund = p["funds"][0]
        assert fund["balance_before"] == 100
        assert fund["draw"] == 200
        assert fund["shortfall"] == 1000
        assert p["shortfall"] == 1000
        assert p["leftover"] == 1900

    def test_reopening_restores_the_balances_exactly(self, client, world):
        self.approve_jan(client, world)
        assert client.post("/api/sweeps/2025-01/reopen").status_code == 200
        assert goal_balance(client, world["vacation"]) == 0
        assert goal_balance(client, world["car"]) == 0
        assert client.get("/api/sweeps/closed").json() == []

    def test_a_month_cannot_be_reopened_under_a_later_closed_month(self, client, world):
        self.approve_jan(client, world)
        client.put("/api/month-plans/2025-02/income", json={"amount": 3000})
        approve_from_proposal(client, "2025-02")
        r = client.post("/api/sweeps/2025-01/reopen")
        assert r.status_code == 409
        assert "later month" in r.json()["detail"]

    def test_reopen_then_reapprove_gives_the_same_split(self, client, world):
        self.approve_jan(client, world)
        client.post("/api/sweeps/2025-01/reopen")
        p = client.get("/api/sweeps/proposal", params={"month": "2025-01"}).json()
        body = {
            "allocations": [
                {"goal_id": g["goal_id"], "amount": g["amount"]} for g in p["goals"]
            ]
        }
        assert client.post("/api/sweeps/2025-01/approve", json=body).status_code == 200


class TestGoals:
    def test_a_withdrawal_reduces_the_balance_and_cannot_overdraw(self, client, world):
        client.post(
            "/api/sweeps/2025-01/approve",
            json={
                "allocations": [
                    {"goal_id": world["vacation"], "amount": 300},
                    {"goal_id": world["car"], "amount": 1125},
                ]
            },
        )
        assert (
            client.post(
                f"/api/goals/{world['vacation']}/withdrawals", json={"amount": 500}
            ).status_code
            == 400
        )
        r = client.post(
            f"/api/goals/{world['vacation']}/withdrawals", json={"amount": 100}
        )
        assert r.status_code == 201
        assert goal_balance(client, world["vacation"]) == 200

    def test_a_goal_with_ledger_history_cannot_be_deleted(self, client, world):
        client.post(
            "/api/sweeps/2025-01/approve",
            json={
                "allocations": [
                    {"goal_id": world["vacation"], "amount": 300},
                    {"goal_id": world["car"], "amount": 1125},
                ]
            },
        )
        r = client.delete(f"/api/goals/{world['vacation']}")
        assert r.status_code == 409

    def test_a_goal_without_history_can_still_be_deleted(self, client, world):
        spare = make_goal(client, "Spare", 100)
        assert client.delete(f"/api/goals/{spare}").status_code == 204
