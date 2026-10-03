"""
routers/categories.py — Category identity and active category querying.

Routes:
    GET   /api/categories/active    active budget lines' category/subcategory/frequency for a month
    GET   /api/categories           list all category surrogate records
    POST  /api/categories           create a category surrogate record
    PATCH /api/categories/{id}      rename a category surrogate record (dual-writes legacy string columns)
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from database import get_db

router = APIRouter(prefix="/api/categories", tags=["categories"])


# ── Pydantic models ──────────────────────────────────────────────────────────


class CategoryCreate(BaseModel):
    name: str
    kind: str = "category"  # 'category' or 'subcategory'


class CategoryUpdate(BaseModel):
    name: str


# ── Helpers ──────────────────────────────────────────────────────────────────


def _resolve_month(month_str: Optional[str]) -> tuple[int, int]:
    """Return (year, month) ints for a YYYY-MM string, defaulting to now."""
    if month_str:
        try:
            parts = month_str.split("-")
            return int(parts[0]), int(parts[1])
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid month format. Expected YYYY-MM")
    today = date.today()
    return today.year, today.month


def _last_day(year: int, month: int) -> date:
    """Last day of the given calendar month."""
    if month == 12:
        return date(year + 1, 1, 1) - timedelta(days=1)
    return date(year, month + 1, 1) - timedelta(days=1)


# ── Routes ───────────────────────────────────────────────────────────────────


@router.get("/active")
def list_active_categories(
    month: Optional[str] = Query(
        None, description="YYYY-MM, defaults to current month"
    )
) -> list[dict]:
    """
    Return active budget lines' category/subcategory/frequency for the specified month.
    """
    y, m = _resolve_month(month)
    first_day = f"{y:04d}-{m:02d}-01"
    last_day = _last_day(y, m).isoformat()

    with get_db() as conn:
        rows = conn.execute(
            """SELECT id as budget_id, category, subcategory, frequency, category_id, subcategory_id
               FROM budgets
               WHERE limit_amount > 0
                 AND effective_date <= ?
                 AND (conclusion_date IS NULL OR conclusion_date >= ?)
               ORDER BY category, subcategory""",
            (last_day, first_day),
        ).fetchall()

    return [dict(r) for r in rows]


@router.get("")
def list_categories(
    kind: Optional[str] = Query(None, description="'category' or 'subcategory'")
) -> list[dict]:
    """List category surrogate records from the categories table."""
    sql = "SELECT id, name, kind, created_date FROM categories WHERE 1=1"
    params: list = []
    if kind:
        if kind not in ("category", "subcategory"):
            raise HTTPException(status_code=400, detail="kind must be 'category' or 'subcategory'")
        sql += " AND kind = ?"
        params.append(kind)
    sql += " ORDER BY name, kind"

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [dict(r) for r in rows]


@router.post("", status_code=201)
def create_category(body: CategoryCreate) -> dict:
    """Create a new category surrogate record."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Category name cannot be empty")
    if body.kind not in ("category", "subcategory"):
        raise HTTPException(status_code=400, detail="kind must be 'category' or 'subcategory'")

    today_str = date.today().isoformat()
    with get_db() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO categories (name, kind, created_date) VALUES (?, ?, ?)",
                (name, body.kind, today_str),
            )
            conn.commit()
            cat_id = cur.lastrowid
        except sqlite3.IntegrityError:
            raise HTTPException(
                status_code=409,
                detail=f"Category '{name}' of kind '{body.kind}' already exists.",
            )

        row = conn.execute(
            "SELECT id, name, kind, created_date FROM categories WHERE id = ?", (cat_id,)
        ).fetchone()

    return dict(row)


@router.patch("/{category_id}")
def update_category(category_id: int, body: CategoryUpdate) -> dict:
    """
    Rename a category surrogate record by ID.
    Updates categories table and dual-writes string columns in budgets and expenses.
    """
    new_name = body.name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Category name cannot be empty")

    with get_db() as conn:
        row = conn.execute(
            "SELECT id, name, kind FROM categories WHERE id = ?", (category_id,)
        ).fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="Category not found")

        kind = row["kind"]
        try:
            conn.execute(
                "UPDATE categories SET name = ? WHERE id = ?",
                (new_name, category_id),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(
                status_code=409,
                detail=f"Category '{new_name}' of kind '{kind}' already exists.",
            )

        # Dual-write string columns for backwards compatibility during expand phase
        if kind == "category":
            conn.execute(
                "UPDATE budgets SET category = ? WHERE category_id = ?",
                (new_name, category_id),
            )
            conn.execute(
                "UPDATE expenses SET category = ? WHERE category_id = ?",
                (new_name, category_id),
            )
        else:  # subcategory
            conn.execute(
                "UPDATE budgets SET subcategory = ? WHERE subcategory_id = ?",
                (new_name, category_id),
            )
            conn.execute(
                "UPDATE expenses SET subcategory = ? WHERE subcategory_id = ?",
                (new_name, category_id),
            )

        conn.commit()

        updated_row = conn.execute(
            "SELECT id, name, kind, created_date FROM categories WHERE id = ?",
            (category_id,),
        ).fetchone()

    return dict(updated_row)
