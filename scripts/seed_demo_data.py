#!/usr/bin/env python3
"""
seed_demo_data.py — Seed a SQLite database with realistic, high-fidelity mock data.
This generates rich, premium-looking dashboards, line charts, overage indicators, 
and goal achievements to make the application shine for demo screenshots.
"""

import os
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# Resolve database path, prioritizing BUDGET_DB_PATH, defaulting to data/demo_budget.db
env_path = os.environ.get("BUDGET_DB_PATH")
if env_path:
    DB_PATH = Path(env_path)
else:
    PROJECT_DIR = Path(__file__).parent.parent.resolve()
    DB_PATH = PROJECT_DIR / "data" / "demo_budget.db"


def print_step(msg: str):
    print(f"==> \033[1;34m{msg}\033[0m")


def print_success(msg: str):
    print(f"\033[1;32m✓ {msg}\033[0m")


def init_db(conn: sqlite3.Connection):
    """Ensure all required tables exist in the database."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS expenses (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            date         TEXT    NOT NULL,
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
            effective_date  TEXT    NOT NULL,
            conclusion_date TEXT
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
            target_month  TEXT    NOT NULL,
            created_date  TEXT    NOT NULL,
            completed     INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS goal_budget_links (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_name   TEXT    NOT NULL,
            category    TEXT    NOT NULL,
            subcategory TEXT    NOT NULL DEFAULT '',
            start_date  TEXT    NOT NULL,
            end_date    TEXT
        );
    """)
    conn.commit()


def clear_tables(conn: sqlite3.Connection):
    """Truncate existing tables to make seeding clean and idempotent."""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM expenses")
    cursor.execute("DELETE FROM budgets")
    cursor.execute("DELETE FROM income_sources")
    cursor.execute("DELETE FROM goals")
    cursor.execute("DELETE FROM goal_budget_links")
    conn.commit()


def seed_data():
    print_step(f"Connecting to database: {DB_PATH}")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    # 1. Initialize schema
    init_db(conn)
    
    # 2. Clear old data
    clear_tables(conn)
    print_success("Initialized database schema and cleared existing tables.")
    
    cursor = conn.cursor()
    
    # 3. Seed Income Sources
    print_step("Seeding monthly income sources...")
    income_data = [
        ("Caleb's Tech Salary", 5400.00),
        ("Rae's Design Salary", 4900.00),
        ("Consulting / Side Hustle", 1250.00),
    ]
    cursor.executemany(
        "INSERT INTO income_sources (source, amount) VALUES (?, ?)", 
        income_data
    )
    
    # 4. Seed Budgets
    print_step("Seeding monthly budget categories...")
    budget_data = [
        # Category, Subcategory, Limit, Frequency, Effective Date, Conclusion Date
        ("Housing", "", 3200.00, "Monthly", "2026-01-01", None),
        ("Groceries", "", 750.00, "Monthly", "2026-01-01", None),
        ("Dining Out", "", 450.00, "Monthly", "2026-01-01", None),
        ("Utilities", "", 350.00, "Monthly", "2026-01-01", None),
        ("Entertainment", "", 250.00, "Monthly", "2026-01-01", None),
        ("Transportation", "", 300.00, "Monthly", "2026-01-01", None),
        ("Vacation", "", 600.00, "Monthly", "2026-01-01", None),
        ("Subscriptions", "", 80.00, "Monthly", "2026-01-01", None),
    ]
    cursor.executemany(
        """
        INSERT INTO budgets (category, subcategory, limit_amount, frequency, effective_date, conclusion_date)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        budget_data
    )
    
    # 5. Seed Goals
    print_step("Seeding active and completed goals...")
    goal_data = [
        # Name, Target, Target Month, Created, Completed
        ("Summer Trip to Japan", 6000.00, "2026-08", "2026-01-15", 0),
        ("Emergency Fund Reserve", 12000.00, "2026-12", "2026-01-01", 0),
        ("New Retina Workstation", 3500.00, "2026-05", "2026-02-10", 1), # Marked completed!
    ]
    cursor.executemany(
        "INSERT INTO goals (name, target_amount, target_month, created_date, completed) VALUES (?, ?, ?, ?, ?)",
        goal_data
    )
    
    # 6. Seed Goal Budget Links
    print_step("Seeding goal links...")
    link_data = [
        ("Summer Trip to Japan", "Vacation", "", "2026-01-15", None)
    ]
    cursor.executemany(
        "INSERT INTO goal_budget_links (goal_name, category, subcategory, start_date, end_date) VALUES (?, ?, ?, ?, ?)",
        link_data
    )
    
    # 7. Seed Historical & Active Month Expenses (March, April, and current month May 2026)
    print_step("Seeding rich financial ledger records...")
    
    # We will insert three months of data to ensure the graphs look dynamic and fully loaded.
    expenses_data = [
        # --- MARCH 2026 ---
        ("2026-03-01", "Monthly Mortgage Payment", "Housing", "", 3200.00, "Joint", "Monthly"),
        ("2026-03-03", "Whole Foods Market Run", "Groceries", "", 185.20, "Caleb", "Monthly"),
        ("2026-03-04", "City Power & Gas Bill", "Utilities", "", 172.40, "Joint", "Monthly"),
        ("2026-03-07", "Chez Panisse Bistro Dinner", "Dining Out", "", 145.00, "Rae", "Monthly"),
        ("2026-03-09", "Gas Station Chevron", "Transportation", "", 48.00, "Caleb", "Monthly"),
        ("2026-03-10", "Netflix Standard Premium", "Subscriptions", "", 22.99, "Joint", "Monthly"),
        ("2026-03-12", "Trader Joe's Provisions", "Groceries", "", 134.10, "Rae", "Monthly"),
        ("2026-03-14", "Stumptown Coffee Roasters", "Dining Out", "", 12.80, "Caleb", "Monthly"),
        ("2026-03-15", "SF Symphony Night", "Entertainment", "", 110.00, "Joint", "Monthly"),
        ("2026-03-18", "Apple Music Family", "Subscriptions", "", 16.99, "Caleb", "Monthly"),
        ("2026-03-20", "SafeWay Supermarket Store", "Groceries", "", 98.60, "Caleb", "Monthly"),
        ("2026-03-22", "Shell Station Gas Fill", "Transportation", "", 52.00, "Rae", "Monthly"),
        ("2026-03-24", "Uber Downtown Rides", "Transportation", "", 24.50, "Rae", "Monthly"),
        ("2026-03-28", "Blue Bottle Espresso Beans", "Dining Out", "", 38.00, "Caleb", "Monthly"),
        
        # --- APRIL 2026 ---
        ("2026-04-01", "Monthly Mortgage Payment", "Housing", "", 3200.00, "Joint", "Monthly"),
        ("2026-04-03", "Whole Foods Market Run", "Groceries", "", 210.45, "Caleb", "Monthly"),
        ("2026-04-04", "City Power & Gas Bill", "Utilities", "", 158.10, "Joint", "Monthly"),
        ("2026-04-07", "Ippudo Ramen House", "Dining Out", "", 74.20, "Joint", "Monthly"),
        ("2026-04-10", "Netflix Standard Premium", "Subscriptions", "", 22.99, "Joint", "Monthly"),
        ("2026-04-12", "Trader Joe's Provisions", "Groceries", "", 115.80, "Rae", "Monthly"),
        ("2026-04-14", "Blue Bottle Espresso Beans", "Dining Out", "", 18.00, "Caleb", "Monthly"),
        ("2026-04-15", "Chevron Gas Fill", "Transportation", "", 45.00, "Caleb", "Monthly"),
        ("2026-04-18", "Independent Theater Tickets", "Entertainment", "Concerts", 85.00, "Rae", "Monthly"),
        ("2026-04-20", "Japan Rail Pass Vouchers (Goal)", "Vacation", "", 480.00, "Joint", "Goal"),
        ("2026-04-22", "Retina Monitor & Ergo Desk (Goal)", "New Retina Workstation", "", 3500.00, "Caleb", "Goal"), # Fully completes workstation goal!
        ("2026-04-24", "SafeWay Provisions", "Groceries", "", 86.40, "Joint", "Monthly"),
        ("202SF-04-25", "Uber Ride", "Transportation", "", 21.00, "Rae", "Monthly"),
        ("2026-04-28", "Apple Music Family", "Subscriptions", "", 16.99, "Caleb", "Monthly"),
        
        # --- MAY 2026 (Active/Current Month) ---
        ("2026-05-01", "Monthly Mortgage Payment", "Housing", "", 3200.00, "Joint", "Monthly"),
        ("2026-05-03", "Whole Foods Market Run", "Groceries", "", 192.50, "Caleb", "Monthly"),
        ("2026-05-05", "City Power & Gas Bill", "Utilities", "", 185.60, "Joint", "Monthly"),
        ("2026-05-07", "Mourad Moroccan Fine Dining", "Dining Out", "", 210.00, "Rae", "Monthly"),
        ("2026-05-09", "Chevron Gas Fill", "Transportation", "", 55.00, "Caleb", "Monthly"),
        ("2026-05-10", "Netflix Standard Premium", "Subscriptions", "", 22.99, "Joint", "Monthly"),
        ("2026-05-12", "Trader Joe's Provisions", "Groceries", "", 164.20, "Rae", "Monthly"),
        ("2026-05-14", "Stumptown Espresso Drinks", "Dining Out", "", 16.40, "Caleb", "Monthly"),
        ("2026-05-15", "Outside Lands Music Pass", "Entertainment", "", 285.00, "Joint", "Monthly"), # Overage trigger! (Overage is over $250 limit!)
        ("2026-05-18", "Apple Music Family", "Subscriptions", "", 16.99, "Caleb", "Monthly"),
        ("2026-05-20", "Roundtrip Flights to Tokyo (Goal)", "Vacation", "", 1850.00, "Joint", "Goal"), # Linked saving spending!
        ("2026-05-21", "Tokyo Hotel Deposit (Goal)", "Vacation", "", 650.00, "Joint", "Goal"),    # Linked saving spending!
        ("2026-05-22", "SafeWay Provisions", "Groceries", "", 112.50, "Caleb", "Monthly"),
        ("2026-05-24", "Uber Airport Rides", "Transportation", "", 62.00, "Rae", "Monthly"),
        ("2026-05-25", "Tonkotsu Ramen Lunch", "Dining Out", "", 42.00, "Joint", "Monthly"),
    ]
    
    # Standardize any minor typing slip
    cleaned_expenses = []
    for date, desc, cat, sub, amt, payer, etype in expenses_data:
        if date.startswith("202SF"):
            date = date.replace("202SF", "2026")
        cleaned_expenses.append((date, desc, cat, sub, amt, payer, etype))

    cursor.executemany(
        """
        INSERT INTO expenses (date, description, category, subcategory, amount, payer, expense_type)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        cleaned_expenses
    )
    
    conn.commit()
    conn.close()
    
    print_success(f"Successfully generated database seed! File size: {DB_PATH.stat().st_size} bytes")
    print("\nTo launch the application using this demo database, run the following:")
    print(f"  export BUDGET_DB_PATH=\"{DB_PATH}\"")
    print("  PYTHONPATH=backend uvicorn backend.main:app --reload --port 8001")
    print("  (Then verify the UI at http://localhost:5173 or run desktop_app.py)\n")


if __name__ == "__main__":
    seed_data()
