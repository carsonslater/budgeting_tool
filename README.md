# Household Budgeting

A local-first, private-by-design desktop budgeting application. 

This application replaces an older R/Shiny stack with a modern architecture: **FastAPI (Python)** on the backend and **Vite + React (TypeScript)** on the frontend. The entire application runs locally, utilizing SQLite for fast, robust data persistence without any cloud tracking or external databases.

## Technology Stack

- **Backend:** FastAPI, Python, SQLite
- **Frontend:** Vite, React, TypeScript, React Query, Recharts
- **Desktop Wrapper:** `pywebview` (renders the React app in a native OS window)

## Requirements

- Python 3.9+
- Node.js 18+

## Quick Start (Development)

To run the application in a hot-reloading development environment:

1. **Install Backend Dependencies:**
   ```bash
   pip install -r backend/requirements.txt
   ```

2. **Install Frontend Dependencies:**
   ```bash
   cd web
   npm install
   ```

3. **Start the Backend:**
   In a new terminal window, run:
   ```bash
   uvicorn backend.main:app --reload
   ```

4. **Start the Frontend:**
   In a new terminal window, run:
   ```bash
   cd web
   npm run dev
   ```

The application will be available in your browser at `http://localhost:5173`.

## Data Migration

If you are migrating from the old R/Shiny application, you must import your existing CSV files into the new SQLite database:

1. Ensure your old `budget.csv`, `budgets.csv`, `goals.csv`, etc., are located in `data/`.
2. Run the migration script once:
   ```bash
   python backend/migrate.py
   ```
This will seed `data/budget.db` with all your historical data.

## Desktop Launch

To run the application as a standalone desktop window:

1. Build the production frontend bundle:
   ```bash
   cd web
   npm run build
   ```
2. Launch the desktop app from the project root:
   ```bash
   python desktop_app.py
   ```
This script automatically spins up the FastAPI server, serves the built static frontend files, and mounts it into a native `pywebview` desktop window.

### Dev Mode Desktop Launch
If you want to test the desktop window while keeping Vite's hot-reloading active:
```bash
python desktop_app.py --dev
```
*(Ensure `npm run dev` is running in another terminal).*
