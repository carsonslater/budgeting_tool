import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    fetchSweepRules, createSweepRule, updateSweepRule, deleteSweepRule,
    fetchSweepProposal, fetchClosedMonths, approveSweep, reopenSweep,
} from '../api/sweeps';
import type { SweepRuleCreate, SweepRuleUpdate } from '../types';

export const sweepKeys = {
    all: ['sweeps'] as const,
    rules: ['sweeps', 'rules'] as const,
    closed: ['sweeps', 'closed'] as const,
    proposal: (month: string) => ['sweeps', 'proposal', month] as const,
};

export function useSweepRules() {
    return useQuery({ queryKey: sweepKeys.rules, queryFn: fetchSweepRules });
}

export function useClosedMonths() {
    return useQuery({ queryKey: sweepKeys.closed, queryFn: fetchClosedMonths });
}

/** Retries are off: a month without expected income answers 400 and will not change on retry. */
export function useSweepProposal(month: string) {
    return useQuery({
        queryKey: sweepKeys.proposal(month),
        queryFn: () => fetchSweepProposal(month),
        enabled: month !== '',
        retry: false,
    });
}

export function useSweepActions() {
    const qc = useQueryClient();
    // A sweep changes goal balances and fund rows, so both sides are refreshed.
    const refresh = () => {
        qc.invalidateQueries({ queryKey: sweepKeys.all });
        qc.invalidateQueries({ queryKey: ['goals'] });
    };

    return {
        createRule: useMutation({
            mutationFn: (data: SweepRuleCreate) => createSweepRule(data),
            onSuccess: refresh,
        }),
        updateRule: useMutation({
            mutationFn: ({ id, data }: { id: number; data: SweepRuleUpdate }) => updateSweepRule(id, data),
            onSuccess: refresh,
        }),
        deleteRule: useMutation({
            mutationFn: (id: number) => deleteSweepRule(id),
            onSuccess: refresh,
        }),
        approve: useMutation({
            mutationFn: ({ month, allocations }: { month: string; allocations: { goal_id: number; amount: number }[] }) =>
                approveSweep(month, allocations),
            onSuccess: refresh,
        }),
        reopen: useMutation({
            mutationFn: (month: string) => reopenSweep(month),
            onSuccess: refresh,
        }),
    };
}
