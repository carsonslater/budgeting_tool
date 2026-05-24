import { useMutation, useQueryClient } from '@tanstack/react-query';
import { stageImport, confirmImport } from '../api/import';
import type { StagedRow } from '../types';
import { expenseKeys } from './useExpenses';
import { reportingKeys } from './useReporting';

export function useStageImport() {
  return useMutation({
    mutationFn: (file: File) => stageImport(file),
  });
}

export function useConfirmImport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (rows: StagedRow[]) => confirmImport(rows),
    onSuccess: () => {
      // Invalidate expenses and reports since new data was added
      qc.invalidateQueries({ queryKey: expenseKeys.all });
      qc.invalidateQueries({ queryKey: reportingKeys.all });
    },
  });
}
