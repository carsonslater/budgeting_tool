import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchBudgetDrafts,
  createBudgetDraft,
  updateBudgetDraft,
  deleteBudgetDraft,
  commitBudgetDrafts,
} from '../api/budgetDrafts';
import type { BudgetDraftUpdate } from '../types';

export function useBudgetDrafts(targetMonth: string) {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ['budgetDrafts', targetMonth],
    queryFn: () => fetchBudgetDrafts(targetMonth),
    enabled: !!targetMonth,
  });

  const createMutation = useMutation({
    mutationFn: createBudgetDraft,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['budgetDrafts', targetMonth] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: BudgetDraftUpdate }) =>
      updateBudgetDraft(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['budgetDrafts', targetMonth] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteBudgetDraft,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['budgetDrafts', targetMonth] });
    },
  });

  const commitMutation = useMutation({
    mutationFn: () => commitBudgetDrafts(targetMonth),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['budgetDrafts', targetMonth] });
      queryClient.invalidateQueries({ queryKey: ['budgets'] });
    },
  });

  return {
    drafts: query.data ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    createDraft: createMutation.mutateAsync,
    updateDraft: updateMutation.mutateAsync,
    deleteDraft: deleteMutation.mutateAsync,
    commitDrafts: commitMutation.mutateAsync,
    isCommitting: commitMutation.isPending,
  };
}
