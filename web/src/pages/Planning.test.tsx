/**
 * Planning — the month status strip, "Keep as is" / "Edit", the Applies-to control,
 * and expected income. Data hooks are mocked so each test states the server state it
 * depends on.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { format, addMonths } from 'date-fns';

const h = vi.hoisted(() => ({
  createMutate: vi.fn(async (_data: unknown) => ({})),
  updateMutate: vi.fn(async (_data: unknown) => ({})),
  deleteMutate: vi.fn(async (_data: unknown) => ({})),
  confirmMutate: vi.fn(async (_month: unknown) => ({})),
  incomeMutate: vi.fn(async (_data: unknown) => ({})),
  showToast: vi.fn(),
  lines: [] as any[],
  plan: null as any,
  statuses: [] as any[],
}));

vi.mock('../hooks/useExpenses', () => ({
  useCategories: () => ({ data: ['Food'] }),
  useSubcategories: () => ({ data: [] }),
}));

vi.mock('../hooks/useBudgets', () => ({
  useBudgets: () => ({ data: h.lines, isLoading: false }),
  useCreateBudget: () => ({ mutateAsync: h.createMutate, isPending: false }),
  useUpdateBudget: () => ({ mutateAsync: h.updateMutate, isPending: false }),
  useDeleteBudget: () => ({ mutateAsync: h.deleteMutate, isPending: false }),
}));

vi.mock('../hooks/useMonthPlans', () => ({
  useMonthPlanStatuses: () => ({ data: h.statuses }),
  useMonthPlan: () => ({ data: h.plan }),
  useConfirmMonth: () => ({ mutateAsync: h.confirmMutate, isPending: false }),
  useSetExpectedIncome: () => ({ mutateAsync: h.incomeMutate, isPending: false }),
}));

vi.mock('../contexts/ToastContext', () => ({
  useToast: () => ({ showToast: h.showToast }),
}));

import { Planning } from './Planning';

const currentMonth = format(new Date(), 'yyyy-MM');
const nextMonth = format(addMonths(new Date(), 1), 'yyyy-MM');

const groceries = {
  line_key: 'key-groceries',
  category: 'Food',
  subcategory: 'Groceries',
  limit_amount: 300,
  frequency: 'Monthly',
  month: currentMonth,
  inherited: true,
  effective_since: currentMonth,
};

function setPlan(overrides: Record<string, unknown> = {}) {
  h.plan = {
    month: currentMonth,
    status: 'inherited',
    confirmed_at: null,
    expected_income: null,
    income_set_in: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  h.lines = [groceries];
  h.statuses = [
    { month: currentMonth, status: 'inherited', confirmed_at: null },
    { month: nextMonth, status: 'confirmed', confirmed_at: '2026-10-20T10:00:00' },
  ];
  setPlan();
});

describe('Planning — status strip', () => {
  it('shows a chip per month with its inherited or confirmed status', () => {
    render(<Planning />);
    const group = screen.getByRole('group', { name: 'Budget months' });
    expect(group).toHaveTextContent('Inherited');
    expect(group).toHaveTextContent('Confirmed');
  });

  it('says the selected month is not confirmed and follows the previous month', () => {
    render(<Planning />);
    expect(screen.getByText(/is not confirmed\. Its lines follow/)).toBeInTheDocument();
  });
});

describe('Planning — Keep as is / Edit', () => {
  it('confirms the selected month', async () => {
    render(<Planning />);
    fireEvent.click(screen.getByRole('button', { name: 'Keep as is' }));
    await waitFor(() => expect(h.confirmMutate).toHaveBeenCalledWith(currentMonth));
  });

  it('hides Keep as is once the month is confirmed', () => {
    setPlan({ status: 'confirmed', confirmed_at: '2026-10-20T10:00:00' });
    render(<Planning />);
    expect(screen.queryByRole('button', { name: 'Keep as is' })).not.toBeInTheDocument();
    expect(screen.getByText(/^Confirmed on/)).toBeInTheDocument();
  });

  it('Edit moves focus to the line form', () => {
    render(<Planning />);
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    expect(screen.getByLabelText('Category')).toHaveFocus();
  });
});

describe('Planning — Applies to', () => {
  it('defaults to until changed', () => {
    render(<Planning />);
    expect(screen.getByLabelText('Until changed')).toBeChecked();
  });

  it('sends apply=month when a new line is set to this month only', async () => {
    render(<Planning />);
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'Food' } });
    fireEvent.change(screen.getByLabelText('Amount per period'), { target: { value: '50' } });
    fireEvent.click(screen.getByLabelText('This month only'));
    fireEvent.click(screen.getByRole('button', { name: 'Add Line' }));

    await waitFor(() =>
      expect(h.createMutate).toHaveBeenCalledWith(
        expect.objectContaining({ month: currentMonth, category: 'Food', apply: 'month' }),
      ),
    );
  });

  it('warns that a name change applies to every month, but not a frequency change', () => {
    render(<Planning />);
    fireEvent.click(screen.getByText('Groceries'));
    expect(screen.queryByText(/applies to every month/)).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Frequency'), { target: { value: 'Quarterly' } });
    expect(screen.queryByText(/applies to every month/)).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Subcategory'), { target: { value: 'Produce' } });
    expect(screen.getByText(/applies to every month/)).toBeInTheDocument();
  });

  it('sends a frequency change with the chosen scope', async () => {
    render(<Planning />);
    fireEvent.click(screen.getByText('Groceries'));
    fireEvent.change(screen.getByLabelText('Frequency'), { target: { value: 'Quarterly' } });
    fireEvent.click(screen.getByLabelText('This month only'));
    fireEvent.click(screen.getByRole('button', { name: 'Save Line' }));

    await waitFor(() =>
      expect(h.updateMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          lineKey: 'key-groceries',
          data: expect.objectContaining({ frequency: 'Quarterly' }),
          scope: { apply: 'month' },
        }),
      ),
    );
  });
});

describe('Planning — expected income', () => {
  it('shows Not set when no income is recorded', () => {
    render(<Planning />);
    expect(screen.getByText('Not set')).toBeInTheDocument();
  });

  it('saves income with the chosen scope', async () => {
    render(<Planning />);
    fireEvent.change(screen.getByLabelText('Expected income'), { target: { value: '4200' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save income' }));

    await waitFor(() =>
      expect(h.incomeMutate).toHaveBeenCalledWith({
        month: currentMonth,
        amount: 4200,
        scope: { apply: 'forward' },
      }),
    );
  });

  it('shows income less the monthly budget', () => {
    setPlan({ expected_income: 4200, income_set_in: currentMonth });
    render(<Planning />);
    // 4200 income - 300 budgeted per month = 3900
    expect(screen.getByText('$3,900.00')).toBeInTheDocument();
  });
});
