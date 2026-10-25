import { api } from './client';
import type { ApplyScope, Budget, BudgetCreate, BudgetUpdate, SuggestedBudget } from '../types';

/**
 * Budgets are month-scoped: a line is read for a month and identified across
 * months by its `line_key`. A write takes an apply scope; left out, the server
 * applies it from that month until the next explicit change.
 */

const scopeQuery = (scope?: ApplyScope) => {
  if (!scope?.apply) return '';
  const through = scope.through ? `&through=${encodeURIComponent(scope.through)}` : '';
  return `&apply=${scope.apply}${through}`;
};

export const fetchBudgets = (month?: string) =>
  api.get<Budget[]>(`/api/budgets${month ? `?month=${encodeURIComponent(month)}` : ''}`);

export const createBudget = (data: BudgetCreate) =>
  api.post<Budget>('/api/budgets', data);

export const updateBudget = (
  lineKey: string,
  month: string,
  data: BudgetUpdate,
  scope?: ApplyScope,
) =>
  api.patch<Budget>(
    `/api/budgets/${encodeURIComponent(lineKey)}?month=${encodeURIComponent(month)}` +
      scopeQuery(scope),
    data,
  );

export const deleteBudget = (lineKey: string, month: string, scope?: ApplyScope) =>
  api.delete(
    `/api/budgets/${encodeURIComponent(lineKey)}?month=${encodeURIComponent(month)}` +
      scopeQuery(scope),
  );

export const fetchSuggestedBudgets = (month?: string) =>
  api.get<SuggestedBudget[]>(
    `/api/budgets/suggested${month ? `?month=${encodeURIComponent(month)}` : ''}`,
  );
