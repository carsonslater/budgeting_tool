"""
routers/month_plans.py — per-month plan state: confirmation and expected income.

A month is *inherited* until it is confirmed ("keep as is"); confirming writes nothing to
the budget itself.  Expected income is a manual per-month input that is inherited forward
like a budget line and takes the same apply scopes (forward / month / through).

Routes:
    GET  /api/month-plans?start=&end=      status per month (at most 36 months)
    GET  /api/month-plans/{month}          status, confirmation time, effective income
    POST /api/month-plans/{month}/confirm  mark the month reviewed (idempotent)
    PUT  /api/month-plans/{month}/income   set expected income with an apply scope

A failed request leaves the database untouched: errors are raised inside the connection
context, before anything is committed.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import budget_store
from budget_schema import is_month
from database import get_db
from routers.budgets import ApplyMode

router = APIRouter(prefix="/api/month-plans", tags=["month-plans"])

MAX_RANGE_MONTHS = 36


class IncomeSet(BaseModel):
    amount: float = Field(ge=0)
    apply: ApplyMode = "forward"
    through: Optional[str] = None


def _valid_month(month: str) -> str:
    if not is_month(month):
        raise HTTPException(
            status_code=400, detail="Invalid month format. Expected YYYY-MM"
        )
    return month


# ── Static paths before dynamic ──────────────────────────────────────────────


@router.get("")
def list_month_plans(
    start: str = Query(..., description="YYYY-MM"),
    end: str = Query(..., description="YYYY-MM, inclusive"),
) -> list[dict]:
    _valid_month(start)
    _valid_month(end)
    if end < start:
        raise HTTPException(status_code=400, detail="'end' must not be before 'start'")
    span = (int(end[:4]) - int(start[:4])) * 12 + int(end[5:7]) - int(start[5:7]) + 1
    if span > MAX_RANGE_MONTHS:
        raise HTTPException(
            status_code=400,
            detail=f"Range too large: at most {MAX_RANGE_MONTHS} months",
        )
    with get_db() as conn:
        return budget_store.plan_statuses(conn, start, end)


@router.get("/{month}")
def get_month_plan(month: str) -> dict:
    _valid_month(month)
    with get_db() as conn:
        return budget_store.get_plan(conn, month)


@router.post("/{month}/confirm")
def confirm_month_plan(month: str) -> dict:
    _valid_month(month)
    with get_db() as conn:
        plan = budget_store.confirm_month(conn, month)
        conn.commit()
    return plan


@router.put("/{month}/income")
def set_month_income(month: str, body: IncomeSet) -> dict:
    _valid_month(month)
    with get_db() as conn:
        try:
            plan = budget_store.set_expected_income(
                conn, month, body.amount, apply=body.apply, through=body.through
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        conn.commit()
    return plan
