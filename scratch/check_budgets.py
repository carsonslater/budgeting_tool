import sqlite3
from pathlib import Path

db_path = Path("/Users/carson/Documents/R_Projects/budgeting_tool/data/budget.db")
if not db_path.exists():
    print("Database does not exist.")
    exit(1)

conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row

rows = conn.execute(
    "SELECT * FROM budgets WHERE subcategory LIKE '%Lukas%' OR subcategory LIKE '%Lukáš%'"
).fetchall()

print(f"Found {len(rows)} budget entries:")
for r in rows:
    print(dict(r))

conn.close()
