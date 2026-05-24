"""
routers/import_csv.py — CSV import staging and confirmation.

Routes:
    POST /api/import          Upload CSV, auto-detect format, return staged rows
    POST /api/import/confirm  Accept staged rows, run duplicate check, insert

Supported CSV formats (matching the original R app):
    - BECU Credit Card   : Date, Description, Amount (debit positive)
    - Chase Credit        : Transaction Date, Description, Amount (credit positive → negate)
    - Chase Bank          : Details, Posting Date, Description, Amount, ...
    - Generic             : date, description, amount columns (case-insensitive)
"""

from __future__ import annotations

import io
from datetime import date
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from database import get_db

router = APIRouter(prefix="/api/import", tags=["import"])


# ── Pydantic models ──────────────────────────────────────────────────────────

class StagedRow(BaseModel):
    date: str
    description: str
    amount: float
    category: str = ""
    subcategory: str = ""
    payer: str = ""
    expense_type: str = "Monthly"
    is_duplicate: bool = False
    original_index: Optional[int] = None


class ConfirmImportRequest(BaseModel):
    rows: list[StagedRow]


# ── Format detection & parsing ───────────────────────────────────────────────

def _detect_and_parse(content: bytes, filename: str) -> pd.DataFrame:
    """
    Auto-detect the CSV format and return a normalised DataFrame with columns:
        date, description, amount
    Amount is always positive (expense) after normalisation.
    """
    text = content.decode("utf-8", errors="replace")
    df = pd.read_csv(io.StringIO(text))
    cols_lower = [c.lower().strip() for c in df.columns]

    # ── Chase Bank (checking) ────────────────────────────────────────────────
    # Columns: Details, Posting Date, Description, Amount, Type, Balance, ...
    if "posting date" in cols_lower or "details" in cols_lower:
        df.columns = [c.lower().strip() for c in df.columns]
        df = df.rename(columns={"posting date": "date", "description": "description"})
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").abs()
        return df[["date", "description", "amount"]].dropna()

    # ── Chase Credit ─────────────────────────────────────────────────────────
    # Columns: Transaction Date, Post Date, Description, Category, Type, Amount, ...
    if "transaction date" in cols_lower:
        df.columns = [c.lower().strip() for c in df.columns]
        df = df.rename(columns={"transaction date": "date"})
        # Chase credit: negative = purchase
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce") * -1
        df = df[df["amount"] > 0]  # keep charges only
        return df[["date", "description", "amount"]].dropna()

    # ── BECU Credit Card ─────────────────────────────────────────────────────
    # Columns: Date, Description, Amount   (debit is positive already in BECU)
    if set(["date", "description", "amount"]).issubset(set(cols_lower)):
        df.columns = [c.lower().strip() for c in df.columns]
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").abs()
        df = df[df["amount"] > 0]
        return df[["date", "description", "amount"]].dropna()

    # ── Generic fallback ─────────────────────────────────────────────────────
    # Try to find date/description/amount columns case-insensitively
    col_map = {}
    for i, c in enumerate(cols_lower):
        if "date" in c and "date" not in col_map:
            col_map["date"] = df.columns[i]
        if "desc" in c and "description" not in col_map:
            col_map["description"] = df.columns[i]
        if "amount" in c or "total" in c and "amount" not in col_map:
            col_map["amount"] = df.columns[i]

    if len(col_map) < 3:
        raise HTTPException(
            status_code=422,
            detail="Could not detect CSV format. Expected columns: date, description, amount.",
        )

    df = df.rename(columns={v: k for k, v in col_map.items()})
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").abs()
    df = df[df["amount"] > 0]
    return df[["date", "description", "amount"]].dropna()


def _auto_categorize(description: str, conn) -> tuple[str, str]:
    """
    Fuzzy-match description against existing expense descriptions to predict
    category and subcategory. Returns ("", "") if no match found.
    """
    try:
        from thefuzz import process  # type: ignore

        rows = conn.execute(
            "SELECT DISTINCT description, category, subcategory FROM expenses"
        ).fetchall()
        if not rows:
            return "", ""

        choices = {r["description"]: (r["category"], r["subcategory"]) for r in rows}
        match, score = process.extractOne(description, list(choices.keys()))
        if score and score >= 75:
            return choices[match]
    except ImportError:
        pass
    return "", ""


def _is_duplicate(row_date: str, row_desc: str, row_amount: float, conn) -> bool:
    """Check if an identical expense already exists in the DB."""
    existing = conn.execute(
        """SELECT id FROM expenses
           WHERE date = ? AND description = ? AND ABS(amount - ?) < 0.01
           LIMIT 1""",
        (row_date, row_desc, row_amount),
    ).fetchone()
    return existing is not None


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("")
async def stage_import(file: UploadFile = File(...)) -> list[dict]:
    """
    Parse the uploaded CSV, auto-detect format, auto-categorize rows,
    flag duplicates — but do NOT persist to the database.
    """
    content = await file.read()
    try:
        df = _detect_and_parse(content, file.filename or "")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"CSV parse error: {exc}") from exc

    staged: list[dict] = []
    with get_db() as conn:
        for i, row in df.iterrows():
            row_date = str(row["date"]).strip()
            desc     = str(row["description"]).strip()
            amount   = float(row["amount"])

            cat, sub = _auto_categorize(desc, conn)
            dup      = _is_duplicate(row_date, desc, amount, conn)

            staged.append({
                "original_index": int(i),  # type: ignore[arg-type]
                "date":           row_date,
                "description":    desc,
                "amount":         amount,
                "category":       cat,
                "subcategory":    sub,
                "payer":          "",
                "expense_type":   "Monthly",
                "is_duplicate":   dup,
            })

    return staged


@router.post("/confirm")
def confirm_import(body: ConfirmImportRequest) -> dict:
    """
    Insert staged rows into expenses. Rows marked is_duplicate are
    still inserted if the caller includes them (the UI should filter them).
    Returns counts of imported and skipped rows.
    """
    imported = 0
    skipped  = 0

    with get_db() as conn:
        for row in body.rows:
            # Re-check for duplicates at confirm time
            if _is_duplicate(row.date, row.description, row.amount, conn):
                skipped += 1
                continue

            conn.execute(
                """INSERT INTO expenses
                     (date, description, category, subcategory, amount, payer, expense_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (row.date, row.description, row.category, row.subcategory,
                 row.amount, row.payer, row.expense_type),
            )
            imported += 1

        conn.commit()

    return {"imported": imported, "skipped": skipped}
