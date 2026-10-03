import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchExpenses,
  createExpense,
  updateExpense,
  deleteExpense,
  fetchPayers,
} from '../api/expenses';
import { fetchActiveCategories, updateCategory, fetchAllCategories } from '../api/categories';
import type { ExpenseCreate, ExpenseFilters, ExpenseUpdate, CategoryUpdate } from '../types';

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


export function useCategories(month?: string) {
  return useQuery({
    queryKey: ['categories', 'active', month ?? 'current'],
    queryFn: () => fetchActiveCategories(month),
    select: (data) => Array.from(new Set(data.map((d) => d.category).filter(Boolean))).sort(),
    staleTime: 60_000,
  });
}

export function usePayers() {
  return useQuery({
    queryKey: expenseKeys.payers,
    queryFn:  fetchPayers,
    staleTime: 5 * 60_000,
  });
}

export function useSubcategories(category?: string, month?: string) {
  return useQuery({
    queryKey: ['categories', 'active', month ?? 'current'],
    queryFn: () => fetchActiveCategories(month),
    select: (data) =>
      Array.from(
        new Set(
          data
            .filter((d) => !category || d.category === category)
            .map((d) => d.subcategory)
            .filter(Boolean)
        )
      ).sort(),
    staleTime: 60_000,
  });
}

export function useAllCategoryRecords(kind?: string) {
  return useQuery({
    queryKey: ['categories', 'all', kind ?? 'all'],
    queryFn: () => fetchAllCategories(kind),
    staleTime: 60_000,
  });
}

export function useUpdateCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: CategoryUpdate }) => updateCategory(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['categories'] });
      qc.invalidateQueries({ queryKey: expenseKeys.all });
      qc.invalidateQueries({ queryKey: ['budgets'] });
    },
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
