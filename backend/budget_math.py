"""
budget_math.py — the single source of truth for budget-period arithmetic.

Extracted from the two copies that had drifted apart (`routers/reporting.py` and
`routers/budgets.py`) so the ÷-by-cadence math can no longer disagree between
views. Mirrored on the client in `web/src/lib/budgetMath.ts`.

Scope note: this module holds the **monthly equivalent only**. There is
deliberately no accrual model and no status helper here. A non-monthly line is
not "a monthly line spread thin" — pro-rating an annual limit onto a single
month is exactly the defect this module exists to prevent. Non-monthly lines are
reported on their own basis in `routers/reporting.py`.
"""

from __future__ import annotations

FREQUENCY_DIVISORS: dict[str, int] = {
    "Monthly": 1,
    "Quarterly": 3,
    "Bi-annually": 6,
    "Annually": 12,
}


def is_period_start(frequency: str, month: str) -> bool:
    """True when ``month`` (``YYYY-MM``) opens a calendar-aligned period of ``frequency``."""
    return (int(month[5:7]) - 1) % FREQUENCY_DIVISORS[frequency] == 0


def is_period_end(frequency: str, month: str) -> bool:
    """True when ``month`` (``YYYY-MM``) is the last month of a calendar-aligned period."""
    return int(month[5:7]) % FREQUENCY_DIVISORS[frequency] == 0


def monthly_equivalent(limit: float, frequency: str) -> float:
    """
    A per-period `limit` expressed as a monthly amount.

    Only meaningful for a line that is actually compared against a single month
    of spending. Never use it to compare a non-monthly line against one month.
    """
    return round(limit / FREQUENCY_DIVISORS.get(frequency, 1), 2)
