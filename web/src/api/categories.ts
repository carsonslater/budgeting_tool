import { api } from './client';
import type { ActiveCategory, CategoryRow, CategoryCreate, CategoryUpdate } from '../types';

export const fetchActiveCategories = (month?: string) =>
  api.get<ActiveCategory[]>(`/api/categories/active${month ? `?month=${encodeURIComponent(month)}` : ''}`);

export const fetchAllCategories = (kind?: string) =>
  api.get<CategoryRow[]>(`/api/categories${kind ? `?kind=${encodeURIComponent(kind)}` : ''}`);

export const createCategory = (data: CategoryCreate) =>
  api.post<CategoryRow>('/api/categories', data);

export const updateCategory = (id: number, data: CategoryUpdate) =>
  api.patch<CategoryRow>(`/api/categories/${id}`, data);
