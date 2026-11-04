/**
 * TurnoverModal — the blocking prompt. Hooks are mocked so each test states the server
 * state it depends on.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const h = vi.hoisted(() => ({
    status: null as any,
    lines: [] as any[],
    plan: null as any,
    proposal: null as any,
    proposalError: null as any,
    setupMutate: vi.fn(async (_data: unknown) => ({})),
    confirmMutate: vi.fn(async (_month: unknown) => ({})),
    incomeMutate: vi.fn(async (_data: unknown) => ({})),
    approveMutate: vi.fn(async (_data: unknown) => ({})),
}));

vi.mock('../../hooks/useTurnover', () => ({
    useTurnover: () => ({ data: h.status }),
    useSetupTurnover: () => ({ mutateAsync: h.setupMutate, isPending: false }),
}));

vi.mock('../../hooks/useBudgets', () => ({
    useBudgets: () => ({ data: h.lines }),
}));

vi.mock('../../hooks/useMonthPlans', () => ({
    useMonthPlan: () => ({ data: h.plan }),
    useConfirmMonth: () => ({ mutateAsync: h.confirmMutate, isPending: false }),
    useSetExpectedIncome: () => ({ mutateAsync: h.incomeMutate, isPending: false }),
}));

vi.mock('../../hooks/useSweeps', () => ({
    useSweepProposal: () => ({ data: h.proposal, error: h.proposalError }),
    useSweepActions: () => ({ approve: { mutateAsync: h.approveMutate, isPending: false } }),
}));

import { TurnoverModal } from './TurnoverModal';

const irregular = {
    line_key: 'key-insurance',
    category: 'Car',
    subcategory: 'Insurance',
    limit_amount: 1200,
    frequency: 'Annually',
    month: '2025-01',
    inherited: true,
    effective_since: '2025-01',
};

const proposal = {
    month: '2025-01',
    income: 3000,
    regular_spend: 350,
    irregular_spend: 0,
    reserve_total: 100,
    shortfall: 0,
    leftover: 2550,
    pot: 2550,
    swept_total: 2000,
    unallocated: 550,
    funds: [],
    goals: [
        { goal_id: 7, name: 'Vacation', amount: 2000, balance: 0, projected_balance: 2000 },
        { goal_id: 8, name: 'Car', amount: 0, balance: 0, projected_balance: 0 },
    ],
    approvable: true,
    blocked_reason: null,
};

beforeEach(() => {
    vi.clearAllMocks();
    h.status = { state: 'turnover', baseline: '2025-01', target: '2025-01', default_month: '2025-01', confirmed: true, income_missing: false };
    h.lines = [irregular];
    h.plan = { month: '2025-01', status: 'confirmed', expected_income: 3000 };
    h.proposal = proposal;
    h.proposalError = null;
});

describe('TurnoverModal — when it shows', () => {
    it('renders nothing when every ended month is closed', () => {
        h.status = { state: 'none', baseline: '2025-01', target: null, default_month: '2025-01', confirmed: null, income_missing: null };
        const { container } = render(<TurnoverModal />);
        expect(container).toBeEmptyDOMElement();
    });
});

describe('TurnoverModal — blocking', () => {
    it('has no close control and ignores Escape and overlay clicks', () => {
        render(<TurnoverModal />);
        expect(screen.queryByRole('button', { name: /close$/i })).not.toBeInTheDocument();

        fireEvent.keyDown(document, { key: 'Escape' });
        fireEvent.click(screen.getByRole('dialog').parentElement!);
        expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
});

describe('TurnoverModal — setup', () => {
    beforeEach(() => {
        h.status = { state: 'setup', baseline: null, target: null, default_month: '2025-01', confirmed: null, income_missing: null };
    });

    it('starts tracking with only the openings that were entered', async () => {
        render(<TurnoverModal />);
        fireEvent.change(screen.getByLabelText(/Car > Insurance/), { target: { value: '500' } });
        fireEvent.click(screen.getByRole('button', { name: /Start tracking from/ }));

        await waitFor(() =>
            expect(h.setupMutate).toHaveBeenCalledWith({
                month: '2025-01',
                openings: [{ line_key: 'key-insurance', amount: 500 }],
            }),
        );
    });

    it('sends no openings for a blank field', async () => {
        render(<TurnoverModal />);
        fireEvent.click(screen.getByRole('button', { name: /Start tracking from/ }));

        await waitFor(() =>
            expect(h.setupMutate).toHaveBeenCalledWith({ month: '2025-01', openings: [] }),
        );
    });
});

describe('TurnoverModal — close a month', () => {
    it('asks for confirmation when the month is not yet confirmed', async () => {
        h.status = { ...h.status, confirmed: false };
        h.plan = { month: '2025-01', status: 'inherited', expected_income: 3000 };
        render(<TurnoverModal />);

        fireEvent.click(screen.getByRole('button', { name: 'Keep as is' }));
        await waitFor(() => expect(h.confirmMutate).toHaveBeenCalledWith('2025-01'));
    });

    it('blocks Keep as is until an expected income is saved', () => {
        h.status = { ...h.status, confirmed: false };
        h.plan = { month: '2025-01', status: 'inherited', expected_income: null };
        render(<TurnoverModal />);
        expect(screen.getByRole('button', { name: 'Keep as is' })).toBeDisabled();
        expect(screen.getByText(/Save the expected income to continue/)).toBeInTheDocument();
    });

    it('approves the goal amounts shown in the review', async () => {
        render(<TurnoverModal />);
        fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
        fireEvent.click(screen.getByRole('button', { name: /Approve and close/ }));

        await waitFor(() =>
            expect(h.approveMutate).toHaveBeenCalledWith({
                month: '2025-01',
                allocations: [{ goal_id: 7, amount: 2000 }],
            }),
        );
    });

    it('does not allow review to continue when the proposal is blocked', () => {
        h.proposal = { ...proposal, approvable: false, blocked_reason: 'set the sweep baseline first' };
        render(<TurnoverModal />);
        expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled();
        expect(screen.getByText('set the sweep baseline first')).toBeInTheDocument();
    });
});
