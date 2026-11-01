"""
routers/reporting.py — Spending analytics endpoints.

Routes:
    GET /api/reporting/summary    budget vs actual, partitioned by cadence
    GET /api/reporting/trends     monthly or weekly spending totals
    GET /api/reporting/categories spending by category for a date range

Partitioning (Phase 1): `/summary` returns `{ monthly, non_monthly }` rather than
one blended list. Monthly lines compare a single month's spend against their
monthly-equivalent limit; non-monthly lines accrue spend across their
calendar-aligned period (year / half / quarter) through the requested month and
compare the cumulative total against the full per-period limit — no ÷-by-cadence
pro-rating and no time-proration. The explicit partition means an annual or
quarterly line can never distort a recurring monthly line's status, totals, or
remaining budget. Trends stay *true cash flow* — a once-a-year spike is real and
should remain visible.

Versioned budgets (Phase 4 pivot): a month's lines come from `budget_store`, and
a non-monthly line is active in every month from its first version until it
is ended, so its accrual window starts at the first month *within the period*
where the line is active — the versioned-model equivalent of the old
`effective_date` mid-period rule.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Query

import budget_store
from budget_math import monthly_equivalent
from database import get_db

router = APIRouter(prefix="/api/reporting", tags=["reporting"])

# A monthly line at or above this share of its limit counts as "On Track".
_ON_TRACK_RATIO = 0.85


# ── Helpers ──────────────────────────────────────────────────────────────────


def _resolve_month(month_str: Optional[str]) -> tuple[int, int]:
    """Return (year, month) ints for a YYYY-MM string, defaulting to now."""
    if month_str:
        return int(month_str[:4]), int(month_str[5:7])
    today = date.today()
    return today.year, today.month


def _last_day(year: int, month: int) -> date:
    """Last day of the given calendar month."""
    if month == 12:
        return date(year + 1, 1, 1) - timedelta(days=1)
    return date(year, month + 1, 1) - timedelta(days=1)


def _period_bounds(frequency: str, year: int, month: int) -> tuple[date, date]:
    """Calendar-aligned period bounds (start, end) containing the given month.

    Periods are calendar-aligned: years Jan 1–Dec 31, halves Jan–Jun / Jul–Dec,
    quarters Jan–Mar / Apr–Jun / Jul–Sep / Oct–Dec. This is the window a
    non-monthly line accrues spend over.
    """
    if frequency == "Annually":
        return date(year, 1, 1), date(year, 12, 31)
    if frequency == "Bi-annually":
        if month <= 6:
            return date(year, 1, 1), date(year, 6, 30)
        return date(year, 7, 1), date(year, 12, 31)
    quarter = (month - 1) // 3
    start_month = quarter * 3 + 1
    end_month = quarter * 3 + 3
    return date(year, start_month, 1), _last_day(year, end_month)


def _status(spent: float, limit: float) -> str:
    """Budget status for a line compared against its own limit."""
    if limit <= 0:
        return "No Budget"
    if spent > limit:
        return "Over"
    if spent >= limit * _ON_TRACK_RATIO:
        return "On Track"
    return "Under"


def _spent_between(
    conn,
    category_id: int,
    subcategory_id: int | None,
    start: str,
    end: str,
) -> float:
    """
    Actual 'Monthly'-type spend for one category line within [start, end].

    Matched on the category ids, never on names: an expense carries the id it
    was filed under, so a rename cannot split or lose its attribution.
    """
    row = conn.execute(
        """SELECT COALESCE(SUM(amount), 0) AS spent
           FROM expenses
           WHERE category_id = ?
             AND COALESCE(subcategory_id, 0) = COALESCE(?, 0)
             AND date >= ? AND date <= ?
             AND expense_type = 'Monthly'""",
        (category_id, subcategory_id, start, end),
    ).fetchone()
    return row["spent"]


def _accrual_start(period_start: date, months: list[str]) -> date:
    """
    First day of the earliest month the line appears in, floored at the period.

    A line added mid-period does not accrue spend from before it existed; this
    is the versioned-model equivalent of the old `effective_date` clamp.
    """
    if not months:
        return period_start
    month_start = date.fromisoformat(f"{min(months)}-01")
    return max(period_start, month_start)


# ── Routes ───────────────────────────────────────────────────────────────────


@router.get("/summary")
def budget_summary(
    month: Optional[str] = Query(
        None, description="YYYY-MM, defaults to current month"
    ),
) -> dict:
    """
    Budget vs actual spending for a given month, partitioned by cadence.

    Returns `{ "monthly": [...], "non_monthly": [...] }`:

    - `monthly` — only `frequency == 'Monthly'` lines, each compared to its
      limit (monthly equivalent == its own limit). This is the monthly budget
      health view.
    - `non_monthly` — quarterly / bi-annual / annual lines. Spend accrues across
      the line's calendar-aligned period (year / half / quarter) through the end
      of the requested month, and the cumulative total is compared to the full
      per-period limit (no ÷-by-cadence, no time-proration). Each row carries
      `period_start` / `period_end` so the window being accrued over is visible.

    The explicit partition means the client cannot silently re-mix the two.
    """
    y, m = _resolve_month(month)
    month_str = f"{y:04d}-{m:02d}"
    first = date(y, m, 1).isoformat()
    last = _last_day(y, m).isoformat()

    with get_db() as conn:
        lines, _inherited = budget_store.resolve_view(conn, month_str)
        lines = [line for line in lines if line["limit_amount"] > 0]
        lines.sort(key=lambda line: (line["category"], line["subcategory"]))

        non_monthly_lines = [l for l in lines if l["frequency"] != "Monthly"]

        # Accrual start per non-monthly line: the first month *within its own
        # calendar period* where the line appears. One cross-month read covers
        # every line's window (they all end at the requested month).
        periods = {
            line["line_key"]: _period_bounds(line["frequency"], y, m)
            for line in non_monthly_lines
        }
        months_by_line: dict[str, list[str]] = {}
        if periods:
            earliest = min(period_start for period_start, _ in periods.values())
            months_by_line = budget_store.months_by_line(
                conn,
                f"{earliest.year:04d}-{earliest.month:02d}",
                month_str,
            )

        monthly: list[dict] = []
        non_monthly: list[dict] = []

        for line in lines:
            key = line["line_key"]
            if line["frequency"] == "Monthly":
                spent = _spent_between(
                    conn,
                    line["category_id"],
                    line["subcategory_id"],
                    first,
                    last,
                )
                limit = monthly_equivalent(line["limit_amount"], line["frequency"])
                monthly.append(
                    {
                        "budget_id": line["id"],
                        "line_key": key,
                        "category": line["category"],
                        "subcategory": line["subcategory"],
                        "budget": limit,
                        "spent": round(spent, 2),
                        "remaining": round(limit - spent, 2),
                        "status": _status(spent, limit),
                        "frequency": line["frequency"],
                    }
                )
            else:
                # Accrue across the calendar period, from the first month the
                # line appears in within that period, through the end of the
                # requested month. Compare against the full per-period limit —
                # no time-proration.
                period_start, period_end = periods[key]
                accrue_from = _accrual_start(period_start, months_by_line.get(key, []))
                spent = _spent_between(
                    conn,
                    line["category_id"],
                    line["subcategory_id"],
                    accrue_from.isoformat(),
                    last,
                )
                limit = round(line["limit_amount"], 2)
                non_monthly.append(
                    {
                        "budget_id": line["id"],
                        "line_key": key,
                        "category": line["category"],
                        "subcategory": line["subcategory"],
                        "budget": limit,
                        "spent": round(spent, 2),
                        "remaining": round(limit - spent, 2),
                        "status": _status(spent, limit),
                        "frequency": line["frequency"],
                        "period_start": period_start.isoformat(),
                        "period_end": period_end.isoformat(),
                    }
                )

    return {"monthly": monthly, "non_monthly": non_monthly}


@router.get("/trends")
def spending_trends(
    period: str = Query("monthly", description="'monthly' or 'weekly'"),
    category: Optional[str] = Query(None, description="Filter to a single category"),
    months: int = Query(12, description="How many months of history"),
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
                sql += (
                    " AND category_id = (SELECT id FROM categories"
                    " WHERE name = ? AND kind = 'category')"
                )
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
                sql += (
                    " AND category_id = (SELECT id FROM categories"
                    " WHERE name = ? AND kind = 'category')"
                )
                params.append(category)
            sql += " GROUP BY period ORDER BY period"

        rows = conn.execute(sql, params).fetchall()

    return [{"period": r["period"], "total": round(r["total"], 2)} for r in rows]


@router.get("/categories")
def spending_by_category(
    start: Optional[str] = Query(None, description="ISO date"),
    end: Optional[str] = Query(None, description="ISO date"),
) -> list[dict]:
    """
    Total spending grouped by category for a date range.

    Grouped by the category ids and named from `categories`, so a rename merges
    the rows under the current name instead of splitting the total in two.
    """
    sql = """
        SELECT COALESCE(c.name, e.category, '')    AS category,
               COALESCE(s.name, e.subcategory, '') AS subcategory,
               COALESCE(SUM(e.amount), 0)          AS total,
               COUNT(*)                            AS transaction_count
        FROM expenses e
        LEFT JOIN categories c ON c.id = e.category_id
        LEFT JOIN categories s ON s.id = e.subcategory_id
        WHERE e.expense_type = 'Monthly'
    """
    params: list = []
    if start:
        sql += " AND e.date >= ?"
        params.append(start)
    if end:
        sql += " AND e.date <= ?"
        params.append(end)
    # Group by ids only: the names are a function of them, and grouping by the
    # alias would resolve back to the denormalized text column in SQLite.
    sql += """
        GROUP BY e.category_id, e.subcategory_id
        ORDER BY total DESC
    """

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [
        {
            "category": r["category"],
            "subcategory": r["subcategory"],
            "total": round(r["total"], 2),
            "transaction_count": r["transaction_count"],
        }
        for r in rows
    ]
