#!/usr/bin/env python
"""
verify_m0003_expansion.py — check the v3 migration against the legacy window query.

(The filename predates the sparse model; it is kept because AGENTS.md refers to it.)

Migration v3 replaces an effective-dated `budgets` table with versioned lines
(`budget_lines` / `budget_amounts`).  The old table answered "what is the budget for month
M?" with a window predicate::

    effective_date <= last_day(M)
    AND (conclusion_date IS NULL OR conclusion_date >= first_day(M))

and, where several rows of one (category, subcategory) lineage were active, the latest
``(effective_date, id)`` won.  This script proves the migration is faithful by evaluating
that predicate *independently* — it deliberately shares no code with the migration — and
comparing the result to the store's view for every month in a window that spans the whole
history plus a year beyond the last change.

Frequency is kept only as the latest value per line, with earlier amounts converted to
preserve their monthly equivalent.  The expectation computed here applies the same rule
from first principles (the newest row that was ever in effect decides the frequency).

Beyond the equivalence check it reports what the predicate does not express:

* legacy rows that were never in effect in any month (e.g. effective after concluded),
* lineages with overlapping windows, resolved by "latest effective date wins",
* lineages whose frequency changed, with the before/after amounts,
* rows the migration cannot represent (NULL category ids),
* ``budget_drafts`` rows, which the migration does not read, compared to the result.

Usage::

    python scripts/verify_m0003_expansion.py [DB_PATH]

``DB_PATH`` defaults to ``data/budget.db``.  The database is copied with SQLite's backup
API to a temporary file first, so the original is never touched.
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import budget_store  # noqa: E402
from migrations.runner import run_migrations  # noqa: E402

LEGACY_COLUMNS = (
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

# Restated here on purpose: the check must not share data with the code under test.
DIVISORS = {"Monthly": 1, "Quarterly": 3, "Bi-annually": 6, "Annually": 12}

# A malformed date should fail loudly, not walk a thousand years of months.
MAX_SPAN_MONTHS = 1200


# ── Independent re-implementation of the old predicate ───────────────────────


def month_bounds(month: str) -> tuple[date, date]:
    year, mon = int(month[:4]), int(month[5:7])
    first = date(year, mon, 1)
    last = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return first, last


def shift(month: str, delta: int) -> str:
    index = int(month[:4]) * 12 + int(month[5:7]) - 1 + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def as_date(value) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return date.fromisoformat(text[:10])


def representable(row) -> bool:
    """Rows the migration can store: a category id, and an id for any subcategory."""
    if row["category_id"] is None:
        return False
    return not (row["subcategory_id"] is None and (row["subcategory"] or "").strip())


def lineage(row) -> tuple:
    return (row["category_id"], row["subcategory_id"])


def active_rows(rows, month: str) -> list:
    """Every row active in ``month`` under the legacy predicate."""
    first, last = month_bounds(month)
    out = []
    for row in rows:
        eff = as_date(row["effective_date"])
        concl = as_date(row["conclusion_date"])
        if eff is None or eff > last:
            continue
        if concl is not None and concl < first:
            continue
        out.append(row)
    return out


def winners(rows, month: str) -> dict:
    """One winning row per lineage: latest ``(effective_date, id)``."""
    best: dict = {}
    for row in active_rows(rows, month):
        key = lineage(row)
        prev = best.get(key)
        if prev is None or (row["effective_date"], row["id"]) > (
            prev["effective_date"],
            prev["id"],
        ):
            best[key] = row
    return best


def convert(row, final: str) -> float:
    if row["frequency"] == final:
        return row["limit_amount"]
    return (
        row["limit_amount"]
        / DIVISORS.get(row["frequency"], 1)
        * DIVISORS.get(final, 1)
    )


# ── Loading ──────────────────────────────────────────────────────────────────


def load_legacy(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    sql = f"SELECT {', '.join(LEGACY_COLUMNS)} FROM budgets ORDER BY id"
    return conn.execute(sql).fetchall()


def horizon(rows) -> tuple[str, str]:
    """Earliest effective month .. a year past the last change."""
    effective = [str(r["effective_date"])[:7] for r in rows]
    concluded = [
        shift(str(r["conclusion_date"])[:7], 1)
        for r in rows
        if as_date(r["conclusion_date"]) is not None
    ]
    start = min(effective)
    end = shift(max(effective + concluded), 12)
    span = (int(end[:4]) - int(start[:4])) * 12 + int(end[5:7]) - int(start[5:7]) + 1
    if span > MAX_SPAN_MONTHS:
        raise ValueError(f"history spans {span} months ({start}..{end}); check for bad dates")
    return start, end


def months_between(start: str, end: str) -> list[str]:
    out, month = [], start
    while month <= end:
        out.append(month)
        month = shift(month, 1)
    return out


def snapshot(conn: sqlite3.Connection) -> tuple:
    return (
        sorted(tuple(r) for r in conn.execute("SELECT * FROM budget_lines")),
        sorted(tuple(r) for r in conn.execute("SELECT * FROM budget_amounts")),
    )


def money(value) -> float:
    return round(float(value), 6)


def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "budget.db"
    if not source.exists():
        print(f"no such database: {source}", file=sys.stderr)
        return 2

    tmpdir = Path(tempfile.mkdtemp(prefix="verify_m0003_"))
    copy = tmpdir / "budget.db"
    # SQLite's backup API, not a file copy: a database in WAL mode can hold committed
    # pages only in the -wal file, which a plain copy would miss.
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(copy)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    print(f"source : {source}")
    print(f"copy   : {copy}\n")

    conn = sqlite3.connect(copy)
    conn.row_factory = sqlite3.Row
    try:
        version_before = conn.execute("PRAGMA user_version;").fetchone()[0]
        applied = run_migrations(conn)
        version_after = conn.execute("PRAGMA user_version;").fetchone()[0]
        print(f"user_version: {version_before} -> {version_after} (applied {applied})")

        legacy = load_legacy(conn)
        if not legacy:
            print("no legacy rows; nothing to check")
            return 0

        usable = [r for r in legacy if representable(r)]
        skipped = [r for r in legacy if not representable(r)]
        start, end = horizon(legacy)
        months = months_between(start, end)
        n_lines = conn.execute("SELECT COUNT(*) FROM budget_lines").fetchone()[0]
        n_versions = conn.execute("SELECT COUNT(*) FROM budget_amounts").fetchone()[0]
        print(f"legacy rows: {len(legacy)}   checked months: {len(months)} ({start}..{end})")
        print(f"lines: {n_lines}   version rows: {n_versions}\n")

        failures = 0

        # Which row was ever in effect per lineage decides the final frequency.
        newest: dict = {}
        for month in months:
            for key, row in winners(usable, month).items():
                rank = (row["effective_date"], row["id"])
                if key not in newest or rank > newest[key][0]:
                    newest[key] = (rank, row["frequency"])
        final_frequency = {
            key: (freq if freq in DIVISORS else "Monthly") for key, (_, freq) in newest.items()
        }

        # 1. Every month reproduces the legacy predicate exactly.
        for month in months:
            expected = {
                key: (money(convert(row, final_frequency[key])), final_frequency[key])
                for key, row in winners(usable, month).items()
            }
            got = {
                (r["category_id"], r["subcategory_id"]): (
                    money(r["limit_amount"]),
                    r["frequency"],
                )
                for r in budget_store.lines_for_month(conn, month)
            }
            if expected != got:
                failures += 1
                print(f"MISMATCH {month}: {len(expected)} expected, {len(got)} present")
                for key in sorted(set(expected) | set(got), key=str):
                    if expected.get(key) != got.get(key):
                        print(f"    {key}: expected {expected.get(key)}  got {got.get(key)}")

        # 2. One line per ever-active lineage, and no line without a version.
        if n_lines != len(newest):
            failures += 1
            print(f"LINE COUNT: {n_lines} lines, {len(newest)} lineages were ever active")
        orphans = conn.execute(
            "SELECT COUNT(*) FROM budget_lines l WHERE NOT EXISTS "
            "(SELECT 1 FROM budget_amounts a WHERE a.line_key = l.line_key)"
        ).fetchone()[0]
        if orphans:
            failures += 1
            print(f"ORPHAN lines with no versions: {orphans}")

        # 3. Storage is normalized: no redundant row, no leading tombstone.
        for (key,) in conn.execute("SELECT line_key FROM budget_lines").fetchall():
            previous = None
            for row in conn.execute(
                "SELECT effective_month, amount FROM budget_amounts "
                "WHERE line_key = ? ORDER BY effective_month",
                (key,),
            ):
                if row["amount"] == previous:
                    failures += 1
                    print(f"REDUNDANT version {row['effective_month']} on line {key}")
                previous = row["amount"]

        # 4. Rows never in effect in any month.
        ever_active_ids = {
            row["id"] for month in months for row in active_rows(usable, month)
        }
        never = [r for r in usable if r["id"] not in ever_active_ids]
        if never:
            print(f"\nNOTE: {len(never)} legacy row(s) were never in effect in any month:")
            for r in never:
                print(
                    f"    id={r['id']:>3}  {r['category']} / {r['subcategory']}"
                    f"  eff={r['effective_date']}  concl={r['conclusion_date']}"
                )

        # 5. Overlapping windows (resolved by "latest effective date wins").
        overlaps: dict = {}
        for month in months:
            by_lineage: dict = {}
            for row in active_rows(usable, month):
                by_lineage.setdefault(lineage(row), []).append(row["id"])
            for key, ids in by_lineage.items():
                if len(ids) > 1:
                    overlaps.setdefault(key, set()).update(ids)
        if overlaps:
            print(f"\nNOTE: {len(overlaps)} lineage(s) have overlapping windows:")
            for key, ids in overlaps.items():
                print(f"    lineage {key}: row ids {sorted(ids)}")

        # 6. Frequency changes within a lineage, with the amounts as converted.
        by_lin: dict = {}
        for r in usable:
            by_lin.setdefault(lineage(r), []).append(r)
        for key, group in by_lin.items():
            freqs = {r["frequency"] for r in group if r["id"] in ever_active_ids}
            if len(freqs) > 1 and key in final_frequency:
                final = final_frequency[key]
                print(f"\nNOTE: lineage {key} changed frequency; kept {final!r}:")
                for r in sorted(group, key=lambda r: (r["effective_date"], r["id"])):
                    if r["id"] in ever_active_ids:
                        print(
                            f"    id={r['id']:>3} {r['category']} / {r['subcategory']}: "
                            f"{r['limit_amount']} {r['frequency']} "
                            f"({r['effective_date']}..{r['conclusion_date'] or 'open'})"
                            f"  ->  {convert(r, final):.2f} {final}"
                        )

        # 7. Rows the migration cannot represent.
        if skipped:
            print(f"\nNOTE: {len(skipped)} legacy row(s) have unrepresentable category ids:")
            for r in skipped:
                print(f"    id={r['id']:>3}  {r['category']!r} / {r['subcategory']!r}")

        # 8. Drafts the migration does not read.
        has_drafts = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='budget_drafts';"
        ).fetchone()
        if has_drafts:
            drafts = conn.execute(
                "SELECT target_month, category, subcategory, limit_amount, frequency "
                "FROM budget_drafts ORDER BY target_month"
            ).fetchall()
            if drafts:
                tally: dict = {}
                for d in drafts:
                    month = str(d["target_month"])[:7]
                    present = {
                        (r["category"], r["subcategory"], money(r["limit_amount"]), r["frequency"])
                        for r in budget_store.lines_for_month(conn, month)
                    }
                    same = (
                        d["category"],
                        d["subcategory"],
                        money(d["limit_amount"]),
                        d["frequency"],
                    ) in present
                    counts = tally.setdefault(month, [0, 0])
                    counts[0 if same else 1] += 1
                print(f"\nNOTE: budget_drafts holds {len(drafts)} row(s) the migration never reads:")
                for month, (ok, bad) in sorted(tally.items()):
                    print(f"    {month}: {ok} match the migrated budget, {bad} differ")

        # 9. Idempotency: re-applying the migration changes nothing.
        before = snapshot(conn)
        conn.execute("PRAGMA user_version = 2;")
        run_migrations(conn)
        if snapshot(conn) != before:
            failures += 1
            print("\nFAIL: re-running the migration changed the budget tables")
        else:
            print("\nidempotency: re-run left every line and version unchanged")

        print()
        if failures:
            print(f"FAILED: {failures} check(s) did not pass")
            return 1
        print("OK: every month matches the legacy window predicate")
        return 0
    finally:
        conn.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
