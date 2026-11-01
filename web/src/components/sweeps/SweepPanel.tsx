import React, { useState } from 'react';
import { format, subMonths } from 'date-fns';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';
import { MonthPicker } from '../ui/MonthPicker';
import { SweepRules } from './SweepRules';
import { ApiError } from '../../api/client';
import { useClosedMonths, useSweepActions, useSweepProposal } from '../../hooks/useSweeps';
import styles from './SweepPanel.module.css';

function formatCurrency(amount: number | null | undefined) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount ?? 0);
}

function monthLabel(month: string) {
    const [y, m] = month.split('-').map(Number);
    return format(new Date(y, m - 1, 1), 'MMMM yyyy');
}

/**
 * Month-end sweep: the leftover for a month, how it splits across goals, and the
 * approval that writes it. Closed months show the figures recorded at close, not a
 * fresh recomputation, so the audit view does not drift as data changes.
 */
export const SweepPanel: React.FC = () => {
    const [month, setMonth] = useState(format(subMonths(new Date(), 1), 'yyyy-MM'));
    const [actionError, setActionError] = useState<string | null>(null);

    const { data: proposal, error: proposalError, isLoading } = useSweepProposal(month);
    const { data: closed = [] } = useClosedMonths();
    const { approve, reopen } = useSweepActions();

    const closedRecord = closed.find(c => c.month_id === month);
    const incomeMissing = proposalError instanceof ApiError && proposalError.status === 400;

    const handleApprove = async () => {
        if (!proposal) return;
        setActionError(null);
        try {
            await approve.mutateAsync({
                month,
                allocations: proposal.goals
                    .filter(g => g.amount > 0)
                    .map(g => ({ goal_id: g.goal_id, amount: g.amount })),
            });
        } catch (err) {
            setActionError(err instanceof Error ? err.message : 'Approval failed');
        }
    };

    const handleReopen = async () => {
        setActionError(null);
        try {
            await reopen.mutateAsync(month);
        } catch (err) {
            setActionError(err instanceof Error ? err.message : 'Reopen failed');
        }
    };

    const renderSummary = () => {
        if (closedRecord) {
            return (
                <dl className={styles.summary}>
                    <Item label="Expected income" value={closedRecord.expected_income} />
                    <Item label="Regular spend" value={closedRecord.regular_spend} />
                    <Item label="Reserved for irregular bills" value={closedRecord.reserve_total} />
                    <Item label="Shortfall" value={closedRecord.shortfall} />
                    <Item label="Leftover" value={closedRecord.leftover_raw} />
                    <Item label="Swept to goals" value={closedRecord.swept_total} />
                </dl>
            );
        }
        if (!proposal) return null;
        return (
            <dl className={styles.summary}>
                <Item label="Expected income" value={proposal.income} />
                <Item label="Regular spend" value={proposal.regular_spend} />
                <Item label="Reserved for irregular bills" value={proposal.reserve_total} />
                <Item label="Shortfall" value={proposal.shortfall} />
                <Item label="Leftover" value={proposal.leftover} />
                <Item label="Pot (leftover, if positive)" value={proposal.pot} />
            </dl>
        );
    };

    return (
        <Card title="Month-end sweep" padding="lg">
            <div className={styles.header}>
                <MonthPicker label="Month" value={month} onChange={setMonth} />
                {closedRecord ? <Badge variant="success">Closed</Badge> : <Badge variant="muted">Open</Badge>}
            </div>

            {isLoading && <div className={styles.muted}>Loading {monthLabel(month)}...</div>}

            {incomeMissing && !closedRecord && (
                <div className={styles.muted}>
                    Set expected income for {monthLabel(month)} on the Planning page to see its sweep.
                </div>
            )}

            {!incomeMissing && renderSummary()}

            {!closedRecord && proposal && (
                <>
                    {proposal.funds.length > 0 && (
                        <table className={styles.table}>
                            <thead>
                                <tr>
                                    <th>Irregular bill fund</th>
                                    <th className={styles.num}>Reserved</th>
                                    <th className={styles.num}>Spent</th>
                                    <th className={styles.num}>From fund</th>
                                    <th className={styles.num}>Shortfall</th>
                                    <th className={styles.num}>Fund after</th>
                                </tr>
                            </thead>
                            <tbody>
                                {proposal.funds.map(f => (
                                    <tr key={f.line_key}>
                                        <td>{f.name}</td>
                                        <td className={styles.num}>{formatCurrency(f.reserve)}</td>
                                        <td className={styles.num}>{formatCurrency(f.spent)}</td>
                                        <td className={styles.num}>{formatCurrency(f.draw)}</td>
                                        <td className={styles.num}>{formatCurrency(f.shortfall)}</td>
                                        <td className={styles.num}>{formatCurrency(f.balance_after)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}

                    {proposal.goals.length > 0 && (
                        <table className={styles.table}>
                            <thead>
                                <tr>
                                    <th>Goal</th>
                                    <th className={styles.num}>Sweep</th>
                                    <th className={styles.num}>Balance now</th>
                                    <th className={styles.num}>Balance after</th>
                                </tr>
                            </thead>
                            <tbody>
                                {proposal.goals.map(g => (
                                    <tr key={g.goal_id}>
                                        <td>{g.name}</td>
                                        <td className={styles.num}>{formatCurrency(g.amount)}</td>
                                        <td className={styles.num}>{formatCurrency(g.balance)}</td>
                                        <td className={styles.num}>{formatCurrency(g.projected_balance)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}

                    <div className={styles.muted}>
                        Unallocated: {formatCurrency(proposal.unallocated)}. It stays in the account and is not
                        moved to other goals.
                    </div>
                    {!proposal.approvable && proposal.blocked_reason && (
                        <div className={styles.muted}>{proposal.blocked_reason}</div>
                    )}
                </>
            )}

            <div className={styles.actions}>
                {closedRecord ? (
                    <Button variant="ghost" onClick={handleReopen} loading={reopen.isPending}>Reopen month</Button>
                ) : (
                    <Button
                        onClick={handleApprove}
                        loading={approve.isPending}
                        disabled={!proposal || !proposal.approvable}
                    >
                        Approve sweep
                    </Button>
                )}
            </div>
            {actionError && <div className={styles.error}>{actionError}</div>}

            <div className={styles.rulesBlock}>
                <SweepRules />
            </div>
        </Card>
    );
};

const Item: React.FC<{ label: string; value: number | null | undefined }> = ({ label, value }) => (
    <div className={styles.item}>
        <dt>{label}</dt>
        <dd>{formatCurrency(value)}</dd>
    </div>
);

export default SweepPanel;
