import React, { useState } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { Select } from '../ui/Select';
import { useGoals } from '../../hooks/useGoals';
import { useSweepActions, useSweepRules } from '../../hooks/useSweeps';
import { ApiError } from '../../api/client';
import styles from './SweepPanel.module.css';

const TYPE_OPTIONS = [
    { value: 'fixed', label: 'Fixed amount' },
    { value: 'percentage', label: '% of remainder' },
];

function errorMessage(err: unknown): string {
    if (err instanceof ApiError || err instanceof Error) return err.message;
    return 'Something went wrong';
}

/** Sweep rules: which goals receive a month's pot, in what order, and how much. */
export const SweepRules: React.FC = () => {
    const { data: rules = [] } = useSweepRules();
    const { data: goals = [] } = useGoals();
    const { createRule, deleteRule } = useSweepActions();

    const [goalId, setGoalId] = useState('');
    const [rank, setRank] = useState('');
    const [kind, setKind] = useState<'fixed' | 'percentage'>('fixed');
    const [amount, setAmount] = useState('');
    const [error, setError] = useState<string | null>(null);

    const eligible = goals.filter(g => g.completed === 0);
    const percentTotal = rules
        .filter(r => r.allocation_type === 'percentage')
        .reduce((sum, r) => sum + r.amount, 0);

    const handleAdd = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        try {
            await createRule.mutateAsync({
                goal_id: Number(goalId),
                priority_rank: rank === '' ? rules.length + 1 : Number(rank),
                allocation_type: kind,
                amount: parseFloat(amount) || 0,
            });
            setGoalId('');
            setRank('');
            setAmount('');
        } catch (err) {
            setError(errorMessage(err));
        }
    };

    const handleDelete = async (id: number) => {
        setError(null);
        try {
            await deleteRule.mutateAsync(id);
        } catch (err) {
            setError(errorMessage(err));
        }
    };

    return (
        <Card title="Sweep rules" padding="lg">
            <p className={styles.muted}>
                Lower priority numbers are paid first. Fixed amounts are capped by the pot and by
                each goal's remaining need. Percentages share what is left after the fixed amounts.
                Whatever is not allocated stays unallocated.
            </p>

            {rules.length > 0 && (
                <table className={styles.table}>
                    <thead>
                        <tr>
                            <th>Priority</th>
                            <th>Goal</th>
                            <th>Rule</th>
                            <th className={styles.num}>Amount</th>
                            <th />
                        </tr>
                    </thead>
                    <tbody>
                        {rules.map(r => (
                            <tr key={r.id}>
                                <td>{r.priority_rank}</td>
                                <td>{r.goal_name}</td>
                                <td>{r.allocation_type === 'fixed' ? 'Fixed' : '% of remainder'}</td>
                                <td className={styles.num}>
                                    {r.allocation_type === 'fixed' ? `$${r.amount.toFixed(2)}` : `${r.amount}%`}
                                </td>
                                <td className={styles.num}>
                                    <Button variant="ghost" size="sm" onClick={() => handleDelete(r.id)}>Remove</Button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
            {rules.length > 0 && (
                <div className={styles.muted}>Percentage rules total {percentTotal}% (at most 100%).</div>
            )}

            <form onSubmit={handleAdd} className={styles.ruleForm}>
                <Select
                    label="Goal"
                    value={goalId}
                    onChange={e => setGoalId(e.target.value)}
                    placeholder="Choose a goal"
                    options={eligible.map(g => ({ value: String(g.id), label: g.name }))}
                    required
                />
                <Input
                    label="Priority"
                    type="number"
                    min="0"
                    value={rank}
                    onChange={e => setRank(e.target.value)}
                    placeholder="Next"
                />
                <Select
                    label="Rule"
                    value={kind}
                    onChange={e => setKind(e.target.value as 'fixed' | 'percentage')}
                    options={TYPE_OPTIONS}
                />
                <Input
                    label={kind === 'fixed' ? 'Amount' : 'Percent'}
                    type="number"
                    step="0.01"
                    min="0"
                    value={amount}
                    onChange={e => setAmount(e.target.value)}
                    required
                />
                <Button type="submit" loading={createRule.isPending} disabled={!goalId}>Add rule</Button>
            </form>
            {error && <div className={styles.error}>{error}</div>}
        </Card>
    );
};

export default SweepRules;
