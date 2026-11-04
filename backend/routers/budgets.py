"""
routers/budgets.py — Month-keyed budget CRUD + weighted moving average suggestions.

Budgets are stored sparsely (see `budget_store`): a line carries a per-period amount from
an effective month until its next explicit change, so a month with no edits simply
follows the previous one.  Reads never write.

Every write takes an *apply scope*, so one request can change an arbitrary run of months:

    apply=forward   from `month` until the next explicit change (the default)
    apply=month     `month` only
    apply=through   `month` through the `through` month, inclusive

Lines are identified publicly by their ``line_key``: the UUID assigned once at creation,
so the same line is addressable across months.  A failed write (404/409/400) leaves the
database untouched — the request is rolled back before it can commit.

Routes:
    GET    /api/budgets?month=YYYY-MM      lines in effect for a month
    POST   /api/budgets                    create (or revive) a line
    PATCH  /api/budgets/{line_key}         update one line
    DELETE /api/budgets/{line_key}         end a line
    GET    /api/budgets/suggested          WMA suggestions for a month

Suggestion logic replicates the R app's hasty/conservative WMA:
    Hasty:        weights [0.6, 0.3, 0.1] over last 3 months
    Conservative: weights [0.4, 0.4, 0.2] over last 3 months
Only suggests budgets where the most recent complete month's spending deviated
> $50 from the existing limit.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import budget_store
from budget_math import monthly_equivalent
from budget_schema import is_month
from database import get_db

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


# ── Pydantic models ──────────────────────────────────────────────────────────


ApplyMode = Literal["forward", "month", "through"]


class BudgetCreate(BaseModel):
    month: str
    category: str
    subcategory: str = ""
    limit_amount: float = 0.0
    frequency: str = "Monthly"
    apply: ApplyMode = "forward"
    through: Optional[str] = None


class BudgetUpdate(BaseModel):
    category: Optional[str] = None
    subcategory: Optional[str] = None
    limit_amount: Optional[float] = None
    frequency: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _current_month() -> str:
    return date.today().strftime("%Y-%m")


def _require_month(month: Optional[str]) -> str:
    """Validate a ``YYYY-MM`` month, defaulting to the current one."""
    value = month or _current_month()
    if not is_month(value):
        raise HTTPException(
            status_code=400, detail="Invalid month format. Expected YYYY-MM"
        )
    return value


def _month_end(month: str) -> str:
    """Last calendar day of ``month``, as ISO date."""
    year, mon = int(month[:4]), int(month[5:7])
    if mon == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, mon + 1, 1) - timedelta(days=1)
    return last.isoformat()


def _public(row: dict, *, month: str, inherited: bool = False) -> dict:
    """The wire shape for one budget line."""
    return {
        "line_key": row["line_key"],
        "category": row["category"],
        "subcategory": row["subcategory"],
        "limit_amount": row["limit_amount"],
        "frequency": row["frequency"],
        "category_id": row["category_id"],
        "subcategory_id": row["subcategory_id"],
        "month": month,
        "inherited": inherited,
        "effective_since": row.get("effective_since"),
    }


# ── Static routes first (before /{line_key}) ─────────────────────────────────


@router.get("/suggested")
def get_suggested_budgets(
    month: Optional[str] = Query(None, description="YYYY-MM, defaults to now"),
) -> list[dict]:
    """
    WMA-based budget suggestions for a month, for lines whose most recent
    complete month's spending deviated from the limit by more than $50.
    """
    target = _require_month(month)
    # The three complete months preceding the target month, most recent first.
    month_starts = [budget_store.shift_month(target, -i) for i in (1, 2, 3)]

    hasty_weights = [0.6, 0.3, 0.1]
    conservative_weights = [0.4, 0.4, 0.2]

    with get_db() as conn:
        lines, _inherited = budget_store.resolve_view(conn, target)
        # Non-monthly lines are skipped: a bill that lands in one month would make the
        # WMA a spike, not a monthly rate. Their reserve is set by the amount per period.
        active = sorted(
            (
                line
                for line in lines
                if line["limit_amount"] > 0 and line["frequency"] == "Monthly"
            ),
            key=lambda line: (line["category"], line["subcategory"]),
        )

        suggestions = []
        for line in active:
            cat = line["category"]
            sub = line["subcategory"]
            current_limit = monthly_equivalent(line["limit_amount"], line["frequency"])

            monthly_spent: list[float] = []
            for month in month_starts:
                # Attributed by category id: a rename never moves history.
                row = conn.execute(
                    """SELECT COALESCE(SUM(amount), 0) AS total
                       FROM expenses
                       WHERE category_id = ?
                         AND COALESCE(subcategory_id, 0) = COALESCE(?, 0)
                         AND date >= ? AND date <= ?
                         AND expense_type = 'Monthly'""",
                    (
                        line["category_id"],
                        line["subcategory_id"],
                        f"{month}-01",
                        _month_end(month),
                    ),
                ).fetchone()
                monthly_spent.append(row["total"])

            if not monthly_spent or abs(monthly_spent[0] - current_limit) <= 50:
                continue

            while len(monthly_spent) < 3:
                monthly_spent.append(monthly_spent[-1] if monthly_spent else 0)

            hasty_suggestion = round(
                sum(w * s for w, s in zip(hasty_weights, monthly_spent)), 2
            )
            conservative_suggestion = round(
                sum(w * s for w, s in zip(conservative_weights, monthly_spent)), 2
            )

            suggestions.append(
                {
                    "line_key": line["line_key"],
                    "month": target,
                    "category": cat,
                    "subcategory": sub,
                    "current_limit": line["limit_amount"],
                    "current_monthly_equiv": current_limit,
                    "frequency": line["frequency"],
                    "hasty": hasty_suggestion,
                    "conservative": conservative_suggestion,
                    "recent_month_spent": monthly_spent[0],
                }
            )

    return suggestions


# ── CRUD ─────────────────────────────────────────────────────────────────────


@router.get("")
def list_budgets(
    month: Optional[str] = Query(None, description="YYYY-MM, defaults to now"),
) -> list[dict]:
    """Lines in effect for a month. `inherited` is true until the month is confirmed."""
    target = _require_month(month)
    with get_db() as conn:
        rows, inherited = budget_store.resolve_view(conn, target)
    return [
        _public(row, month=target, inherited=inherited)
        for row in rows
        if row["limit_amount"] > 0
    ]


@router.post("", status_code=201)
def create_budget(body: BudgetCreate) -> dict:
    target = _require_month(body.month)
    with get_db() as conn:
        try:
            row = budget_store.insert_line(
                conn,
                target,
                category=body.category,
                subcategory=body.subcategory,
                limit_amount=body.limit_amount,
                frequency=body.frequency,
                apply=body.apply,
                through=body.through,
            )
        except budget_store.LineConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        _, inherited = budget_store.resolve_view(conn, target)
        conn.commit()
    return _public(row, month=target, inherited=inherited)


@router.patch("/{line_key}")
def update_budget(
    line_key: str,
    body: BudgetUpdate,
    month: Optional[str] = Query(None, description="YYYY-MM, defaults to now"),
    apply: ApplyMode = Query("forward", description="How far an amount edit reaches"),
    through: Optional[str] = Query(None, description="Last month, when apply=through"),
) -> dict:
    target = _require_month(month)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    with get_db() as conn:
        try:
            row = budget_store.update_line(
                conn, target, line_key, apply=apply, through=through, **updates
            )
        except budget_store.LineConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        # Raised inside the connection context, so nothing has been committed.
        if row is None:
            raise HTTPException(status_code=404, detail="Budget line not found")
        _, inherited = budget_store.resolve_view(conn, target)
        conn.commit()
    return _public(row, month=target, inherited=inherited)


@router.delete("/{line_key}", status_code=204)
def delete_budget(
    line_key: str,
    month: Optional[str] = Query(None, description="YYYY-MM, defaults to now"),
    apply: ApplyMode = Query("forward", description="How far the delete reaches"),
    through: Optional[str] = Query(None, description="Last month, when apply=through"),
) -> None:
    target = _require_month(month)
    with get_db() as conn:
        try:
            deleted = budget_store.delete_line(
                conn, target, line_key, apply=apply, through=through
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if deleted == 0:
            raise HTTPException(status_code=404, detail="Budget line not found")
        conn.commit()
