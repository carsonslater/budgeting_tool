"""
routers/goals.py — Goals CRUD + goal-budget link management.

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

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import get_db

router = APIRouter(prefix="/api/goals", tags=["goals"])


# ── Pydantic models ──────────────────────────────────────────────────────────

class GoalCreate(BaseModel):
    name: str
    target_amount: float = 0.0
    target_month: str
    created_date: str
    completed: int = 0


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
        cur = conn.execute(
            """INSERT INTO goal_budget_links
                 (goal_name, category, subcategory, start_date, end_date)
               VALUES (?, ?, ?, ?, ?)""",
            (body.goal_name, body.category, body.subcategory,
             body.start_date, body.end_date),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM goal_budget_links WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _row_to_dict(row)


@router.delete("/links/{link_id}", status_code=204)
def delete_goal_link(link_id: int) -> None:
    with get_db() as conn:
        result = conn.execute(
            "DELETE FROM goal_budget_links WHERE id = ?", (link_id,)
        )
        conn.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Link not found")


# ── Goal CRUD ─────────────────────────────────────────────────────────────────

@router.get("")
def list_goals() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM goals ORDER BY completed ASC, target_month ASC"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


@router.post("", status_code=201)
def create_goal(body: GoalCreate) -> dict:
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO goals (name, target_amount, target_month, created_date, completed)
               VALUES (?, ?, ?, ?, ?)""",
            (body.name, body.target_amount, body.target_month,
             body.created_date, body.completed),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM goals WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _row_to_dict(row)


@router.patch("/{goal_id}")
def update_goal(goal_id: int, body: GoalUpdate) -> dict:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [goal_id]

    with get_db() as conn:
        conn.execute(
            f"UPDATE goals SET {set_clause} WHERE id = ?", values
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM goals WHERE id = ?", (goal_id,)
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return _row_to_dict(row)


@router.delete("/{goal_id}", status_code=204)
def delete_goal(goal_id: int) -> None:
    with get_db() as conn:
        result = conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
        conn.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Goal not found")
