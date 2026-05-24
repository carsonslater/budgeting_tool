"""
routers/budgets.py — Budget CRUD + weighted moving average suggestions.

Routes:
    GET    /api/budgets           list all budgets
    POST   /api/budgets           create
    PATCH  /api/budgets/{id}      update
    DELETE /api/budgets/{id}      delete
    GET    /api/budgets/suggested weighted moving average suggestions

Suggestion logic replicates the R app's hasty/conservative WMA:
    Hasty:        weights [0.6, 0.3, 0.1] over last 3 months
    Conservative: weights [0.4, 0.4, 0.2] over last 3 months
Only suggests budgets where the current month's spending deviated > $50
from the existing limit.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import get_db

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


# ── Pydantic models ──────────────────────────────────────────────────────────

class BudgetCreate(BaseModel):
    category: str
    subcategory: str = ""
    limit_amount: float = 0.0
    frequency: str = "Monthly"
    effective_date: str
    conclusion_date: Optional[str] = None


class BudgetUpdate(BaseModel):
    category: Optional[str] = None
    subcategory: Optional[str] = None
    limit_amount: Optional[float] = None
    frequency: Optional[str] = None
    effective_date: Optional[str] = None
    conclusion_date: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _row_to_dict(row) -> dict:
    return dict(row)


def _monthly_equivalent(limit: float, freq: str) -> float:
    """Convert a budget limit to its monthly equivalent."""
    divisors = {
        "Monthly": 1,
        "Quarterly": 3,
        "Bi-annually": 6,
        "Annually": 12,
    }
    return round(limit / divisors.get(freq, 1), 2)


# ── Static routes first (before /{id}) ──────────────────────────────────────

@router.get("/suggested")
def get_suggested_budgets() -> list[dict]:
    """
    Return WMA-based budget suggestions for categories where actual spending
    in the current month differs from the budget by more than $50.
    """
    today = date.today()
    # Build month starts for the last 3 complete months
    month_starts: list[str] = []
    d = date(today.year, today.month, 1)
    for _ in range(3):
        # Go back one month
        d = (d - timedelta(days=1)).replace(day=1)
        month_starts.append(d.isoformat())
    # month_starts[0] = most recent completed month, [2] = oldest

    hasty_weights        = [0.6, 0.3, 0.1]
    conservative_weights = [0.4, 0.4, 0.2]

    with get_db() as conn:
        # Active budgets today
        active = conn.execute(
            """SELECT * FROM budgets
               WHERE limit_amount > 0
                 AND effective_date <= ?
                 AND (conclusion_date IS NULL OR conclusion_date >= ?)
               ORDER BY category, subcategory""",
            (today.isoformat(), today.isoformat()),
        ).fetchall()

        suggestions = []
        for budget in active:
            cat = budget["category"]
            sub = budget["subcategory"]
            current_limit = _monthly_equivalent(budget["limit_amount"], budget["frequency"])

            # Spending per month for the last 3 months
            monthly_spent: list[float] = []
            for month_start in month_starts:
                month_date = date.fromisoformat(month_start)
                last_day = (month_date.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                row = conn.execute(
                    """SELECT COALESCE(SUM(amount), 0) as total
                       FROM expenses
                       WHERE category = ? AND subcategory = ?
                         AND date >= ? AND date <= ?
                         AND expense_type = 'Monthly'""",
                    (cat, sub, month_start, last_day.isoformat()),
                ).fetchone()
                monthly_spent.append(row["total"])

            # Most-recent month spending vs current budget
            if not monthly_spent or abs(monthly_spent[0] - current_limit) <= 50:
                continue

            # Pad if we have fewer than 3 months of data
            while len(monthly_spent) < 3:
                monthly_spent.append(monthly_spent[-1] if monthly_spent else 0)

            hasty_suggestion = round(
                sum(w * s for w, s in zip(hasty_weights, monthly_spent)), 2
            )
            conservative_suggestion = round(
                sum(w * s for w, s in zip(conservative_weights, monthly_spent)), 2
            )

            suggestions.append({
                "budget_id":              budget["id"],
                "category":               cat,
                "subcategory":            sub,
                "current_limit":          budget["limit_amount"],
                "current_monthly_equiv":  current_limit,
                "frequency":              budget["frequency"],
                "hasty":                  hasty_suggestion,
                "conservative":           conservative_suggestion,
                "recent_month_spent":     monthly_spent[0],
            })

    return suggestions


# ── CRUD ─────────────────────────────────────────────────────────────────────

@router.get("")
def list_budgets() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM budgets WHERE limit_amount > 0 ORDER BY category, subcategory, effective_date"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


@router.post("", status_code=201)
def create_budget(body: BudgetCreate) -> dict:
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO budgets
                 (category, subcategory, limit_amount, frequency, effective_date, conclusion_date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (body.category, body.subcategory, body.limit_amount,
             body.frequency, body.effective_date, body.conclusion_date),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM budgets WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _row_to_dict(row)


@router.patch("/{budget_id}")
def update_budget(budget_id: int, body: BudgetUpdate) -> dict:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [budget_id]

    with get_db() as conn:
        conn.execute(
            f"UPDATE budgets SET {set_clause} WHERE id = ?", values
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM budgets WHERE id = ?", (budget_id,)
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Budget not found")
    return _row_to_dict(row)


@router.delete("/{budget_id}", status_code=204)
def delete_budget(budget_id: int) -> None:
    with get_db() as conn:
        result = conn.execute(
            "DELETE FROM budgets WHERE id = ?", (budget_id,)
        )
        conn.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Budget not found")
