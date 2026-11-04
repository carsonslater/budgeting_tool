"""
tests/test_migration_m0007.py

m0007 creates app_settings, sets the schema version, and is a no-op when re-run.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import database
from migrations import LATEST_VERSION, run_migrations
from migrations.runner import get_user_version


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "test_budget.db"
    monkeypatch.setattr(database, "_DB_PATH", path)
    database.init_db()
    return path


def test_creates_app_settings_and_advances_the_version(db_path):
    with database.get_db() as conn:
        run_migrations(conn)
        assert get_user_version(conn) == LATEST_VERSION == 7
        columns = [r[1] for r in conn.execute("PRAGMA table_info(app_settings)")]
        assert columns == ["key", "value"]


def test_rerunning_applies_nothing(db_path):
    with database.get_db() as conn:
        run_migrations(conn)
        assert run_migrations(conn) == []
