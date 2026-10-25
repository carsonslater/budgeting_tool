"""
budget_store.py — the only module that touches the budget tables.

Storage is sparse and versioned (DDL: ``migrations/m0003_per_month_budgets.py``):

* ``budget_lines``   one row per (category, subcategory): ``line_key``, ids, ``frequency``
* ``budget_amounts`` ``(line_key, effective_month, amount)`` — the amount for month M is
  the row with the greatest ``effective_month <= M``; ``amount IS NULL`` is a tombstone
  that ends the line
* ``month_plans``    confirmed state and per-month expected income

"Reuse last month" is therefore zero writes, and a month before a line's first version
simply does not contain it.  Reads never write.

Line identity
~~~~~~~~~~~~~
``line_key`` is a ``uuid4`` assigned **once**, when a line is first created.  It is never
derived from live values: a key hashed from the category name breaks on rename, and one
derived from ``(category_id, subcategory_id)`` breaks on reclassification.  There is at
most one line per (category, subcategory); a line that has ended is *revived* by a later
``insert_line`` rather than duplicated, so its ``line_key`` and history continue.

Names are not stored on a line — they are joined from ``categories`` — so a rename is a
single ``categories`` update.

Apply scopes
~~~~~~~~~~~~
Every amount write takes an ``apply`` scope:

* ``forward`` (default) — from the month until the next explicit change
* ``month``             — that month only
* ``through``           — that month through a chosen later month (inclusive)

Callers own the transaction: nothing here commits.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import date, datetime
from typing import Any, Optional

from budget_math import FREQUENCY_DIVISORS
from budget_schema import is_month

APPLY_MODES = ("forward", "month", "through")


class LineConflict(Exception):
    """A (category, subcategory) pair is already used by another active line."""


# ── Small helpers ────────────────────────────────────────────────────────────


def new_line_key() -> str:
    """A fresh, stable identity for a budget line."""
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _require_month(month: str) -> str:
    if not is_month(month):
        raise ValueError(f"invalid month {month!r}; expected YYYY-MM")
    return month


def _require_frequency(frequency: str) -> str:
    if frequency not in FREQUENCY_DIVISORS:
        raise ValueError(
            f"invalid frequency {frequency!r}; expected one of {sorted(FREQUENCY_DIVISORS)}"
        )
    return frequency


def shift_month(month: str, delta: int) -> str:
    """``month`` plus ``delta`` calendar months, as ``YYYY-MM``."""
    _require_month(month)
    year, mon = int(month[:4]), int(month[5:7])
    index = year * 12 + (mon - 1) + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def month_of_date(value: str) -> str:
    """The ``YYYY-MM`` containing an ISO date (``YYYY-MM-DD``) or month string."""
    month = (value or "")[:7]
    if not is_month(month):
        raise ValueError(f"invalid date {value!r}; expected YYYY-MM or YYYY-MM-DD")
    return month


def _current_month() -> str:
    return date.today().strftime("%Y-%m")


def _dicts(cursor: sqlite3.Cursor) -> list[dict]:
    """Rows as dicts, independent of the connection's ``row_factory``."""
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _resolve_ids(
    conn, category: str, subcategory: str
) -> tuple[int | None, int | None]:
    """
    Surrogate keys for a category/subcategory name pair.

    Imported lazily: ``routers.categories`` imports this module at load time, so
    a module-level import here would be circular.
    """
    from routers.categories import resolve_category_ids

    return resolve_category_ids(conn, category, subcategory)


def _range_end(month: str, apply: str, through: Optional[str]) -> Optional[str]:
    """
    The last month an edit applies to, or ``None`` for "until changed".

    Validates the scope, so callers can (and do) call it before writing anything.
    """
    _require_month(month)
    if apply == "forward":
        return None
    if apply == "month":
        return month
    if apply == "through":
        if not through or not is_month(through):
            raise ValueError("apply='through' requires a valid 'through' month (YYYY-MM)")
        if through < month:
            raise ValueError(f"'through' ({through}) must not be before the month ({month})")
        return through
    raise ValueError(f"invalid apply {apply!r}; expected one of {list(APPLY_MODES)}")


# ── Reads: lines ─────────────────────────────────────────────────────────────

_EFFECTIVE_SQL = """
SELECT l.id              AS id,
       l.line_key        AS line_key,
       l.category_id     AS category_id,
       l.subcategory_id  AS subcategory_id,
       c.name            AS category,
       COALESCE(s.name, '') AS subcategory,
       a.amount          AS limit_amount,
       l.frequency       AS frequency,
       a.effective_month AS effective_since
FROM budget_lines l
JOIN categories c ON c.id = l.category_id
LEFT JOIN categories s ON s.id = l.subcategory_id
JOIN budget_amounts a
  ON a.line_key = l.line_key
 AND a.effective_month = (SELECT MAX(effective_month) FROM budget_amounts
                          WHERE line_key = l.line_key AND effective_month <= :month)
WHERE a.amount IS NOT NULL
"""


def lines_for_month(conn: sqlite3.Connection, month: str) -> list[dict]:
    """Every line in effect in ``month`` (no inheritance concept: it is just the model)."""
    _require_month(month)
    cur = conn.execute(
        _EFFECTIVE_SQL + " ORDER BY c.name, subcategory, l.line_key", {"month": month}
    )
    rows = _dicts(cur)
    for row in rows:
        row["month"] = month
    return rows


def get_line(conn: sqlite3.Connection, line_key: str, month: str) -> Optional[dict]:
    """One line as it stands in ``month``; ``None`` if absent or not active there."""
    _require_month(month)
    cur = conn.execute(
        _EFFECTIVE_SQL + " AND l.line_key = :key",
        {"month": month, "key": line_key},
    )
    rows = _dicts(cur)
    if not rows:
        return None
    rows[0]["month"] = month
    return rows[0]


def resolve_view(conn: sqlite3.Connection, month: str) -> tuple[list[dict], bool]:
    """
    The lines to show for ``month``, computed **without writing anything**.

    ``inherited`` is True while the month has not been confirmed (see
    :func:`confirm_month`); the lines themselves are always the effective ones.
    """
    return lines_for_month(conn, month), not is_confirmed(conn, month)


def _find_line(
    conn: sqlite3.Connection, category_id: int, subcategory_id: Optional[int]
) -> Optional[dict]:
    cur = conn.execute(
        """SELECT line_key, id, frequency FROM budget_lines
           WHERE category_id = ? AND COALESCE(subcategory_id, 0) = COALESCE(?, 0)""",
        (category_id, subcategory_id),
    )
    rows = _dicts(cur)
    return rows[0] if rows else None


def _effective_amount(
    conn: sqlite3.Connection, line_key: str, month: str
) -> Optional[float]:
    row = conn.execute(
        """SELECT amount FROM budget_amounts
           WHERE line_key = ? AND effective_month <= ?
           ORDER BY effective_month DESC LIMIT 1""",
        (line_key, month),
    ).fetchone()
    return None if row is None else row[0]


def line_versions(conn: sqlite3.Connection, line_key: str) -> Optional[dict]:
    """A line's frequency and every version row (``amount`` None = tombstone)."""
    head = conn.execute(
        "SELECT frequency FROM budget_lines WHERE line_key = ?", (line_key,)
    ).fetchone()
    if head is None:
        return None
    rows = conn.execute(
        "SELECT effective_month, amount FROM budget_amounts "
        "WHERE line_key = ? ORDER BY effective_month",
        (line_key,),
    ).fetchall()
    return {
        "line_key": line_key,
        "frequency": head[0],
        "versions": [{"effective_month": r[0], "amount": r[1]} for r in rows],
    }


# ── Reads: ranges (compat shims; expand versions into per-month results) ─────


def _load_versions(conn: sqlite3.Connection) -> dict[str, list[tuple[str, Optional[float]]]]:
    out: dict[str, list[tuple[str, Optional[float]]]] = {}
    for key, month, amount in conn.execute(
        "SELECT line_key, effective_month, amount FROM budget_amounts "
        "ORDER BY line_key, effective_month"
    ):
        out.setdefault(key, []).append((month, amount))
    return out


def _latest_version_month(conn: sqlite3.Connection) -> Optional[str]:
    row = conn.execute("SELECT MAX(effective_month) FROM budget_amounts").fetchone()
    return row[0] if row else None


def _range_bounds(
    conn: sqlite3.Connection, start_month: Optional[str], end_month: Optional[str]
) -> Optional[tuple[str, str]]:
    """Concrete ``(start, end)`` for a possibly open range, or ``None`` when empty."""
    if start_month is not None:
        _require_month(start_month)
    if end_month is not None:
        _require_month(end_month)

    first = conn.execute("SELECT MIN(effective_month) FROM budget_amounts").fetchone()[0]
    if first is None:
        return None
    start = start_month or first
    # An open end runs to the later of today and the latest explicit change: the lines
    # are still in force today even if nothing was edited recently.
    end = end_month or max(_current_month(), _latest_version_month(conn) or first)
    return (start, end) if start <= end else None


def _active_months(
    versions: list[tuple[str, Optional[float]]], start: str, end: str
) -> list[str]:
    """Months in ``[start, end]`` in which a line with these versions is active."""
    months: list[str] = []
    for index, (effective, amount) in enumerate(versions):
        if amount is None:
            continue
        nxt = versions[index + 1][0] if index + 1 < len(versions) else None
        lo = max(effective, start)
        hi = end if nxt is None else min(shift_month(nxt, -1), end)
        month = lo
        while month <= hi:
            months.append(month)
            month = shift_month(month, 1)
    return months


def months_by_line(
    conn: sqlite3.Connection,
    start_month: Optional[str] = None,
    end_month: Optional[str] = None,
) -> dict[str, list[str]]:
    """Map each ``line_key`` to the months in range where it is active."""
    bounds = _range_bounds(conn, start_month, end_month)
    if bounds is None:
        return {}
    start, end = bounds
    result: dict[str, list[str]] = {}
    for key, versions in _load_versions(conn).items():
        months = _active_months(versions, start, end)
        if months:
            result[key] = months
    return result


def lines_in_range(
    conn: sqlite3.Connection,
    start_month: Optional[str] = None,
    end_month: Optional[str] = None,
) -> list[dict]:
    """One row per (line, active month) in range, carrying a ``month`` column."""
    bounds = _range_bounds(conn, start_month, end_month)
    if bounds is None:
        return []
    start, end = bounds
    versions_by_key = _load_versions(conn)

    cur = conn.execute(
        """SELECT l.id AS id, l.line_key AS line_key, l.category_id AS category_id,
                  l.subcategory_id AS subcategory_id, c.name AS category,
                  COALESCE(s.name, '') AS subcategory, l.frequency AS frequency
           FROM budget_lines l
           JOIN categories c ON c.id = l.category_id
           LEFT JOIN categories s ON s.id = l.subcategory_id"""
    )
    out: list[dict] = []
    for line in _dicts(cur):
        versions = versions_by_key.get(line["line_key"], [])
        for month in _active_months(versions, start, end):
            amount = _amount_in(versions, month)
            out.append({**line, "limit_amount": amount, "month": month})
    out.sort(key=lambda r: (r["month"], r["category"], r["subcategory"], r["line_key"]))
    return out


def _amount_in(versions: list[tuple[str, Optional[float]]], month: str) -> Optional[float]:
    amount: Optional[float] = None
    for effective, value in versions:
        if effective > month:
            break
        amount = value
    return amount


# ── Writes: versions ─────────────────────────────────────────────────────────


def _normalize(conn: sqlite3.Connection, line_key: str) -> None:
    """
    Drop redundant version rows; delete the line if nothing remains.

    A row is redundant when its state equals the state before it (a leading tombstone
    equals "not yet started").  This never removes a row that changes an effective
    value, so history is preserved, and it is idempotent.
    """
    rows = conn.execute(
        "SELECT effective_month, amount FROM budget_amounts "
        "WHERE line_key = ? ORDER BY effective_month",
        (line_key,),
    ).fetchall()
    previous: Optional[float] = None
    redundant: list[str] = []
    for month, amount in rows:
        if amount == previous:
            redundant.append(month)
        else:
            previous = amount
    for month in redundant:
        conn.execute(
            "DELETE FROM budget_amounts WHERE line_key = ? AND effective_month = ?",
            (line_key, month),
        )
    if len(redundant) == len(rows):
        conn.execute("DELETE FROM budget_amounts WHERE line_key = ?", (line_key,))
        conn.execute("DELETE FROM budget_lines WHERE line_key = ?", (line_key,))


def _upsert_version(
    conn: sqlite3.Connection, line_key: str, month: str, amount: Optional[float]
) -> None:
    conn.execute(
        """INSERT INTO budget_amounts (line_key, effective_month, amount) VALUES (?, ?, ?)
           ON CONFLICT(line_key, effective_month) DO UPDATE SET amount = excluded.amount""",
        (line_key, month, amount),
    )


def _write_version(
    conn: sqlite3.Connection,
    line_key: str,
    month: str,
    amount: Optional[float],
    apply: str,
    through: Optional[str],
) -> None:
    """
    Write ``amount`` (``None`` = tombstone) at ``month`` under an apply scope.

    With a bounded scope the prior state is restored the month after the range, unless an
    explicit row already governs that month; explicit rows inside the range are
    overridden.  ``forward`` leaves later explicit rows alone.
    """
    end = _range_end(month, apply, through)

    restore_month: Optional[str] = None
    restore: Optional[float] = None
    if end is not None:
        restore_month = shift_month(end, 1)
        # Read before mutating: the value in force after the range may come from a row
        # inside it that is about to be overridden.
        restore = _effective_amount(conn, line_key, restore_month)
        conn.execute(
            "DELETE FROM budget_amounts "
            "WHERE line_key = ? AND effective_month > ? AND effective_month <= ?",
            (line_key, month, end),
        )

    _upsert_version(conn, line_key, month, amount)

    if restore_month is not None:
        explicit = conn.execute(
            "SELECT 1 FROM budget_amounts WHERE line_key = ? AND effective_month = ?",
            (line_key, restore_month),
        ).fetchone()
        if explicit is None:
            _upsert_version(conn, line_key, restore_month, restore)

    _normalize(conn, line_key)


def _set_frequency(
    conn: sqlite3.Connection, line_key: str, old: str, new: str
) -> None:
    """
    Change a line's frequency, rescaling every version so monthly equivalents hold.

    Only the latest frequency is kept (see the plan, S4); rescaling stops a past
    ``100`` per month being re-read as ``100`` per year.  Amounts are stored unrounded.
    """
    if old == new:
        return
    conn.execute(
        "UPDATE budget_amounts SET amount = amount * ? / ? "
        "WHERE line_key = ? AND amount IS NOT NULL",
        (FREQUENCY_DIVISORS[new], FREQUENCY_DIVISORS[old], line_key),
    )
    conn.execute(
        "UPDATE budget_lines SET frequency = ? WHERE line_key = ?", (new, line_key)
    )


def insert_line(
    conn: sqlite3.Connection,
    month: str,
    *,
    category: str,
    subcategory: str = "",
    limit_amount: float = 0.0,
    frequency: str = "Monthly",
    line_key: Optional[str] = None,
    apply: str = "forward",
    through: Optional[str] = None,
) -> dict:
    """
    Add a line to ``month`` under an apply scope, reviving an ended line if one exists.

    Raises :class:`LineConflict` when the (category, subcategory) pair is already active
    in ``month``, and ``ValueError`` for a bad month, scope, frequency or blank category.
    """
    _range_end(month, apply, through)  # validate before any write
    _require_frequency(frequency)

    category_id, subcategory_id = _resolve_ids(conn, category, subcategory)
    if category_id is None:
        raise ValueError("category is required")

    existing = _find_line(conn, category_id, subcategory_id)
    if existing is not None:
        key = existing["line_key"]
        if line_key is not None and line_key != key:
            raise ValueError("line_key does not match the existing line for this category")
        if _effective_amount(conn, key, month) is not None:
            raise LineConflict("a budget line for this category already exists in this month")
        _set_frequency(conn, key, existing["frequency"], frequency)
    else:
        key = line_key or new_line_key()
        conn.execute(
            """INSERT INTO budget_lines
                 (line_key, category_id, subcategory_id, frequency, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (key, category_id, subcategory_id, frequency, _now()),
        )

    _write_version(conn, key, month, limit_amount, apply, through)
    return get_line(conn, key, month) or {}


def update_line(
    conn: sqlite3.Connection,
    month: str,
    line_key: str,
    *,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    limit_amount: Optional[float] = None,
    frequency: Optional[str] = None,
    apply: str = "forward",
    through: Optional[str] = None,
) -> Optional[dict]:
    """
    Patch one line as seen from ``month``.  Returns the updated row, or ``None`` when the
    line is not active in ``month`` — in which case **nothing has been written**.

    Category and frequency edits are line-level (they apply to every month); an amount
    edit obeys ``apply``.  A frequency change rescales existing versions first, so an
    amount supplied in the same call is applied on top of the rescaled history.
    """
    _range_end(month, apply, through)  # validate before any write
    if frequency is not None:
        _require_frequency(frequency)

    current = get_line(conn, line_key, month)
    if current is None:
        return None

    if frequency is not None:
        _set_frequency(conn, line_key, current["frequency"], frequency)

    if category is not None or subcategory is not None:
        final_cat = category if category is not None else current["category"]
        final_sub = subcategory if subcategory is not None else current["subcategory"]
        category_id, subcategory_id = _resolve_ids(conn, final_cat, final_sub)
        if category_id is None:
            raise ValueError("category is required")
        clash = _find_line(conn, category_id, subcategory_id)
        if clash is not None and clash["line_key"] != line_key:
            raise LineConflict("another budget line already uses this category")
        conn.execute(
            "UPDATE budget_lines SET category_id = ?, subcategory_id = ? WHERE line_key = ?",
            (category_id, subcategory_id, line_key),
        )

    if limit_amount is not None:
        _write_version(conn, line_key, month, limit_amount, apply, through)

    return get_line(conn, line_key, month)


def delete_line(
    conn: sqlite3.Connection,
    month: str,
    line_key: str,
    *,
    apply: str = "forward",
    through: Optional[str] = None,
) -> int:
    """
    End a line from ``month`` under an apply scope (a tombstone, not a row delete).

    Returns 1, or 0 — with nothing written — when the line is not active in ``month``.
    """
    _range_end(month, apply, through)  # validate before any write
    if get_line(conn, line_key, month) is None:
        return 0
    _write_version(conn, line_key, month, None, apply, through)
    return 1


# ── Month plans: confirmed state and expected income ─────────────────────────


def is_confirmed(conn: sqlite3.Connection, month: str) -> bool:
    _require_month(month)
    row = conn.execute(
        "SELECT status FROM month_plans WHERE month = ?", (month,)
    ).fetchone()
    return row is not None and row[0] == "confirmed"


def _income_at(conn: sqlite3.Connection, month: str) -> tuple[Optional[str], Optional[float]]:
    """``(month the value was set in, value)`` in force at ``month``."""
    row = conn.execute(
        """SELECT month, expected_income FROM month_plans
           WHERE month <= ? AND expected_income IS NOT NULL
           ORDER BY month DESC LIMIT 1""",
        (month,),
    ).fetchone()
    return (None, None) if row is None else (row[0], row[1])


def effective_expected_income(conn: sqlite3.Connection, month: str) -> Optional[float]:
    """The expected income in force at ``month``, or ``None`` if never set."""
    _require_month(month)
    return _income_at(conn, month)[1]


def get_plan(conn: sqlite3.Connection, month: str) -> dict:
    """Status, confirmation time and effective expected income for one month."""
    _require_month(month)
    row = conn.execute(
        "SELECT status, confirmed_at FROM month_plans WHERE month = ?", (month,)
    ).fetchone()
    set_in, income = _income_at(conn, month)
    return {
        "month": month,
        "status": row[0] if row else "inherited",
        "confirmed_at": row[1] if row else None,
        "expected_income": income,
        "income_set_in": set_in,
    }


def plan_statuses(conn: sqlite3.Connection, start_month: str, end_month: str) -> list[dict]:
    """One ``{month, status, confirmed_at}`` per month in ``[start, end]``."""
    _require_month(start_month)
    _require_month(end_month)
    known = {
        r[0]: (r[1], r[2])
        for r in conn.execute(
            "SELECT month, status, confirmed_at FROM month_plans "
            "WHERE month >= ? AND month <= ?",
            (start_month, end_month),
        )
    }
    out: list[dict] = []
    month = start_month
    while month <= end_month:
        status, confirmed_at = known.get(month, ("inherited", None))
        out.append({"month": month, "status": status, "confirmed_at": confirmed_at})
        month = shift_month(month, 1)
    return out


def confirm_month(conn: sqlite3.Connection, month: str) -> dict:
    """
    Mark a month reviewed ("keep as is").  Idempotent; keeps the first ``confirmed_at``.
    Writes nothing to the budget itself.
    """
    _require_month(month)
    conn.execute(
        """INSERT INTO month_plans (month, status, confirmed_at) VALUES (?, 'confirmed', ?)
           ON CONFLICT(month) DO UPDATE SET
               status = 'confirmed',
               confirmed_at = COALESCE(month_plans.confirmed_at, excluded.confirmed_at)""",
        (month, _now()),
    )
    return get_plan(conn, month)


def _prune_plans(conn: sqlite3.Connection) -> None:
    conn.execute(
        "DELETE FROM month_plans "
        "WHERE status = 'inherited' AND confirmed_at IS NULL AND expected_income IS NULL"
    )


def set_expected_income(
    conn: sqlite3.Connection,
    month: str,
    amount: float,
    *,
    apply: str = "forward",
    through: Optional[str] = None,
) -> dict:
    """
    Set the expected income from ``month`` under an apply scope.

    Same range semantics as budget amounts.  There is no tombstone for income: when a
    bounded edit ends and no earlier value existed, the month after the range is given an
    explicit ``0`` so the new value does not leak past ``through``.
    """
    end = _range_end(month, apply, through)
    if amount is None or amount < 0:
        raise ValueError("expected income must be a non-negative number")

    restore_month: Optional[str] = None
    restore: Optional[float] = None
    if end is not None:
        restore_month = shift_month(end, 1)
        restore = _income_at(conn, restore_month)[1]
        conn.execute(
            "UPDATE month_plans SET expected_income = NULL WHERE month > ? AND month <= ?",
            (month, end),
        )

    conn.execute(
        """INSERT INTO month_plans (month, expected_income) VALUES (?, ?)
           ON CONFLICT(month) DO UPDATE SET expected_income = excluded.expected_income""",
        (month, amount),
    )

    if restore_month is not None:
        explicit = conn.execute(
            "SELECT 1 FROM month_plans WHERE month = ? AND expected_income IS NOT NULL",
            (restore_month,),
        ).fetchone()
        if explicit is None:
            conn.execute(
                """INSERT INTO month_plans (month, expected_income) VALUES (?, ?)
                   ON CONFLICT(month) DO UPDATE SET expected_income = excluded.expected_income""",
                (restore_month, 0.0 if restore is None else restore),
            )

    # Normalize: an explicit value equal to the one in force before it is redundant.
    previous: Optional[float] = None
    rows = conn.execute(
        "SELECT month, expected_income FROM month_plans "
        "WHERE expected_income IS NOT NULL ORDER BY month"
    ).fetchall()
    for row_month, value in rows:
        if value == previous:
            conn.execute(
                "UPDATE month_plans SET expected_income = NULL WHERE month = ?",
                (row_month,),
            )
        else:
            previous = value
    _prune_plans(conn)
    return get_plan(conn, month)


__all__: list[Any] = [
    "APPLY_MODES",
    "LineConflict",
    "confirm_month",
    "delete_line",
    "effective_expected_income",
    "get_line",
    "get_plan",
    "insert_line",
    "is_confirmed",
    "line_versions",
    "lines_for_month",
    "lines_in_range",
    "month_of_date",
    "months_by_line",
    "new_line_key",
    "plan_statuses",
    "resolve_view",
    "set_expected_income",
    "shift_month",
    "update_line",
]
