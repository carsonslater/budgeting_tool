"""
routers/turnover.py — the month-end turnover prompt.

Routes:
    GET  /api/turnover           what to ask for now: setup, a month to close, or nothing
    POST /api/turnover/setup     start tracking at a month, with its fund openings (one write)

Errors are raised inside the connection context, so a failed request writes nothing.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import goal_ledger
from database import get_db

router = APIRouter(prefix="/api/turnover", tags=["turnover"])


class OpeningIn(BaseModel):
    line_key: str
    amount: float = Field(ge=0)


class SetupBody(BaseModel):
    month: str
    openings: list[OpeningIn] = []


@router.get("")
def get_turnover() -> dict:
    with get_db() as conn:
        return goal_ledger.turnover_status(conn)


@router.post("/setup", status_code=201)
def setup(body: SetupBody) -> dict:
    with get_db() as conn:
        try:
            result = goal_ledger.complete_setup(
                conn, body.month, {o.line_key: o.amount for o in body.openings}
            )
        except goal_ledger.LedgerConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        conn.commit()
    return result
