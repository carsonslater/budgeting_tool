import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchBudgets,
  createBudget,
  updateBudget,
  deleteBudget,
  fetchSuggestedBudgets,
} from '../api/budgets';
import type { BudgetCreate, BudgetUpdate } from '../types';

// ── Query keys ────────────────────────────────────────────────────────────────

export const budgetKeys = {
  all:       ['budgets']               as const,
  list:      ['budgets', 'list']       as const,
  suggested: ['budgets', 'suggested']  as const,
};

// ── Queries ───────────────────────────────────────────────────────────────────

export function useBudgets() {
  return useQuery({
    queryKey: budgetKeys.list,
    queryFn:  fetchBudgets,
  });
}

export function useSuggestedBudgets() {
  return useQuery({
    queryKey: budgetKeys.suggested,
    queryFn:  fetchSuggestedBudgets,
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
    mutationFn: ({ id, data }: { id: number; data: BudgetUpdate }) =>
      updateBudget(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: budgetKeys.all });
    },
  });
}

export function useDeleteBudget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteBudget(id),
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
