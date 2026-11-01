"""
routers/goals.py — Goals CRUD + goal-budget link management.

`goal_budget_links` is envelope metadata only: it records which category a goal
is funded from and over what window. It no longer mints a synthetic `budgets`
row — budgets now live in versioned lines and are owned by the planner, not by
goals (2026-10-03 plan §9, which retires the synthetic-budget-row behavior).

Routes:
    GET    /api/goals              list all goals
    POST   /api/goals              create
    PATCH  /api/goals/{id}         update / mark complete
    DELETE /api/goals/{id}         delete
    GET    /api/goals/links        list all goal-budget links
    POST   /api/goals/links        create link
    DELETE /api/goals/links/{id}   delete link
"""

from __future__ import annotations

import calendar
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import goal_ledger
from database import get_db

router = APIRouter(prefix="/api/goals", tags=["goals"])


# ── Pydantic models ──────────────────────────────────────────────────────────


class GoalCreate(BaseModel):
    name: str
    target_amount: float = 0.0
    target_month: str
    created_date: str
    completed: int = 0
    category: Optional[str] = None
    subcategory: Optional[str] = ""


class GoalUpdate(BaseModel):
    name: Optional[str] = None
    target_amount: Optional[float] = None
    target_month: Optional[str] = None
    created_date: Optional[str] = None
    completed: Optional[int] = None


class GoalLinkCreate(BaseModel):
    goal_name: str
    category: str
    subcategory: str = ""
    start_date: str
    end_date: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _row_to_dict(row) -> dict:
    return dict(row)


# ── Static paths before dynamic ──────────────────────────────────────────────


@router.get("/links")
def list_goal_links() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM goal_budget_links ORDER BY goal_name, category, subcategory"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


@router.post("/links", status_code=201)
def create_goal_link(body: GoalLinkCreate) -> dict:
    with get_db() as conn:
        # Get the goal info to calculate the limit amount
        goal = conn.execute(
            "SELECT target_amount, target_month, created_date FROM goals WHERE name = ?",
            (body.goal_name,),
        ).fetchone()

        conclusion_date = body.end_date

        if goal:
            try:
                end_dt = datetime.strptime(goal["target_month"], "%Y-%m-%d")
                last_day = calendar.monthrange(end_dt.year, end_dt.month)[1]
                conclusion_date = f"{end_dt.year:04d}-{end_dt.month:02d}-{last_day:02d}"
            except Exception:
                pass

        # Insert link
        cur = conn.execute(
            """INSERT INTO goal_budget_links
                 (goal_name, category, subcategory, start_date, end_date)
               VALUES (?, ?, ?, ?, ?)""",
            (
                body.goal_name,
                body.category,
                body.subcategory,
                body.start_date,
                conclusion_date,
            ),
        )

        conn.commit()
        row = conn.execute(
            "SELECT * FROM goal_budget_links WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _row_to_dict(row)


@router.delete("/links/{link_id}", status_code=204)
def delete_goal_link(link_id: int) -> None:
    with get_db() as conn:
        link = conn.execute(
            "SELECT id FROM goal_budget_links WHERE id = ?", (link_id,)
        ).fetchone()
        if not link:
            raise HTTPException(status_code=404, detail="Link not found")

        result = conn.execute("DELETE FROM goal_budget_links WHERE id = ?", (link_id,))
        conn.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Link not found")


# ── Goal CRUD ─────────────────────────────────────────────────────────────────


class WithdrawalCreate(BaseModel):
    amount: float = Field(gt=0)


def _months_remaining(target_month: str, today: datetime) -> Optional[int]:
    """Months from this month through the target month, inclusive; None when it has passed."""
    try:
        ty, tm = int(target_month[:4]), int(target_month[5:7])
    except (TypeError, ValueError):
        return None
    n = (ty * 12 + tm) - (today.year * 12 + today.month) + 1
    return n if n > 0 else None


@router.get("")
def list_goals() -> list[dict]:
    today = datetime.now()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM goals ORDER BY completed ASC, target_month ASC"
        ).fetchall()
        balances = goal_ledger.goal_balances(conn)
        this_month = goal_ledger.goal_contributions(conn, today.strftime("%Y-%m"))
    out = []
    for row in rows:
        goal = _row_to_dict(row)
        balance = balances.get(goal["id"], 0.0)
        months_left = _months_remaining(goal["target_month"], today)
        goal["balance"] = balance
        goal["contributed_this_month"] = this_month.get(goal["id"], 0.0)
        goal["needs_per_month"] = (
            round(max(0.0, goal["target_amount"] - balance) / months_left, 2)
            if months_left and goal["completed"] == 0
            else None
        )
        out.append(goal)
    return out


@router.post("/{goal_id}/withdrawals", status_code=201)
def withdraw_from_goal(goal_id: int, body: WithdrawalCreate) -> dict:
    with get_db() as conn:
        try:
            result = goal_ledger.add_withdrawal(conn, goal_id, body.amount)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        conn.commit()
    return result


@router.post("", status_code=201)
def create_goal(body: GoalCreate) -> dict:
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO goals (name, target_amount, target_month, created_date, completed)
               VALUES (?, ?, ?, ?, ?)""",
            (
                body.name,
                body.target_amount,
                body.target_month,
                body.created_date,
                body.completed,
            ),
        )

        # If a category is provided, also record the goal's funding link.
        if body.category:
            try:
                start_dt = datetime.strptime(body.created_date, "%Y-%m-%d")
                end_dt = datetime.strptime(body.target_month, "%Y-%m-%d")

                last_day = calendar.monthrange(end_dt.year, end_dt.month)[1]
                conclusion_date = f"{end_dt.year:04d}-{end_dt.month:02d}-{last_day:02d}"
                start_date_normalized = f"{start_dt.year:04d}-{start_dt.month:02d}-01"
            except Exception:
                conclusion_date = None
                start_date_normalized = body.created_date

            # Create link
            conn.execute(
                """INSERT INTO goal_budget_links
                     (goal_name, category, subcategory, start_date, end_date)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    body.name,
                    body.category,
                    body.subcategory,
                    start_date_normalized,
                    conclusion_date,
                ),
            )

        conn.commit()
        row = conn.execute(
            "SELECT * FROM goals WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _row_to_dict(row)


@router.patch("/{goal_id}")
def update_goal(goal_id: int, body: GoalUpdate) -> dict:
    with get_db() as conn:
        # Get old goal info
        old_goal = conn.execute(
            "SELECT name, target_month FROM goals WHERE id = ?",
            (goal_id,),
        ).fetchone()
        if not old_goal:
            raise HTTPException(status_code=404, detail="Goal not found")

        old_name = old_goal["name"]
        old_target_month = old_goal["target_month"]

        # Apply updates to goal
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [goal_id]

        conn.execute(f"UPDATE goals SET {set_clause} WHERE id = ?", values)

        new_name = updates.get("name", old_name)
        new_target_month = updates.get("target_month", old_target_month)

        # If name changed, update the links
        if new_name != old_name:
            conn.execute(
                "UPDATE goal_budget_links SET goal_name = ? WHERE goal_name = ?",
                (new_name, old_name),
            )

        # A goal owns no budget rows, so only the links' end_date tracks the
        # target month. Every link for the goal shares the same end_date.
        if new_target_month != old_target_month:
            try:
                end_dt = datetime.strptime(new_target_month, "%Y-%m-%d")
                last_day = calendar.monthrange(end_dt.year, end_dt.month)[1]
                new_conclusion_date = (
                    f"{end_dt.year:04d}-{end_dt.month:02d}-{last_day:02d}"
                )
            except Exception:
                new_conclusion_date = None

            if new_conclusion_date is not None:
                conn.execute(
                    "UPDATE goal_budget_links SET end_date = ? WHERE goal_name = ?",
                    (new_conclusion_date, new_name),
                )

        conn.commit()
        row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return _row_to_dict(row)


@router.delete("/{goal_id}", status_code=204)
def delete_goal(goal_id: int) -> None:
    with get_db() as conn:
        goal = conn.execute(
            "SELECT name FROM goals WHERE id = ?", (goal_id,)
        ).fetchone()
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")

        # Ledger history is never deleted. A goal with any money movement is archived
        # by marking it completed instead.
        if goal_ledger.goal_has_ledger(conn, goal_id):
            raise HTTPException(
                status_code=409,
                detail="Goal has sweep or withdrawal history; mark it completed instead",
            )

        goal_name = goal["name"]

        # Delete links
        conn.execute("DELETE FROM goal_budget_links WHERE goal_name = ?", (goal_name,))

        # Delete goal
        result = conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
        conn.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Goal not found")
