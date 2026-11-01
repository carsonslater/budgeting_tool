/**
 * SweepPanel — the open-month proposal, the blocked and closed states, and the
 * missing-income message. Data hooks are mocked so each test states the server state
 * it depends on.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { format, subMonths } from 'date-fns';
import { ApiError } from '../../api/client';

const h = vi.hoisted(() => ({
    approveMutate: vi.fn(async (_data: unknown) => ({})),
    reopenMutate: vi.fn(async (_month: unknown) => ({})),
    proposal: { data: undefined as any, error: null as any },
    closed: [] as any[],
}));

vi.mock('../../hooks/useSweeps', () => ({
    useSweepProposal: () => h.proposal,
    useClosedMonths: () => ({ data: h.closed }),
    useSweepRules: () => ({ data: [] }),
    useSweepActions: () => ({
        approve: { mutateAsync: h.approveMutate, isPending: false },
        reopen: { mutateAsync: h.reopenMutate, isPending: false },
        createRule: { mutateAsync: vi.fn(), isPending: false },
        deleteRule: { mutateAsync: vi.fn(), isPending: false },
    }),
}));

vi.mock('../../hooks/useGoals', () => ({
    useGoals: () => ({ data: [] }),
}));

import { SweepPanel } from './SweepPanel';

const openProposal = {
    month: '2025-01',
    income: 3000,
    regular_spend: 350,
    irregular_spend: 0,
    reserve_total: 100,
    shortfall: 0,
    leftover: 2550,
    pot: 2550,
    swept_total: 1425,
    unallocated: 1125,
    funds: [],
    goals: [
        { goal_id: 1, name: 'Vacation', amount: 300, balance: 0, projected_balance: 300 },
        { goal_id: 2, name: 'Car', amount: 1125, balance: 0, projected_balance: 1125 },
    ],
    approvable: true,
    blocked_reason: null,
};

beforeEach(() => {
    h.approveMutate.mockClear();
    h.reopenMutate.mockClear();
    h.proposal = { data: openProposal, error: null };
    h.closed = [];
});

describe('SweepPanel', () => {
    it('shows the proposed split and approves the amounts as shown', async () => {
        render(<SweepPanel />);
        expect(screen.getByText('Vacation')).toBeTruthy();
        expect(screen.getByText('Car')).toBeTruthy();

        const approve = screen.getByRole('button', { name: 'Approve sweep' });
        expect((approve as HTMLButtonElement).disabled).toBe(false);
        fireEvent.click(approve);

        await waitFor(() => expect(h.approveMutate).toHaveBeenCalledTimes(1));
        const call = h.approveMutate.mock.calls[0][0] as any;
        expect(call.allocations).toEqual([
            { goal_id: 1, amount: 300 },
            { goal_id: 2, amount: 1125 },
        ]);
    });

    it('disables approval and explains a blocked month', () => {
        h.proposal = {
            data: { ...openProposal, approvable: false, blocked_reason: '2025-02 must be closed before 2025-03' },
            error: null,
        };
        render(<SweepPanel />);
        const approve = screen.getByRole('button', { name: 'Approve sweep' });
        expect((approve as HTMLButtonElement).disabled).toBe(true);
        expect(screen.getByText('2025-02 must be closed before 2025-03')).toBeTruthy();
    });

    it('a closed month shows its recorded figures and offers reopen, not approval', () => {
        h.closed = [
            {
                month_id: format(subMonths(new Date(), 1), 'yyyy-MM'),
                closed_at: '2026-11-01T10:00:00',
                expected_income: 3000,
                regular_spend: 350,
                reserve_total: 100,
                shortfall: 0,
                swept_total: 1425,
                leftover_raw: 2550,
            },
        ];
        render(<SweepPanel />);
        expect(screen.getByText('Closed')).toBeTruthy();
        expect(screen.queryByRole('button', { name: 'Approve sweep' })).toBeNull();
        expect(screen.getByRole('button', { name: 'Reopen month' })).toBeTruthy();
        expect(screen.queryByText('Vacation')).toBeNull();
    });

    it('asks for expected income when the month has none', () => {
        h.proposal = { data: undefined, error: new ApiError(400, 'set expected income') };
        render(<SweepPanel />);
        expect(screen.getByText(/Set expected income/)).toBeTruthy();
    });
});
