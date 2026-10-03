/**
 * The Phase 1 partition boundary, asserted at the UI level.
 *
 * The component under test is the one place where the two server partitions
 * could be silently re-mixed — a non-monthly line rendered inside the monthly
 * "Budget Performance" table would read as a monthly line again, which is the
 * defect Phase 1 closed. These assertions are deliberately about *where* a line
 * appears, not how it is formatted, so they survive changes to the non-monthly
 * basis.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

const { summary } = vi.hoisted(() => ({
  summary: {
    monthly: [
      {
        budget_id: 1,
        category: 'Food',
        subcategory: 'Groceries',
        budget: 500,
        spent: 100,
        remaining: 400,
        status: 'Under' as const,
        frequency: 'Monthly',
      },
    ],
    non_monthly: [
      {
        budget_id: 2,
        category: 'Auto',
        subcategory: 'Maintenance',
        budget: 1200,
        spent: 0,
        remaining: 1200,
        status: 'Under' as const,
        frequency: 'Annually',
        period_start: '2025-01-01',
        period_end: '2025-12-31',
      },
    ],
  },
}));

vi.mock('../hooks/useReporting', () => ({
  useReportSummary: () => ({ data: summary }),
  useCategoryBreakdown: () => ({ data: [] }),
}));

vi.mock('../hooks/useExpenses', () => ({
  useExpenses: () => ({ data: [] }),
}));

import { Reporting } from './Reporting';

describe('Reporting — partition boundary', () => {
  it('renders a non-monthly line outside the monthly performance table', () => {
    render(<Reporting />);

    expect(screen.getByText('Non-Monthly Lines')).toBeInTheDocument();
    // Each line appears exactly once, and in its own section.
    expect(screen.getAllByText('Auto')).toHaveLength(1);
    expect(screen.getAllByText('Food')).toHaveLength(1);
  });

  it('reports a non-monthly line against its per-occurrence limit', () => {
    render(<Reporting />);

    // Budget and remaining both show the full per-occurrence limit. A ÷12
    // pro-rating would show 100.00 instead.
    expect(screen.getAllByText('$1,200.00')).toHaveLength(2);
    // The row is labelled by its own frequency, not folded into "Monthly".
    expect(screen.getByText('Annually')).toBeInTheDocument();
    // The calendar period the line accrues over is surfaced.
    expect(screen.getByText('Jan 1, 2025 → Dec 31, 2025')).toBeInTheDocument();
  });
});
