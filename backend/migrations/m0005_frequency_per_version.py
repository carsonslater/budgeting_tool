"""
m0005 — a frequency per version.

Until now ``budget_lines.frequency`` was the only frequency a line had, so changing it
rewrote every month's amount.  Each version row now carries its own frequency
(``budget_amounts.frequency``) and is read the way its amount is.  A change can therefore
start and end at a chosen month, on whole calendar periods.

Existing history is backfilled with each line's current frequency.  ``m0003`` already
converted earlier amounts to that frequency's monthly equivalent, so every stored amount
stays correct.  The past cadence is not recovered here.  Tombstones carry no frequency.

``budget_lines.frequency`` is kept as a cache of the latest active version's frequency.
"""

from __future__ import annotations

import sqlite3

from .helpers import column_exists


def migrate(conn: sqlite3.Connection) -> None:
    if not column_exists(conn, "budget_amounts", "frequency"):
        conn.execute(
            "ALTER TABLE budget_amounts ADD COLUMN frequency TEXT "
            "CHECK (frequency IN ('Monthly', 'Quarterly', 'Bi-annually', 'Annually'))"
        )
    conn.execute(
        """
        UPDATE budget_amounts
        SET frequency = (
            SELECT l.frequency FROM budget_lines l
            WHERE l.line_key = budget_amounts.line_key
        )
        WHERE amount IS NOT NULL
        """
    )
