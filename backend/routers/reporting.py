"""
routers/reporting.py — Spending analytics endpoints.

Routes:
    GET /api/reporting/summary    budget vs actual, partitioned by cadence
    GET /api/reporting/trends     monthly or weekly spending totals
    GET /api/reporting/categories spending by category for a date range

Partitioning (Phase 1): `/summary` returns `{ monthly, non_monthly }` rather than
one blended list. A non-monthly line is reported against its own per-occurrence
limit with no ÷-by-cadence pro-rating, so an annual or quarterly line can never
distort a recurring monthly line's status, totals, or remaining budget. Trends
stay *true cash flow* — a once-a-year spike is real and should remain visible.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Query

from budget_math import monthly_equivalent
from database import get_db

router = APIRouter(prefix="/api/reporting", tags=["reporting"])

# A monthly line at or above this share of its limit counts as "On Track".
_ON_TRACK_RATIO = 0.85


# ── Helpers ──────────────────────────────────────────────────────────────────

def _month_bounds(month_str: Optional[str]) -> tuple[str, str]:
    """Return (first_day, last_day) ISO strings for the given YYYY-MM string.
    Defaults to the current calendar month."""
    if month_str:
        y, m = int(month_str[:4]), int(month_str[5:7])
    else:
        today = date.today()
        y, m = today.year, today.month

    first = date(y, m, 1)
    # Last day: go to first day of next month, subtract one day
    if m == 12:
        last = date(y + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(y, m + 1, 1) - timedelta(days=1)
    return first.isoformat(), last.isoformat()


def _status(spent: float, limit: float) -> str:
    """Budget status for a line compared against its own limit."""
    if limit <= 0:
        return "No Budget"
    if spent > limit:
        return "Over"
    if spent >= limit * _ON_TRACK_RATIO:
        return "On Track"
    return "Under"


def _spent_in_month(conn, category: str, subcategory: str, first: str, last: str) -> float:
    """Actual 'Monthly'-type spend for one category line within a month."""
    row = conn.execute(
        """SELECT COALESCE(SUM(amount), 0) AS spent
           FROM expenses
           WHERE category = ? AND subcategory = ?
             AND date >= ? AND date <= ?
             AND expense_type = 'Monthly'""",
        (category, subcategory, first, last),
    ).fetchone()
    return row["spent"]


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/summary")
def budget_summary(
    month: Optional[str] = Query(None, description="YYYY-MM, defaults to current month"),
) -> dict:
    """
    Budget vs actual spending for a given month, partitioned by cadence.

    Returns `{ "monthly": [...], "non_monthly": [...] }`:

    - `monthly` — only `frequency == 'Monthly'` lines, each compared to its
      limit (monthly equivalent == its own limit). This is the monthly budget
      health view.
    - `non_monthly` — quarterly / bi-annual / annual lines, each compared to its
      **per-occurrence** limit with no pro-rating, and carrying its window
      (`effective_date` → `conclusion_date`) so the basis is visible.

    The explicit partition means the client cannot silently re-mix the two.
    """
    first, last = _month_bounds(month)

    with get_db() as conn:
        # Active budgets during this month
        budgets = conn.execute(
            """SELECT * FROM budgets
               WHERE limit_amount > 0
                 AND effective_date <= ?
                 AND (conclusion_date IS NULL OR conclusion_date >= ?)
               ORDER BY category, subcategory""",
            (last, first),
        ).fetchall()

        monthly: list[dict] = []
        non_monthly: list[dict] = []

        for b in budgets:
            spent = _spent_in_month(conn, b["category"], b["subcategory"], first, last)

            if b["frequency"] == "Monthly":
                limit = monthly_equivalent(b["limit_amount"], b["frequency"])
                monthly.append({
                    "budget_id":   b["id"],
                    "category":    b["category"],
                    "subcategory": b["subcategory"],
                    "budget":      limit,
                    "spent":       round(spent, 2),
                    "remaining":   round(limit - spent, 2),
                    "status":      _status(spent, limit),
                    "frequency":   b["frequency"],
                })
            else:
                # Own basis: per-occurrence limit, no ÷-by-cadence, no accrual.
                limit = round(b["limit_amount"], 2)
                non_monthly.append({
                    "budget_id":       b["id"],
                    "category":        b["category"],
                    "subcategory":     b["subcategory"],
                    "budget":          limit,
                    "spent":           round(spent, 2),
                    "remaining":       round(limit - spent, 2),
                    "status":          _status(spent, limit),
                    "frequency":       b["frequency"],
                    "effective_date":  b["effective_date"],
                    "conclusion_date": b["conclusion_date"],
                })

    return {"monthly": monthly, "non_monthly": non_monthly}


@router.get("/trends")
def spending_trends(
    period:   str           = Query("monthly", description="'monthly' or 'weekly'"),
    category: Optional[str] = Query(None, description="Filter to a single category"),
    months:   int           = Query(12, description="How many months of history"),
) -> list[dict]:
    """
    Aggregated spending over time — true cash flow. Returns a list of
    {period, total} or {period, category, total} when by_category is True.
    """
    today = date.today()
    # Start date: N months ago
    start_month = date(today.year, today.month, 1)
    for _ in range(months - 1):
        start_month = (start_month - timedelta(days=1)).replace(day=1)
    start_str = start_month.isoformat()

    with get_db() as conn:
        if period == "weekly":
            sql = """
                SELECT strftime('%Y-W%W', date) as period,
                       COALESCE(SUM(amount), 0)  as total
                FROM expenses
                WHERE date >= ?
                  AND expense_type = 'Monthly'
            """
            params: list = [start_str]
            if category:
                sql += " AND category = ?"
                params.append(category)
            sql += " GROUP BY period ORDER BY period"
        else:
            sql = """
                SELECT strftime('%Y-%m', date) as period,
                       COALESCE(SUM(amount), 0) as total
                FROM expenses
                WHERE date >= ?
                  AND expense_type = 'Monthly'
            """
            params = [start_str]
            if category:
                sql += " AND category = ?"
                params.append(category)
            sql += " GROUP BY period ORDER BY period"

        rows = conn.execute(sql, params).fetchall()

    return [{"period": r["period"], "total": round(r["total"], 2)} for r in rows]


@router.get("/categories")
def spending_by_category(
    start: Optional[str] = Query(None, description="ISO date"),
    end:   Optional[str] = Query(None, description="ISO date"),
) -> list[dict]:
    """Total spending grouped by category for a date range."""
    sql = """
        SELECT category,
               subcategory,
               COALESCE(SUM(amount), 0) as total,
               COUNT(*)                 as transaction_count
        FROM expenses
        WHERE expense_type = 'Monthly'
    """
    params: list = []
    if start:
        sql += " AND date >= ?"
        params.append(start)
    if end:
        sql += " AND date <= ?"
        params.append(end)
    sql += " GROUP BY category, subcategory ORDER BY total DESC"

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [
        {
            "category":          r["category"],
            "subcategory":       r["subcategory"],
            "total":             round(r["total"], 2),
            "transaction_count": r["transaction_count"],
        }
        for r in rows
    ]
