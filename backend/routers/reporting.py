"""
routers/reporting.py — Spending analytics endpoints.

Routes:
    GET /api/reporting/summary    budget vs actual by category for a month
    GET /api/reporting/trends     monthly or weekly spending totals
    GET /api/reporting/categories spending by category for a date range
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Query

from database import get_db

router = APIRouter(prefix="/api/reporting", tags=["reporting"])


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


def _monthly_equivalent(limit: float, freq: str) -> float:
    divisors = {"Monthly": 1, "Quarterly": 3, "Bi-annually": 6, "Annually": 12}
    return round(limit / divisors.get(freq, 1), 2)


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/summary")
def budget_summary(
    month: Optional[str] = Query(None, description="YYYY-MM, defaults to current month"),
) -> list[dict]:
    """
    Budget vs actual spending by category+subcategory for a given month.
    Returns every active budget line with its actual spend.
    """
    first, last = _month_bounds(month)

    with get_db() as conn:
        # Active budgets during this month
        budgets = conn.execute(
            """SELECT * FROM budgets
               WHERE effective_date <= ?
                 AND (conclusion_date IS NULL OR conclusion_date >= ?)
               ORDER BY category, subcategory""",
            (last, first),
        ).fetchall()

        results = []
        for b in budgets:
            cat = b["category"]
            sub = b["subcategory"]
            monthly_limit = _monthly_equivalent(b["limit_amount"], b["frequency"])

            row = conn.execute(
                """SELECT COALESCE(SUM(amount), 0) as spent
                   FROM expenses
                   WHERE category = ? AND subcategory = ?
                     AND date >= ? AND date <= ?
                     AND expense_type = 'Monthly'""",
                (cat, sub, first, last),
            ).fetchone()
            spent = row["spent"]

            remaining = round(monthly_limit - spent, 2)
            if monthly_limit == 0:
                status = "No Budget"
            elif spent > monthly_limit:
                status = "Over"
            elif spent >= monthly_limit * 0.85:
                status = "On Track"
            else:
                status = "Under"

            results.append({
                "budget_id":    b["id"],
                "category":     cat,
                "subcategory":  sub,
                "budget":       monthly_limit,
                "spent":        round(spent, 2),
                "remaining":    remaining,
                "status":       status,
                "frequency":    b["frequency"],
            })

    return results


@router.get("/trends")
def spending_trends(
    period:   str           = Query("monthly", description="'monthly' or 'weekly'"),
    category: Optional[str] = Query(None, description="Filter to a single category"),
    months:   int           = Query(12, description="How many months of history"),
) -> list[dict]:
    """
    Aggregated spending over time. Returns a list of {period, total} or
    {period, category, total} when by_category is True.
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
