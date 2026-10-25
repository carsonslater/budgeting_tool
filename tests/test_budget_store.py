"""
tests/test_budget_store.py

Unit tests for the sparse versioned budget model in backend/budget_store.py.

Semantics under test (plan 2026-10-25 §4):

* the amount for month M is the version row with the greatest effective_month <= M
* a tombstone (amount IS NULL) ends a line; reads never write
* an edit takes an apply scope: forward (until changed), month, or through <month>
* one line per (category, subcategory); an ended line is revived, not duplicated
* only the latest frequency is kept; changing it rescales history

A model-based test at the end drives random edits and checks them against both an
independent oracle and a scope property that needs no oracle at all.
"""

import random
import sys
from pathlib import Path

import pytest

# Allow imports from backend/ when running tests from project root
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import budget_store as store
import database
from migrations import run_migrations

TABLES = ("budget_lines", "budget_amounts", "month_plans")


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    """A freshly initialized, fully migrated database on a temp path."""
    path = tmp_path / "test_budget.db"
    monkeypatch.setattr(database, "_DB_PATH", path)
    database.init_db()
    c = database.get_db()
    run_migrations(c)
    yield c
    c.close()


def snapshot(conn):
    """Every row of every budget table, for 'nothing was written' assertions."""
    return {
        t: sorted(tuple(r) for r in conn.execute(f"SELECT * FROM {t}")) for t in TABLES
    }


def amount_in(conn, key, month):
    line = store.get_line(conn, key, month)
    return None if line is None else line["limit_amount"]


def amounts(conn, key, months):
    return {m: amount_in(conn, key, m) for m in months}


def versions(conn, key):
    info = store.line_versions(conn, key)
    return [(v["effective_month"], v["amount"]) for v in info["versions"]]


@pytest.fixture()
def food(conn):
    """Food/Groceries at 100, effective from 2025-01 until changed."""
    row = store.insert_line(
        conn, "2025-01", category="Food", subcategory="Groceries", limit_amount=100.0
    )
    return row["line_key"]


# ── Resolution ───────────────────────────────────────────────────────────────


class TestResolution:
    def test_a_month_before_the_first_version_has_no_line(self, conn, food):
        assert store.lines_for_month(conn, "2024-12") == []

    def test_every_later_month_resolves_forward(self, conn, food):
        for month in ("2025-01", "2025-02", "2027-06", "2040-12"):
            [line] = store.lines_for_month(conn, month)
            assert line["limit_amount"] == 100.0
            assert line["category"] == "Food"
            assert line["subcategory"] == "Groceries"
            assert line["month"] == month

    def test_row_shape_keeps_the_fields_routers_use(self, conn, food):
        [line] = store.lines_for_month(conn, "2025-03")
        assert {
            "id",
            "line_key",
            "category_id",
            "subcategory_id",
            "category",
            "subcategory",
            "limit_amount",
            "frequency",
            "month",
            "effective_since",
        } <= set(line)
        assert line["effective_since"] == "2025-01"
        assert isinstance(line["id"], int)

    def test_reads_never_write(self, conn, food):
        store.delete_line(conn, "2025-06", food, apply="through", through="2025-08")
        before = snapshot(conn)

        store.resolve_view(conn, "2025-04")
        store.resolve_view(conn, "2031-01")
        store.lines_for_month(conn, "2024-01")
        store.get_line(conn, food, "2025-07")
        store.lines_in_range(conn, "2025-01", "2025-12")
        store.months_by_line(conn, "2025-01", None)
        store.line_versions(conn, food)
        store.get_plan(conn, "2025-04")

        assert snapshot(conn) == before

    def test_a_blank_subcategory_reads_as_empty_string(self, conn):
        store.insert_line(conn, "2025-01", category="Rent", limit_amount=900.0)
        [line] = store.lines_for_month(conn, "2025-01")
        assert line["subcategory"] == ""
        assert line["subcategory_id"] is None

    def test_inherited_means_not_confirmed(self, conn, food):
        _, inherited = store.resolve_view(conn, "2025-03")
        assert inherited is True
        store.confirm_month(conn, "2025-03")
        assert store.resolve_view(conn, "2025-03")[1] is False
        # Confirming one month does not confirm its neighbours.
        assert store.resolve_view(conn, "2025-04")[1] is True
        assert store.resolve_view(conn, "2025-02")[1] is True

    def test_malformed_months_are_rejected(self, conn, food):
        for bad in ("2025-13", "2025-1", "25-01", "", "2025-01-01", "2025_01"):
            with pytest.raises(ValueError):
                store.lines_for_month(conn, bad)
        with pytest.raises(ValueError):
            store.insert_line(conn, "2025-13", category="X")


# ── Apply scopes ─────────────────────────────────────────────────────────────

MONTHS = [f"2025-{m:02d}" for m in range(1, 9)]


class TestApplyScopes:
    def test_month_scope_changes_only_that_month(self, conn, food):
        store.update_line(conn, "2025-03", food, limit_amount=150.0, apply="month")

        got = amounts(conn, food, MONTHS)
        assert got["2025-02"] == 100.0
        assert got["2025-03"] == 150.0
        assert got["2025-04"] == 100.0
        assert got["2025-08"] == 100.0

    def test_through_scope_restores_the_prior_value_afterwards(self, conn, food):
        store.update_line(
            conn,
            "2025-03",
            food,
            limit_amount=150.0,
            apply="through",
            through="2025-05",
        )

        got = amounts(conn, food, MONTHS)
        assert got["2025-02"] == 100.0
        assert [got[m] for m in ("2025-03", "2025-04", "2025-05")] == [150.0] * 3
        assert got["2025-06"] == 100.0
        assert got["2025-08"] == 100.0

    def test_through_overrides_explicit_rows_inside_the_range(self, conn, food):
        store.update_line(conn, "2025-04", food, limit_amount=120.0)  # forward
        store.update_line(
            conn,
            "2025-03",
            food,
            limit_amount=150.0,
            apply="through",
            through="2025-05",
        )

        got = amounts(conn, food, MONTHS)
        assert [got[m] for m in ("2025-03", "2025-04", "2025-05")] == [150.0] * 3
        # What was in force after the range (120, set at April) is restored, not lost.
        assert got["2025-06"] == 120.0
        assert got["2025-08"] == 120.0
        assert ("2025-04", 120.0) not in versions(conn, food)

    def test_through_keeps_an_explicit_row_already_at_the_following_month(
        self, conn, food
    ):
        store.update_line(conn, "2025-06", food, limit_amount=300.0)  # forward
        store.update_line(
            conn,
            "2025-03",
            food,
            limit_amount=150.0,
            apply="through",
            through="2025-05",
        )

        got = amounts(conn, food, MONTHS)
        assert got["2025-05"] == 150.0
        assert got["2025-06"] == 300.0
        assert got["2025-08"] == 300.0

    def test_forward_scope_stops_at_the_next_explicit_change(self, conn, food):
        store.update_line(conn, "2025-06", food, limit_amount=300.0)
        store.update_line(conn, "2025-03", food, limit_amount=150.0)  # default: forward

        got = amounts(conn, food, MONTHS)
        assert got["2025-02"] == 100.0
        assert [got[m] for m in ("2025-03", "2025-04", "2025-05")] == [150.0] * 3
        assert got["2025-06"] == 300.0

    def test_forward_edits_reach_far_future_months(self, conn, food):
        store.update_line(conn, "2025-03", food, limit_amount=150.0)
        assert amount_in(conn, food, "2031-11") == 150.0

    def test_a_scope_error_writes_nothing(self, conn, food):
        before = snapshot(conn)
        with pytest.raises(ValueError):
            store.update_line(
                conn,
                "2025-05",
                food,
                limit_amount=1.0,
                apply="through",
                through="2025-03",
            )
        with pytest.raises(ValueError):
            store.update_line(conn, "2025-05", food, limit_amount=1.0, apply="through")
        with pytest.raises(ValueError):
            store.update_line(conn, "2025-05", food, limit_amount=1.0, apply="sideways")
        with pytest.raises(ValueError):
            store.delete_line(conn, "2025-05", food, apply="through", through="bogus")
        assert snapshot(conn) == before

    def test_editing_to_the_value_already_in_force_adds_no_rows(self, conn, food):
        store.update_line(conn, "2025-05", food, limit_amount=100.0)
        assert versions(conn, food) == [("2025-01", 100.0)]

    def test_changing_a_value_back_collapses_the_redundant_rows(self, conn, food):
        store.update_line(conn, "2025-03", food, limit_amount=150.0, apply="month")
        assert versions(conn, food) == [
            ("2025-01", 100.0),
            ("2025-03", 150.0),
            ("2025-04", 100.0),
        ]
        store.update_line(conn, "2025-03", food, limit_amount=100.0, apply="month")
        assert versions(conn, food) == [("2025-01", 100.0)]

    def test_create_with_through_ends_the_line_afterwards(self, conn):
        row = store.insert_line(
            conn,
            "2025-02",
            category="Auto",
            subcategory="Oil",
            limit_amount=50.0,
            apply="through",
            through="2025-03",
        )
        key = row["line_key"]
        got = amounts(
            conn, key, ["2025-01", "2025-02", "2025-03", "2025-04", "2025-09"]
        )
        assert got == {
            "2025-01": None,
            "2025-02": 50.0,
            "2025-03": 50.0,
            "2025-04": None,
            "2025-09": None,
        }


class TestDelete:
    def test_month_scope(self, conn, food):
        assert store.delete_line(conn, "2025-03", food, apply="month") == 1
        got = amounts(conn, food, MONTHS)
        assert got["2025-02"] == 100.0
        assert got["2025-03"] is None
        assert got["2025-04"] == 100.0

    def test_forward_scope_ends_the_line(self, conn, food):
        assert store.delete_line(conn, "2025-03", food) == 1  # default: forward
        got = amounts(conn, food, MONTHS)
        assert got["2025-02"] == 100.0
        assert got["2025-03"] is None
        assert got["2025-08"] is None
        assert amount_in(conn, food, "2035-01") is None

    def test_through_scope(self, conn, food):
        store.delete_line(conn, "2025-03", food, apply="through", through="2025-04")
        got = amounts(conn, food, MONTHS)
        assert got["2025-02"] == 100.0
        assert got["2025-03"] is None and got["2025-04"] is None
        assert got["2025-05"] == 100.0

    def test_deleting_from_a_lines_first_month_removes_it_entirely(self, conn, food):
        store.delete_line(conn, "2025-01", food)
        assert store.line_versions(conn, food) is None
        assert conn.execute("SELECT COUNT(*) FROM budget_lines").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM budget_amounts").fetchone()[0] == 0

    def test_history_survives_a_forward_delete(self, conn, food):
        store.delete_line(conn, "2025-03", food)
        assert amount_in(conn, food, "2025-02") == 100.0
        assert versions(conn, food) == [("2025-01", 100.0), ("2025-03", None)]

    def test_readding_an_ended_pair_revives_the_same_line(self, conn, food):
        store.delete_line(conn, "2025-03", food)
        row = store.insert_line(
            conn,
            "2025-07",
            category="Food",
            subcategory="Groceries",
            limit_amount=120.0,
        )
        assert row["line_key"] == food
        got = amounts(conn, food, MONTHS)
        assert got["2025-02"] == 100.0
        assert got["2025-04"] is None
        assert got["2025-07"] == 120.0
        assert conn.execute("SELECT COUNT(*) FROM budget_lines").fetchone()[0] == 1

    def test_an_inactive_line_is_a_noop(self, conn, food):
        store.delete_line(conn, "2025-03", food)
        before = snapshot(conn)

        assert store.delete_line(conn, "2025-05", food) == 0
        assert store.delete_line(conn, "2025-05", "no-such-key") == 0
        assert store.update_line(conn, "2025-05", food, limit_amount=1.0) is None
        assert store.update_line(conn, "2024-01", food, limit_amount=1.0) is None
        assert snapshot(conn) == before


# ── Conflicts and line-level edits ───────────────────────────────────────────


class TestLineIdentity:
    def test_a_second_active_line_for_the_same_pair_conflicts(self, conn, food):
        before = snapshot(conn)
        with pytest.raises(store.LineConflict):
            store.insert_line(
                conn,
                "2025-04",
                category="Food",
                subcategory="Groceries",
                limit_amount=5.0,
            )
        assert snapshot(conn) == before

    def test_the_same_category_with_a_different_subcategory_is_a_new_line(
        self, conn, food
    ):
        other = store.insert_line(
            conn, "2025-01", category="Food", subcategory="Dining", limit_amount=40.0
        )
        assert other["line_key"] != food
        assert len(store.lines_for_month(conn, "2025-01")) == 2

    def test_line_key_is_assigned_once_and_survives_edits(self, conn, food):
        store.update_line(conn, "2025-03", food, limit_amount=150.0, apply="month")
        store.update_line(
            conn, "2025-05", food, category="Eating", subcategory="Groceries"
        )
        assert {l["line_key"] for l in store.lines_for_month(conn, "2025-03")} == {food}
        assert {l["line_key"] for l in store.lines_for_month(conn, "2031-01")} == {food}

    def test_a_given_line_key_is_used_for_a_new_line(self, conn):
        row = store.insert_line(
            conn, "2025-01", category="Pets", limit_amount=30.0, line_key="fixed-key"
        )
        assert row["line_key"] == "fixed-key"

    def test_a_mismatched_line_key_for_an_existing_pair_is_rejected(self, conn, food):
        store.delete_line(conn, "2025-03", food)
        with pytest.raises(ValueError):
            store.insert_line(
                conn,
                "2025-06",
                category="Food",
                subcategory="Groceries",
                limit_amount=1.0,
                line_key="another-key",
            )

    def test_recategorizing_applies_to_every_month(self, conn, food):
        store.update_line(conn, "2025-05", food, category="Eating Out")
        for month in ("2025-01", "2025-05", "2030-01"):
            [line] = store.lines_for_month(conn, month)
            assert line["category"] == "Eating Out"
            assert line["subcategory"] == "Groceries"
            assert line["line_key"] == food

    def test_recategorizing_onto_an_occupied_pair_conflicts(self, conn, food):
        other = store.insert_line(
            conn, "2025-01", category="Food", subcategory="Dining", limit_amount=40.0
        )["line_key"]
        before = snapshot(conn)
        with pytest.raises(store.LineConflict):
            store.update_line(conn, "2025-02", other, subcategory="Groceries")
        assert amount_in(conn, other, "2025-02") == 40.0
        # No budget row changed (categories rows may have been created and are rolled
        # back by the caller's transaction).
        assert snapshot(conn) == before

    def test_a_blank_category_is_rejected(self, conn):
        with pytest.raises(ValueError):
            store.insert_line(conn, "2025-01", category="  ", limit_amount=1.0)

    def test_a_rename_is_visible_through_the_join_alone(self, conn, food):
        category_id = conn.execute(
            "SELECT category_id FROM budget_lines WHERE line_key = ?", (food,)
        ).fetchone()[0]
        conn.execute(
            "UPDATE categories SET name = 'Eating' WHERE id = ?", (category_id,)
        )

        [line] = store.lines_for_month(conn, "2025-04")
        assert line["category"] == "Eating"
        assert line["line_key"] == food


class TestFrequency:
    def test_an_invalid_frequency_is_rejected(self, conn, food):
        with pytest.raises(ValueError):
            store.insert_line(conn, "2025-01", category="X", frequency="Weekly")
        with pytest.raises(ValueError):
            store.update_line(conn, "2025-01", food, frequency="Weekly")

    def test_changing_frequency_rescales_history_and_applies_the_new_amount(
        self, conn, food
    ):
        # 100/month from January; from June it becomes 1500/year.
        store.update_line(
            conn, "2025-06", food, frequency="Annually", limit_amount=1500.0
        )

        [early] = store.lines_for_month(conn, "2025-03")
        [late] = store.lines_for_month(conn, "2025-07")
        assert early["frequency"] == late["frequency"] == "Annually"
        # 100/month == 1200/year, so the past keeps its monthly equivalent.
        assert early["limit_amount"] == pytest.approx(1200.0)
        assert late["limit_amount"] == 1500.0

    def test_changing_frequency_alone_preserves_monthly_equivalents(self, conn, food):
        store.update_line(conn, "2025-03", food, frequency="Quarterly")
        [line] = store.lines_for_month(conn, "2025-05")
        assert line["frequency"] == "Quarterly"
        assert line["limit_amount"] == pytest.approx(300.0)

    def test_reviving_with_a_new_frequency_rescales_the_old_versions(self, conn, food):
        store.delete_line(conn, "2025-03", food)
        store.insert_line(
            conn,
            "2025-06",
            category="Food",
            subcategory="Groceries",
            limit_amount=1200.0,
            frequency="Annually",
        )
        assert amount_in(conn, food, "2025-02") == pytest.approx(1200.0)
        assert store.line_versions(conn, food)["frequency"] == "Annually"


# ── Range shims (used by reporting and the subcategory suggestions) ──────────


class TestRangeReads:
    def test_months_by_line_lists_the_active_months(self, conn):
        key = store.insert_line(
            conn,
            "2025-02",
            category="Auto",
            subcategory="Oil",
            limit_amount=50.0,
            apply="through",
            through="2025-04",
        )["line_key"]

        assert store.months_by_line(conn, "2025-01", "2025-06") == {
            key: ["2025-02", "2025-03", "2025-04"]
        }
        assert store.months_by_line(conn, "2025-03", "2025-03") == {key: ["2025-03"]}
        assert store.months_by_line(conn, "2025-05", "2025-09") == {}

    def test_lines_in_range_carries_the_amount_in_force_each_month(self, conn, food):
        store.update_line(conn, "2025-03", food, limit_amount=150.0, apply="month")

        rows = store.lines_in_range(conn, "2025-02", "2025-04")
        assert [(r["month"], r["limit_amount"]) for r in rows] == [
            ("2025-02", 100.0),
            ("2025-03", 150.0),
            ("2025-04", 100.0),
        ]
        assert {r["category"] for r in rows} == {"Food"}

    def test_an_open_end_runs_to_the_present(self, conn, food):
        months = store.months_by_line(conn, "2025-01", None)[food]
        assert months[0] == "2025-01"
        assert months[-1] >= "2025-01"
        assert months == sorted(set(months))
        # Runs through today (a line with no end is still in force).
        import datetime

        assert months[-1] >= datetime.date.today().strftime("%Y-%m")

    def test_ranges_on_an_empty_database(self, conn):
        assert store.months_by_line(conn, "2025-01", "2025-12") == {}
        assert store.lines_in_range(conn, "2025-01", None) == []

    def test_line_versions(self, conn, food):
        store.update_line(conn, "2025-03", food, limit_amount=150.0)
        info = store.line_versions(conn, food)
        assert info["frequency"] == "Monthly"
        assert [(v["effective_month"], v["amount"]) for v in info["versions"]] == [
            ("2025-01", 100.0),
            ("2025-03", 150.0),
        ]
        assert store.line_versions(conn, "missing") is None


# ── Month plans ──────────────────────────────────────────────────────────────


class TestPlans:
    def test_an_untouched_month_is_inherited_with_no_income(self, conn):
        assert store.get_plan(conn, "2025-03") == {
            "month": "2025-03",
            "status": "inherited",
            "confirmed_at": None,
            "expected_income": None,
            "income_set_in": None,
        }

    def test_confirm_is_idempotent_and_keeps_the_first_timestamp(
        self, conn, monkeypatch
    ):
        stamps = iter(["2025-03-31T10:00:00", "2025-04-02T09:00:00"])
        monkeypatch.setattr(store, "_now", lambda: next(stamps))

        first = store.confirm_month(conn, "2025-03")
        second = store.confirm_month(conn, "2025-03")

        assert first["status"] == second["status"] == "confirmed"
        assert first["confirmed_at"] == second["confirmed_at"] == "2025-03-31T10:00:00"

    def test_confirming_writes_nothing_to_the_budget(self, conn, food):
        before = {k: v for k, v in snapshot(conn).items() if k != "month_plans"}
        store.confirm_month(conn, "2025-03")
        after = {k: v for k, v in snapshot(conn).items() if k != "month_plans"}
        assert after == before

    def test_income_is_inherited_forward(self, conn):
        store.set_expected_income(conn, "2025-03", 5000.0)
        assert store.effective_expected_income(conn, "2025-02") is None
        assert store.effective_expected_income(conn, "2025-03") == 5000.0
        assert store.effective_expected_income(conn, "2031-01") == 5000.0
        assert store.get_plan(conn, "2025-07")["income_set_in"] == "2025-03"

    def test_income_month_scope(self, conn):
        store.set_expected_income(conn, "2025-01", 5000.0)
        store.set_expected_income(conn, "2025-03", 5500.0, apply="month")
        got = [store.effective_expected_income(conn, f"2025-0{m}") for m in (2, 3, 4)]
        assert got == [5000.0, 5500.0, 5000.0]

    def test_income_through_scope_overrides_inside_and_restores_after(self, conn):
        store.set_expected_income(conn, "2025-01", 5000.0)
        store.set_expected_income(conn, "2025-04", 6000.0)
        store.set_expected_income(
            conn, "2025-03", 5500.0, apply="through", through="2025-05"
        )

        got = {
            m: store.effective_expected_income(conn, f"2025-{m:02d}")
            for m in range(2, 8)
        }
        assert got[2] == 5000.0
        assert [got[3], got[4], got[5]] == [5500.0] * 3
        assert got[6] == 6000.0  # the value in force after the range comes back
        assert got[7] == 6000.0

    def test_income_through_with_no_prior_value_ends_at_zero(self, conn):
        store.set_expected_income(
            conn, "2025-03", 5500.0, apply="through", through="2025-04"
        )
        assert store.effective_expected_income(conn, "2025-04") == 5500.0
        assert store.effective_expected_income(conn, "2025-05") == 0.0

    def test_income_forward_stops_at_the_next_explicit_value(self, conn):
        store.set_expected_income(conn, "2025-06", 7000.0)
        store.set_expected_income(conn, "2025-03", 5500.0)
        assert store.effective_expected_income(conn, "2025-05") == 5500.0
        assert store.effective_expected_income(conn, "2025-06") == 7000.0

    def test_redundant_income_rows_are_pruned(self, conn):
        store.set_expected_income(conn, "2025-01", 5000.0)
        store.set_expected_income(conn, "2025-06", 5000.0)
        assert conn.execute("SELECT COUNT(*) FROM month_plans").fetchone()[0] == 1

    def test_setting_income_does_not_confirm_a_month(self, conn):
        store.set_expected_income(conn, "2025-03", 5000.0)
        assert store.get_plan(conn, "2025-03")["status"] == "inherited"

    def test_confirmed_state_survives_income_changes(self, conn):
        store.confirm_month(conn, "2025-03")
        store.set_expected_income(conn, "2025-03", 5000.0)
        store.set_expected_income(conn, "2025-03", 5000.0, apply="month")
        assert store.get_plan(conn, "2025-03")["status"] == "confirmed"

    def test_income_validation(self, conn):
        with pytest.raises(ValueError):
            store.set_expected_income(conn, "2025-03", -1.0)
        with pytest.raises(ValueError):
            store.set_expected_income(conn, "2025-03", 1.0, apply="through")
        with pytest.raises(ValueError):
            store.set_expected_income(conn, "2025-13", 1.0)

    def test_plan_statuses_covers_every_month_in_range(self, conn):
        store.confirm_month(conn, "2025-03")
        out = store.plan_statuses(conn, "2025-02", "2025-04")
        assert [(p["month"], p["status"]) for p in out] == [
            ("2025-02", "inherited"),
            ("2025-03", "confirmed"),
            ("2025-04", "inherited"),
        ]


# ── Model-based test ─────────────────────────────────────────────────────────

PAIRS = [("Food", "Groceries"), ("Food", "Dining"), ("Auto", "")]
HORIZON = [f"{y}-{m:02d}" for y in (2025, 2026) for m in range(1, 13)]
SEED = 7319
STEPS = 400


class Oracle:
    """
    An independent, brute-force statement of the semantics: a plain dict of explicit
    versions per pair, evaluated by scanning keys.  No SQL.
    """

    def __init__(self):
        self.rows: dict[tuple, dict[str, float | None]] = {p: {} for p in PAIRS}

    def eff(self, pair, month):
        keys = [k for k in self.rows[pair] if k <= month]
        return self.rows[pair][max(keys)] if keys else None

    def write(self, pair, month, amount, apply, through):
        rows = self.rows[pair]
        end = {"forward": None, "month": month, "through": through}[apply]
        if end is not None:
            after = store.shift_month(end, 1)
            restore = self.eff(pair, after)
            for k in [k for k in rows if month < k <= end]:
                del rows[k]
        rows[month] = amount
        if end is not None and after not in rows:
            rows[after] = restore

        # A row that does not change the value in force is invisible to the user, so it
        # must not bound a later "forward" edit either.  Drop such rows.
        previous = None
        for k in sorted(rows):
            if rows[k] == previous:
                del rows[k]
            else:
                previous = rows[k]


def _key_for(conn, pair):
    row = conn.execute(
        """SELECT l.line_key FROM budget_lines l
           JOIN categories c ON c.id = l.category_id
           LEFT JOIN categories s ON s.id = l.subcategory_id
           WHERE c.name = ? AND COALESCE(s.name, '') = ?""",
        pair,
    ).fetchone()
    return row[0] if row else None


def _view(conn, pair):
    key = _key_for(conn, pair)
    return {m: (None if key is None else amount_in(conn, key, m)) for m in HORIZON}


def _assert_no_redundant_rows(conn):
    for (key,) in conn.execute("SELECT line_key FROM budget_lines").fetchall():
        prev = None
        for month, amount in versions(conn, key):
            assert amount != prev, f"redundant row {month} for {key}"
            prev = amount


def test_random_edits_match_the_oracle_and_the_scope_properties(conn):
    rng = random.Random(SEED)
    oracle = Oracle()

    for step in range(STEPS):
        pair = rng.choice(PAIRS)
        month = rng.choice(HORIZON)
        apply = rng.choice(["forward", "month", "through"])
        through = None
        if apply == "through":
            through = store.shift_month(month, rng.randint(0, 5))
        amount = float(rng.randint(1, 20) * 10)
        op = rng.choice(["insert", "update", "update", "delete"])

        before = _view(conn, pair)
        active = oracle.eff(pair, month) is not None
        scope = {"apply": apply, "through": through}

        if op == "insert":
            category, subcategory = pair
            if active:
                with pytest.raises(store.LineConflict):
                    store.insert_line(
                        conn,
                        month,
                        category=category,
                        subcategory=subcategory,
                        limit_amount=amount,
                        **scope,
                    )
                continue
            store.insert_line(
                conn,
                month,
                category=category,
                subcategory=subcategory,
                limit_amount=amount,
                **scope,
            )
            oracle.write(pair, month, amount, apply, through)
        else:
            key = _key_for(conn, pair)
            if not active or key is None:
                continue
            if op == "update":
                assert store.update_line(conn, month, key, limit_amount=amount, **scope)
                oracle.write(pair, month, amount, apply, through)
            else:
                assert store.delete_line(conn, month, key, **scope) == 1
                oracle.write(pair, month, None, apply, through)
                amount = None

        after = _view(conn, pair)

        # 1. The store agrees with the oracle in every month.
        assert after == {m: oracle.eff(pair, m) for m in HORIZON}, f"step {step}"

        # 2. Scope properties, stated densely (no oracle needed).
        end = {"forward": None, "month": month, "through": through}[apply]
        for m in HORIZON:
            if m < month or (end is not None and m > end):
                assert after[m] == before[m], f"step {step}: {m} changed outside scope"
        assert after[month] == amount

        # 3. Storage stays normalized.
        _assert_no_redundant_rows(conn)
