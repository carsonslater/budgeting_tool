import { api } from './client';
import type { ActiveCategory, CategoryRow, CategoryUpdate } from '../types';

export const fetchActiveCategories = (month?: string) =>
  api.get<ActiveCategory[]>(`/api/categories/active${month ? `?month=${encodeURIComponent(month)}` : ''}`);

export const fetchAllCategories = (kind?: string) =>
  api.get<CategoryRow[]>(`/api/categories${kind ? `?kind=${encodeURIComponent(kind)}` : ''}`);

export const updateCategory = (id: number, data: CategoryUpdate) =>
  api.patch<CategoryRow>(`/api/categories/${id}`, data);

