import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchTurnover, setupTurnover } from '../api/turnover';
import type { TurnoverSetup } from '../types';

export const turnoverKeys = {
  all: ['turnover'] as const,
};

/** Retries are off: a failed status check should not hold the app behind a retry loop. */
export function useTurnover() {
  return useQuery({
    queryKey: turnoverKeys.all,
    queryFn: fetchTurnover,
    retry: false,
  });
}

export function useSetupTurnover() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: TurnoverSetup) => setupTurnover(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: turnoverKeys.all });
    },
  });
}
