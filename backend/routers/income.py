"""
routers/income.py — Monthly income management.

Routes:
    GET  /api/income   return total monthly income
    POST /api/income   replace all income_sources rows (single-source model)
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from database import get_db

router = APIRouter(prefix="/api/income", tags=["income"])


class IncomeSet(BaseModel):
    amount: float


@router.get("")
def get_income() -> dict:
    with get_db() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) as total FROM income_sources"
        ).fetchone()
    return {"total": row["total"]}


@router.post("")
def set_income(body: IncomeSet) -> dict:
    """Replace all income_sources rows with a single 'Monthly' entry."""
    with get_db() as conn:
        conn.execute("DELETE FROM income_sources")
        conn.execute(
            "INSERT INTO income_sources (source, amount) VALUES (?, ?)",
            ("Monthly", body.amount),
        )
        conn.commit()
    return {"total": body.amount}
