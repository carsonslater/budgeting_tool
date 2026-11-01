import { api } from './client';
import type {
    ClosedMonth, SweepProposal, SweepRule, SweepRuleCreate, SweepRuleUpdate,
} from '../types';

export const fetchSweepRules = () =>
    api.get<SweepRule[]>('/api/sweeps/rules');

export const createSweepRule = (data: SweepRuleCreate) =>
    api.post<SweepRule>('/api/sweeps/rules', data);

export const updateSweepRule = (id: number, data: SweepRuleUpdate) =>
    api.patch<SweepRule>(`/api/sweeps/rules/${id}`, data);

export const deleteSweepRule = (id: number) =>
    api.delete(`/api/sweeps/rules/${id}`);

export const fetchSweepProposal = (month: string) =>
    api.get<SweepProposal>(`/api/sweeps/proposal?month=${month}`);

export const fetchClosedMonths = () =>
    api.get<ClosedMonth[]>('/api/sweeps/closed');

export const approveSweep = (month: string, allocations: { goal_id: number; amount: number }[]) =>
    api.post<SweepProposal>(`/api/sweeps/${month}/approve`, { allocations });

export const reopenSweep = (month: string) =>
    api.post<{ month: string; closed: boolean }>(`/api/sweeps/${month}/reopen`, {});
