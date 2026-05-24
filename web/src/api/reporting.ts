import { api } from './client';
import type { ReportSummary, TrendPoint, CategoryTotal } from '../types';

export const fetchReportSummary = (month?: string) => {
  const qs = month ? `?month=${encodeURIComponent(month)}` : '';
  return api.get<ReportSummary[]>(`/api/reporting/summary${qs}`);
};

export const fetchSpendingTrends = (
  period: 'monthly' | 'weekly' = 'monthly',
  category?: string,
  months?: number,
) => {
  const params = new URLSearchParams({ period });
  if (category) params.set('category', category);
  if (months)   params.set('months',   String(months));
  return api.get<TrendPoint[]>(`/api/reporting/trends?${params}`);
};

export const fetchCategoryBreakdown = (start?: string, end?: string) => {
  const params = new URLSearchParams();
  if (start) params.set('start', start);
  if (end)   params.set('end',   end);
  const qs = params.toString();
  return api.get<CategoryTotal[]>(`/api/reporting/categories${qs ? `?${qs}` : ''}`);
};
