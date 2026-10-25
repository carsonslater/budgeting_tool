import React, { useState, useMemo, useEffect } from 'react';
import { format, parseISO, subMonths, startOfMonth } from 'date-fns';
import { Trash2 } from 'lucide-react';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { Select } from '../components/ui/Select';
import { MonthPicker } from '../components/ui/MonthPicker';
import { useCategories, useSubcategories } from '../hooks/useExpenses';
import {
  useBudgets,
  useCreateBudget,
  useUpdateBudget,
  useDeleteBudget,
} from '../hooks/useBudgets';
import { useToast } from '../contexts/ToastContext';
import styles from './Planning.module.css';
import type { Budget } from '../types';
import { monthlyEquivalent } from '../lib/budgetMath';

const FREQUENCIES: Budget['frequency'][] = [
  'Monthly',
  'Quarterly',
  'Bi-annually',
  'Annually',
];

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(amount);
}

/**
 * Planning — edit one month's budget.
 *
 * Edits apply immediately (there are no drafts). A line keeps its amount from
 * the month it was set until its next change, so a month with no edits of its
 * own simply follows the months before it. An edit here carries forward to later
 * months until they are changed, and never touches earlier months.
 */
export const Planning: React.FC = () => {
  const { showToast } = useToast();

  const [month, setMonth] = useState(format(new Date(), 'yyyy-MM'));

  // Form state
  const [editKey, setEditKey] = useState<string | null>(null);
  const [category, setCategory] = useState('');
  const [subcategory, setSubcategory] = useState('');
  const [frequency, setFrequency] = useState<Budget['frequency']>('Monthly');
  const [limit, setLimit] = useState('');

  // UI state
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());

  const prevMonth = useMemo(
    () => format(startOfMonth(subMonths(parseISO(`${month}-01`), 1)), 'yyyy-MM'),
    [month],
  );

  const { data: categories } = useCategories(month);
  const { data: subcategories } = useSubcategories(category, month);
  const { data: budgets, isLoading } = useBudgets(month);
  const { data: prevBudgets } = useBudgets(prevMonth);

  const createBudget = useCreateBudget();
  const updateBudget = useUpdateBudget();
  const deleteBudget = useDeleteBudget();

  const lines = useMemo(() => budgets ?? [], [budgets]);
  const inherited = lines.length > 0 && lines[0].inherited;
  const busy = createBudget.isPending || updateBudget.isPending || deleteBudget.isPending;

  const prevMonthlyEquiv = useMemo(() => {
    const map = new Map<string, number>();
    for (const b of prevBudgets ?? []) {
      map.set(b.line_key, monthlyEquivalent(b.limit_amount, b.frequency));
    }
    return map;
  }, [prevBudgets]);

  const resetForm = () => {
    setEditKey(null);
    setCategory('');
    setSubcategory('');
    setFrequency('Monthly');
    setLimit('');
  };

  // A new month starts from a clean slate — no stale edit or selection.
  useEffect(() => {
    setSelectedKeys(new Set());
    setEditKey(null);
    setCategory('');
    setSubcategory('');
    setFrequency('Monthly');
    setLimit('');
  }, [month]);

  const handleRowClick = (line: Budget) => {
    setEditKey(line.line_key);
    setCategory(line.category);
    setSubcategory(line.subcategory);
    setFrequency(line.frequency);
    setLimit(line.limit_amount.toString());
  };

  const toggleSelect = (key: string) => {
    const next = new Set(selectedKeys);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setSelectedKeys(next);
  };

  const handleDeleteSelected = async () => {
    const keys = Array.from(selectedKeys);
    try {
      for (const key of keys) {
        await deleteBudget.mutateAsync({ lineKey: key, month });
      }
      setSelectedKeys(new Set());
      showToast(keys.length === 1 ? 'Budget line deleted' : 'Budget lines deleted', 'success');
    } catch (e: any) {
      showToast(e?.message || 'Could not delete the selected lines', 'error');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const amount = parseFloat(limit) || 0;

    try {
      if (editKey) {
        await updateBudget.mutateAsync({
          lineKey: editKey,
          month,
          data: { category, subcategory, frequency, limit_amount: amount },
        });
        showToast('Budget line updated', 'success');
      } else {
        await createBudget.mutateAsync({
          month,
          category,
          subcategory,
          frequency,
          limit_amount: amount,
        });
        showToast('Budget line added', 'success');
      }
      resetForm();
    } catch (e: any) {
      showToast(e?.message || 'Could not save the budget line', 'error');
    }
  };

  const monthLabel = format(parseISO(`${month}-01`), 'MMMM yyyy');
  const prevMonthLabel = format(parseISO(`${prevMonth}-01`), 'MMM yyyy');
  const totalMonthlyBudgeted = lines.reduce(
    (sum, b) => sum + monthlyEquivalent(b.limit_amount, b.frequency),
    0,
  );

  return (
    <div className={styles.container}>
      {/* Sidebar Form */}
      <div className={styles.sidebar}>
        <Card padding="lg">
          <div style={{ marginBottom: '1.5rem' }}>
            <MonthPicker label="Budget Month" value={month} onChange={setMonth} required />
          </div>

          <h3 style={{ marginTop: '0.5rem', marginBottom: '1rem', fontSize: '1.1rem' }}>
            {editKey ? 'Edit Line' : 'Add Line'}
          </h3>
          <form onSubmit={handleSubmit} className={styles.formCard}>
            <Input
              label="Category"
              list="categories-list"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              required
            />

            <Input
              label="Subcategory"
              list="subcategories-list"
              value={subcategory}
              onChange={(e) => setSubcategory(e.target.value)}
            />

            <Select
              label="Frequency"
              value={frequency}
              onChange={(e) => setFrequency(e.target.value as Budget['frequency'])}
              options={FREQUENCIES.map((f) => ({ value: f, label: f }))}
              required
            />

            <Input
              label="Amount per period"
              type="number"
              step="0.01"
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
              required
            />

            <div className={styles.buttonGroup}>
              <Button type="submit" style={{ flex: 1 }} disabled={busy}>
                {editKey ? 'Save Line' : 'Add Line'}
              </Button>
              {editKey && (
                <Button type="button" variant="ghost" onClick={resetForm}>
                  Cancel
                </Button>
              )}
            </div>
          </form>

          <datalist id="categories-list">
            {categories?.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
          <datalist id="subcategories-list">
            {subcategories?.map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
        </Card>
      </div>

      {/* Main Area */}
      <div className={styles.mainArea}>
        {/* Summary Row */}
        <div className={styles.summaryRow}>
          <div className={styles.summaryItem} style={{ flex: 2 }}>
            <span className={styles.summaryLabel}>Total monthly budget — {monthLabel}</span>
            <span className={styles.summaryValue}>{formatCurrency(totalMonthlyBudgeted)}</span>
          </div>
        </div>

        {inherited && (
          <div
            style={{
              marginBottom: '1rem',
              padding: '0.75rem 1rem',
              borderRadius: '6px',
              background: 'var(--color-surface-raised)',
              color: 'var(--color-text-muted)',
              fontSize: '0.9rem',
            }}
          >
            {monthLabel} follows {prevMonthLabel} and has not been confirmed. An edit here
            carries forward to later months until they are changed — it never affects{' '}
            {prevMonthLabel} or earlier.
          </div>
        )}

        {/* Lines */}
        <div className={styles.section}>
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>Budget Lines</h2>
            {selectedKeys.size > 0 && (
              <Button variant="danger" size="sm" onClick={handleDeleteSelected} disabled={busy}>
                <Trash2 size={16} style={{ marginRight: 6 }} />
                Delete Selected
              </Button>
            )}
          </div>
          <div className={styles.tableContainer}>
            <table className={`${styles.table} ${styles.interactive}`}>
              <thead>
                <tr>
                  <th style={{ width: '40px' }}>
                    <input
                      type="checkbox"
                      className={styles.checkbox}
                      checked={selectedKeys.size === lines.length && lines.length > 0}
                      onChange={(e) => {
                        if (e.target.checked) setSelectedKeys(new Set(lines.map((l) => l.line_key)));
                        else setSelectedKeys(new Set());
                      }}
                    />
                  </th>
                  <th>Category</th>
                  <th>Subcategory</th>
                  <th>Frequency</th>
                  <th className={styles.amountCell}>Amount / period</th>
                  <th className={styles.amountCell}>Monthly Equiv</th>
                  <th className={styles.amountCell}>Change vs {prevMonthLabel}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={7} style={{ textAlign: 'center', padding: '1rem' }}>
                      Loading...
                    </td>
                  </tr>
                ) : lines.length === 0 ? (
                  <tr>
                    <td colSpan={7} style={{ textAlign: 'center', padding: '1rem' }}>
                      No budget lines for {monthLabel}.
                    </td>
                  </tr>
                ) : (
                  lines.map((line) => {
                    const equiv = monthlyEquivalent(line.limit_amount, line.frequency);
                    const prevEquiv = prevMonthlyEquiv.get(line.line_key) ?? 0;
                    const diff = equiv - prevEquiv;

                    return (
                      <tr
                        key={line.line_key}
                        className={editKey === line.line_key ? styles.selected : ''}
                        onClick={() => handleRowClick(line)}
                      >
                        <td onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            className={styles.checkbox}
                            checked={selectedKeys.has(line.line_key)}
                            onChange={() => toggleSelect(line.line_key)}
                          />
                        </td>
                        <td>{line.category}</td>
                        <td>{line.subcategory}</td>
                        <td>{line.frequency}</td>
                        <td className={styles.amountCell}>{formatCurrency(line.limit_amount)}</td>
                        <td className={styles.amountCell}>{formatCurrency(equiv)}</td>
                        <td className={styles.amountCell}>
                          {diff > 0.01 && (
                            <span style={{ color: 'var(--color-danger)' }}>
                              +{formatCurrency(diff)}
                            </span>
                          )}
                          {diff < -0.01 && (
                            <span style={{ color: 'var(--color-success)' }}>
                              {formatCurrency(diff)}
                            </span>
                          )}
                          {Math.abs(diff) <= 0.01 && (
                            <span style={{ color: 'var(--color-text-muted)' }}>No change</span>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Planning;
