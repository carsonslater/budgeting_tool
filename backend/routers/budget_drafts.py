"""
routers/budget_drafts.py — Draft budget management for planning scenarios.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import get_db

router = APIRouter(prefix="/api/budget-drafts", tags=["budget-drafts"])

# ── Pydantic models ──────────────────────────────────────────────────────────

class BudgetDraftCreate(BaseModel):
    target_month: str
    category: str
    subcategory: str = ""
    limit_amount: float = 0.0
    frequency: str = "Monthly"

class BudgetDraftUpdate(BaseModel):
    category: Optional[str] = None
    subcategory: Optional[str] = None
    limit_amount: Optional[float] = None
    frequency: Optional[str] = None

def _row_to_dict(row) -> dict:
    return dict(row)

# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/{target_month}")
def get_drafts_for_month(target_month: str) -> list[dict]:
    """
    Get all draft budget items for a specific target month.
    If none exist, we automatically populate from the currently active budgets.
    """
    with get_db() as conn:
        drafts = conn.execute(
            "SELECT * FROM budget_drafts WHERE target_month = ? ORDER BY category, subcategory",
            (target_month,)
        ).fetchall()

        if not drafts:
            # Auto-populate from active budgets
            today = date.today().isoformat()
            active_budgets = conn.execute(
                """SELECT * FROM budgets
                   WHERE limit_amount > 0
                     AND effective_date <= ?
                     AND (conclusion_date IS NULL OR conclusion_date >= ?)""",
                (today, today)
            ).fetchall()
            
            for b in active_budgets:
                conn.execute(
                    """INSERT INTO budget_drafts (target_month, category, subcategory, limit_amount, frequency)
                       VALUES (?, ?, ?, ?, ?)""",
                    (target_month, b["category"], b["subcategory"], b["limit_amount"], b["frequency"])
                )
            conn.commit()
            
            # Fetch again
            drafts = conn.execute(
                "SELECT * FROM budget_drafts WHERE target_month = ? ORDER BY category, subcategory",
                (target_month,)
            ).fetchall()

    return [_row_to_dict(r) for r in drafts]


@router.post("")
def create_draft_item(body: BudgetDraftCreate) -> dict:
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO budget_drafts (target_month, category, subcategory, limit_amount, frequency)
               VALUES (?, ?, ?, ?, ?)""",
            (body.target_month, body.category, body.subcategory, body.limit_amount, body.frequency)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM budget_drafts WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _row_to_dict(row)


@router.patch("/{draft_id}")
def update_draft_item(draft_id: int, body: BudgetDraftUpdate) -> dict:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [draft_id]

    with get_db() as conn:
        conn.execute(f"UPDATE budget_drafts SET {set_clause} WHERE id = ?", values)
        conn.commit()
        row = conn.execute("SELECT * FROM budget_drafts WHERE id = ?", (draft_id,)).fetchone()
        
    if row is None:
        raise HTTPException(status_code=404, detail="Draft item not found")
    return _row_to_dict(row)


@router.delete("/{draft_id}", status_code=204)
def delete_draft_item(draft_id: int) -> None:
    with get_db() as conn:
        result = conn.execute("DELETE FROM budget_drafts WHERE id = ?", (draft_id,))
        conn.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Draft item not found")


@router.post("/{target_month}/commit")
def commit_draft_for_month(target_month: str) -> dict:
    """
    Submits the draft as the finalized budget for the target month.
    This creates new records in the `budgets` table with `effective_date` = target_month.
    It also sets `conclusion_date` on the active budgets to the day before target_month.
    """
    # Calculate the day before target_month
    try:
        t_month_date = date.fromisoformat(target_month)
        conclusion_date = (t_month_date - timedelta(days=1)).isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid target_month format. Use YYYY-MM-DD")

    with get_db() as conn:
        # Get all drafts
        drafts = conn.execute(
            "SELECT * FROM budget_drafts WHERE target_month = ?",
            (target_month,)
        ).fetchall()
        
        if not drafts:
            raise HTTPException(status_code=400, detail="No draft items found for this month.")

        # Get active budgets
        active_budgets = conn.execute(
            """SELECT * FROM budgets 
               WHERE conclusion_date IS NULL OR conclusion_date >= ?""",
            (conclusion_date,)
        ).fetchall()

        # Map active budgets by (category, subcategory) for easy comparison
        active_map = {}
        for b in active_budgets:
            key = (b["category"], b["subcategory"])
            active_map[key] = b

        # For each draft, check if it differs from the active one.
        for draft in drafts:
            key = (draft["category"], draft["subcategory"])
            active_b = active_map.get(key)
            
            # If there's an active budget, check if it's different.
            if active_b:
                if (active_b["limit_amount"] != draft["limit_amount"] or
                    active_b["frequency"] != draft["frequency"]):
                    
                    # Update active budget conclusion date
                    conn.execute(
                        "UPDATE budgets SET conclusion_date = ? WHERE id = ?",
                        (conclusion_date, active_b["id"])
                    )
                    
                    # Insert new budget
                    conn.execute(
                        """INSERT INTO budgets (category, subcategory, limit_amount, frequency, effective_date, conclusion_date)
                           VALUES (?, ?, ?, ?, ?, NULL)""",
                        (draft["category"], draft["subcategory"], draft["limit_amount"], draft["frequency"], target_month)
                    )
            else:
                # No active budget for this category, just insert it
                conn.execute(
                    """INSERT INTO budgets (category, subcategory, limit_amount, frequency, effective_date, conclusion_date)
                       VALUES (?, ?, ?, ?, ?, NULL)""",
                    (draft["category"], draft["subcategory"], draft["limit_amount"], draft["frequency"], target_month)
                )

        # Handle budgets that were active but are missing from the draft (user deleted them from draft)
        draft_keys = set((d["category"], d["subcategory"]) for d in drafts)
        for key, active_b in active_map.items():
            if key not in draft_keys:
                # Conclude this budget without creating a new one
                conn.execute(
                    "UPDATE budgets SET conclusion_date = ? WHERE id = ?",
                    (conclusion_date, active_b["id"])
                )

        # Clear the drafts for this month
        conn.execute("DELETE FROM budget_drafts WHERE target_month = ?", (target_month,))
        conn.commit()

    return {"status": "success", "message": f"Draft committed for {target_month}"}
