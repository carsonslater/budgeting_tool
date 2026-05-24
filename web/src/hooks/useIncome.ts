import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchIncome, setIncome } from '../api/income';

export const incomeKeys = {
  all:  ['income']        as const,
  total: ['income', 'total'] as const,
};

export function useIncome() {
  return useQuery({
    queryKey: incomeKeys.total,
    queryFn:  fetchIncome,
    staleTime: 60_000,  // income rarely changes mid-session
  });
}

export function useSetIncome() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (amount: number) => setIncome(amount),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: incomeKeys.all });
    },
  });
}
