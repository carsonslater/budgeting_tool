import { useQuery } from '@tanstack/react-query';
import {
  fetchReportSummary,
  fetchSpendingTrends,
  fetchCategoryBreakdown,
} from '../api/reporting';

export const reportingKeys = {
  all:       ['reporting'] as const,
  summary:   (month?: string) => ['reporting', 'summary', month ?? 'current'] as const,
  trends:    (period: 'monthly' | 'weekly', category?: string, months?: number) =>
    ['reporting', 'trends', period, category ?? '', months ?? 0] as const,
  breakdown: (start?: string, end?: string) => ['reporting', 'breakdown', start ?? '', end ?? ''] as const,
};

export function useReportSummary(month?: string) {
  return useQuery({
    queryKey: reportingKeys.summary(month),
    queryFn:  () => fetchReportSummary(month),
  });
}

export function useSpendingTrends(
  period: 'monthly' | 'weekly' = 'monthly',
  category?: string,
  months?: number,
) {
  return useQuery({
    queryKey: reportingKeys.trends(period, category, months),
    queryFn:  () => fetchSpendingTrends(period, category, months),
  });
}

export function useCategoryBreakdown(start?: string, end?: string) {
  return useQuery({
    queryKey: reportingKeys.breakdown(start, end),
    queryFn:  () => fetchCategoryBreakdown(start, end),
  });
}
