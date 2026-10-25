"""
budget_schema.py — month-string validation shared by the routers and the store.

Budgets are stored sparsely (``budget_lines`` / ``budget_amounts`` / ``month_plans``,
see ``budget_store``).  The DDL for those tables lives in
``migrations/m0003_per_month_budgets.py``: a migration is a frozen snapshot and must
not change behaviour because a runtime module moved.

This module is a **leaf**: it imports nothing from the application.  Months are
``YYYY-MM`` strings compared lexically, so every month that reaches the store is
validated here first.
"""

from __future__ import annotations

import re

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def is_month(value: str) -> bool:
    """True when ``value`` is a well-formed ``YYYY-MM`` string."""
    return bool(MONTH_RE.match(value or ""))
