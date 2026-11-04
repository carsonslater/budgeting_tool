import { describe, it, expect } from 'vitest';
import {
  FREQUENCY_DIVISORS,
  monthlyEquivalent,
  periodAmountFromMonthly,
} from './budgetMath';

describe('periodAmountFromMonthly', () => {
  it('leaves a monthly amount unchanged', () => {
    expect(periodAmountFromMonthly(500, 'Monthly')).toBe(500);
  });

  it('multiplies by the cadence divisor', () => {
    expect(periodAmountFromMonthly(100, 'Annually')).toBe(1200);
    expect(periodAmountFromMonthly(100, 'Quarterly')).toBe(300);
    expect(periodAmountFromMonthly(100, 'Bi-annually')).toBe(600);
  });

  it('round-trips with monthlyEquivalent to the cent', () => {
    for (const frequency of ['Monthly', 'Quarterly', 'Bi-annually', 'Annually']) {
      const period = periodAmountFromMonthly(87.5, frequency);
      expect(monthlyEquivalent(period, frequency)).toBe(87.5);
    }
  });
});

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
