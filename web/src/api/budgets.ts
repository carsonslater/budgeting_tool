import { api } from './client';
import type { Budget, BudgetCreate, BudgetUpdate, SuggestedBudget } from '../types';

export const fetchBudgets         = () =>
  api.get<Budget[]>('/api/budgets');

export const createBudget         = (data: BudgetCreate) =>
  api.post<Budget>('/api/budgets', data);

export const updateBudget         = (id: number, data: BudgetUpdate) =>
  api.patch<Budget>(`/api/budgets/${id}`, data);

export const deleteBudget         = (id: number) =>
  api.delete(`/api/budgets/${id}`);

export const fetchSuggestedBudgets = () =>
  api.get<SuggestedBudget[]>('/api/budgets/suggested');
