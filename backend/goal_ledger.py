"""
goal_ledger.py — the only module that touches ``goal_allocations`` and ``sweep_rules``.

Mirrors ``budget_store``: it never commits (callers own the transaction), and every
failure is raised before a write, or after writes that the caller rolls back.

Error contract for routers:
    ValueError     -> 400 (bad input)
    LookupError    -> 404 (goal or rule missing)
    LedgerConflict -> 409 (the request conflicts with the ledger's current state)

Month-end flow (``compute_proposal`` then ``approve``):

1. Read the month's income, regular spend (Monthly expenses not filed under an irregular
   line), and each irregular line's reserve and bill.
2. Settle each irregular line's fund (``sweep_math.fund_month``).
3. Leftover = income - regular spend - reserves - shortfall. The pot is its positive part.
4. Allocate the pot across eligible goals by rule (``sweep_math.allocate``).

``approve`` recomputes the proposal and rejects any accepted amounts that differ, so
the rows written are exactly what the user saw.
"""

from __future__ import annotations

import calendar
import sqlite3
from datetime import date, datetime
from typing import Optional

import budget_store
import sweep_math
from budget_math import monthly_equivalent
from budget_schema import is_month

ALLOCATION_TYPES = ("fixed", "percentage")
_TOLERANCE = 0.005


class LedgerConflict(Exception):
    """The request conflicts with the ledger's current state (HTTP 409)."""


# ── Helpers ──────────────────────────────────────────────────────────────────


def _require_month(month: str) -> str:
    if not is_month(month):
        raise ValueError(f"invalid month {month!r}; expected YYYY-MM")
    return month


def _current_month() -> str:
    return date.today().strftime("%Y-%m")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _month_bounds(month: str) -> tuple[str, str]:
    year, mon = int(month[:4]), int(month[5:7])
    last = calendar.monthrange(year, mon)[1]
    return f"{month}-01", f"{month}-{last:02d}"


def _goal_exists(conn: sqlite3.Connection, goal_id: int) -> None:
    if conn.execute("SELECT 1 FROM goals WHERE id = ?", (goal_id,)).fetchone() is None:
        raise LookupError(f"goal {goal_id} not found")


# ── Sweep rules ──────────────────────────────────────────────────────────────


def list_rules(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT r.id, r.goal_id, g.name AS goal_name, r.priority_rank,
                  r.allocation_type, r.amount
           FROM sweep_rules r
           JOIN goals g ON g.id = r.goal_id
           ORDER BY r.priority_rank, r.id"""
    ).fetchall()
    return [dict(r) for r in rows]


def _rule_by_id(conn: sqlite3.Connection, rule_id: int) -> Optional[dict]:
    row = next((r for r in list_rules(conn) if r["id"] == rule_id), None)
    return row


def _check_rule(rule: dict) -> None:
    if rule["allocation_type"] not in ALLOCATION_TYPES:
        raise ValueError(
            f"invalid allocation_type {rule['allocation_type']!r}; "
            f"expected one of {list(ALLOCATION_TYPES)}"
        )
    if rule["amount"] < 0:
        raise ValueError("amount must be zero or more")
    if rule["allocation_type"] == "percentage" and rule["amount"] > 100:
        raise ValueError("a percentage rule cannot exceed 100")


def _check_rule_set(rules: list[dict]) -> None:
    """Priorities unique, and percentage rules together at most 100."""
    ranks = [r["priority_rank"] for r in rules]
    if len(ranks) != len(set(ranks)):
        raise ValueError("priority_rank must be unique across sweep rules")
    total = sum(r["amount"] for r in rules if r["allocation_type"] == "percentage")
    if total > 100 + _TOLERANCE:
        raise ValueError(
            f"percentage rules total {total:g}%; at most 100% can be allocated"
        )


def create_rule(
    conn: sqlite3.Connection,
    goal_id: int,
    priority_rank: int,
    allocation_type: str,
    amount: float,
) -> dict:
    _goal_exists(conn, goal_id)
    candidate = {
        "goal_id": goal_id,
        "priority_rank": priority_rank,
        "allocation_type": allocation_type,
        "amount": float(amount),
    }
    _check_rule(candidate)
    _check_rule_set(
        [{k: r[k] for k in candidate} for r in list_rules(conn)] + [candidate]
    )
    cur = conn.execute(
        """INSERT INTO sweep_rules (goal_id, priority_rank, allocation_type, amount)
           VALUES (?, ?, ?, ?)""",
        (goal_id, priority_rank, allocation_type, float(amount)),
    )
    return _rule_by_id(conn, cur.lastrowid)


def update_rule(conn: sqlite3.Connection, rule_id: int, changes: dict) -> dict:
    current = _rule_by_id(conn, rule_id)
    if current is None:
        raise LookupError(f"sweep rule {rule_id} not found")
    merged = {
        **{
            k: current[k]
            for k in ("goal_id", "priority_rank", "allocation_type", "amount")
        },
        **{k: v for k, v in changes.items() if v is not None},
    }
    _goal_exists(conn, merged["goal_id"])
    merged["amount"] = float(merged["amount"])
    _check_rule(merged)
    others = [
        {k: r[k] for k in ("goal_id", "priority_rank", "allocation_type", "amount")}
        for r in list_rules(conn)
        if r["id"] != rule_id
    ]
    _check_rule_set(others + [merged])
    conn.execute(
        """UPDATE sweep_rules
           SET goal_id = ?, priority_rank = ?, allocation_type = ?, amount = ?
           WHERE id = ?""",
        (
            merged["goal_id"],
            merged["priority_rank"],
            merged["allocation_type"],
            merged["amount"],
            rule_id,
        ),
    )
    return _rule_by_id(conn, rule_id)


def delete_rule(conn: sqlite3.Connection, rule_id: int) -> None:
    result = conn.execute("DELETE FROM sweep_rules WHERE id = ?", (rule_id,))
    if result.rowcount == 0:
        raise LookupError(f"sweep rule {rule_id} not found")


# ── Balances ─────────────────────────────────────────────────────────────────


def goal_balances(conn: sqlite3.Connection) -> dict[int, float]:
    rows = conn.execute(
        """SELECT goal_id, COALESCE(SUM(amount), 0) AS balance
           FROM goal_allocations
           WHERE goal_id IS NOT NULL
           GROUP BY goal_id"""
    ).fetchall()
    return {r["goal_id"]: round(r["balance"], 2) for r in rows}


def goal_contributions(conn: sqlite3.Connection, month: str) -> dict[int, float]:
    """Net sweep money a goal received in ``month`` (reversals included)."""
    _require_month(month)
    rows = conn.execute(
        """SELECT goal_id, COALESCE(SUM(amount), 0) AS total
           FROM goal_allocations
           WHERE goal_id IS NOT NULL AND kind IN ('sweep', 'reversal') AND month = ?
           GROUP BY goal_id""",
        (month,),
    ).fetchall()
    return {r["goal_id"]: round(r["total"], 2) for r in rows}


def goal_has_ledger(conn: sqlite3.Connection, goal_id: int) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM goal_allocations WHERE goal_id = ? LIMIT 1", (goal_id,)
        ).fetchone()
        is not None
    )


def fund_balance_before(conn: sqlite3.Connection, line_key: str, month: str) -> float:
    row = conn.execute(
        """SELECT COALESCE(SUM(amount), 0) AS balance
           FROM goal_allocations
           WHERE line_key = ? AND month < ?""",
        (line_key, month),
    ).fetchone()
    return round(row["balance"], 2)


def add_withdrawal(conn: sqlite3.Connection, goal_id: int, amount: float) -> dict:
    """Take money out of a goal, dated to the current month. Balance may not go negative."""
    if amount <= 0:
        raise ValueError("withdrawal amount must be positive")
    _goal_exists(conn, goal_id)
    balance = goal_balances(conn).get(goal_id, 0.0)
    if amount > balance + _TOLERANCE:
        raise ValueError(
            f"withdrawal {amount:.2f} exceeds the goal balance {balance:.2f}"
        )
    conn.execute(
        """INSERT INTO goal_allocations (goal_id, month, kind, amount, created_at)
           VALUES (?, ?, 'withdrawal', ?, ?)""",
        (goal_id, _current_month(), -round(amount, 2), _now()),
    )
    return {"goal_id": goal_id, "balance": round(balance - amount, 2)}


# ── Month-end proposal ───────────────────────────────────────────────────────


def _monthly_spend(
    conn: sqlite3.Connection, month: str
) -> tuple[float, dict[tuple[int, int], float]]:
    """(total Monthly-type spend, spend keyed by (category_id, subcategory_id or 0))."""
    first, last = _month_bounds(month)
    total = conn.execute(
        """SELECT COALESCE(SUM(amount), 0) AS total FROM expenses
           WHERE expense_type = 'Monthly' AND date >= ? AND date <= ?""",
        (first, last),
    ).fetchone()["total"]
    by_pair = {
        (r["category_id"], r["sub"]): r["total"]
        for r in conn.execute(
            """SELECT category_id, COALESCE(subcategory_id, 0) AS sub,
                      COALESCE(SUM(amount), 0) AS total
               FROM expenses
               WHERE expense_type = 'Monthly' AND date >= ? AND date <= ?
                 AND category_id IS NOT NULL
               GROUP BY category_id, COALESCE(subcategory_id, 0)""",
            (first, last),
        ).fetchall()
    }
    return round(total, 2), by_pair


def _previous_month(month: str) -> str:
    return budget_store.shift_month(month, -1)


def closed_months(conn: sqlite3.Connection) -> list[str]:
    return [
        r["month_id"]
        for r in conn.execute("SELECT month_id FROM closed_months ORDER BY month_id")
    ]


def _blocker(conn: sqlite3.Connection, month: str) -> Optional[str]:
    """Why ``month`` cannot be approved right now, or ``None``."""
    closed = closed_months(conn)
    if month in closed:
        return f"{month} is already closed"
    if month > _previous_month(_current_month()):
        return f"{month} has not ended yet"
    if closed and _previous_month(month) not in closed:
        return f"{_previous_month(month)} must be closed before {month}"
    return None


def compute_proposal(conn: sqlite3.Connection, month: str) -> dict:
    """The month's leftover, fund settlements and goal split. Read-only."""
    _require_month(month)
    income = budget_store.effective_expected_income(conn, month)
    if income is None:
        raise ValueError(f"set expected income for {month} before sweeping it")

    lines, _inherited = budget_store.resolve_view(conn, month)
    irregular = [line for line in lines if line["frequency"] != "Monthly"]
    total_spend, spend_by_pair = _monthly_spend(conn, month)

    funds: list[dict] = []
    reserve_total = shortfall_total = irregular_spend = 0.0
    for line in irregular:
        pair = (line["category_id"], line["subcategory_id"] or 0)
        reserve = monthly_equivalent(line["limit_amount"], line["frequency"])
        spent = round(spend_by_pair.get(pair, 0.0), 2)
        balance_before = fund_balance_before(conn, line["line_key"], month)
        step = sweep_math.fund_month(balance_before, reserve, spent)
        name = line["category"] + (
            f" > {line['subcategory']}" if line["subcategory"] else ""
        )
        funds.append(
            {
                "line_key": line["line_key"],
                "name": name,
                "frequency": line["frequency"],
                "reserve": round(reserve, 2),
                "balance_before": balance_before,
                "spent": spent,
                "draw": step.draw,
                "shortfall": step.shortfall,
                "balance_after": step.balance_after,
            }
        )
        reserve_total += reserve
        shortfall_total += step.shortfall
        irregular_spend += spent

    reserve_total = round(reserve_total, 2)
    shortfall_total = round(shortfall_total, 2)
    regular_spend = round(total_spend - irregular_spend, 2)
    leftover = sweep_math.leftover(
        income, regular_spend, reserve_total, shortfall_total
    )
    pot = max(0.0, leftover)

    balances = goal_balances(conn)
    rules = list_rules(conn)
    eligible: dict[int, dict] = {}
    needs: dict[int, float] = {}
    for goal in conn.execute(
        "SELECT id, name, target_amount, completed FROM goals"
    ).fetchall():
        if goal["completed"] or goal["id"] not in {r["goal_id"] for r in rules}:
            continue
        balance = balances.get(goal["id"], 0.0)
        needs[goal["id"]] = max(0.0, goal["target_amount"] - balance)
        eligible[goal["id"]] = {"name": goal["name"], "balance": balance}

    grants, unallocated = sweep_math.allocate(pot, rules, needs)
    goals = [
        {
            "goal_id": gid,
            "name": info["name"],
            "amount": round(grants.get(gid, 0.0), 2),
            "balance": info["balance"],
            "projected_balance": round(info["balance"] + grants.get(gid, 0.0), 2),
        }
        for gid, info in eligible.items()
    ]
    goals.sort(key=lambda g: g["name"])

    blocker = _blocker(conn, month)
    return {
        "month": month,
        "income": round(income, 2),
        "regular_spend": regular_spend,
        "irregular_spend": round(irregular_spend, 2),
        "reserve_total": reserve_total,
        "shortfall": shortfall_total,
        "leftover": leftover,
        "pot": round(pot, 2),
        "swept_total": round(pot - unallocated, 2),
        "unallocated": round(unallocated, 2),
        "funds": funds,
        "goals": goals,
        "approvable": blocker is None,
        "blocked_reason": blocker,
    }


def approve(conn: sqlite3.Connection, month: str, accepted: dict[int, float]) -> dict:
    """
    Close ``month``: write its reserves, draws and sweeps, and the close record.

    ``accepted`` maps goal_id to the amount the user approved. Any difference from the
    recomputed proposal raises ``LedgerConflict``, so nothing is written from a stale view.
    Writes only; the caller commits.
    """
    proposal = compute_proposal(conn, month)
    if not proposal["approvable"]:
        raise LedgerConflict(proposal["blocked_reason"])

    shown = {g["goal_id"]: g["amount"] for g in proposal["goals"] if g["amount"] > 0}
    given = {gid: amt for gid, amt in accepted.items() if amt > 0}
    if set(shown) != set(given) or any(
        abs(shown[gid] - given[gid]) > _TOLERANCE for gid in shown
    ):
        raise LedgerConflict(
            "the proposal changed since it was shown; reload and review again"
        )

    now = _now()
    for fund in proposal["funds"]:
        if fund["reserve"] > 0:
            conn.execute(
                """INSERT INTO goal_allocations (line_key, month, kind, amount, created_at)
                   VALUES (?, ?, 'reserve', ?, ?)""",
                (fund["line_key"], month, fund["reserve"], now),
            )
        if fund["draw"] > 0:
            conn.execute(
                """INSERT INTO goal_allocations (line_key, month, kind, amount, created_at)
                   VALUES (?, ?, 'draw', ?, ?)""",
                (fund["line_key"], month, -fund["draw"], now),
            )
    for goal in proposal["goals"]:
        if goal["amount"] > 0:
            conn.execute(
                """INSERT INTO goal_allocations (goal_id, month, kind, amount, created_at)
                   VALUES (?, ?, 'sweep', ?, ?)""",
                (goal["goal_id"], month, goal["amount"], now),
            )

    conn.execute(
        """INSERT INTO closed_months (month_id, closed_at, leftover_raw, expected_income,
                                      regular_spend, reserve_total, shortfall, swept_total)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            month,
            now,
            proposal["leftover"],
            proposal["income"],
            proposal["regular_spend"],
            proposal["reserve_total"],
            proposal["shortfall"],
            proposal["swept_total"],
        ),
    )
    return {
        **proposal,
        "approvable": False,
        "blocked_reason": f"{month} is already closed",
    }


def reopen(conn: sqlite3.Connection, month: str) -> None:
    """
    Undo a close by appending reversals for its reserves, draws and sweeps.

    Refused while a later month is closed, because that month's fund balances depend
    on this one. Rows are never deleted.
    """
    _require_month(month)
    if month not in closed_months(conn):
        raise LedgerConflict(f"{month} is not closed")
    later = conn.execute(
        "SELECT 1 FROM closed_months WHERE month_id > ? LIMIT 1", (month,)
    ).fetchone()
    if later is not None:
        raise LedgerConflict("a later month is closed; reopen that month first")

    rows = conn.execute(
        """SELECT id, goal_id, line_key, amount FROM goal_allocations
           WHERE month = ? AND kind IN ('sweep', 'reserve', 'draw')
             AND id NOT IN (SELECT reverses_id FROM goal_allocations
                            WHERE reverses_id IS NOT NULL)""",
        (month,),
    ).fetchall()
    now = _now()
    for row in rows:
        conn.execute(
            """INSERT INTO goal_allocations
                   (goal_id, line_key, month, kind, amount, reverses_id, created_at)
               VALUES (?, ?, ?, 'reversal', ?, ?, ?)""",
            (row["goal_id"], row["line_key"], month, -row["amount"], row["id"], now),
        )
    conn.execute("DELETE FROM closed_months WHERE month_id = ?", (month,))
