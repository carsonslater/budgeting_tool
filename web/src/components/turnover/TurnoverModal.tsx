import React, { useEffect, useState } from 'react';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { MonthPicker } from '../ui/MonthPicker';
import { useTurnover, useSetupTurnover } from '../../hooks/useTurnover';
import { useBudgets } from '../../hooks/useBudgets';
import { useMonthPlan, useConfirmMonth, useSetExpectedIncome } from '../../hooks/useMonthPlans';
import { useSweepActions, useSweepProposal } from '../../hooks/useSweeps';
import { monthlyEquivalent } from '../../lib/budgetMath';
import { monthLabel } from '../../lib/monthMath';
import type { Budget } from '../../types';
import styles from './TurnoverModal.module.css';

function formatCurrency(amount: number | null | undefined) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount ?? 0);
}

function errorText(err: unknown) {
    return err instanceof Error ? err.message : 'Something went wrong. Try again.';
}

/**
 * The month-end turnover prompt. It is blocking: there is no close control, Escape and
 * an overlay click do nothing, and it stays until every ended month since the baseline
 * is closed. The steps for each month are confirm the budget (and its expected income),
 * review the leftover, then approve the sweep.
 */
export const TurnoverModal: React.FC = () => {
    const { data: status } = useTurnover();

    if (!status || status.state === 'none') return null;

    return (
        <div className={styles.overlay}>
            <div role="dialog" aria-modal="true" aria-labelledby="turnover-title" className={styles.panel}>
                {status.state === 'setup' ? (
                    <SetupView defaultMonth={status.default_month} />
                ) : (
                    <CloseView
                        key={status.target ?? ''}
                        month={status.target ?? ''}
                        confirmed={status.confirmed === true}
                    />
                )}
            </div>
        </div>
    );
};

/** First run: choose the first tracked month and enter its irregular fund openings. */
const SetupView: React.FC<{ defaultMonth: string }> = ({ defaultMonth }) => {
    const [month, setMonth] = useState(defaultMonth);
    const [amounts, setAmounts] = useState<Record<string, string>>({});
    const [error, setError] = useState<string | null>(null);
    const { data: lines = [] } = useBudgets(month);
    const setup = useSetupTurnover();

    const irregular = lines.filter((line: Budget) => line.frequency !== 'Monthly');

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        const openings: { line_key: string; amount: number }[] = [];
        for (const line of irregular) {
            const raw = (amounts[line.line_key] ?? '').trim();
            const value = raw === '' ? 0 : Number(raw);
            if (!Number.isFinite(value) || value < 0) {
                setError(`Enter zero or more for ${line.category}.`);
                return;
            }
            if (value > 0) openings.push({ line_key: line.line_key, amount: value });
        }
        try {
            await setup.mutateAsync({ month, openings });
        } catch (err) {
            setError(errorText(err));
        }
    };

    return (
        <form onSubmit={handleSubmit}>
            <h2 id="turnover-title" className={styles.title}>Start sweep tracking</h2>
            <p className={styles.lead}>
                Choose the first month to track. Enter what each irregular fund held at the start of
                that month; a blank means zero. Months before it are never prompted or swept.
            </p>

            <div className={styles.field}>
                <MonthPicker
                    label="First tracked month"
                    value={month}
                    onChange={(value) => {
                        setMonth(value);
                        setAmounts({});
                    }}
                    required
                />
            </div>

            {irregular.length === 0 ? (
                <p className={styles.hint}>
                    {monthLabel(month)} has no irregular budget lines, so no fund openings are needed.
                </p>
            ) : (
                irregular.map((line: Budget) => (
                    <div key={line.line_key} className={styles.field}>
                        <Input
                            label={`${line.category}${line.subcategory ? ` > ${line.subcategory}` : ''} (${line.frequency})`}
                            type="number"
                            step="0.01"
                            min="0"
                            value={amounts[line.line_key] ?? ''}
                            onChange={(e) => setAmounts({ ...amounts, [line.line_key]: e.target.value })}
                        />
                    </div>
                ))
            )}

            {error && <p role="alert" className={styles.error}>{error}</p>}

            <div className={styles.actions}>
                <Button type="submit" disabled={setup.isPending || month === ''}>
                    Start tracking from {monthLabel(month)}
                </Button>
            </div>
        </form>
    );
};

/** One ended month: confirm, review, approve. The step is derived from the server state. */
const CloseView: React.FC<{ month: string; confirmed: boolean }> = ({ month, confirmed }) => {
    const [reviewed, setReviewed] = useState(false);
    const [incomeInput, setIncomeInput] = useState('');
    const [error, setError] = useState<string | null>(null);

    const { data: plan } = useMonthPlan(month);
    const { data: lines = [] } = useBudgets(month);
    const { data: proposal, error: proposalError } = useSweepProposal(month);
    const confirm = useConfirmMonth();
    const setIncome = useSetExpectedIncome();
    const { approve } = useSweepActions();

    const expectedIncome = plan?.expected_income ?? null;

    useEffect(() => {
        setIncomeInput(expectedIncome !== null ? String(expectedIncome) : '');
    }, [expectedIncome]);

    const step = !confirmed ? 1 : reviewed ? 3 : 2;
    const monthlyTotal = lines.reduce(
        (sum: number, line: Budget) => sum + monthlyEquivalent(line.limit_amount, line.frequency),
        0,
    );

    const run = async (action: () => Promise<unknown>, onDone?: () => void) => {
        setError(null);
        try {
            await action();
            onDone?.();
        } catch (err) {
            setError(errorText(err));
        }
    };

    const handleSaveIncome = (e: React.FormEvent) => {
        e.preventDefault();
        const amount = parseFloat(incomeInput);
        if (!Number.isFinite(amount) || amount < 0) {
            setError('Enter an expected income of zero or more.');
            return;
        }
        run(() => setIncome.mutateAsync({ month, amount }));
    };

    const handleApprove = () => {
        if (!proposal) return;
        run(
            () =>
                approve.mutateAsync({
                    month,
                    allocations: proposal.goals
                        .filter((g) => g.amount > 0)
                        .map((g) => ({ goal_id: g.goal_id, amount: g.amount })),
                }),
        );
    };

    return (
        <div>
            <h2 id="turnover-title" className={styles.title}>Close {monthLabel(month)}</h2>
            <ol className={styles.steps}>
                <li className={step === 1 ? styles.stepActive : step > 1 ? styles.stepDone : ''}>
                    1. Confirm budget
                </li>
                <li className={step === 2 ? styles.stepActive : step > 2 ? styles.stepDone : ''}>
                    2. Review leftover
                </li>
                <li className={step === 3 ? styles.stepActive : ''}>3. Approve sweep</li>
            </ol>

            {step === 1 && (
                <section>
                    <p className={styles.lead}>
                        {lines.length} budget {lines.length === 1 ? 'line' : 'lines'}, {formatCurrency(monthlyTotal)} per
                        month. Expected income is needed before the leftover can be calculated.
                    </p>
                    <form onSubmit={handleSaveIncome} className={styles.field}>
                        <Input
                            label="Expected income"
                            type="number"
                            step="0.01"
                            min="0"
                            value={incomeInput}
                            onChange={(e) => setIncomeInput(e.target.value)}
                            required
                        />
                        <div className={styles.actions}>
                            <Button type="submit" variant="ghost" disabled={setIncome.isPending || incomeInput.trim() === ''}>
                                Save income
                            </Button>
                        </div>
                    </form>
                    <div className={styles.actions}>
                        <Button
                            onClick={() => run(() => confirm.mutateAsync(month))}
                            disabled={confirm.isPending || expectedIncome === null}
                        >
                            Keep as is
                        </Button>
                    </div>
                    {expectedIncome === null && (
                        <p className={styles.hint}>Save the expected income to continue.</p>
                    )}
                </section>
            )}

            {step === 2 && (
                <section>
                    {proposalError && <p role="alert" className={styles.error}>{errorText(proposalError)}</p>}
                    {proposal && (
                        <>
                            <dl className={styles.figures}>
                                <dt>Income</dt><dd>{formatCurrency(proposal.income)}</dd>
                                <dt>Regular spend</dt><dd>{formatCurrency(proposal.regular_spend)}</dd>
                                <dt>Reserved for irregular bills</dt><dd>{formatCurrency(proposal.reserve_total)}</dd>
                                <dt>Shortfall</dt><dd>{formatCurrency(proposal.shortfall)}</dd>
                                <dt>Leftover to sweep</dt><dd>{formatCurrency(proposal.pot)}</dd>
                            </dl>
                            {proposal.funds.length > 0 && (
                                <table className={styles.table}>
                                    <thead>
                                        <tr>
                                            <th>Fund</th><th>Start</th><th>Reserve</th><th>Bills paid</th><th>Shortfall</th><th>End</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {proposal.funds.map((f) => (
                                            <tr key={f.line_key}>
                                                <td>{f.name}</td>
                                                <td>{formatCurrency(f.balance_before)}</td>
                                                <td>{formatCurrency(f.reserve)}</td>
                                                <td>{formatCurrency(f.draw)}</td>
                                                <td>{formatCurrency(f.shortfall)}</td>
                                                <td>{formatCurrency(f.balance_after)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            )}
                            {!proposal.approvable && proposal.blocked_reason && (
                                <p role="alert" className={styles.error}>{proposal.blocked_reason}</p>
                            )}
                        </>
                    )}
                    <div className={styles.actions}>
                        <Button onClick={() => setReviewed(true)} disabled={!proposal || !proposal.approvable}>
                            Continue
                        </Button>
                    </div>
                </section>
            )}

            {step === 3 && proposal && (
                <section>
                    <p className={styles.lead}>
                        {formatCurrency(proposal.swept_total)} goes to goals; {formatCurrency(proposal.unallocated)}
                        stays unallocated. Approving closes {monthLabel(month)} and writes the fund and goal rows.
                    </p>
                    <div className={styles.actions}>
                        <Button onClick={handleApprove} disabled={approve.isPending}>
                            Approve and close {monthLabel(month)}
                        </Button>
                    </div>
                </section>
            )}

            {error && <p role="alert" className={styles.error}>{error}</p>}
        </div>
    );
};

export default TurnoverModal;
