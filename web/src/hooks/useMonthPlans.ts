import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  confirmMonthPlan,
  fetchMonthPlan,
  fetchMonthPlanStatuses,
  setExpectedIncome,
} from '../api/monthPlans';
import { budgetKeys } from './useBudgets';
import type { ApplyScope } from '../types';

export const monthPlanKeys = {
  all:      ['month-plans']                                          as const,
  statuses: (start: string, end: string) =>
    ['month-plans', 'statuses', start, end]                          as const,
  plan:     (month: string) => ['month-plans', 'plan', month]        as const,
};

export function useMonthPlanStatuses(start?: string, end?: string) {
  return useQuery({
    queryKey: monthPlanKeys.statuses(start ?? '', end ?? ''),
    queryFn:  () => fetchMonthPlanStatuses(start!, end!),
    enabled:  !!start && !!end,
  });
}

export function useMonthPlan(month?: string) {
  return useQuery({
    queryKey: monthPlanKeys.plan(month ?? ''),
    queryFn:  () => fetchMonthPlan(month!),
    enabled:  !!month,
  });
}

export function useConfirmMonth() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (month: string) => confirmMonthPlan(month),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: monthPlanKeys.all });
      qc.invalidateQueries({ queryKey: ['turnover'] });
      // A line's `inherited` flag is read from the month's confirmation state.
      qc.invalidateQueries({ queryKey: budgetKeys.all });
    },
  });
}

export function useSetExpectedIncome() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ month, amount, scope }: { month: string; amount: number; scope?: ApplyScope }) =>
      setExpectedIncome(month, amount, scope),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: monthPlanKeys.all });
      qc.invalidateQueries({ queryKey: ['turnover'] });
    },
  });
}
