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


# ── Levenshtein distance & fuzzy duplicate check helpers ─────────────────────

def _levenshtein_distance(s1: str, s2: str) -> int:
    """Pure Python Levenshtein distance computation."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def _is_duplicate(row_date: str, row_desc: str, row_amount: float, conn) -> bool:
    """Fuzzy-check duplicate records using Levenshtein distance < 5 (matching the R app's LV logic)."""
    candidates = conn.execute(
        """SELECT description FROM expenses
           WHERE date = ? AND ABS(amount - ?) < 0.01""",
        (row_date, row_amount),
    ).fetchall()

    if not candidates:
        return False

    s1 = row_desc.lower().strip()
    for cand in candidates:
        s2 = cand["description"].lower().strip()
        if _levenshtein_distance(s1, s2) < 5 or s1 in s2 or s2 in s1:
            return True

    return False


# ── Format detection & parsing ───────────────────────────────────────────────

def _detect_and_parse(content: bytes, filename: str) -> pd.DataFrame:
    """
    Auto-detect the CSV format using exact first-line matching (matching the R app),
    and return a normalized DataFrame with:
        date, description, amount, category, payer
    """
    text = content.decode("utf-8", errors="replace")
    lines = text.splitlines()
    first_line = lines[0].strip() if lines else ""

    # Exact headers matching R app
    is_credit_card = "Status,Date,Description,Debit,Credit,Member Name" in first_line
    is_chase = "Transaction Date,Post Date,Description,Category,Type,Amount,Memo" in first_line
    is_chase_simple = "Trans. Date,Post Date,Description,Amount,Category" in first_line
    is_chase_bank = "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #" in first_line

    # 1. BECU Credit Card
    if is_credit_card:
        df = pd.read_csv(io.StringIO(text))
        df = df[df["Debit"].notna() & (df["Debit"] > 0)]
        
        df["date"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
        df["description"] = df["Description"].fillna("").astype(str).str.strip()
        df["amount"] = pd.to_numeric(df["Debit"], errors="coerce")
        df["category"] = ""
        
        # Payer detection
        member_name = df["Member Name"].fillna("").astype(str).str.upper()
        df["payer"] = "Joint"
        df.loc[member_name.str.contains("CALEB", na=False), "payer"] = "Caleb"
        df.loc[member_name.str.contains("RAE", na=False), "payer"] = "Rae"
        
        return df[["date", "description", "amount", "category", "payer"]].dropna(subset=["date", "amount"])

    # 2. Chase Credit (Type == "Sale" & Amount < 0)
    elif is_chase:
        df = pd.read_csv(io.StringIO(text))
        df = df[(df["Type"] == "Sale") & (df["Amount"].notna()) & (df["Amount"] < 0)]
        
        df["date"] = pd.to_datetime(df["Transaction Date"], errors="coerce").dt.strftime("%Y-%m-%d")
        df["description"] = df["Description"].fillna("").astype(str).str.strip()
        df["amount"] = pd.to_numeric(df["Amount"], errors="coerce").abs()
        df["category"] = df["Category"].fillna("").astype(str).str.strip()
        df["payer"] = "Joint"
        
        return df[["date", "description", "amount", "category", "payer"]].dropna(subset=["date", "amount"])

    # 3. Chase Simple (Amount > 0)
    elif is_chase_simple:
        df = pd.read_csv(io.StringIO(text))
        df = df[df["Amount"].notna() & (df["Amount"] > 0)]
        
        df["date"] = pd.to_datetime(df["Trans. Date"], errors="coerce").dt.strftime("%Y-%m-%d")
        df["description"] = df["Description"].fillna("").astype(str).str.strip()
        df["amount"] = pd.to_numeric(df["Amount"], errors="coerce")
        df["category"] = df["Category"].fillna("").astype(str).str.strip()
        df["payer"] = "Joint"
        
        return df[["date", "description", "amount", "category", "payer"]].dropna(subset=["date", "amount"])

    # 4. Chase Bank checking/saving (Details == "DEBIT" & Amount < 0)
    elif is_chase_bank:
        df = pd.read_csv(io.StringIO(text))
        df = df[(df["Details"] == "DEBIT") & (df["Amount"].notna()) & (df["Amount"] < 0)]
        
        df["date"] = pd.to_datetime(df["Posting Date"], errors="coerce").dt.strftime("%Y-%m-%d")
        df["description"] = df["Description"].fillna("").astype(str).str.strip()
        df["amount"] = pd.to_numeric(df["Amount"], errors="coerce").abs()
        df["category"] = ""
        df["payer"] = "Joint"
        
        return df[["date", "description", "amount", "category", "payer"]].dropna(subset=["date", "amount"])

    # 5. R Fallback (No header: X1=Date, X2=Amount < 0, X5=Description)
    try:
        df_no_hdr = pd.read_csv(io.StringIO(text), header=None)
        if df_no_hdr.shape[1] >= 5:
            test_date = pd.to_datetime(df_no_hdr[0], errors="coerce")
            test_amount = pd.to_numeric(df_no_hdr[1], errors="coerce")
            if test_date.notna().sum() > 0 and test_amount.notna().sum() > 0:
                df = pd.DataFrame()
                df["date"] = pd.to_datetime(df_no_hdr[0], errors="coerce").dt.strftime("%Y-%m-%d")
                df["amount"] = pd.to_numeric(df_no_hdr[1], errors="coerce")
                df["description"] = df_no_hdr[4].fillna("").astype(str).str.strip()
                df["category"] = ""
                df["payer"] = "Joint"
                # R Fallback filters charges only (X2 < 0)
                df = df[df["amount"] < 0]
                df["amount"] = df["amount"].abs()
                return df.dropna(subset=["date", "amount"])
    except Exception:
        pass

    # 6. Generic Case-Insensitive Column-Name Fallback
    df = pd.read_csv(io.StringIO(text))
    cols_lower = [c.lower().strip() for c in df.columns]
    col_map = {}
    for i, c in enumerate(cols_lower):
        if "date" in c and "date" not in col_map:
            col_map["date"] = df.columns[i]
        if "desc" in c and "description" not in col_map:
            col_map["description"] = df.columns[i]
        if "amount" in c or "total" in c and "amount" not in col_map:
            col_map["amount"] = df.columns[i]

    if len(col_map) == 3:
        df = df.rename(columns={v: k for k, v in col_map.items()})
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        df["description"] = df["description"].fillna("").astype(str).str.strip()
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").abs()
        df["category"] = ""
        df["payer"] = "Joint"
        df = df[df["amount"] > 0]
        return df[["date", "description", "amount", "category", "payer"]].dropna(subset=["date", "amount"])

    raise HTTPException(
        status_code=422,
        detail="Could not detect CSV format. Expected columns: date, description, amount.",
    )


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


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("")
async def stage_import(file: UploadFile = File(...)) -> list[dict]:
    """
    Parse the uploaded CSV, auto-detect format, auto-categorize rows,
    flag duplicates, detect internal batch duplicates — but do NOT persist.
    """
    content = await file.read()
    try:
        df = _detect_and_parse(content, file.filename or "")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"CSV parse error: {exc}") from exc

    staged: list[dict] = []
    seen_staged = set()  # To track internal duplicates within this file upload

    with get_db() as conn:
        for i, row in df.iterrows():
            row_date = str(row["date"]).strip()
            desc     = str(row["description"]).strip()
            amount   = float(row["amount"])

            # Map category and payer pre-detected by bank CSV parser, or fall back to defaults
            csv_cat   = str(row.get("category", "")).strip()
            csv_payer = str(row.get("payer", "")).strip()

            cat, sub = _auto_categorize(desc, conn)
            if csv_cat:
                cat = csv_cat
            payer = csv_payer if csv_payer else "Joint"

            # Check duplicate against existing DB
            dup = _is_duplicate(row_date, desc, amount, conn)

            # Check duplicate within this batch (internal duplicate)
            key = (row_date, desc, amount, payer)
            if key in seen_staged:
                dup = True
            else:
                seen_staged.add(key)

            staged.append({
                "original_index": int(i),  # type: ignore[arg-type]
                "date":           row_date,
                "description":    desc,
                "amount":         amount,
                "category":       cat,
                "subcategory":    sub,
                "payer":          payer,
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
