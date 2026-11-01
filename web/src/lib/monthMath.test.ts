import { describe, it, expect } from 'vitest';
import { shiftMonth, monthLabel } from './monthMath';

describe('shiftMonth', () => {
  it('moves forward and back across a year boundary', () => {
    expect(shiftMonth('2026-12', 1)).toBe('2027-01');
    expect(shiftMonth('2027-01', -1)).toBe('2026-12');
  });

  it('handles multi-month offsets', () => {
    expect(shiftMonth('2026-03', -3)).toBe('2025-12');
    expect(shiftMonth('2026-10', 8)).toBe('2027-06');
  });

  it('returns the same month for a zero offset', () => {
    expect(shiftMonth('2026-10', 0)).toBe('2026-10');
  });
});

describe('monthLabel', () => {
  it('formats a YYYY-MM month as Mon yyyy', () => {
    expect(monthLabel('2026-10')).toBe('Oct 2026');
  });
});
