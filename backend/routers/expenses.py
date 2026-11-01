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

from datetime import date
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import budget_store
from database import get_db
from routers.categories import resolve_category_ids, select_expenses

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
            """SELECT DISTINCT COALESCE(c.name, e.category) AS category
                 FROM expenses e
                 LEFT JOIN categories c ON c.id = e.category_id
                WHERE COALESCE(c.name, e.category, '') != ''
                ORDER BY category"""
        ).fetchall()
    return [r["category"] for r in rows]


@router.get("/payers")
def list_payers() -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT payer FROM expenses WHERE payer != '' ORDER BY payer"
        ).fetchall()
    return [r["payer"] for r in rows]


@router.get("/subcategories")
def list_subcategories(category: Optional[str] = Query(None)) -> list[str]:
    """
    Distinct subcategories from expenses and from recent budget lines.

    Budget lines are read over the trailing 12 months (plan §11.3) — enough for a
    useful suggestion list without walking the whole history.
    """
    sql_exp = """SELECT DISTINCT COALESCE(s.name, e.subcategory) AS subcategory
                   FROM expenses e
                   LEFT JOIN categories c ON c.id = e.category_id
                   LEFT JOIN categories s ON s.id = e.subcategory_id
                  WHERE COALESCE(s.name, e.subcategory, '') != ''"""
    params_exp: list = []
    if category:
        sql_exp += " AND COALESCE(c.name, e.category, '') = ?"
        params_exp.append(category)

    today = date.today()
    start_month = budget_store.shift_month(f"{today:%Y-%m}", -11)

    with get_db() as conn:
        rows_exp = conn.execute(sql_exp, params_exp).fetchall()
        budget_rows = budget_store.lines_in_range(conn, start_month, None)

    subs = {r["subcategory"] for r in rows_exp if r["subcategory"]}
    subs.update(
        r["subcategory"]
        for r in budget_rows
        if r["subcategory"] and (not category or r["category"] == category)
    )
    return sorted(subs)


@router.get("")
def list_expenses(
    start: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
    category: Optional[str] = Query(None, description="Category name"),
    subcategory: Optional[str] = Query(None, description="Subcategory name"),
    category_id: Optional[int] = Query(None),
    subcategory_id: Optional[int] = Query(None),
    payer: Optional[str] = Query(None),
) -> list[dict]:
    """
    Expenses with `category` / `subcategory` resolved from their ids.

    Filters take either the id or the name; the name is matched against the
    resolved name, so it always agrees with what the response shows.
    """
    clauses: list[str] = []
    params: list = []
    if start:
        clauses.append("e.date >= ?")
        params.append(start)
    if end:
        clauses.append("e.date <= ?")
        params.append(end)
    if category_id is not None:
        clauses.append("e.category_id = ?")
        params.append(category_id)
    if category:
        clauses.append("COALESCE(c.name, e.category, '') = ?")
        params.append(category)
    if subcategory_id is not None:
        clauses.append("e.subcategory_id = ?")
        params.append(subcategory_id)
    if subcategory:
        clauses.append("COALESCE(s.name, e.subcategory, '') = ?")
        params.append(subcategory)
    if payer:
        clauses.append("e.payer = ?")
        params.append(payer)

    where = " AND ".join(clauses) if clauses else "1=1"
    with get_db() as conn:
        rows = select_expenses(
            conn, where, tuple(params), order="e.date DESC, e.id DESC"
        )
    return [_row_to_dict(r) for r in rows]


@router.post("", status_code=201)
def create_expense(body: ExpenseCreate) -> dict:
    with get_db() as conn:
        cat_id, sub_id = resolve_category_ids(conn, body.category, body.subcategory)
        cur = conn.execute(
            """INSERT INTO expenses (date, description, category, subcategory,
                                     amount, payer, expense_type, category_id, subcategory_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                body.date,
                body.description,
                body.category,
                body.subcategory,
                body.amount,
                body.payer,
                body.expense_type,
                cat_id,
                sub_id,
            ),
        )
        conn.commit()
        row = select_expenses(conn, "e.id = ?", (cur.lastrowid,))
    return _row_to_dict(row[0])


@router.patch("/{expense_id}")
def update_expense(expense_id: int, body: ExpenseUpdate) -> dict:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    with get_db() as conn:
        # If the caller is changing category or subcategory, resolve fresh surrogate
        # keys so the row stays rename-safe.  We need the final category/subcategory
        # values, which may be a mix of the patch fields and the existing row.
        if "category" in updates or "subcategory" in updates:
            existing = conn.execute(
                "SELECT category, subcategory FROM expenses WHERE id = ?", (expense_id,)
            ).fetchone()
            if existing is None:
                raise HTTPException(status_code=404, detail="Expense not found")
            final_cat = updates.get("category", existing["category"])
            final_sub = updates.get("subcategory", existing["subcategory"])
            cat_id, sub_id = resolve_category_ids(conn, final_cat, final_sub)
            updates["category_id"] = cat_id
            updates["subcategory_id"] = sub_id

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [expense_id]
        conn.execute(f"UPDATE expenses SET {set_clause} WHERE id = ?", values)
        conn.commit()
        row = select_expenses(conn, "e.id = ?", (expense_id,))

    if not row:
        raise HTTPException(status_code=404, detail="Expense not found")
    return _row_to_dict(row[0])


@router.delete("/{expense_id}", status_code=204)
def delete_expense(expense_id: int) -> None:
    with get_db() as conn:
        result = conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        conn.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Expense not found")
