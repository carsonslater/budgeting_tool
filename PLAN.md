# Household Budgeting Tool — Rebuild Plan (Option B)

## Vision

Replace the R/Shiny monolith with a modern, local-first desktop application:

- **Frontend**: Vite + React (TypeScript) with a fully custom design system
- **Backend**: Python + FastAPI served locally
- **Storage**: SQLite (replacing flat CSVs)
- **Desktop wrapper**: `pywebview` (already in use)
- **Design language**: Spectral serif font · dark background · Substack orange (`#FF6719`) accents

The app stays **100% local** — no cloud, no accounts, no telemetry. Data lives in a single `data/budget.db` SQLite file.

---

## Design System Reference

```
Font: Spectral (Google Fonts) — weights 200–800, normal + italic
Background:  #0F0F0F  (near-black)
Surface:     #1A1A1A  (card / panel)
Border:      #2A2A2A
Accent:      #FF6719  (Substack orange)
Accent Dim:  #CC5214  (hover / pressed)
Text:        #F0EDE8  (warm off-white)
Text Muted:  #8A867F
Danger:      #E05252
Success:     #4CAF79
```

---

## Prompt-by-Prompt Build Plan

Work through these prompts **in order**. Each prompt produces a working checkpoint that the next prompt builds on.

---

### Prompt 1 — Project Scaffold & Design System

**Goal:** Initialize the Vite + React + TypeScript project and establish the complete design system before writing any feature code.

```
Create a new Vite + React + TypeScript project in the `web/` subdirectory of this
repository. Use `npx -y create-vite@latest web/ -- --template react-ts`.

Then configure the project:

1. Install dependencies:
   - react-router-dom (routing)
   - @tanstack/react-query (server state)
   - recharts (charts)
   - lucide-react (icons)
   - date-fns (date utilities)

2. Create `web/src/styles/globals.css` with:
   - @import for Spectral from Google Fonts (weights 200–800 normal + italic)
   - CSS custom properties for the full design token set:
       --color-bg: #0F0F0F
       --color-surface: #1A1A1A
       --color-surface-raised: #222222
       --color-border: #2A2A2A
       --color-accent: #FF6719
       --color-accent-dim: #CC5214
       --color-text: #F0EDE8
       --color-text-muted: #8A867F
       --color-danger: #E05252
       --color-success: #4CAF79
   - Global resets: box-sizing, margin/padding zero, font-family Spectral
   - Base typographic scale (--text-xs through --text-3xl) using rem
   - All Spectral utility classes (.spectral-extralight through .spectral-extrabold,
     plus italic variants)
   - Scrollbar styling (thin, dark, orange thumb)
   - Focus ring using accent color

3. Create `web/src/components/ui/` with these primitive components, each with
   their own CSS module:
   - Button.tsx — variants: primary (orange fill), ghost (transparent), danger
   - Input.tsx — dark surface, subtle border, orange focus ring
   - Select.tsx — custom styled select, matches Input
   - Card.tsx — dark surface card with border and subtle shadow
   - Badge.tsx — small label in accent / muted / danger / success colors
   - Modal.tsx — centered overlay with dark backdrop and slide-in animation
   - Tabs.tsx — underline-style tabs with orange active indicator

4. Create `web/src/layouts/AppLayout.tsx` — a persistent shell with:
   - Left sidebar navigation (icons + labels) with links to all 5 tabs
   - Active link highlighted with orange left-border accent
   - App title "Household Budgeting" in Spectral 300 weight at top of sidebar
   - Main content area with padding and scroll

5. Create `web/src/App.tsx` with react-router-dom routes for:
   /            → Dashboard (placeholder)
   /expenses    → Expenses (placeholder)
   /budgets     → Budgets (placeholder)
   /goals       → Goals (placeholder)
   /reporting   → Reporting (placeholder)
   /settings    → Settings (placeholder)

Verify the app runs (`npm run dev` from `web/`) and the sidebar navigation works.
All placeholder pages should show the tab name in Spectral heading style.
```

---

### Prompt 2 — Python FastAPI Backend & SQLite Schema

**Goal:** Stand up the Python backend with all database tables and REST endpoints. No frontend wiring yet — just a working API.

```
Create a Python FastAPI backend in `backend/` at the project root.

1. Create `backend/requirements.txt`:
   fastapi
   uvicorn[standard]
   pydantic
   python-multipart
   python-dateutil
   pandas
   thefuzz[speedup]

2. Create `backend/database.py`:
   - Use Python's built-in `sqlite3` (no ORM — keep it simple)
   - DB file path: `../data/budget.db` (relative to backend/)
   - `init_db()` function that creates tables with IF NOT EXISTS:

   ```sql
   CREATE TABLE IF NOT EXISTS expenses (
     id          INTEGER PRIMARY KEY AUTOINCREMENT,
     date        TEXT NOT NULL,
     description TEXT NOT NULL DEFAULT '',
     category    TEXT NOT NULL DEFAULT '',
     subcategory TEXT NOT NULL DEFAULT '',
     amount      REAL NOT NULL DEFAULT 0,
     payer       TEXT NOT NULL DEFAULT '',
     expense_type TEXT NOT NULL DEFAULT 'Monthly'
   );

   CREATE TABLE IF NOT EXISTS budgets (
     id              INTEGER PRIMARY KEY AUTOINCREMENT,
     category        TEXT NOT NULL,
     subcategory     TEXT NOT NULL DEFAULT '',
     limit_amount    REAL NOT NULL DEFAULT 0,
     frequency       TEXT NOT NULL DEFAULT 'Monthly',
     effective_date  TEXT NOT NULL,
     conclusion_date TEXT
   );

   CREATE TABLE IF NOT EXISTS income_sources (
     id     INTEGER PRIMARY KEY AUTOINCREMENT,
     source TEXT NOT NULL,
     amount REAL NOT NULL DEFAULT 0
   );

   CREATE TABLE IF NOT EXISTS goals (
     id            INTEGER PRIMARY KEY AUTOINCREMENT,
     name          TEXT NOT NULL,
     target_amount REAL NOT NULL DEFAULT 0,
     target_month  TEXT NOT NULL,
     created_date  TEXT NOT NULL,
     completed     INTEGER NOT NULL DEFAULT 0
   );

   CREATE TABLE IF NOT EXISTS goal_budget_links (
     id          INTEGER PRIMARY KEY AUTOINCREMENT,
     goal_name   TEXT NOT NULL,
     category    TEXT NOT NULL,
     subcategory TEXT NOT NULL DEFAULT '',
     start_date  TEXT NOT NULL,
     end_date    TEXT
   );
   ```

3. Create `backend/migrate.py`:
   - Script that reads the existing CSV files from `../data/*.csv` and
     inserts their rows into the SQLite database (one-time migration)
   - Handles: expenses.csv, category_budget.csv, income_sources.csv, goals.csv,
     goal_budget_links.csv
   - Skips migration if tables already have data (idempotent)
   - Print a summary of rows migrated per table

4. Create `backend/routers/expenses.py` with these FastAPI routes:
   GET    /api/expenses              — list all (supports ?start=&end=&category=)
   POST   /api/expenses              — create one
   PATCH  /api/expenses/{id}         — update one
   DELETE /api/expenses/{id}         — delete one
   GET    /api/expenses/categories   — distinct categories list
   GET    /api/expenses/payers       — distinct payers list

5. Create `backend/routers/budgets.py`:
   GET    /api/budgets               — list all
   POST   /api/budgets               — create/upsert
   PATCH  /api/budgets/{id}          — update
   DELETE /api/budgets/{id}          — delete
   GET    /api/budgets/suggested     — weighted moving average suggestions
                                       (replicate Shiny hasty/conservative logic)

6. Create `backend/routers/income.py`:
   GET    /api/income                — current monthly income total
   POST   /api/income                — set income (replaces all rows)

7. Create `backend/routers/goals.py`:
   GET    /api/goals                 — list all
   POST   /api/goals                 — create
   PATCH  /api/goals/{id}            — update / mark complete
   DELETE /api/goals/{id}            — delete
   GET    /api/goals/links           — budget links for goals
   POST   /api/goals/links           — create link
   DELETE /api/goals/links/{id}      — delete link

8. Create `backend/routers/reporting.py`:
   GET    /api/reporting/summary     — budget vs actual by category for a month
   GET    /api/reporting/trends      — monthly/weekly spending totals
   GET    /api/reporting/categories  — spending by category for a period

9. Create `backend/routers/import_csv.py`:
   POST   /api/import               — accepts a multipart CSV upload, auto-detects
                                      format (same 4 formats as R app: credit card,
                                      Chase credit, Chase bank, generic),
                                      returns staged rows (does not persist)
   POST   /api/import/confirm       — accepts staged rows array and inserts them,
                                      running duplicate detection first

10. Create `backend/main.py`:
    - Initialize FastAPI app with CORS middleware (allow localhost origins)
    - Call init_db() on startup
    - Include all routers with /api prefix
    - Run with uvicorn on port 8000 (configurable via PORT env var)

Verify the API starts cleanly with `uvicorn main:app --reload` from `backend/`.
Test a few endpoints manually. Do NOT wire to frontend yet.
```

---

### Prompt 3 — API Client & React Query Setup

**Goal:** Create the frontend data layer so components can call the API cleanly.

```
In `web/src/`, create an API client and React Query wrappers for all backend
endpoints.

1. Create `web/src/api/client.ts`:
   - Base URL from `import.meta.env.VITE_API_URL` defaulting to
     `http://localhost:8000`
   - `apiFetch<T>(path, options?)` helper that throws on non-2xx with an
     error message from the response body

2. Create `web/src/api/expenses.ts` — typed functions:
   fetchExpenses(filters?) → Expense[]
   createExpense(data) → Expense
   updateExpense(id, data) → Expense
   deleteExpense(id) → void
   fetchCategories() → string[]
   fetchPayers() → string[]

3. Create `web/src/api/budgets.ts`:
   fetchBudgets() → Budget[]
   createBudget(data) → Budget
   updateBudget(id, data) → Budget
   deleteBudget(id) → void
   fetchSuggestedBudgets() → SuggestedBudget[]

4. Create `web/src/api/income.ts`:
   fetchIncome() → number
   setIncome(amount) → void

5. Create `web/src/api/goals.ts`:
   fetchGoals() → Goal[]
   createGoal(data) → Goal
   updateGoal(id, data) → Goal
   deleteGoal(id) → void
   fetchGoalLinks() → GoalLink[]
   createGoalLink(data) → GoalLink
   deleteGoalLink(id) → void

6. Create `web/src/api/reporting.ts`:
   fetchReportSummary(month?) → ReportSummary
   fetchSpendingTrends(period, category?) → TrendPoint[]
   fetchCategoryBreakdown(start, end) → CategoryTotal[]

7. Create `web/src/api/import.ts`:
   stageImport(file) → StagedRow[]
   confirmImport(rows) → { imported: number; skipped: number }

8. Create `web/src/types/index.ts` with all shared TypeScript interfaces:
   Expense, Budget, Goal, GoalLink, ReportSummary, TrendPoint,
   CategoryTotal, StagedRow, SuggestedBudget

9. In `web/src/main.tsx`, wrap the app with `QueryClientProvider`.

10. Create `web/src/hooks/` with React Query custom hooks for each resource:
    useExpenses, useBudgets, useGoals, useReporting, useIncome
    Each hook encapsulates useQuery + useMutation + cache invalidation.

No UI changes needed — this is infrastructure only.
```

---

### Prompt 4 — Dashboard Page

**Goal:** Build the landing Dashboard page with key financial metrics at a glance.

```
Build the Dashboard page at `web/src/pages/Dashboard.tsx`.

The dashboard should show at a glance:
- Current month's total spending vs income (large hero number with progress arc)
- Budget health: how many categories are over / on track / under budget
- Recent expenses (last 5 transactions in a compact list)
- Goals progress (each goal as a progress bar with % to target)

Layout:
  Row 1: Full-width "spending vs income" hero card
  Row 2: Three stat cards side-by-side:
    · Total spent this month (with % change vs last month)
    · Monthly income
    · Net (income minus spending), colored green or red
  Row 3: Two-column layout:
    · Left (60%): Budget health — a compact table of categories showing
      spent / limit / status badge (Over, On Track, Under)
    · Right (40%): Recent expenses list
  Row 4: Goals progress row (horizontal cards, one per active goal)

Design requirements:
- All numbers in a slightly larger Spectral semibold weight
- Positive net shown in --color-success, negative in --color-danger
- Progress bars use --color-accent for the fill
- Status badges: Over = danger, On Track = accent, Under = muted
- Cards use the Card primitive with subtle hover lift (transform + box-shadow)
- Numbers animate in with a count-up effect on mount (use a small custom hook)
- Skeleton loading state while data fetches (pulsing dark rectangles)

Use useExpenses, useBudgets, useIncome, useGoals hooks for data.
All data derivation (totals, % changes, budget status) happens in the component
or a local utility — not in the API.
```

---

### Prompt 5 — Expenses Page

**Goal:** Full expense management page with log form, transaction table, and inline editing.

```
Build the Expenses page at `web/src/pages/Expenses.tsx`.

Left panel (sidebar, ~340px wide) — "Log an Expense" form:
  - Date picker (defaults to today)
  - Description text input
  - Expense Type toggle: "Monthly" | "Goal"
  - Category combobox (shows existing categories, allows free-type to create new)
  - Subcategory combobox (filtered to chosen category, allows free-type)
  - When type is "Goal": replace Category/Subcategory with a Goal selector
  - Amount numeric input (two decimal places)
  - Payer combobox (Joint / Caleb / Rae + free-type)
  - "Add Expense" button (primary orange)
  - Below the button: running total of expenses this month for each payer

Right panel — "Recorded Expenses" table:
  - Column headers: Date · Description · Category · Subcategory · Amount · Payer · Type
  - Rows are selectable (click to select, click again to deselect)
  - Clicking a row populates the left-panel form so the expense can be edited
    (form switches to "Update" mode with a Cancel button)
  - "Delete Selected" button (danger, top-right of table) — shows confirmation
    modal before deleting
  - Pagination: 25 rows per page with next/prev controls
  - Column sorting on all columns
  - Text filter input above the table (client-side, instant)
  - Amount column right-aligned and formatted as $X,XXX.XX
  - Expense type "Goal" rows shown with a small orange Goal badge

Animations:
  - New rows slide in from the top when added
  - Deleted rows fade out before removal
  - Form submitting state shows a spinner in the button

Use useMutation from React Query for add/update/delete, invalidating the
expenses cache on success.
```

---

### Prompt 6 — Budgets Page

**Goal:** Budget planning and management with current budgets, future scheduled budgets, and smart suggestions.

```
Build the Budgets page at `web/src/pages/Budgets.tsx`.

Left panel — "Add or Update Budget" form:
  - Monthly income input at top with "Save" button (links to income API)
  - Effective Month date picker (month-year picker, defaults to start of current month)
  - Category combobox (existing + free-type)
  - Subcategory combobox (filtered by category + free-type)
  - Frequency select: Monthly / Quarterly / Bi-annually / Annually
  - Limit input (numeric, labeled "Amount per period")
  - "Save Budget" primary button

Right panel — three stacked sections:

Section 1: "Active Budgets"
  - Table showing budgets effective today with columns:
    Category · Subcategory · Frequency · Monthly Equiv · Effective Date
  - Row click → populate the form for editing
  - "Delete Selected" danger button
  - Income summary row above: "Monthly Income: $X,XXX — Total Budgeted: $X,XXX
    — Remaining: $XXX" (colored green/red)

Section 2: "Upcoming Budgets"
  - Same table format, filtered to budgets with effective_date in the future
  - Collapsed by default, expandable with a toggle

Section 3: "Suggested Budgets"
  - Explanatory text about Hasty (0.6/0.3/0.1) vs Conservative (0.4/0.4/0.2) WMA
  - Table with columns: Category · Current Limit · Hasty Suggestion · Conservative
  - Only shows rows where current month spending deviated from budget by >$50
  - Two buttons: "Apply Hasty" and "Apply Conservative" — each updates budgets
    via the API and invalidates the cache
  - Suggestion values highlighted in orange if higher than current, muted if lower

All monetary values formatted as $X,XXX.
```

---

### Prompt 7 — Goals Page

**Goal:** Visual goal management with progress tracking.

```
Build the Goals page at `web/src/pages/Goals.tsx`.

Left panel — "New Goal" form:
  - Goal Name text input
  - Target Amount numeric input
  - Target Month date picker (month-year, defaults to next month)
  - "Save Goal" primary button

  Below the form: "Monthly Allocation Summary" — a small summary showing
  total allocated to goals this month vs. total income.

Right panel — "Active Goals" section:
  Each goal rendered as a rich card (not a table row):
  ┌─────────────────────────────────────────────────────────┐
  │  🎯 Goal Name                          [Complete] [✕]   │
  │  $X,XXX spent of $X,XXX target                          │
  │  ████████████░░░░░░░░  68%  · Due: March 2026           │
  │  Linked categories: Vacation > Flights, Vacation > Hotel │
  └─────────────────────────────────────────────────────────┘

  - Progress bar uses orange fill
  - % is calculated from expenses with expense_type = 'Goal' and matching category
  - "Complete" button marks goal as done (moves to completed section)
  - "✕" deletes the goal (with confirmation modal)
  - Clicking a goal card expands it to show: all linked budget lines (category +
    subcategory), with buttons to add or remove links

  Below active goals: "Completed Goals" section (collapsed by default)
  Same card format but with a muted checkmark badge and no action buttons.

Linked budget line form (shown when a goal card is expanded):
  - Category combobox + Subcategory combobox + Start date + End date
  - "Link" button to create the association
  - Existing links shown as removable chips
```

---

### Prompt 8 — Reporting Page

**Goal:** Comprehensive spending analytics with charts and budget performance table.

```
Build the Reporting page at `web/src/pages/Reporting.tsx`.

Controls bar at top:
  - Period select (dynamic list of past months + "All Time")
  - All charts and tables update when period changes

Section 1: "Budget Performance" (full width)
  Table columns: Category · Subcategory · Budget · Spent · Remaining · Status
  - Status badge: Over / On Track / Under
  - Rows sorted by overage descending (worst first)
  - "Over budget" rows have a subtle red-tinted row background
  - Summary row at bottom: Total Budget · Total Spent · Net

Section 2: "Goal Project Spending" (full width)
  Table of expenses with expense_type = 'Goal', grouped by goal name
  Columns: Goal · Total Spent · # Transactions

Section 3: "Spending Trends" chart
  - Toggle: Monthly | Weekly aggregation
  - Toggle: Total | By Category
  - Recharts LineChart or BarChart (stacked when by-category)
  - Orange primary line/bar, muted colors for additional categories
  - Tooltip styled to match dark theme
  - Smooth curve animation on load

Section 4: "Spending by Category" bar chart
  - Horizontal bar chart, categories on Y axis, amount on X
  - Bars colored with orange and muted palette
  - Sorted by amount descending

Section 5: "Transaction Detail" table
  - Full expense list for the selected period
  - Same columns as Expenses page table
  - Sortable, filterable, paginated (50 per page)

All chart containers have a Card wrapper with title and subtle border.
```

---

### Prompt 9 — Settings & CSV Import Page

**Goal:** Data management, backup, and the CSV import staging workflow.

```
Build the Settings page at `web/src/pages/Settings.tsx`.

Section 1: "Data Management"
  - "Backup Data" button: calls a new backend endpoint
    POST /api/backup that copies budget.db to
    ../backups/budget_YYYYMMDD.db
  - Shows last backup timestamp if available
  - "Open Data Folder" button (calls POST /api/open-data-folder which runs
    `open ../data` on macOS, `explorer ../data` on Windows)

Section 2: "Import Bank Statement"
  Two-step flow:

  Step 1 — Upload:
    - Large dashed drop zone for CSV drag-and-drop (also has a click-to-browse)
    - Supported format badges: "BECU Credit Card" · "Chase Credit" ·
      "Chase Bank" · "Generic"
    - On file drop: POST to /api/import, show a loading spinner
    - Transition to Step 2 on success

  Step 2 — Review & Import (staging area):
    - Shows count of rows loaded and count of auto-removed duplicates
    - Toolbar: "Auto-Categorize" · "Delete Selected" · "Import Selected" · "Clear"
    - Table: Date · Description · Amount · Category · Subcategory · Payer
    - Duplicate rows highlighted with red-tinted background and a "Duplicate" badge
    - Right sidebar panel: "Edit Selected Rows"
        · Category combobox
        · Subcategory combobox
        · Payer combobox
        · "Apply Changes" button (updates all selected rows)
    - "Import Selected" triggers POST /api/import/confirm, shows result toast,
      removes imported rows from staging
    - After all rows imported, returns to Step 1 with a success animation

Toast notifications (top-right corner):
  - Success (green), Warning (orange), Error (red)
  - Auto-dismiss after 4 seconds
  - Slide in from right, slide out to right
  - Create a shared Toast context so any page can trigger a toast
```

---

### Prompt 10 — Desktop Launcher & Final Polish

**Goal:** Wire up the Python desktop launcher for the new stack, add final UI polish, and verify the end-to-end experience.

```
Update the desktop launcher and add final polish across the whole app.

1. Update `desktop_app.py` to launch FastAPI instead of (or alongside) the
   Shiny app:
   - Start `uvicorn backend.main:app --port <port>` as a subprocess
   - Serve the built Vite frontend from `web/dist/` using FastAPI's
     StaticFiles mount at "/" so pywebview just opens http://127.0.0.1:<port>
   - The `web/` build step (`npm run build`) should be run once before packaging
   - Add --dev flag that skips the static file serving and points webview to
     http://localhost:5173 (for development)
   - Update wait_for_server to poll the FastAPI /healthz endpoint

2. Add a GET /healthz endpoint to the FastAPI app that returns {"status":"ok"}.

3. Add GET /api/backup endpoint to FastAPI (for Settings page backup button).

4. Add GET /api/open-data-folder endpoint that opens the data directory in
   Finder/Explorer using subprocess.

5. Final UI polish across all pages:
   - Add page transition animations (fade + slight upward slide) when switching
     routes via react-router-dom
   - Add keyboard shortcut 'n' on the Expenses page to focus the Description
     input (for quick entry)
   - Add an empty state illustration (inline SVG, orange-toned) for tables with
     no data yet
   - Ensure all interactive elements have focus rings using --color-accent
   - Add a compact "last saved" timestamp in the sidebar footer showing when
     data was last written

6. Update README.md:
   - Document the new stack
   - New quick-start instructions (backend + frontend dev commands)
   - Data migration step (run `python backend/migrate.py` once)
   - Desktop launch instructions

7. Verify the full flow works end-to-end:
   - Run `python backend/migrate.py` to import existing CSVs
   - Run `uvicorn backend.main:app --reload` and `npm run dev` from `web/`
   - Navigate all 6 pages and confirm data loads correctly
   - Add an expense, set a budget, check the dashboard updates
   - Upload a CSV and complete a staging import
```

---

## Suggested File Structure After Completion

```
budgeting_tool/
├── backend/
│   ├── main.py
│   ├── database.py
│   ├── migrate.py
│   ├── requirements.txt
│   └── routers/
│       ├── expenses.py
│       ├── budgets.py
│       ├── income.py
│       ├── goals.py
│       ├── reporting.py
│       └── import_csv.py
├── web/
│   ├── src/
│   │   ├── api/          (client + per-resource fetch fns)
│   │   ├── components/
│   │   │   └── ui/       (Button, Input, Card, Modal, etc.)
│   │   ├── hooks/        (useExpenses, useBudgets, etc.)
│   │   ├── layouts/      (AppLayout)
│   │   ├── pages/        (Dashboard, Expenses, Budgets, Goals, Reporting, Settings)
│   │   ├── styles/       (globals.css)
│   │   ├── types/        (index.ts)
│   │   └── App.tsx
│   ├── index.html
│   └── package.json
├── data/
│   └── budget.db         (SQLite — replaces CSVs)
├── backups/
├── desktop_app.py        (updated)
└── README.md             (updated)
```

---

## Notes

- **Payers** default to `Joint`, `Carson`, `Chloe` — same as the R app.
- **Subcategory** is always optional; empty string is the canonical "none" value.
- **Budget conclusion dates** are computed server-side in the budgets router
  (replicating the `calculate_budget_conclusions` R function logic).
- **Auto-categorization** in the import flow uses substring matching against
  existing expense descriptions (Python equivalent of the R `predict_categories`
  function, optionally enhanced with `thefuzz` for fuzzy matching).
- **Goal spending** is tracked via `expense_type = 'Goal'` on individual
  expense rows — the goal name is stored in the `category` field when type is Goal.
