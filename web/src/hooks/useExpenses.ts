import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchExpenses,
  createExpense,
  updateExpense,
  deleteExpense,
  fetchCategories,
  fetchPayers,
  fetchSubcategories,
} from '../api/expenses';
import type { ExpenseCreate, ExpenseFilters, ExpenseUpdate } from '../types';

// ── Query keys ────────────────────────────────────────────────────────────────

export const expenseKeys = {
  all:        ['expenses']                  as const,
  list:       (filters?: ExpenseFilters)    => ['expenses', 'list', filters ?? {}] as const,
  categories: ['expenses', 'categories']    as const,
  payers:     ['expenses', 'payers']        as const,
};

// ── Queries ───────────────────────────────────────────────────────────────────

export function useExpenses(filters?: ExpenseFilters) {
  return useQuery({
    queryKey: expenseKeys.list(filters),
    queryFn:  () => fetchExpenses(filters),
  });
}

export function useCategories() {
  return useQuery({
    queryKey: expenseKeys.categories,
    queryFn:  fetchCategories,
    staleTime: 5 * 60_000,   // categories change infrequently
  });
}

export function usePayers() {
  return useQuery({
    queryKey: expenseKeys.payers,
    queryFn:  fetchPayers,
    staleTime: 5 * 60_000,
  });
}

export function useSubcategories(category?: string) {
  return useQuery({
    queryKey: ['expenses', 'subcategories', category ?? 'all'],
    queryFn:  () => fetchSubcategories(category),
    staleTime: 5 * 60_000,
  });
}

// ── Mutations ─────────────────────────────────────────────────────────────────

export function useCreateExpense() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ExpenseCreate) => createExpense(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: expenseKeys.all });
    },
  });
}

export function useUpdateExpense() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: ExpenseUpdate }) =>
      updateExpense(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: expenseKeys.all });
    },
  });
}

export function useDeleteExpense() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteExpense(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: expenseKeys.all });
    },
  });
}

/**
 * Convenience bundle — returns queries + mutations for the Expenses page.
 */
export function useExpenseActions() {
  return {
    create: useCreateExpense(),
    update: useUpdateExpense(),
    remove: useDeleteExpense(),
  };
}
