---
description: Guide for maintaining, extending, and debugging the local-first household budgeting app. Details stack restrictions, database schema, design rules, and build pipeline.
---

# Household Budgeting App Maintenance Guide

You are an expert software engineer maintaining and extending a gorgeous, local-first personal budgeting application. All changes to this application must adhere strictly to the design principles, constraints, and architecture established below.

## Technology Stack & Architectural Constraints

The application is designed to be **100% offline, local-first, and private-by-design**.

1. **Privacy-by-Design**:
   - Zero cloud synchronization, external auth systems, or analytics/telemetry engines.
   - All user financial data must reside locally in the SQLite database (`data/budget.db`).
   - No external APIs or networking requests are permitted unless explicitly requested.

2. **Backend (Python + FastAPI)**:
   - Served locally via FastAPI.
   - **Strictly No ORM**: Write explicit, raw SQL queries using the standard Python `sqlite3` driver. Do not introduce SQLAlchemy, SQLModel, or other ORMs.
   - Run locally for development using:
     ```bash
     source .venv/bin/activate
     cd backend
     uvicorn main:app --reload --port 8000
     ```

3. **Frontend (Vite + React + TypeScript)**:
   - Built on Vite, React, and TypeScript.
   - **Strictly No CSS Utility Frameworks**: Do not use Tailwind CSS, Bootstrap, or other utility libraries.
   - **Styling Method**: CSS custom properties for tokens, combined with CSS Modules (`*.module.css`) for component-specific isolation.
   - Remote data fetching must use `@tanstack/react-query` and the api helper client defined in `web/src/api/client.ts`.
   - Run locally for development using:
     ```bash
     cd web
     npm run dev
     ```

4. **Desktop Wrapper (pywebview) & Packaging**:
   - The application runs in a desktop window using `pywebview` in `desktop_app.py`.
   - A PyInstaller-based packaging script compiles the project into a standalone `.app` bundle on macOS (using `scripts/build_mac_app.py` and `scripts/generate_vector_icon.py`).
   - Built output is placed on the user's Desktop as `Household Budgeting.app`.

---

## Database Schema Reference

The local SQLite database is stored at `data/budget.db`. The core tables are defined and initialized in `backend/database.py`:

```sql
CREATE TABLE IF NOT EXISTS expenses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT    NOT NULL,  -- YYYY-MM-DD format
    description  TEXT    NOT NULL DEFAULT '',
    category     TEXT    NOT NULL DEFAULT '',
    subcategory  TEXT    NOT NULL DEFAULT '',
    amount       REAL    NOT NULL DEFAULT 0,
    payer        TEXT    NOT NULL DEFAULT '',
    expense_type TEXT    NOT NULL DEFAULT 'Monthly'
);

CREATE TABLE IF NOT EXISTS budgets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT    NOT NULL,
    subcategory     TEXT    NOT NULL DEFAULT '',
    limit_amount    REAL    NOT NULL DEFAULT 0,
    frequency       TEXT    NOT NULL DEFAULT 'Monthly',
    effective_date  TEXT    NOT NULL,  -- YYYY-MM-DD format
    conclusion_date TEXT               -- YYYY-MM-DD format (nullable)
);

CREATE TABLE IF NOT EXISTS income_sources (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT    NOT NULL,
    amount REAL    NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS goals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    target_amount REAL    NOT NULL DEFAULT 0,
    target_month  TEXT    NOT NULL,  -- YYYY-MM format
    created_date  TEXT    NOT NULL,  -- YYYY-MM-DD format
    completed     INTEGER NOT NULL DEFAULT 0
```

```sql
CREATE TABLE IF NOT EXISTS goal_budget_links (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_name   TEXT    NOT NULL,
    category    TEXT    NOT NULL,
    subcategory TEXT    NOT NULL DEFAULT '',
    start_date  TEXT    NOT NULL,  -- YYYY-MM-DD format
    end_date    TEXT               -- YYYY-MM-DD format (nullable)
);

CREATE TABLE IF NOT EXISTS budget_drafts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    target_month    TEXT    NOT NULL,  -- YYYY-MM format
    category        TEXT    NOT NULL,
    subcategory     TEXT    NOT NULL DEFAULT '',
    limit_amount    REAL    NOT NULL DEFAULT 0,
    frequency       TEXT    NOT NULL DEFAULT 'Monthly'
);
```

---

## Design System Tokens & Aesthetics

Ensure any UI changes strictly adopt these CSS properties defined in `web/src/styles/globals.css`:

| CSS Variable | Color Value | Purpose |
| :--- | :--- | :--- |
| `--color-bg` | `#0F0F0F` | Main dark background |
| `--color-surface` | `#1A1A1A` | Cards, sidebars, modales |
| `--color-surface-raised` | `#222222` | Buttons, inputs, active states |
| `--color-border` | `#2A2A2A` | Standard dividers and card borders |
| `--color-accent` | `#FF6719` | Premium Substack Orange |
| `--color-accent-dim` | `#CC5214` | Orange hover/focused state |
| `--color-text` | `#F0EDE8` | Warm white text |
| `--color-text-muted` | `#8A867F` | Subtext/placeholders |
| `--color-danger` | `#E05252` | Over-budget alerts, deletes, error toasts |
| `--color-success` | `#4CAF79` | Under-budget states, met goals, success toasts |

- **Typography**: The primary typeface is **Spectral** from Google Fonts (weights 200–800, normal and italic).
- **Default Payers**: **Joint, Carson, Chloe** are standard defaults. While settings list distinct values dynamically from current database entries, default fallback references must respect these names.
- **sidebar**: Keep the left navigation layout in `web/src/layouts/AppLayout.tsx` persistent, featuring a Spectral 300 weight app title and active-indicator highlights on links.

---

## Key Features & Logic to Maintain

1. **Dashboard & Sparklines**:
   - High-level charts are generated using `recharts`.
   - Live budget health calculates expenses versus current active budgets.

2. **Budget Planner**:
   - Supports monthly limit settings and draft management. Draft budgets are created under `budget_drafts` and can be bulk committed to the active database.
   - Recommended budget limits utilize a **Weighted Moving Average (WMA)** of historical monthly spends with "Hasty" (0.6 / 0.3 / 0.1) and "Conservative" (0.4 / 0.4 / 0.2) modes.

3. **CSV Bank Statement Importer**:
   - Handles parsing for **BECU Credit Card, Chase Credit Card, Chase Bank, and Generic** formats.
   - Implements fuzzy duplicate detection against the `expenses` table based on dates, description signatures, and amounts.
   - Features a bulk staging database editor in settings to review columns, apply custom categories/payers, and save.

4. **Goal Milestones**:
   - Supports linking categories/subcategories to savings goals via `goal_budget_links`.
   - Tracks current saved amounts dynamically based on connected budget lines and dates.

---

## Maintenance & Release Verification

Before committing changes:
1. **Frontend Verification**:
   - Build frontend assets cleanly: `cd web && npm run build` (ensure no TypeScript compiler or linter failures).
   - Verify React components are fully responsive and feature smooth micro-animations.
2. **Backend Verification**:
   - Verify all endpoints run cleanly by testing against the local uvicorn host.
   - Make sure no exceptions are swallowed without logging.
3. **Standalone App Package Verification**:
   - Check if PyInstaller can compile the desktop bundle correctly on macOS:
     ```bash
     source .venv/bin/activate
     python3 scripts/generate_vector_icon.py
     python3 scripts/build_mac_app.py
     ```
   - Verify that the generated desktop app launcher (`Household Budgeting.app`) correctly boots, connects to the local FastAPI socket, and opens the UI.

---

## Agent Session Logging

At the end of every conversation session, you MUST write a new session log file under `.agents/agent_logs/session_YYYYMMDD_HHMMSS.md` (using the current date and time). This file acts as a handover log for the next session.

The log MUST follow this exact format:
- **Title**: `# Agent Session Log — session_YYYYMMDD_HHMMSS`
- **Session Date**: `**Session Date:** YYYY-MM-DD`
- **Focus Files**: A bullet point list of files that were primarily targeted, added, or modified in the session.
- **What Was Completed**: Detailed, descriptive bullet points explaining files changed, bugs resolved, data migrations, script execution outputs, and any critical design decisions.
- **What Is Left To Do**: A task list with checkboxes showing outstanding tasks and next steps.
- **How to Catch Up Fast**: Simple developer quick-start steps detailing how to run verification, test the database, or spin up the server to see the current state of the application.

