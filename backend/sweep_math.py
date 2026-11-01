"""
sweep_math.py — pure month-end arithmetic. No database access.

Three steps, each a function here:

* ``fund_month``  — one irregular line's fund for one month: reserve in, bill out,
  shortfall (the part of the bill the fund could not cover).
* ``leftover``    — what the month leaves after regular spending, reserves and shortfall.
* ``allocate``    — how a positive pot is split across goals by rule priority.

Money is rounded to cents at each step, so ``sum(grants) + unallocated == pot`` holds
exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


def _cents(value: float) -> float:
    return round(value + 0.0, 2)


@dataclass(frozen=True)
class FundStep:
    draw: float
    shortfall: float
    balance_after: float


def fund_month(balance_before: float, reserve: float, spent: float) -> FundStep:
    """
    Settle one fund for one month.

    The reserve is credited before the bill is paid, so a bill in the month it is
    reserved can be covered by that month's reserve. The fund never goes negative: the
    uncovered part is reported as ``shortfall`` instead.
    """
    if reserve < 0 or spent < 0:
        raise ValueError("reserve and spent must be non-negative")
    available = balance_before + reserve
    draw = min(spent, available)
    return FundStep(
        draw=_cents(draw),
        shortfall=_cents(spent - draw),
        balance_after=_cents(available - draw),
    )


def leftover(
    income: float, regular_spend: float, reserve_total: float, shortfall: float
) -> float:
    """What the month leaves. May be negative; a negative leftover sweeps nothing."""
    return _cents(income - regular_spend - reserve_total - shortfall)


def allocate(
    pot: float,
    rules: Iterable[Mapping],
    needs: Mapping[int, float],
) -> tuple[dict[int, float], float]:
    """
    Split ``pot`` across goals. Returns ``(grants by goal_id, unallocated)``.

    ``rules`` are dicts with ``goal_id``, ``priority_rank``, ``allocation_type``
    (``'fixed'`` or ``'percentage'``) and ``amount``. ``needs`` maps each eligible goal
    to its remaining need (target minus balance); rules for goals not in ``needs`` are
    ignored.

    Order: fixed amounts by ascending priority, each capped by the pot left and the
    goal's need. Then each percentage is a share of the pot left after all fixed
    amounts (the same base for every percentage rule), capped the same way. Nothing
    overflows to another goal; whatever remains is unallocated.
    """
    ordered = sorted(
        (r for r in rules if r["goal_id"] in needs),
        key=lambda r: (r["priority_rank"], r["goal_id"]),
    )
    grants: dict[int, float] = {}
    remaining = _cents(max(pot, 0.0))

    def give(goal_id: int, want: float) -> None:
        nonlocal remaining
        room = min(want, remaining, needs[goal_id] - grants.get(goal_id, 0.0))
        room = _cents(max(room, 0.0))
        if room > 0:
            grants[goal_id] = _cents(grants.get(goal_id, 0.0) + room)
            remaining = _cents(remaining - room)

    for rule in ordered:
        if rule["allocation_type"] == "fixed":
            give(rule["goal_id"], float(rule["amount"]))

    base = remaining
    for rule in ordered:
        if rule["allocation_type"] == "percentage":
            give(rule["goal_id"], base * float(rule["amount"]) / 100.0)

    return grants, remaining
