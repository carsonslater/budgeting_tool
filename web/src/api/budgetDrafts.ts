import { apiFetch } from './client';
import type { BudgetDraft, BudgetDraftCreate, BudgetDraftUpdate } from '../types';

export async function fetchBudgetDrafts(targetMonth: string): Promise<BudgetDraft[]> {
  return apiFetch<BudgetDraft[]>(`/api/budget-drafts/${targetMonth}`);
}

export async function createBudgetDraft(data: BudgetDraftCreate): Promise<BudgetDraft> {
  return apiFetch<BudgetDraft>('/api/budget-drafts', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateBudgetDraft(id: number, data: BudgetDraftUpdate): Promise<BudgetDraft> {
  return apiFetch<BudgetDraft>(`/api/budget-drafts/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deleteBudgetDraft(id: number): Promise<void> {
  return apiFetch<void>(`/api/budget-drafts/${id}`, {
    method: 'DELETE',
  });
}

export async function commitBudgetDrafts(targetMonth: string): Promise<{ status: string; message: string }> {
  return apiFetch<{ status: string; message: string }>(`/api/budget-drafts/${targetMonth}/commit`, {
    method: 'POST',
  });
}
