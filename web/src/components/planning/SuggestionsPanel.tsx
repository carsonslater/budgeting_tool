import React from 'react';
import { Button } from '../ui/Button';
import { periodAmountFromMonthly } from '../../lib/budgetMath';
import type { SuggestedBudget } from '../../types';
import styles from './SuggestionsPanel.module.css';

export type SuggestionChoice = 'hasty' | 'conservative';

interface SuggestionsPanelProps {
    suggestions: SuggestedBudget[];
    monthLabel: string;
    disabled: boolean;
    onApply: (suggestion: SuggestedBudget, choice: SuggestionChoice) => void;
}

function formatCurrency(amount: number) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
    }).format(amount);
}

/**
 * Suggestions for one month, from the last three complete months of spending.
 * The server reports suggestions per month; Apply stores the amount per period for
 * the line's frequency. Nothing is applied until the user clicks.
 */
export const SuggestionsPanel: React.FC<SuggestionsPanelProps> = ({
    suggestions,
    monthLabel,
    disabled,
    onApply,
}) => {
    if (suggestions.length === 0) {
        return (
            <p className={styles.empty}>
                No suggestions for {monthLabel}. A line is suggested when its last complete month
                differs from its budget by more than $50.
            </p>
        );
    }

    return (
        <div className={styles.tableContainer}>
            <table className={styles.table}>
                <thead>
                    <tr>
                        <th>Category</th>
                        <th>Subcategory</th>
                        <th className={styles.amountCell}>Budget / month</th>
                        <th className={styles.amountCell}>Last month spent</th>
                        <th className={styles.amountCell}>Hasty / month</th>
                        <th className={styles.amountCell}>Conservative / month</th>
                    </tr>
                </thead>
                <tbody>
                    {suggestions.map((s) => (
                        <tr key={s.line_key}>
                            <td>{s.category}</td>
                            <td>{s.subcategory}</td>
                            <td className={styles.amountCell}>{formatCurrency(s.current_monthly_equiv)}</td>
                            <td className={styles.amountCell}>{formatCurrency(s.recent_month_spent)}</td>
                            <td className={styles.amountCell}>
                                <Button
                                    size="sm"
                                    variant="ghost"
                                    disabled={disabled}
                                    onClick={() => onApply(s, 'hasty')}
                                    title={`Set the amount per period to ${formatCurrency(
                                        periodAmountFromMonthly(s.hasty, s.frequency),
                                    )}`}
                                >
                                    {formatCurrency(s.hasty)}
                                </Button>
                            </td>
                            <td className={styles.amountCell}>
                                <Button
                                    size="sm"
                                    variant="ghost"
                                    disabled={disabled}
                                    onClick={() => onApply(s, 'conservative')}
                                    title={`Set the amount per period to ${formatCurrency(
                                        periodAmountFromMonthly(s.conservative, s.frequency),
                                    )}`}
                                >
                                    {formatCurrency(s.conservative)}
                                </Button>
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
};
