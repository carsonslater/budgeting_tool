import { api } from './client';
import type { ApplyScope, MonthPlan, MonthPlanStatus } from '../types';

/**
 * Month plans hold per-month state that is not a budget line: whether a month has
 * been confirmed ("keep as is") and its expected income. Confirming writes nothing
 * to the budget itself.
 */

export const fetchMonthPlanStatuses = (start: string, end: string) =>
  api.get<MonthPlanStatus[]>(
    `/api/month-plans?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`,
  );

export const fetchMonthPlan = (month: string) =>
  api.get<MonthPlan>(`/api/month-plans/${encodeURIComponent(month)}`);

export const confirmMonthPlan = (month: string) =>
  api.post<MonthPlan>(`/api/month-plans/${encodeURIComponent(month)}/confirm`, {});

export const setExpectedIncome = (month: string, amount: number, scope?: ApplyScope) =>
  api.put<MonthPlan>(`/api/month-plans/${encodeURIComponent(month)}/income`, {
    amount,
    apply: scope?.apply ?? 'forward',
    through: scope?.through ?? null,
  });
