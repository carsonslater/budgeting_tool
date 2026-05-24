"""
routers/expenses.py — Expense CRUD + category/payer lookups.

Routes:
    GET    /api/expenses              list (supports ?start=&end=&category=&payer=)
    POST   /api/expenses              create
    PATCH  /api/expenses/{id}         update
    DELETE /api/expenses/{id}         delete
    GET    /api/expenses/categories   distinct categories
    GET    /api/expenses/payers       distinct payers
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from database import get_db

router = APIRouter(prefix="/api/expenses", tags=["expenses"])


# ── Pydantic models ──────────────────────────────────────────────────────────

class ExpenseCreate(BaseModel):
    date: str
    description: str = ""
    category: str = ""
    subcategory: str = ""
    amount: float = 0.0
    payer: str = ""
    expense_type: str = "Monthly"


class ExpenseUpdate(BaseModel):
    date: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    amount: Optional[float] = None
    payer: Optional[str] = None
    expense_type: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _row_to_dict(row) -> dict:
    return dict(row)


# ── Routes ───────────────────────────────────────────────────────────────────

# NOTE: static paths must be declared BEFORE the /{id} path to avoid shadowing.

@router.get("/categories")
def list_categories() -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT category FROM expenses WHERE category != '' ORDER BY category"
        ).fetchall()
    return [r["category"] for r in rows]


@router.get("/payers")
def list_payers() -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT payer FROM expenses WHERE payer != '' ORDER BY payer"
        ).fetchall()
    return [r["payer"] for r in rows]


@router.get("")
def list_expenses(
    start: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
    end:   Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
    category: Optional[str] = Query(None),
    payer:    Optional[str] = Query(None),
) -> list[dict]:
    sql = "SELECT * FROM expenses WHERE 1=1"
    params: list = []
    if start:
        sql += " AND date >= ?"
        params.append(start)
    if end:
        sql += " AND date <= ?"
        params.append(end)
    if category:
        sql += " AND category = ?"
        params.append(category)
    if payer:
        sql += " AND payer = ?"
        params.append(payer)
    sql += " ORDER BY date DESC, id DESC"

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


@router.post("", status_code=201)
def create_expense(body: ExpenseCreate) -> dict:
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO expenses (date, description, category, subcategory,
                                     amount, payer, expense_type)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (body.date, body.description, body.category, body.subcategory,
             body.amount, body.payer, body.expense_type),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _row_to_dict(row)


@router.patch("/{expense_id}")
def update_expense(expense_id: int, body: ExpenseUpdate) -> dict:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [expense_id]

    with get_db() as conn:
        conn.execute(
            f"UPDATE expenses SET {set_clause} WHERE id = ?", values
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Expense not found")
    return _row_to_dict(row)


@router.delete("/{expense_id}", status_code=204)
def delete_expense(expense_id: int) -> None:
    with get_db() as conn:
        result = conn.execute(
            "DELETE FROM expenses WHERE id = ?", (expense_id,)
        )
        conn.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Expense not found")
