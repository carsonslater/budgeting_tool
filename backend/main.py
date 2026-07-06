"""
main.py — FastAPI application entry point.

Start in development:
    uvicorn main:app --reload            (from backend/)
    uvicorn backend.main:app --reload    (from project root)

Port defaults to 8000; override with PORT env var.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers import expenses, budgets, income, goals, reporting, import_csv, budget_drafts


# ── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run DB initialisation on startup."""
    init_db()
    yield


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Household Budgeting API",
    description="Local-first budgeting backend — FastAPI + SQLite",
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Allow the Vite dev server (localhost:5173) and any localhost origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(expenses.router)
app.include_router(budgets.router)
app.include_router(budget_drafts.router)
app.include_router(income.router)
app.include_router(goals.router)
app.include_router(reporting.router)
app.include_router(import_csv.router)


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/healthz", tags=["health"])
def health() -> dict:
    return {"status": "ok"}


# ── System / Settings ──────────────────────────────────────────────────────────

import shutil
import platform
import subprocess
from datetime import datetime
from database import _DB_PATH

@app.post("/api/backup", tags=["system"])
def backup_data() -> dict:
    backups_dir = _DB_PATH.parent.parent / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backups_dir / f"budget_{stamp}.db"
    if not _DB_PATH.exists():
        return {"error": "No DB found"}
    shutil.copy2(_DB_PATH, dest)
    return {"message": "Backup created", "timestamp": stamp}

@app.get("/api/system/last-saved", tags=["system"])
def get_last_saved() -> dict:
    if not _DB_PATH.exists():
        return {"last_saved": None}
    try:
        mtime = _DB_PATH.stat().st_mtime
        stamp = datetime.fromtimestamp(mtime).isoformat()
        return {"last_saved": stamp}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/open-data-folder", tags=["system"])
def open_data_folder() -> dict:
    folder = _DB_PATH.parent
    folder.mkdir(parents=True, exist_ok=True)
    try:
        if platform.system() == "Darwin":
            subprocess.run(["open", str(folder)])
        elif platform.system() == "Windows":
            subprocess.run(["explorer", str(folder)])
        else:
            subprocess.run(["xdg-open", str(folder)])
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

# ── Static Files (Frontend) ───────────────────────────────────────────────────
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

frontend_dir = Path(__file__).parent.parent / "web" / "dist"

if frontend_dir.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dir / "assets"), name="assets")

    @app.api_route("/{path_name:path}", methods=["GET"])
    def catch_all(path_name: str):
        file_path = frontend_dir / path_name
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(frontend_dir / "index.html")

# ── Dev runner ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="127.0.0.1", port=port, reload=True)
