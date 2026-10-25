"""
m0003_per_month_budgets — turn the effective-dated `budgets` table into the sparse
versioned budget model: ``budget_lines``, ``budget_amounts`` and ``month_plans``.

(The filename predates the model; the registry slot is version 3 and the module is
unshipped, so it was rewritten in place.)

Model
~~~~~
* ``budget_lines``   one row per (category, subcategory): a stable ``line_key`` (uuid4,
  assigned once, never derived), the two category ids, and the line's ``frequency``.
* ``budget_amounts`` the per-period amount for a line from ``effective_month`` onward.
  The amount for month M is the row with the greatest ``effective_month <= M``;
  ``amount IS NULL`` is a tombstone that ends the line.
* ``month_plans``    confirmed state and per-month expected income.  An absent row means
  "inherited, no income override".

The DDL is inlined here on purpose and this module imports nothing from the app: a
migration is a frozen snapshot, so a later change to a runtime module must not
change what it does on a fresh database.

Expand only
~~~~~~~~~~~
`budgets` is left untouched, as is the retired ``budget_drafts`` table (147 rows in the
live DB), which is deliberately **not** read: it was staging for the old per-month
editor and cannot be reconciled line-for-line with "inherit the previous month".

Window -> versions
~~~~~~~~~~~~~~~~~~
A legacy row is active in month M exactly when::

    effective_date <= last_day(M)
    AND (conclusion_date IS NULL OR conclusion_date >= first_day(M))

and when several rows of one lineage are active, the latest ``(effective_date, id)``
wins.  That is the predicate the routers used before this migration.  The set of months
a lineage's state can change in is small and known: the month of each ``effective_date``
and the month *after* each ``conclusion_date``.  The predicate is evaluated at exactly
those months and a version row is written wherever the amount changes (``None -> x`` is a
start, ``x -> None`` a tombstone).  Nothing depends on today's date and no month tables
are materialized.

Frequency
~~~~~~~~~
``frequency`` is one value per line: that of the most recent legacy row that was ever in
effect (``max(effective_date, id)``).  Earlier rows with a different frequency are
converted so their *monthly equivalent* is preserved
(``amount * divisor(final) / divisor(row)``); otherwise a historical ``100`` per month
would be re-read as ``100`` per year.  The earlier cadence is not recoverable afterwards —
that is the accepted cost of keeping only the latest frequency.

Lineage identity
~~~~~~~~~~~~~~~~
Rows are grouped by surrogate key ``(category_id, subcategory_id)`` — names can be
renamed, ids cannot.  A row whose ids cannot be represented (NULL ``category_id``, or a
non-blank subcategory with a NULL id) is skipped and counted.  None exist in the live
database.  A lineage that was never in effect (e.g. ``effective_date`` after
``conclusion_date``) produces no line.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import date, datetime, timedelta

# ── Inline schema (frozen with this migration) ───────────────────────────────

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS budget_lines (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        line_key       TEXT    NOT NULL UNIQUE,
        category_id    INTEGER NOT NULL REFERENCES categories(id),
        subcategory_id INTEGER REFERENCES categories(id),
        frequency      TEXT    NOT NULL DEFAULT 'Monthly'
                       CHECK (frequency IN ('Monthly','Quarterly','Bi-annually','Annually')),
        created_at     TEXT    NOT NULL
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_budget_lines_target
        ON budget_lines (category_id, COALESCE(subcategory_id, 0))
    """,
    """
    CREATE TABLE IF NOT EXISTS budget_amounts (
        line_key        TEXT NOT NULL REFERENCES budget_lines(line_key) ON DELETE CASCADE,
        effective_month TEXT NOT NULL
                        CHECK (effective_month GLOB '[0-9][0-9][0-9][0-9]-[01][0-9]'),
        amount          REAL,
        PRIMARY KEY (line_key, effective_month)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE IF NOT EXISTS month_plans (
        month           TEXT PRIMARY KEY
                        CHECK (month GLOB '[0-9][0-9][0-9][0-9]-[01][0-9]'),
        status          TEXT NOT NULL DEFAULT 'inherited'
                        CHECK (status IN ('inherited','confirmed')),
        confirmed_at    TEXT,
        expected_income REAL
    )
    """,
)

# Copied, not imported: this migration must not depend on runtime modules.
_DIVISORS = {"Monthly": 1, "Quarterly": 3, "Bi-annually": 6, "Annually": 12}

# Explicit order, positional access throughout: migration code must not depend on
# the caller having set ``row_factory``.
_LEGACY_COLUMNS = (
    "id",
    "category",
    "subcategory",
    "limit_amount",
    "frequency",
    "effective_date",
    "conclusion_date",
    "category_id",
    "subcategory_id",
)
_ID, _CAT, _SUB, _LIMIT, _FREQ, _EFF, _CONCL, _CAT_ID, _SUB_ID = range(9)


# ── Date helpers ─────────────────────────────────────────────────────────────


def _is_month(value: str) -> bool:
    return (
        len(value) == 7
        and value[4] == "-"
        and value[:4].isdigit()
        and value[5:].isdigit()
        and 1 <= int(value[5:]) <= 12
    )


def _shift_month(month: str, delta: int) -> str:
    index = int(month[:4]) * 12 + int(month[5:7]) - 1 + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def _month_of(value: str, row_id: int) -> str:
    """``YYYY-MM-DD`` -> ``YYYY-MM``; raises on a malformed date."""
    month = (value or "")[:7]
    if not _is_month(month):
        raise ValueError(
            f"budgets.id={row_id} has an invalid date {value!r}; expected ISO YYYY-MM-DD"
        )
    return month


def _month_bounds(month: str) -> tuple[str, str]:
    """First and last day of ``month`` as ISO strings, for the window predicate."""
    year, mon = int(month[:4]), int(month[5:7])
    first = f"{year:04d}-{mon:02d}-01"
    last = (date(year, mon, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return first, last.isoformat()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ── Lineage and version construction ─────────────────────────────────────────


def _lineage(row) -> tuple | None:
    """
    The conceptual-line identity of a legacy row, or ``None`` if unrepresentable.

    ``(category_id, subcategory_id)``; ``subcategory_id`` is ``None`` for a blank
    subcategory.  A NULL ``category_id`` or a non-blank subcategory with no id cannot
    be stored in ``budget_lines`` and is skipped by the caller.
    """
    if row[_CAT_ID] is None:
        return None
    if row[_SUB_ID] is None and (row[_SUB] or "").strip():
        return None
    return (row[_CAT_ID], row[_SUB_ID])


def _active_at(rows: list, month: str) -> list:
    """Rows of one lineage in effect in ``month`` (the pre-migration predicate)."""
    first, last = _month_bounds(month)
    out = []
    for row in rows:
        conclusion = row[_CONCL] or None
        if row[_EFF] <= last and (conclusion is None or conclusion >= first):
            out.append(row)
    return out


def _select_at(rows: list, month: str):
    """The single winning row in ``month``: latest ``(effective_date, id)``."""
    active = _active_at(rows, month)
    return max(active, key=lambda r: (r[_EFF], r[_ID])) if active else None


def _event_months(rows: list) -> list[str]:
    """Months in which a lineage's state may change."""
    months = set()
    for row in rows:
        months.add(_month_of(row[_EFF], row[_ID]))
        if (row[_CONCL] or "").strip():
            months.add(_shift_month(_month_of(row[_CONCL], row[_ID]), 1))
    return sorted(months)


def _divisor(frequency: str) -> int:
    return _DIVISORS.get(frequency, 1)


def build_versions(rows: list):
    """
    Collapse one lineage's legacy windows into ``(frequency, versions, converted)``.

    ``versions`` is a list of ``(effective_month, amount | None)`` in ascending order,
    ``None`` being a tombstone.  ``converted`` counts versions whose amount had to be
    rescaled because the row's frequency differs from the line's final frequency.
    Returns ``None`` when the lineage was never in effect.
    """
    events = _event_months(rows)
    selected = [(month, _select_at(rows, month)) for month in events]
    ever = [row for _, row in selected if row is not None]
    if not ever:
        return None

    newest = max(ever, key=lambda r: (r[_EFF], r[_ID]))
    final = newest[_FREQ] if newest[_FREQ] in _DIVISORS else "Monthly"

    versions: list[tuple[str, float | None]] = []
    converted = 0
    previous: float | None = None
    for month, row in selected:
        if row is None:
            amount = None
        elif row[_FREQ] == final:
            amount = row[_LIMIT]
        else:
            amount = row[_LIMIT] / _divisor(row[_FREQ]) * _divisor(final)
            converted += 1
        if amount != previous:
            versions.append((month, amount))
            previous = amount
    return final, versions, converted


# ── Migration ────────────────────────────────────────────────────────────────


def create_tables(conn: sqlite3.Connection) -> None:
    for statement in _DDL:
        conn.execute(statement)


def _existing_rows(conn: sqlite3.Connection) -> list:
    sql = f"SELECT {', '.join(_LEGACY_COLUMNS)} FROM budgets ORDER BY id"
    return conn.execute(sql).fetchall()


def expand(conn: sqlite3.Connection) -> dict:
    """
    Write one line (plus sparse versions) per legacy lineage.

    Returns a summary: ``lines``, ``versions``, ``converted`` (rescaled amounts),
    ``never_active`` (lineages with no month in effect) and ``skipped`` (rows whose ids
    cannot be represented).
    """
    rows = _existing_rows(conn)
    summary = {"lines": 0, "versions": 0, "converted": 0, "never_active": 0, "skipped": 0}

    # Surface malformed dates before writing anything.
    for row in rows:
        _month_of(row[_EFF], row[_ID])
        if (row[_CONCL] or "").strip():
            _month_of(row[_CONCL], row[_ID])

    groups: dict[tuple, list] = {}
    for row in rows:
        key = _lineage(row)
        if key is None:
            summary["skipped"] += 1
            continue
        groups.setdefault(key, []).append(row)

    if summary["skipped"]:
        print(
            f"[m0003] skipped {summary['skipped']} legacy budget row(s) with "
            "unrepresentable category ids"
        )

    for (category_id, subcategory_id), group in groups.items():
        built = build_versions(group)
        if built is None:
            summary["never_active"] += 1
            continue
        frequency, versions, converted = built

        line_key = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO budget_lines
                 (line_key, category_id, subcategory_id, frequency, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (line_key, category_id, subcategory_id, frequency, _now()),
        )
        conn.executemany(
            "INSERT INTO budget_amounts (line_key, effective_month, amount) VALUES (?, ?, ?)",
            [(line_key, month, amount) for month, amount in versions],
        )
        summary["lines"] += 1
        summary["versions"] += len(versions)
        summary["converted"] += converted
    return summary


def migrate(conn: sqlite3.Connection) -> None:
    from .helpers import table_exists

    create_tables(conn)

    # `budgets` exists in every baseline, but stay defensive: a database created
    # exclusively from init_db() plus an early runner could theoretically lack it.
    if not table_exists(conn, "budgets"):
        return

    # All-or-nothing: the runner wraps this in one transaction, so any rows here mean a
    # previous run (or a legacy CSV import) already populated the model.
    if conn.execute("SELECT 1 FROM budget_lines LIMIT 1").fetchone():
        return

    expand(conn)
