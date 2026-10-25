# Household Budgeting — project memory

Local-first desktop budgeting app. FastAPI + raw `sqlite3` backend, React 19 + Vite +
TypeScript frontend, SQLite at `data/budget.db` (demo: `data/demo_budget.db`).
Replaces an older R/Shiny monolith.

## Commands

| Task | Command |
|---|---|
| Backend tests | `source .venv/bin/activate && python -m pytest` (or `.venv/bin/python -m pytest`) |
| Frontend tests | `cd web && npm test` (vitest) |
| Frontend build | `cd web && npm run build` |
| Dev backend | `cd backend && uvicorn main:app --reload --port 8000` |
| Migration verification | `python scripts/verify_m0003_expansion.py [DB]` (works on a backup-API copy; never touches the original) |
| CSV import (legacy) | `python backend/migrate.py` |

## Git

`dev` branch. **Do not** create branches, pull, fetch, or push without explicit permission.
Commits are allowed. Prefer minimal diffs — the `edit` tool has previously reformatted whole
files (black-style churn; the `write` tool does it to Python too); use targeted `edit` for small
changes, full `write` only for multi-line rewrites.

## Budget model (sparse versioned, implemented 2026-10-25)

See `.posit/assistant/plans/2026-10-25-2159-plan.md`. It supersedes the physical per-month
`budget_YYYY_MM` tables of the 2026-10-03 plan (which are gone — no such tables exist anywhere).

Three tables; **the DDL lives only in `backend/migrations/m0003_per_month_budgets.py`** (inlined,
the migration imports nothing from the app):

- `budget_lines` — one row per (category, subcategory): `id` (stable, surfaced as `budget_id`),
  `line_key` (uuid4, assigned once, never derived), `category_id`, `subcategory_id` (NULL = none),
  `frequency` (CHECK: Monthly/Quarterly/Bi-annually/Annually), `created_at`. Unique index on
  `(category_id, COALESCE(subcategory_id,0))`. **Names are not stored** — joined from `categories`,
  so a rename is one `categories` update.
- `budget_amounts(line_key, effective_month, amount)` — amount for month M = row with the greatest
  `effective_month <= M`; `amount IS NULL` is a tombstone that ends the line.
- `month_plans(month, status 'inherited'|'confirmed', confirmed_at, expected_income)` — absent row
  = inherited, no income override; `expected_income NULL` = inherit from the latest earlier value.

`backend/budget_store.py` is the only module that touches them; `budget_schema.py` is just
`MONTH_RE`/`is_month`. Reads never write. Nothing in the store commits (callers own the transaction).
Keys: `resolve_view(conn, month) -> (rows, inherited)`, `lines_for_month`, `get_line`,
`line_versions`, `insert_line`/`update_line`/`delete_line`, `confirm_month`, `get_plan`,
`plan_statuses`, `set_expected_income`, `effective_expected_income`; `months_by_line` and
`lines_in_range` are compat shims that expand versions per month (open end = later of today and
the latest version month).

- **Apply scopes.** Every amount write takes `apply`: `forward` (default — from the month until the
  next explicit change), `month`, or `through` + `through=YYYY-MM`. A bounded scope restores the
  prior value the month after the range unless an explicit row is already there; explicit rows
  inside the range are overridden. Rows that don't change the effective value are dropped
  (normalization), so they never bound a later `forward` edit; a line with no rows left is deleted.
- **One line per (category, subcategory).** Re-adding an ended pair *revives* the same `line_key`;
  an active duplicate or a recategorize onto an occupied pair raises `LineConflict` (HTTP 409).
- **Frequency is one value per line, latest only.** Changing it rescales every version by
  `new_divisor/old_divisor` (monthly equivalents preserved; amounts stored unrounded). The migration
  does the same for legacy rows (see Migrations).
- **`inherited` means "month not confirmed"**, not "has no table". Confirming writes nothing to the
  budget. Expected income has no tombstone: a bounded income edit with no earlier value ends in an
  explicit `0`.
- Non-monthly lines are active in every month from their first version until ended; reporting
  accrues across the calendar-aligned period (Jan–Dec / halves / quarters; no `due_month`), starting
  at the first month *within the period* where the line is active.

Routers: `budgets.py` (`GET/POST/PATCH/DELETE`, `apply`/`through`, `/suggested` WMA over the 3
complete months preceding the target; 400 bad input, 404 not active in month, 409 conflict — a
failed request writes nothing), `month_plans.py` (`GET /api/month-plans?start&end` ≤36 months,
`GET /{month}`, `POST /{month}/confirm`, `PUT /{month}/income`), `reporting.py` (`budget_summary`
per month), `categories.py` (`/active`; rename updates `categories` + `expenses` only),
`expenses.py` (`/subcategories` trailing 12 months), `import_csv.py`, `goals.py`, `income.py`.

## Migrations

`backend/migrations/runner.py` keys on `PRAGMA user_version`; `Migration` dataclass; `MIGRATIONS`
tuple is **append-only**; `LATEST_VERSION = max(m.version for m in MIGRATIONS)` (currently 3).
`run_migrations` requires no pending transaction and sets `PRAGMA foreign_keys=ON` before `BEGIN`.
Helpers in `migrations/helpers.py`.

Shipped migrations (`m0001`, `m0002`) are **frozen — never edit**. `m0003` (filename predates the
model) is **shipped**: the live DB was migrated to v3 on 2026-10-24 (snapshot
`backups/pre_migration_v2_to_v3_20261024_222509.db`). Treat it as frozen — never edit; add `m0004`.

`m0003` expands legacy `budgets` windows into versions **event-based** (no dependency on today's
date, nothing pre-materialized): it evaluates the old predicate at each effective month and each
month after a conclusion, latest `(effective_date, id)` wins, and writes a version row where the
amount changes. Frequency = that of the most recent ever-in-effect row; earlier amounts are
converted to keep their monthly equivalent. Rows with unrepresentable ids are skipped and counted;
never-active lineages create no line. All-or-nothing: skips if `budget_lines` already has rows.

**Startup runs migrations and now snapshots first.** When migrations are pending and the DB has
data, the lifespan writes `backups/pre_migration_v{from}_to_v{to}_{stamp}.db` with SQLite's backup
API before migrating. `POST /api/backup` uses the same helper (`database.snapshot_database`). Take
DB copies with the backup API, never `shutil.copyfile` — a plain copy can miss WAL pages.

`scripts/verify_m0003_expansion.py` re-derives the old predicate independently, on a copy. Last run
against the live DB: OK — 59 lines / 108 versions over 96 months, idempotent.

### Legacy tables

- `budgets` (effective-dated) is expand-only and left `CREATE TABLE IF NOT EXISTS` in
  `database.py` `init_db()`. No runtime read path uses it; only `m0003`, `migrate.py` (the CSV
  importer writes legacy rows then calls `m0003.migrate`), `test_migrations.py`,
  `scripts/seed_demo_data.py`, and the verify script reference it.
- `budget_drafts` is retired: router, API client, hook, and DDL deleted. m0003 does **not** import
  drafts — the 147 rows stay in `data/budget.db` as an inert, reversible archive. Divergences in
  the 2026-08 draft (9 rows) are known and accepted.
- `goals.py` no longer writes synthetic budget rows; it only maintains `goal_budget_links`
  (`end_date` tracks the target month).

## Gotchas

- **App startup runs migrations.** Starting the server against `data/budget.db` migrates it
  (after a snapshot). The live DB is at `user_version=3`. Tests use temp DBs via
  `monkeypatch.setattr(database, "_DB_PATH", ...)`.
- `budget_store._resolve_ids` lazy-imports `routers.categories` (circular-import guard) — write
  paths only. `resolve_category_ids` reads `row["id"]`, so write-path connections need
  `row_factory = sqlite3.Row` (`database.get_db()` has it).
- Errors in budget/month-plan routers are raised **inside** the `with get_db()` block, before
  `conn.commit()`, so a failed request rolls back (this fixed the old commit-before-404 bug).
- `scripts/seed_demo_data.py` still builds its own legacy-shaped schema and seeds the legacy
  `budgets` table; it relies on startup migrations to produce versioned lines. Not updated.
- Frontend suggestion amounts from `/suggested` are **monthly-equivalents**. To prefill or apply
  one on a non-monthly line, multiply by `FREQUENCY_DIVISORS[frequency]`
  (`web/src/lib/budgetMath.ts`); there is no inverse helper.
- Dead CSS in `Planning.module.css` (`.suggestionUp` / `.suggestionDown`) predates any
  suggestions UI — there has never been one.
- Goals/Dashboard still compute goal "saved" client-side from **all** expenses by matching
  `goal_budget_links` category strings — that is category *spending*, not savings.
  `goals.target_month` is stored `YYYY-MM-01` while the rest of the app uses `YYYY-MM`.
  `expenses.goal_id` exists but is unused; `expense_type='Goal'` rows are matched by goal name
  (0 such rows in the live DB).
- `_spent_between` and `/suggested` still match expenses to budgets by category **strings**, not ids.
- **Two income concepts coexist.** `/api/income` + `income_sources` (one row; Dashboard and Goals
  read it) and the new per-month `month_plans.expected_income`. The old one is to be retired.
- **Planning's banner shows for every unconfirmed month** and there is no UI yet to confirm one
  (`POST /api/month-plans/{month}/confirm` exists), so it currently always shows.
- Live-data facts from the verify run: 4 legacy rows were never in effect (inverted windows,
  `effective 2026-07-01 / conclusion 2026-06-30`: Baby Items, Health/Baby Delivery ×2,
  Housing/Baby Items) and therefore produce no line; Health/Medication changed frequency
  (30 Monthly → kept as Quarterly, early amount converted to 90). 3 lineages have overlapping
  windows (resolved latest-effective-wins).

## Current state (2026-10-25)

The sparse-versioned rewrite is **implemented** (backend 190 tests, frontend 7, build clean;
verify script OK on a copy of the live DB). Committed on `dev` as `05fc550` and the live DB is
migrated to v3 (59 lines / 108 versions; legacy `budgets` and `budget_drafts` left intact).

Open for your veto (calls made during implementation): earlier-frequency amounts are converted to
preserve monthly equivalent (only Health/Medication affected live); a runtime frequency edit
rescales all versions; the 4 never-active inverted-window rows produce no line (re-enter them if
they were meant to exist). Tests: `test_budget_store.py` includes a seeded model-based test against
an independent oracle (mutation-checked); `test_reporting_partition.py` is the accrual regression
gate. The 10-03 plan is marked superseded; the 10-25 plan is marked implemented.

### Phase status vs `.posit/assistant/plans/2026-09-28-1903-plan.md`

| Phase | Status |
|---|---|
| 0 migration runner, category IDs | Done; "contract" step (drop legacy string columns) not done |
| 1 annual lines out of monthly reporting | Done (`/summary` → `{monthly, non_monthly}`; Dashboard + Reporting use it) |
| 2 category agility, rename by ID | Done; contract step not done |
| 3 month-end sweep into goals | **Not started** — no `sweeps.py`, no frontend/hook; `sweep_rules` and `closed_months` exist with 0 rows |
| 4 month-by-month budgeting | Backend done (versioned lines, apply scopes, month plans + income endpoints); UI partial — banner copy only, no "Keep as is" / "Applies to" control, no status strip, no turnover modal, no income input |

Because Phase 3 doesn't exist, the dropped synthetic-budget writes in `goals.py` are **not**
compensated: goals currently drive no monthly savings amount.

### Remaining

1. Planning UI: month status strip (Inherited/Confirmed chips) with Keep as is / Edit; an
   "Applies to: this month / through <month> / until changed" control wired to `apply`/`through`;
   expected-income input; hooks + API client for `/api/month-plans`.
2. Wire `useSuggestedBudgets(month)` into `Planning.tsx` (hook and `fetchSuggestedBudgets` exist
   but are unused) — suggestions surface, "Apply" converting monthly-equivalent → per-period for
   non-monthly lines, and a `Planning.test.tsx` covering that conversion.
3. Blocking turnover modal on boot (see decisions) — needs a baseline so history isn't prompted.
4. Phase 3 sweep: `m0004` for `goal_allocations` + annual-bill funds, sweep endpoints/UI; retire
   `income_sources` and move Dashboard/Goals to per-month income.
5. Decide whether to amend the 09-28 plan in place or let the later plans supersede it.

### Design decisions (decided 2026-10-24; not yet implemented)

- **Periods stay calendar-aligned** (Jan–Dec / halves / quarters). No `due_month`.
- **Expected income** is a manual per-month input, inherited forward like budget lines (stored on
  `month_plans`; endpoints exist). `income_sources` is to be retired or migrated.
- **Leftover** = expected income − actual spend − annual reserve. Each annual/non-monthly line's
  monthly equivalent is reserved and credited to a tracked per-line fund in the ledger; when the
  bill hits it draws the fund down (a short fund reduces leftover). Shown as its own
  "Reserved for irregular bills" line. Negative leftover sweeps nothing.
- **Sweep rules:** fixed amounts first (priority order), then percentages of the remainder.
  Percentages < 100 leave the rest as "Unallocated" (kept, not rescaled). A goal that reaches its
  target leaves its share Unallocated (does **not** overflow to the next goal).
- **Goal money:** append-only `goal_allocations` ledger (`goal_id`, `month`, `amount`, `kind`);
  balance = sum, withdrawals are negative rows. Not `expenses` rows. Annual-bill funds reuse it.
- **Turnover UX:** blocking modal on boot when the prior month is unconfirmed/unswept — 3 steps:
  confirm budget → review leftover → approve sweep.
- **Editing scope:** every budget edit offers "Applies to: this month / through <chosen month> /
  until changed" (backend done; default `forward`).
- **UI direction (not formally decided):** Goals cards show saved balance, monthly contribution,
  "needs $X/month" vs sweep delivery; group Planning lines into Monthly vs Irregular bills;
  consider renaming Settings → Import.
