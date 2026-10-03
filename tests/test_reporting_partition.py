"""
tests/test_reporting_partition.py

Phase 1 acceptance criterion (plan §9, "Annual partition"):

    assert a non-monthly line never appears in the monthly budget-health
    payload, and that its spend cannot change a monthly line's status.

The defect this guards: a non-monthly limit used to be divided by its cadence
divisor and compared against a single month's spend, so a $1200/yr line showed
as an $100/mo line and turned into a false red flag in months with no matching
spend. Budgets and expenses are matched by (category, subcategory) name, so the
only thing keeping the two partitions from influencing each other is the
partition itself — these tests pin that boundary.

The database is built on a temp path, never `data/budget.db`.
"""

import sys
from pathlib import Path

import pytest

# Allow imports from backend/ when running tests from project root
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import database
from migrations import run_migrations
from routers.reporting import budget_summary


MONTH = "2025-03"

MONTHLY_LINE = ("Food", "Groceries", 500.0, "Monthly", "2025-01-01", None)
ANNUAL_LINE = ("Auto", "Maintenance", 1200.0, "Annually", "2025-01-01", None)

MONTHLY_EXPENSE = (
    "2025-03-10",
    "Groceries run",
    "Food",
    "Groceries",
    100.0,
    "Joint",
    "Monthly",
)
ANNUAL_EXPENSE = (
    "2025-03-20",
    "Annual service",
    "Auto",
    "Maintenance",
    1200.0,
    "Carson",
    "Monthly",
)


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    """A freshly initialized, fully migrated database on a temp path."""
    path = tmp_path / "test_budget.db"
    monkeypatch.setattr(database, "_DB_PATH", path)
    database.init_db()
    with database.get_db() as conn:
        run_migrations(conn)
    return path


def _insert(db_path, budgets=(), expenses=()):
    conn = database.get_db()
    conn.executemany(
        """INSERT INTO budgets
             (category, subcategory, limit_amount, frequency, effective_date, conclusion_date)
           VALUES (?,?,?,?,?,?)""",
        budgets,
    )
    conn.executemany(
        """INSERT INTO expenses
             (date, description, category, subcategory, amount, payer, expense_type)
           VALUES (?,?,?,?,?,?,?)""",
        expenses,
    )
    conn.commit()
    conn.close()


def _line(payload, category, subcategory):
    """The single row for (category, subcategory) in a partition, or None."""
    hits = [
        r
        for r in payload
        if r["category"] == category and r["subcategory"] == subcategory
    ]
    assert len(hits) <= 1, f"duplicate {category}/{subcategory} rows"
    return hits[0] if hits else None


class TestPartitionBoundary:
    def test_each_line_lands_in_exactly_one_partition(self, db_path):
        _insert(db_path, [MONTHLY_LINE, ANNUAL_LINE], [MONTHLY_EXPENSE, ANNUAL_EXPENSE])
        out = budget_summary(MONTH)

        assert set(out) == {"monthly", "non_monthly"}
        assert _line(out["monthly"], "Food", "Groceries") is not None
        assert _line(out["monthly"], "Auto", "Maintenance") is None
        assert _line(out["non_monthly"], "Auto", "Maintenance") is not None
        assert _line(out["non_monthly"], "Food", "Groceries") is None

    def test_partitions_carry_only_their_own_frequency(self, db_path):
        _insert(db_path, [MONTHLY_LINE, ANNUAL_LINE], [MONTHLY_EXPENSE, ANNUAL_EXPENSE])
        out = budget_summary(MONTH)

        assert {r["frequency"] for r in out["monthly"]} == {"Monthly"}
        assert all(r["frequency"] != "Monthly" for r in out["non_monthly"])

    def test_annual_limit_is_not_divided_by_cadence(self, db_path):
        """The original defect: 1200/yr must not surface as 100/mo."""
        _insert(db_path, [ANNUAL_LINE], [ANNUAL_EXPENSE])
        row = _line(budget_summary(MONTH)["non_monthly"], "Auto", "Maintenance")

        assert row["budget"] == 1200.0
        assert row["budget"] != pytest.approx(100.0)

    def test_non_monthly_row_exposes_its_period(self, db_path):
        _insert(db_path, [ANNUAL_LINE], [])
        row = _line(budget_summary(MONTH)["non_monthly"], "Auto", "Maintenance")

        # Calendar-aligned: 2025-03 falls in the 2025 calendar year.
        assert row["period_start"] == "2025-01-01"
        assert row["period_end"] == "2025-12-31"

    def test_quarterly_period_is_calendar_aligned(self, db_path):
        _insert(
            db_path,
            [("Auto", "Oil", 300.0, "Quarterly", "2025-01-01", None)],
            [],
        )
        row = _line(budget_summary("2025-02")["non_monthly"], "Auto", "Oil")

        assert row["period_start"] == "2025-01-01"
        assert row["period_end"] == "2025-03-31"


class TestMonthlyLineIsIndependent:
    """A non-monthly line's spend must not perturb a monthly line's status."""

    def test_annual_spend_does_not_change_the_monthly_partition(self, db_path):
        _insert(db_path, [MONTHLY_LINE, ANNUAL_LINE], [MONTHLY_EXPENSE])
        without_annual = budget_summary(MONTH)["monthly"]

        _insert(db_path, [], [ANNUAL_EXPENSE])
        with_annual = budget_summary(MONTH)["monthly"]

        assert with_annual == without_annual

    def test_monthly_line_status_reflects_only_its_own_spend(self, db_path):
        # A large annual charge lands under a *different* line; the monthly line
        # stays "Under" because only its own 100.00 is counted against it.
        _insert(
            db_path,
            [MONTHLY_LINE, ANNUAL_LINE],
            [MONTHLY_EXPENSE, ANNUAL_EXPENSE],
        )
        row = _line(budget_summary(MONTH)["monthly"], "Food", "Groceries")

        assert row["spent"] == 100.0
        assert row["remaining"] == 400.0
        assert row["status"] == "Under"


class TestNonMonthlyAccrual:
    def test_spend_accrues_across_the_period(self, db_path):
        # Two charges earlier in the same calendar year both count when viewed
        # in March: cumulative spend across the period, through the month.
        _insert(
            db_path,
            [ANNUAL_LINE],
            [
                (
                    "2025-01-15",
                    "January charge",
                    "Auto",
                    "Maintenance",
                    300.0,
                    "Joint",
                    "Monthly",
                ),
                (
                    "2025-02-10",
                    "February charge",
                    "Auto",
                    "Maintenance",
                    400.0,
                    "Joint",
                    "Monthly",
                ),
            ],
        )
        row = _line(budget_summary(MONTH)["non_monthly"], "Auto", "Maintenance")

        assert row["spent"] == 700.0
        assert row["remaining"] == 500.0
        assert row["status"] == "Under"  # 700 / 1200 < 0.85

    def test_spend_outside_the_period_is_not_accrued(self, db_path):
        # A charge in the previous calendar year must not count toward 2025.
        _insert(
            db_path,
            [ANNUAL_LINE],
            [
                (
                    "2024-12-15",
                    "Prior year",
                    "Auto",
                    "Maintenance",
                    900.0,
                    "Joint",
                    "Monthly",
                )
            ],
        )
        row = _line(budget_summary(MONTH)["non_monthly"], "Auto", "Maintenance")

        assert row["spent"] == 0.0

    def test_spend_in_a_later_month_of_the_period_is_excluded(self, db_path):
        # Viewing March does not pull in spend from April (still 2025, but
        # after the requested month).
        _insert(
            db_path,
            [ANNUAL_LINE],
            [
                (
                    "2025-04-01",
                    "April charge",
                    "Auto",
                    "Maintenance",
                    500.0,
                    "Joint",
                    "Monthly",
                )
            ],
        )
        row = _line(budget_summary(MONTH)["non_monthly"], "Auto", "Maintenance")

        assert row["spent"] == 0.0

    def test_cumulative_spend_against_full_limit_sets_status(self, db_path):
        _insert(
            db_path,
            [ANNUAL_LINE],
            [
                (
                    "2025-01-15",
                    "Large charge",
                    "Auto",
                    "Maintenance",
                    1300.0,
                    "Joint",
                    "Monthly",
                )
            ],
        )
        row = _line(budget_summary(MONTH)["non_monthly"], "Auto", "Maintenance")

        assert row["spent"] == 1300.0
        assert row["status"] == "Over"
        assert row["remaining"] < 0

    def test_accrual_starts_at_effective_date_when_mid_period(self, db_path):
        # A quarterly line effective mid-quarter does not accrue spend from
        # before it existed.
        _insert(
            db_path,
            [("Auto", "Oil", 300.0, "Quarterly", "2025-02-01", None)],
            [
                (
                    "2025-01-10",
                    "Before effective",
                    "Auto",
                    "Oil",
                    100.0,
                    "Joint",
                    "Monthly",
                )
            ],
        )
        row = _line(budget_summary("2025-02")["non_monthly"], "Auto", "Oil")

        assert row["spent"] == 0.0
