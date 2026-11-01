# Household Budgeting — project memory

Local-first desktop budgeting app. FastAPI + raw `sqlite3` backend, React 19 + Vite +
TypeScript frontend, SQLite at `data/budget.db` (demo: `data/demo_budget.db`).
Replaces an older R/Shiny monolith.

## Commands

| Task | Command |
|---|---|
| Backend tests | `.venv/bin/python -m pytest` |
| Frontend tests | `cd web && npx vitest run` (or `npm test`) |
| Frontend build | `cd web && npm run build` (runs `tsc` then `vite build`) |
| Dev backend | `cd backend && uvicorn main:app --reload --port 8000` |
| Migration verification | `python scripts/verify_m0003_expansion.py [DB]` (works on a backup-API copy; never touches the original) |
| CSV import (legacy) | `python backend/migrate.py` |

## Git

`dev` branch. **Do not** create branches, pull, fetch, or push without explicit permission.
Commits are allowed when asked. Prefer minimal diffs. The `edit` tool and the `write` tool have both
caused black-style churn in Python, so use targeted edits for small changes.

**Committed and pushed.** The last feature commit is `ad316f0`, on `origin/dev`. It carries id-based
category reads plus, from `f4f8dd9`, the per-month Planning UI, the income consolidation, the
per-version frequency change, and migrations `m0004`/`m0005`. Later commits may only touch this file.
Check `git status` before assuming a file is clean.

## Budget model

Sparse and versioned. See `.posit/assistant/plans/2026-10-25-2159-plan.md` (implemented). It
supersedes the per-month `budget_YYYY_MM` tables of the 2026-10-03 plan, which no longer exist.

Three tables. **The DDL lives only in the migrations** (`m0003` creates them, `m0005` adds the
frequency column). Each migration is inlined and imports nothing from the app.

- `budget_lines`: one row per (category, subcategory). `id` (stable, surfaced as `budget_id`),
  `line_key` (uuid4, assigned once, never derived), `category_id`, `subcategory_id` (NULL = none),
  `frequency` (CHECK: Monthly/Quarterly/Bi-annually/Annually), `created_at`. Unique index on
  `(category_id, COALESCE(subcategory_id,0))`. Names are not stored here. They are joined from
  `categories`, so a rename is one `categories` update. `frequency` is a **cache** of the latest
  active version's frequency. Nothing computes a month's frequency from it.
- `budget_amounts(line_key, effective_month, amount, frequency)`: the state for month M is the row
  with the greatest `effective_month <= M`. `amount IS NULL` is a tombstone that ends the line, and
  its frequency is NULL.
- `month_plans(month, status 'inherited'|'confirmed', confirmed_at, expected_income)`: an absent row
  means inherited with no income override. `expected_income NULL` means inherit from the latest
  earlier value.

`backend/budget_store.py` is the only module that touches these tables. `budget_schema.py` holds only
`MONTH_RE` and `is_month`. Reads never write. The store never commits: callers own the transaction.
Keys: `resolve_view(conn, month) -> (rows, inherited)`, `lines_for_month`, `get_line`,
`line_versions`, `insert_line`, `update_line`, `delete_line`, `confirm_month`, `get_plan`,
`plan_statuses`, `set_expected_income`, `effective_expected_income`. `months_by_line` and
`lines_in_range` are compat shims that expand versions per month. An open end runs to the later of
today and the latest version month.

Rules:

- **Apply scopes.** Every amount or frequency write takes `apply`: `forward` (default, from the month
  until the next explicit change), `month`, or `through` plus `through=YYYY-MM`. A bounded scope
  restores the prior (amount, frequency) pair the month after the range, unless an explicit row is
  already there. Explicit rows inside the range are overridden. Rows that do not change the effective
  state are dropped (normalization), so they never bound a later `forward` edit. A line with no rows
  left is deleted.
- **Names are line-level.** Category and subcategory edits apply to every month. The Planning UI
  says so.
- **Frequency is per version.** A frequency edit is a scoped write, like an amount edit. The amount
  you enter is stored as given. If you leave it blank, the amount in force is kept. Other months are
  not rescaled.
- **Frequency switches must fall on whole calendar periods.** A switch to `new` at month M is valid
  only if M opens a period of `new` (Quarterly: Jan/Apr/Jul/Oct; Bi-annually: Jan/Jul; Annually:
  Jan) and the `old` period has just finished (the month before M ends one). Periods are never
  split. `_validate_frequency_sequence` checks every adjacent pair of active versions after each
  write. An invalid write raises `ValueError`, which the router turns into a 400 whose message names
  the nearest valid month. Bounded ranges must also line up: the restored frequency must start at
  its own period boundary. For example, Quarterly through June is valid, and Quarterly through May
  is not.
- **"This month only" cannot change frequency in practice.** A one-month quarterly period cannot be
  expressed, so the revert the following month is refused. Use "Until changed" or a range ending on
  a boundary.
- **One line per (category, subcategory).** Re-adding an ended pair revives the same `line_key`. An
  active duplicate, or a recategorize onto an occupied pair, raises `LineConflict` (HTTP 409).
- **`inherited` means "month not confirmed"**, not "has no table". Confirming writes nothing to the
  budget. Confirmation does not un-confirm on edit.
- **Expected income** is per month (`month_plans.expected_income`). It takes the same apply scopes
  and has no tombstone. A bounded income edit with no earlier value ends in an explicit `0`.
- **Reporting.** Each period is governed by one frequency, since no period is ever split. Non-monthly
  lines accrue across the calendar period (Jan–Dec, halves, quarters), starting at the first month
  within the period where the line is active, and are compared with the full per-period limit.
  `budget_summary` needed no change: `resolve_view` now supplies each month's frequency.

Routers: `budgets.py` (`GET/POST/PATCH/DELETE`, `apply`/`through`, `/suggested` WMA over the 3
complete months preceding the target. It returns 400 for bad input, 404 when a line is not active in
the month, and 409 on conflict. A failed request writes nothing). `month_plans.py`
(`GET /api/month-plans?start&end` for at most 36 months, `GET /{month}`, `POST /{month}/confirm`,
`PUT /{month}/income`). `reporting.py` (`budget_summary` per month). `categories.py` (`/active`;
rename updates `categories` and `expenses` only; also owns the expense read projection). `expenses.py`
(list accepts `category_id`/`subcategory_id` as well as names; `/subcategories`, trailing 12 months).
`import_csv.py`, `goals.py`. The `/api/income` router has been removed.

## Goal ledger and sweeps (Phase 3)

- `backend/sweep_math.py`: pure arithmetic (`fund_month`, `leftover`, `allocate`). No DB access.
- `backend/goal_ledger.py`: the only module that touches `goal_allocations` and `sweep_rules`. Like
  `budget_store`, it never commits. Keys: `list_rules`, `create_rule`, `update_rule`, `delete_rule`,
  `goal_balances`, `goal_contributions`, `add_withdrawal`, `compute_proposal`, `approve`, `reopen`.
- Errors: `ValueError` maps to 400, `LookupError` to 404, `LedgerConflict` to 409.
- `goal_allocations` is append-only, with one owner per row. Goal kinds `sweep` and `withdrawal` set
  `goal_id`. Fund kinds `reserve`, `draw`, and `opening` set `line_key`. A `reversal` points at
  `reverses_id`. Signs: sweep, reserve, and opening are positive; withdrawal and draw are negative.
  A balance is the sum of an owner's rows. Both foreign keys are `RESTRICT`.
- Leftover for month M = income (`effective_expected_income`) minus regular spend, minus reserves,
  minus shortfall. Regular spend is Monthly-type expenses not filed under an irregular line active in
  M. Irregular lines are non-Monthly budget lines active in M, and each one's monthly equivalent is its
  reserve. A fund draws `min(bill, balance_before + reserve)`. The uncovered part is shortfall, which
  reduces that month's leftover once. Funds never go negative. Pot = max(0, leftover).
- Split: eligible goals are incomplete goals with rules. Fixed rules are paid by priority, capped by the
  pot and by goal need (target minus balance). Percentages share the post-fixed remainder, capped the
  same way. The remainder is Unallocated, with no overflow.
- Approval (`approve`): recomputes the proposal and returns 409 if the accepted amounts differ. Guards:
  the month must have ended (at or before the previous month), must not already be closed, and must
  follow a closed month if any month is closed. It writes reserve, draw, and sweep rows plus a
  `closed_months` record of the figures. Reopen appends reversals for sweep, reserve, and draw rows and
  deletes the `closed_months` row. It is refused while a later month is closed.
- Routes: `/api/sweeps/rules` (CRUD; percentage rules total at most 100; priorities unique),
  `/api/sweeps/closed`, `/api/sweeps/proposal?month=`, `/api/sweeps/{month}/approve`,
  `/api/sweeps/{month}/reopen`. Goals: `GET /api/goals` adds `balance`, `contributed_this_month`, and
  `needs_per_month`; `POST /api/goals/{id}/withdrawals`; `DELETE` returns 409 for a goal with ledger
  history (mark it completed instead).
- Frontend: `components/sweeps/SweepPanel.tsx` (on the Goals page) and `SweepRules.tsx`, with
  `hooks/useSweeps.ts` and `api/sweeps.ts`. Closed months display the figures stored at close.
- **Open gap: no opening balances.** The ledger starts empty, so the first approved month treats every
  fund as starting at zero. A bill that month then shows a shortfall that is an artifact of the empty
  ledger, not spending. Resolve this (opening rows) before the first live sweep.
- Live DB state: no sweep rules, no closed months, and no goal allocations. The sweep does nothing
  until rules exist. Income is inherited from 2020-01 (see Migrations), so every month has income unless
  overridden.
- Tests pin the latest version in `tests/test_migrations.py` and `tests/test_backup.py`. Update those
  when adding m0007.

## Migrations

`backend/migrations/runner.py` keys on `PRAGMA user_version`. The `MIGRATIONS` tuple is
**append-only**. `LATEST_VERSION` is `max(version)`, currently **6**. `run_migrations` requires no
pending transaction and sets `PRAGMA foreign_keys=ON` before `BEGIN`. Helpers are in
`migrations/helpers.py`.

Shipped migrations are **frozen. Never edit them.** That covers `m0001` through `m0006`. The next
change is `m0007`.

- `m0003` (filename predates the model) expands legacy `budgets` windows into versions. It is
  event-based and independent of today's date. Frequency is that of the most recent ever-in-effect
  row. Earlier amounts are converted to keep their monthly equivalent.
- `m0004` retires `income_sources`. It carries the single legacy figure into `month_plans` as an
  explicit `expected_income` at the earliest month with dated data (expenses or budget versions).
  Every later month then inherits it, which matches what the old single figure did. The table is
  left in place, unused. The migration skips when there is no legacy income, when a per-month
  income already exists, or when there is no dated data.
- `m0005` adds `budget_amounts.frequency`, backfilled from each line's current frequency. It is
  idempotent (`column_exists` guard). The live history therefore carries the latest frequency for
  every past month, so the real past cadence is not recovered (see the legacy `budgets` table if it
  is ever needed). m0003's conversion keeps the stored amounts correct.

- `m0006` creates `goal_allocations` (the goal ledger; see the Goal ledger section) and adds the close
  figures to `closed_months` (`expected_income`, `regular_spend`, `reserve_total`, `shortfall`,
  `swept_total`). `leftover_capped` is no longer written.

**Startup runs migrations and snapshots first.** When migrations are pending and the DB has data,
the lifespan writes `backups/pre_migration_v{from}_to_v{to}_{stamp}.db` via SQLite's backup API, then
migrates. `POST /api/backup` uses the same helper (`database.snapshot_database`). Take DB copies with
the backup API, never `shutil.copyfile`, because a plain copy can miss WAL pages.

**The live DB is still at `user_version=3`.** It will migrate to 6 on the next app start, with a
snapshot. A dry run on a backup-API copy (2026-11-01) applied m0004 to m0006 cleanly, with integrity OK.
The live DB was not changed. m0004 placed the legacy $6,000 income at 2020-01, the earliest dated
row (legacy budgets), not 2025-11.

`scripts/verify_m0003_expansion.py` re-derives the old predicate independently, on a copy. Last run
on the live DB (before m0004/m0005): OK, 59 lines / 108 versions over 96 months, idempotent.

### Legacy tables

- `budgets` is expand-only and still created `IF NOT EXISTS` in `database.py` `init_db()`. No
  runtime read path uses it. Only `m0003`, `migrate.py` (the CSV importer, which writes legacy rows
  and then calls `m0003.migrate`), the tests, `scripts/seed_demo_data.py`, and the verify script
  reference it.
- `income_sources` is expand-only. Nothing in the app reads or writes it after m0004. `migrate.py`
  and `scripts/seed_demo_data.py` still write to it. m0004 carries those values forward on the next
  migration.
- `budget_drafts` is retired (router, client, hook, and DDL are gone). The 147 rows stay in
  `data/budget.db` as an inert archive. m0003 does not import them. Known divergences in the
  2026-08 draft (9 rows) are accepted.
- `goals.py` no longer writes synthetic budget rows. It only maintains `goal_budget_links`
  (`end_date` tracks the target month).

## Frontend: Planning and income

- `Planning.tsx` (rewritten). It has:
  - a 12-month status strip (3 months back, 8 forward) of Inherited/Confirmed chips
    (`components/planning/MonthStatusStrip`), with "Keep as is" (confirm; hidden once confirmed) and
    "Edit" (focuses the line form; changes no state);
  - the "Applies to" control (`components/planning/ApplyScopeControl`): Until changed (default),
    This month only, Through a month. It applies to line saves, line deletes, and income saves. It
    resets to the default after each successful save and when the month changes;
  - an expected-income input, and a summary of expected income, budgeted per month, and income less
    budget. The last is a plan figure, not actual spending;
  - a notice when a name edit is made, because names are global.
- Hooks and client: `hooks/useMonthPlans.ts` and `api/monthPlans.ts`. `api/client.ts` gained `put`.
  `lib/applyScope.ts` and `lib/monthMath.ts` hold the scope and month helpers.
- Dashboard and Goals now read the current month's expected income through `useMonthPlan`. The
  `useIncome` hook, `api/income.ts`, and the `IncomeTotal` type are removed.

## Gotchas

- **App startup runs migrations.** Starting the server against `data/budget.db` migrates it, after a
  snapshot. Tests use temp DBs via `monkeypatch.setattr(database, "_DB_PATH", ...)`.
- **The store raises `ValueError` after it has written rows** when a frequency sequence is invalid.
  Callers must roll back. The routers do, because `sqlite3.Connection` as a context manager rolls
  back on exception. Store-level tests must call `conn.rollback()` after an expected error.
- **Test fixtures insert without committing.** A `conn.rollback()` in a test also erases an
  uncommitted fixture row. Call `conn.commit()` first. The frequency tests and the property test both
  do this.
- `budget_store._resolve_ids` lazy-imports `routers.categories` (a circular-import guard). This applies
  to write paths only. `resolve_category_ids` reads `row["id"]`, so write-path connections need
  `row_factory = sqlite3.Row`, which `database.get_db()` sets.
- Errors in budget and month-plan routers are raised inside the `with get_db()` block, before
  commit, so a failed request rolls back.
- `scripts/seed_demo_data.py` builds a legacy-shaped schema and seeds `budgets` and `income_sources`.
  It relies on startup migrations to produce versioned lines and a per-month income.
- Frontend suggestion amounts from `/suggested` are monthly equivalents. To prefill or apply one on a
  non-monthly line, multiply by `FREQUENCY_DIVISORS[frequency]` (`web/src/lib/budgetMath.ts`). There is
  no inverse helper.
- Dead CSS in `Planning.module.css` (`.suggestionUp`, `.suggestionDown`, `.incomeHeader`) predates
  any suggestions UI. There has never been one.
- Goal "saved" now comes from the ledger (`balance` on `GET /api/goals`), not from expenses. Earlier
  note: the matching on `goal_budget_links` strings was category spending, not savings. `goals.target_month`
  is stored `YYYY-MM-01` while the rest of the app uses `YYYY-MM`. `expenses.goal_id` exists but is
  unused. `expense_type='Goal'` rows are no longer read by the app (0 in the live DB).
- **Category identity is by id end to end.** Expenses are filed under `category_id` /
  `subcategory_id`; every read resolves the name through `categories`, so a rename changes what is
  displayed without touching an expense row. `routers/categories.py` owns the projection
  (`EXPENSE_WITH_NAMES` + `select_expenses`): `COALESCE(c.name, e.category)` so a row that never got
  ids still shows its text. `reporting._spent_between`, `/suggested`, `spending_by_category`,
  `_auto_categorize` and the expense list all match on ids. `spending_by_category` groups by ids
  only — grouping by the name alias resolves back to the text column in SQLite. The legacy text
  columns remain (written by the create/update paths and the rename dual-write) as the display
  fallback for id-less rows and for the CSV importer; there is no plan to drop them. The live DB has
  0 rows without `category_id`. `tests/test_category_identity.py` pins the behavior by staling the
  text copy and asserting attribution still follows the id. Write-path fixtures must stamp ids
  (`resolve_category_ids`), as every production insert does.
- `fetchCategories` and `fetchSubcategories` in `web/src/api/expenses.ts` are unused; pages get their
  lists from `/api/categories/active` through `useCategories` / `useSubcategories`.
- `useSubcategories` and `useCategories` share a query key in `hooks/useExpenses.ts`. Both call the
  same endpoint, so they agree today, but the key ignores the category argument.
- Changing a line's frequency sends the apply scope to the server. The server validates it against the
  period rules above.
- Live-data facts. Four legacy rows were never in effect (inverted windows, `effective 2026-07-01` /
  `conclusion 2026-06-30`: Baby Items, Health/Baby Delivery ×2, Housing/Baby Items) and produce no
  line. Health/Medication was Monthly and changed to Quarterly, and its early amount was converted to
  90. Three lineages have overlapping windows, resolved latest-effective-wins. The live DB has 17
  non-monthly lines (13 Annually, 3 Quarterly, 1 Bi-annually).

## Current state

Verified after the Phase 3 changes: backend 262 tests pass, frontend 34 tests pass, the build is
clean. The property test for frequency edits is mutation-checked: disabling the switch validation
makes five tests fail. The Planning UI has not been checked in a running browser.

### Phase status vs `.posit/assistant/plans/2026-09-28-1903-plan.md`

| Phase | Status |
|---|---|
| 0 migration runner, category IDs | Done. Reads identify by id and resolve names from `categories`; the denormalized text columns are kept as a fallback (see Gotchas). |
| 1 annual lines out of monthly reporting | Done (`/summary` returns `{monthly, non_monthly}`). |
| 2 category agility, rename by ID | Done, including id-based reads. |
| 3 month-end sweep into goals | Built (m0006, `goal_ledger.py`, `routers/sweeps.py`, sweep panel on Goals). Open: opening balances for the first sweep month; see the Goal ledger section. |
| 4 month-by-month budgeting | Backend done. UI done for the status strip, Keep as is / Edit, Applies-to, and expected income. Not done: suggestions wiring, turnover modal. |

Because Phase 3 does not exist, the synthetic-budget writes dropped from `goals.py` are **not
compensated**. Goals currently drive no monthly savings amount.

### Remaining

1. Check the Planning screen in a running app, including a frequency switch and the nearest-month
   message.
2. Wire `useSuggestedBudgets(month)` into `Planning.tsx`. The hook and `fetchSuggestedBudgets` exist but
   are unused. "Apply" converts monthly equivalents to per-period amounts for non-monthly lines, with a
   test for that conversion.
3. Blocking turnover modal on boot. It needs a baseline so history is not prompted.
4. Phase 3 opening balances: enter a starting balance per irregular-line fund for the first sweep
   month (`kind='opening'`, already allowed by the CHECK). Needed before the first live sweep.
5. Decide whether to amend the 09-28 plan in place or let later plans supersede it.

### Decisions

Implemented:

- Periods stay calendar-aligned (Jan–Dec, halves, quarters). No `due_month`.
- Expected income is a manual per-month input, inherited forward like budget lines.
- Income consolidation: one concept, per month. The legacy endpoint is removed.
- Frequency is per version. A change applies to chosen months. Changes must fall on whole periods.
  Amounts are stored as entered. Earlier history keeps its latest frequency (backfilled).
- Editing scope: every amount or frequency edit offers Applies to, default "Until changed" (`forward`).

Phase 3 sweep design (built; the Goal ledger section records what differs in practice):

- **Leftover** = expected income − actual spend − annual reserve. Each annual or non-monthly line's
  monthly equivalent is reserved and credited to a tracked per-line fund in the ledger. When the bill
  hits, it draws the fund down. A short fund reduces leftover, which is shown as "Reserved for
  irregular bills". Negative leftover sweeps nothing.
- **Sweep rules:** fixed amounts first in priority order, then percentages of the remainder.
  Percentages below 100 leave the rest "Unallocated" (kept, not rescaled). A goal that reaches its
  target leaves its share Unallocated. It does **not** overflow to the next goal.
- **Goal money:** an append-only `goal_allocations` ledger (`goal_id`, `month`, `amount`, `kind`).
  Balance is the sum, and withdrawals are negative rows. Not `expenses` rows. Annual-bill funds reuse it.
- **Turnover UX:** a blocking modal on boot when the prior month is unconfirmed or unswept, in three
  steps: confirm budget, review leftover, approve sweep.
- **UI direction (not decided):** Goals cards show saved balance, monthly contribution, and "needs
  $X/month" against sweep delivery. Group Planning lines into Monthly and Irregular bills. Consider
  renaming Settings to Import.
