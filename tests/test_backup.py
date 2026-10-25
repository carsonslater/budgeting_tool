"""
tests/test_backup.py

The safety snapshot taken before a live database is migrated.

`snapshot_database` uses SQLite's backup API: a plain file copy of a database in WAL
mode can miss committed pages that live only in the `-wal` file.  The lifespan test
drives the real startup hook (`with TestClient(app)`).

The database is built on a temp path, never `data/budget.db`.
"""

import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Allow imports from backend/ when running tests from project root
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import database
from main import app


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    """An initialized (not migrated) database at tmp/data/budget.db."""
    path = tmp_path / "data" / "budget.db"
    monkeypatch.setattr(database, "_DB_PATH", path)
    database.init_db()
    return path


def add_expense(conn):
    conn.execute(
        "INSERT INTO expenses (date, description, category, amount) "
        "VALUES ('2025-01-01', 'x', 'Food', 1.0)"
    )
    conn.commit()


def backups(db_path):
    folder = db_path.parent.parent / "backups"
    return sorted(folder.glob("*.db")) if folder.exists() else []


class TestSnapshot:
    def test_backups_live_beside_the_data_folder(self, db_path):
        assert database.backups_dir() == db_path.parent.parent / "backups"

    def test_the_copy_includes_rows_that_only_exist_in_the_wal(self, db_path, tmp_path):
        conn = database.get_db()  # WAL mode, left open: nothing checkpointed
        try:
            add_expense(conn)
            dest = database.snapshot_database(tmp_path / "out" / "copy.db")
        finally:
            conn.close()

        copy = sqlite3.connect(str(dest))
        try:
            assert copy.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 1
        finally:
            copy.close()

    def test_has_data(self, db_path):
        with database.get_db() as conn:
            assert database.has_data(conn) is False
            add_expense(conn)
            assert database.has_data(conn) is True

    def test_the_backup_endpoint_writes_a_snapshot(self, db_path):
        with TestClient(app) as client:
            resp = client.post("/api/backup")
        assert resp.json()["message"] == "Backup created"
        [snap] = [p for p in backups(db_path) if p.name.startswith("budget_")]
        assert snap.stat().st_size > 0


class TestStartupSnapshot:
    def test_an_existing_database_is_snapshotted_before_migrating(self, db_path):
        with database.get_db() as conn:
            add_expense(conn)

        with TestClient(app):
            pass

        [snap] = backups(db_path)
        assert snap.name.startswith("pre_migration_v0_to_v3_")
        # The snapshot is the pre-migration state: no versioned budget tables yet.
        copy = sqlite3.connect(str(snap))
        try:
            assert copy.execute("PRAGMA user_version").fetchone()[0] == 0
            assert copy.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 1
            tables = {r[0] for r in copy.execute("SELECT name FROM sqlite_master")}
            assert "budget_lines" not in tables
        finally:
            copy.close()

        live = sqlite3.connect(str(db_path))
        try:
            assert live.execute("PRAGMA user_version").fetchone()[0] == 3
        finally:
            live.close()

    def test_no_second_snapshot_when_nothing_is_pending(self, db_path):
        with database.get_db() as conn:
            add_expense(conn)
        with TestClient(app):
            pass
        with TestClient(app):
            pass
        assert len(backups(db_path)) == 1

    def test_an_empty_database_is_not_snapshotted(self, db_path):
        with TestClient(app):
            pass
        assert backups(db_path) == []
