"""
routers/categories.py — Category identity and active category querying.

Routes:
    GET   /api/categories/active    active budget lines' category/subcategory/frequency for a month
    GET   /api/categories           list all category surrogate records
    PATCH /api/categories/{id}      rename a category surrogate record (dual-writes legacy string columns)

Internal API
~~~~~~~~~~~~
`resolve_category_ids(conn, category, subcategory)` is exported for use by every
write path (expenses, budgets, import confirm).  It returns `(category_id,
subcategory_id)` after INSERT-OR-IGNORE-ing both names into `categories`, so
every new row immediately carries surrogate keys.  The rename handler can then
be exact: it only rewrites strings on rows whose `*_id` matches **and** whose
string value still agrees with the pre-rename name, so a user's manual category
edit (which changes the string but leaves the old id) is never silently
overwritten.
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


class CategoryUpdate(BaseModel):
    name: str


# ── Internal helper (used by expense / budget / import write paths) ───────────


def resolve_category_ids(
    conn: sqlite3.Connection,
    category: str,
    subcategory: str,
) -> tuple[int | None, int | None]:
    """
    Return `(category_id, subcategory_id)` for the given string names.

    * INSERT OR IGNORE guarantees a row exists before we read it back, so the
      helper is safe to call from a transaction that hasn't committed yet.
    * Empty strings resolve to None — they mean "no category" and there is no
      categories row for an empty name.
    * The helper never creates a row with `name = ''`; it only resolves names
      that are genuinely present.
    """
    today = date.today().isoformat()
    cat_id: int | None = None
    sub_id: int | None = None

    cat = category.strip() if category else ""
    sub = subcategory.strip() if subcategory else ""

    if cat:
        conn.execute(
            "INSERT OR IGNORE INTO categories (name, kind, created_date) VALUES (?, 'category', ?)",
            (cat, today),
        )
        row = conn.execute(
            "SELECT id FROM categories WHERE name = ? AND kind = 'category'", (cat,)
        ).fetchone()
        if row:
            cat_id = row["id"]

    if sub:
        conn.execute(
            "INSERT OR IGNORE INTO categories (name, kind, created_date) VALUES (?, 'subcategory', ?)",
            (sub, today),
        )
        row = conn.execute(
            "SELECT id FROM categories WHERE name = ? AND kind = 'subcategory'", (sub,)
        ).fetchone()
        if row:
            sub_id = row["id"]

    return cat_id, sub_id


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


@router.patch("/{category_id}")
def update_category(category_id: int, body: CategoryUpdate) -> dict:
    """
    Rename a category surrogate record by ID.

    Dual-write safety: only updates a row's string column when BOTH the
    `*_id` matches AND the string still reflects the old name.  This prevents
    clobbering a user's manual recategorisation, which changes the string but
    leaves the original id in place.

    Tables covered: `categories`, `budgets`, `expenses`.
    Not covered (deferred, will be retired in Phase 4): `budget_drafts`.
    Not covered (deferred, will be retired in Phase 3): `goal_budget_links`.
    """
    new_name = body.name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Category name cannot be empty")

    with get_db() as conn:
        existing = conn.execute(
            "SELECT id, name, kind FROM categories WHERE id = ?", (category_id,)
        ).fetchone()

        if existing is None:
            raise HTTPException(status_code=404, detail="Category not found")

        old_name = existing["name"]
        kind = existing["kind"]

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

        # Dual-write: only touch rows whose id AND string still agree with the
        # pre-rename state.  A row whose string diverged was manually edited by
        # the user after the last backfill — leave it alone.
        if kind == "category":
            conn.execute(
                "UPDATE budgets SET category = ? WHERE category_id = ? AND category = ?",
                (new_name, category_id, old_name),
            )
            conn.execute(
                "UPDATE expenses SET category = ? WHERE category_id = ? AND category = ?",
                (new_name, category_id, old_name),
            )
        else:  # subcategory
            conn.execute(
                "UPDATE budgets SET subcategory = ? WHERE subcategory_id = ? AND subcategory = ?",
                (new_name, category_id, old_name),
            )
            conn.execute(
                "UPDATE expenses SET subcategory = ? WHERE subcategory_id = ? AND subcategory = ?",
                (new_name, category_id, old_name),
            )

        conn.commit()

        updated_row = conn.execute(
            "SELECT id, name, kind, created_date FROM categories WHERE id = ?",
            (category_id,),
        ).fetchone()

    return dict(updated_row)
