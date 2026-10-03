/**
 * budgetMath.ts — the single source of truth for budget-period arithmetic.
 * Mirrors `backend/budget_math.py`.
 *
 * Holds the **monthly equivalent only**. A non-monthly line is never pro-rated
 * onto a single month (see the partitioned `/api/reporting/summary` response);
 * this helper exists for the places that genuinely need a monthly figure.
 */

export const FREQUENCY_DIVISORS: Record<string, number> = {
  Monthly: 1,
  Quarterly: 3,
  'Bi-annually': 6,
  Annually: 12,
};

/** A per-period amount expressed as a monthly amount. */
export function monthlyEquivalent(limit: number, frequency: string): number {
  const divisor = FREQUENCY_DIVISORS[frequency] ?? 1;
  return Math.round((limit / divisor) * 100) / 100;
}
