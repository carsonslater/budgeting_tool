import { api } from './client';
import type { Expense, ExpenseCreate, ExpenseUpdate, ExpenseFilters } from '../types';

function buildQuery(filters?: ExpenseFilters): string {
  if (!filters) return '';
  const params = new URLSearchParams();
  if (filters.start)    params.set('start',    filters.start);
  if (filters.end)      params.set('end',      filters.end);
  if (filters.category) params.set('category', filters.category);
  if (filters.payer)    params.set('payer',    filters.payer);
  const qs = params.toString();
  return qs ? `?${qs}` : '';
}

export const fetchExpenses  = (filters?: ExpenseFilters) =>
  api.get<Expense[]>(`/api/expenses${buildQuery(filters)}`);

export const createExpense  = (data: ExpenseCreate) =>
  api.post<Expense>('/api/expenses', data);

export const updateExpense  = (id: number, data: ExpenseUpdate) =>
  api.patch<Expense>(`/api/expenses/${id}`, data);

export const deleteExpense  = (id: number) =>
  api.delete(`/api/expenses/${id}`);

export const fetchCategories = () =>
  api.get<string[]>('/api/expenses/categories');

export const fetchPayers     = () =>
  api.get<string[]>('/api/expenses/payers');
