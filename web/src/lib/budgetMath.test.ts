import { describe, it, expect } from 'vitest';
import { FREQUENCY_DIVISORS, monthlyEquivalent } from './budgetMath';

describe('monthlyEquivalent', () => {
  it('leaves a monthly limit unchanged', () => {
    expect(monthlyEquivalent(500, 'Monthly')).toBe(500);
  });

  it('divides by the cadence divisor', () => {
    expect(monthlyEquivalent(1200, 'Annually')).toBe(100);
    expect(monthlyEquivalent(300, 'Quarterly')).toBe(100);
    expect(monthlyEquivalent(600, 'Bi-annually')).toBe(100);
  });

  it('falls back to the full amount for an unknown frequency', () => {
    expect(monthlyEquivalent(250, 'Weekly')).toBe(250);
  });

  it('rounds to two decimals', () => {
    expect(monthlyEquivalent(1000, 'Quarterly')).toBe(333.33);
  });

  it('covers every cadence the planner offers', () => {
    expect(Object.keys(FREQUENCY_DIVISORS).sort()).toEqual([
      'Annually',
      'Bi-annually',
      'Monthly',
      'Quarterly',
    ]);
  });
});
