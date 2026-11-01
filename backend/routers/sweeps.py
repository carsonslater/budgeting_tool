"""
routers/sweeps.py — month-end sweep: rules, proposal, approve, reopen.

Routes:
    GET    /api/sweeps/rules                 list sweep rules by priority
    POST   /api/sweeps/rules                 create
    PATCH  /api/sweeps/rules/{id}            update
    DELETE /api/sweeps/rules/{id}            delete
    GET    /api/sweeps/closed                closed months, newest first
    GET    /api/sweeps/proposal?month=       read-only leftover and split
    POST   /api/sweeps/{month}/approve       close the month with the accepted split
    POST   /api/sweeps/{month}/reopen        append reversals and reopen the month

Errors are raised inside the connection context, so a failed request writes nothing.
"""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import goal_ledger
from budget_schema import is_month
from database import get_db

router = APIRouter(prefix="/api/sweeps", tags=["sweeps"])


class RuleCreate(BaseModel):
    goal_id: int
    priority_rank: int = 0
    allocation_type: Literal["fixed", "percentage"]
    amount: float = Field(ge=0)


class RulePatch(BaseModel):
    goal_id: Optional[int] = None
    priority_rank: Optional[int] = None
    allocation_type: Optional[Literal["fixed", "percentage"]] = None
    amount: Optional[float] = Field(default=None, ge=0)


class AcceptedGoal(BaseModel):
    goal_id: int
    amount: float = Field(ge=0)


class ApproveBody(BaseModel):
    allocations: list[AcceptedGoal] = []


def _current_month() -> str:
    from datetime import date

    return date.today().strftime("%Y-%m")


def _valid_month(month: str) -> str:
    if not is_month(month):
        raise HTTPException(
            status_code=400, detail="Invalid month format. Expected YYYY-MM"
        )
    return month


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, goal_ledger.LedgerConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


# ── Rules ────────────────────────────────────────────────────────────────────


@router.get("/rules")
def list_rules() -> list[dict]:
    with get_db() as conn:
        return goal_ledger.list_rules(conn)


@router.post("/rules", status_code=201)
def create_rule(body: RuleCreate) -> dict:
    with get_db() as conn:
        try:
            rule = goal_ledger.create_rule(
                conn,
                body.goal_id,
                body.priority_rank,
                body.allocation_type,
                body.amount,
            )
        except (ValueError, LookupError) as exc:
            raise _http(exc)
        conn.commit()
    return rule


@router.patch("/rules/{rule_id}")
def update_rule(rule_id: int, body: RulePatch) -> dict:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No fields to update")
    with get_db() as conn:
        try:
            rule = goal_ledger.update_rule(conn, rule_id, changes)
        except (ValueError, LookupError) as exc:
            raise _http(exc)
        conn.commit()
    return rule


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int) -> None:
    with get_db() as conn:
        try:
            goal_ledger.delete_rule(conn, rule_id)
        except LookupError as exc:
            raise _http(exc)
        conn.commit()


# ── Months ───────────────────────────────────────────────────────────────────


@router.get("/closed")
def list_closed() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT month_id, closed_at, expected_income, regular_spend,
                      reserve_total, shortfall, swept_total, leftover_raw
               FROM closed_months ORDER BY month_id DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/proposal")
def get_proposal(
    month: Optional[str] = Query(
        None, description="YYYY-MM, defaults to the current month"
    ),
) -> dict:
    month = _valid_month(month or _current_month())
    with get_db() as conn:
        try:
            return goal_ledger.compute_proposal(conn, month)
        except ValueError as exc:
            raise _http(exc)


@router.post("/{month}/approve")
def approve(month: str, body: ApproveBody) -> dict:
    _valid_month(month)
    accepted = {a.goal_id: a.amount for a in body.allocations}
    with get_db() as conn:
        try:
            result = goal_ledger.approve(conn, month, accepted)
        except (ValueError, LookupError, goal_ledger.LedgerConflict) as exc:
            raise _http(exc)
        conn.commit()
    return result


@router.post("/{month}/reopen")
def reopen(month: str) -> dict:
    _valid_month(month)
    with get_db() as conn:
        try:
            goal_ledger.reopen(conn, month)
        except (ValueError, goal_ledger.LedgerConflict) as exc:
            raise _http(exc)
        conn.commit()
    return {"month": month, "closed": False}
