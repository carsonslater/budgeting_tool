import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchBudgets,
  createBudget,
  updateBudget,
  deleteBudget,
  fetchSuggestedBudgets,
} from '../api/budgets';
import type { ApplyScope, BudgetCreate, BudgetUpdate } from '../types';

// ── Query keys ────────────────────────────────────────────────────────────────

export const budgetKeys = {
  all:       ['budgets']                                        as const,
  list:      (month?: string) => ['budgets', 'list', month ?? 'current'] as const,
  suggested: (month?: string) => ['budgets', 'suggested', month ?? 'current'] as const,
};

// ── Queries ───────────────────────────────────────────────────────────────────

export function useBudgets(month?: string) {
  return useQuery({
    queryKey: budgetKeys.list(month),
    queryFn:  () => fetchBudgets(month),
    enabled:  !!month,
  });
}

export function useSuggestedBudgets(month?: string) {
  return useQuery({
    queryKey: budgetKeys.suggested(month),
    queryFn:  () => fetchSuggestedBudgets(month),
    enabled:  !!month,
  });
}

// ── Mutations ─────────────────────────────────────────────────────────────────

export function useCreateBudget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: BudgetCreate) => createBudget(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: budgetKeys.all });
    },
  });
}

export function useUpdateBudget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      lineKey,
      month,
      data,
      scope,
    }: {
      lineKey: string;
      month: string;
      data: BudgetUpdate;
      scope?: ApplyScope;
    }) => updateBudget(lineKey, month, data, scope),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: budgetKeys.all });
    },
  });
}

export function useDeleteBudget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      lineKey,
      month,
      scope,
    }: {
      lineKey: string;
      month: string;
      scope?: ApplyScope;
    }) => deleteBudget(lineKey, month, scope),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: budgetKeys.all });
    },
  });
}

export function useBudgetActions() {
  return {
    create: useCreateBudget(),
    update: useUpdateBudget(),
    remove: useDeleteBudget(),
  };
}
