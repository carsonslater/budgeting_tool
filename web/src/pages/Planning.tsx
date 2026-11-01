import React, { useState, useMemo, useEffect, useRef } from 'react';
import { format, isValid, parseISO } from 'date-fns';
import { Trash2 } from 'lucide-react';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { Select } from '../components/ui/Select';
import { MonthPicker } from '../components/ui/MonthPicker';
import { ApplyScopeControl } from '../components/planning/ApplyScopeControl';
import { MonthStatusStrip } from '../components/planning/MonthStatusStrip';
import { useCategories, useSubcategories } from '../hooks/useExpenses';
import {
  useBudgets,
  useCreateBudget,
  useUpdateBudget,
  useDeleteBudget,
} from '../hooks/useBudgets';
import {
  useMonthPlanStatuses,
  useMonthPlan,
  useConfirmMonth,
  useSetExpectedIncome,
} from '../hooks/useMonthPlans';
import { useToast } from '../contexts/ToastContext';
import {
  DEFAULT_APPLY_CHOICE,
  applyScopeError,
  toApplyScope,
  type ApplyChoice,
} from '../lib/applyScope';
import { monthLabel, shiftMonth } from '../lib/monthMath';
import styles from './Planning.module.css';
import type { Budget } from '../types';
import { monthlyEquivalent } from '../lib/budgetMath';

const FREQUENCIES: Budget['frequency'][] = [
  'Monthly',
  'Quarterly',
  'Bi-annually',
  'Annually',
];

/** The status strip shows this many months before and after the selected one. */
const STRIP_MONTHS_BEFORE = 3;
const STRIP_MONTHS_AFTER = 8;

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(amount);
}

function formatConfirmedAt(value: string) {
  const parsed = parseISO(value);
  return isValid(parsed) ? format(parsed, 'MMM d, yyyy') : value;
}

/**
 * Planning — edit one month's budget and expected income.
 *
 * Edits apply immediately (there are no drafts). A line keeps its amount from the
 * month it was set until its next change, so a month with no edits of its own
 * follows the months before it. The "Applies to" control decides how far an amount
 * or income change reaches from the selected month. Confirming a month ("Keep as
 * is") marks it reviewed and writes nothing to the budget.
 */
export const Planning: React.FC = () => {
  const { showToast } = useToast();

  const [month, setMonth] = useState(format(new Date(), 'yyyy-MM'));

  // Line form
  const [editKey, setEditKey] = useState<string | null>(null);
  const [category, setCategory] = useState('');
  const [subcategory, setSubcategory] = useState('');
  const [frequency, setFrequency] = useState<Budget['frequency']>('Monthly');
  const [limit, setLimit] = useState('');

  // Expected income form
  const [incomeInput, setIncomeInput] = useState('');

  // Shared by line and income writes
  const [applyChoice, setApplyChoice] = useState<ApplyChoice>(DEFAULT_APPLY_CHOICE);

  // UI state
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const categoryRef = useRef<HTMLInputElement>(null);

  const prevMonth = shiftMonth(month, -1);
  const stripStart = shiftMonth(month, -STRIP_MONTHS_BEFORE);
  const stripEnd = shiftMonth(month, STRIP_MONTHS_AFTER);

  const { data: categories } = useCategories(month);
  const { data: subcategories } = useSubcategories(category, month);
  const { data: budgets, isLoading } = useBudgets(month);
  const { data: prevBudgets } = useBudgets(prevMonth);
  const { data: statuses } = useMonthPlanStatuses(stripStart, stripEnd);
  const { data: plan } = useMonthPlan(month);

  const createBudget = useCreateBudget();
  const updateBudget = useUpdateBudget();
  const deleteBudget = useDeleteBudget();
  const confirmMonth = useConfirmMonth();
  const setIncome = useSetExpectedIncome();

  const lines = useMemo(() => budgets ?? [], [budgets]);
  const editing = useMemo(
    () => lines.find((l) => l.line_key === editKey) ?? null,
    [lines, editKey],
  );
  const confirmed = plan?.status === 'confirmed';
  const scopeError = applyScopeError(month, applyChoice);
  const budgetBusy = createBudget.isPending || updateBudget.isPending || deleteBudget.isPending;
  const busy = budgetBusy || confirmMonth.isPending || setIncome.isPending;

  // Names are stored once for the whole line, so a category or subcategory edit
  // changes every month and ignores "Applies to". Say so before the user saves.
  const nameChanged =
    editing !== null &&
    (category !== editing.category || subcategory !== editing.subcategory);

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

  // A new month starts from a clean slate: no stale edit, selection or scope.
  useEffect(() => {
    setSelectedKeys(new Set());
    resetForm();
    setApplyChoice(DEFAULT_APPLY_CHOICE);
  }, [month]);

  // Show the saved income for the month, including after a save refetches it.
  useEffect(() => {
    setIncomeInput(plan?.expected_income != null ? String(plan.expected_income) : '');
  }, [month, plan?.expected_income]);

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
    if (scopeError) return;
    const keys = Array.from(selectedKeys);
    const scope = toApplyScope(applyChoice);
    try {
      for (const key of keys) {
        await deleteBudget.mutateAsync({ lineKey: key, month, scope });
      }
      setSelectedKeys(new Set());
      setApplyChoice(DEFAULT_APPLY_CHOICE);
      showToast(keys.length === 1 ? 'Budget line deleted' : 'Budget lines deleted', 'success');
    } catch (e: any) {
      showToast(e?.message || 'Could not delete the selected lines', 'error');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (scopeError) return;
    const amount = parseFloat(limit) || 0;
    const scope = toApplyScope(applyChoice);

    try {
      if (editKey) {
        await updateBudget.mutateAsync({
          lineKey: editKey,
          month,
          data: { category, subcategory, frequency, limit_amount: amount },
          scope,
        });
        showToast('Budget line updated', 'success');
      } else {
        await createBudget.mutateAsync({
          month,
          category,
          subcategory,
          frequency,
          limit_amount: amount,
          ...scope,
        });
        showToast('Budget line added', 'success');
      }
      resetForm();
      setApplyChoice(DEFAULT_APPLY_CHOICE);
    } catch (e: any) {
      showToast(e?.message || 'Could not save the budget line', 'error');
    }
  };

  const handleIncomeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (scopeError) return;
    const amount = parseFloat(incomeInput);
    if (!Number.isFinite(amount) || amount < 0) {
      showToast('Enter an expected income of zero or more', 'error');
      return;
    }
    try {
      await setIncome.mutateAsync({ month, amount, scope: toApplyScope(applyChoice) });
      setApplyChoice(DEFAULT_APPLY_CHOICE);
      showToast('Expected income saved', 'success');
    } catch (e: any) {
      showToast(e?.message || 'Could not save the expected income', 'error');
    }
  };

  const handleKeepAsIs = async () => {
    try {
      await confirmMonth.mutateAsync(month);
      showToast(`${monthLabel(month)} confirmed`, 'success');
    } catch (e: any) {
      showToast(e?.message || 'Could not confirm the month', 'error');
    }
  };

  const handleEdit = () => {
    categoryRef.current?.focus();
  };

  const monthLabelText = monthLabel(month);
  const prevMonthLabel = monthLabel(prevMonth);
  const totalMonthlyBudgeted = lines.reduce(
    (sum, b) => sum + monthlyEquivalent(b.limit_amount, b.frequency),
    0,
  );
  const expectedIncome = plan?.expected_income ?? null;
  const incomeLessBudget = expectedIncome === null ? null : expectedIncome - totalMonthlyBudgeted;

  let statusText = 'Loading…';
  if (plan && confirmed) {
    const when = plan.confirmed_at ? ` on ${formatConfirmedAt(plan.confirmed_at)}` : '';
    statusText = `Confirmed${when}.`;
  } else if (plan) {
    statusText =
      `${monthLabelText} is not confirmed. Its lines follow ${prevMonthLabel} until changed. ` +
      'Keep as is marks it reviewed and does not change the budget.';
  }

  return (
    <div className={styles.container}>
      {/* Sidebar */}
      <div className={styles.sidebar}>
        <Card padding="lg">
          <div style={{ marginBottom: '1.5rem' }}>
            <MonthPicker label="Budget Month" value={month} onChange={setMonth} required />
          </div>
          <ApplyScopeControl
            month={month}
            value={applyChoice}
            onChange={setApplyChoice}
            error={scopeError}
          />
        </Card>

        <Card padding="lg">
          <h3 style={{ marginTop: 0, marginBottom: '1rem', fontSize: '1.1rem' }}>
            Expected income
          </h3>
          <form onSubmit={handleIncomeSubmit} className={styles.formCard}>
            <Input
              id="expected-income"
              label="Expected income"
              type="number"
              step="0.01"
              min="0"
              value={incomeInput}
              onChange={(e) => setIncomeInput(e.target.value)}
              required
            />
            {plan?.income_set_in && (
              <p className={styles.hint}>
                Set in {monthLabel(plan.income_set_in)}; it carries forward until changed.
              </p>
            )}
            <div className={styles.buttonGroup}>
              <Button
                type="submit"
                style={{ flex: 1 }}
                disabled={busy || !!scopeError || incomeInput.trim() === ''}
              >
                Save income
              </Button>
            </div>
          </form>
        </Card>

        <Card padding="lg">
          <h3 style={{ marginTop: 0, marginBottom: '1rem', fontSize: '1.1rem' }}>
            {editKey ? 'Edit Line' : 'Add Line'}
          </h3>
          <form onSubmit={handleSubmit} className={styles.formCard}>
            <Input
              ref={categoryRef}
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

            {nameChanged && (
              <p className={styles.notice}>
                Changing the category or subcategory applies to every month this line exists
                in; "Applies to" does not limit it. Amount and frequency follow "Applies to".
              </p>
            )}

            <div className={styles.buttonGroup}>
              <Button type="submit" style={{ flex: 1 }} disabled={busy || !!scopeError}>
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
          <div className={styles.summaryItem}>
            <span className={styles.summaryLabel}>Expected income</span>
            <span className={styles.summaryValue}>
              {expectedIncome === null ? 'Not set' : formatCurrency(expectedIncome)}
            </span>
          </div>
          <div className={styles.summaryItem}>
            <span className={styles.summaryLabel}>Budgeted per month</span>
            <span className={styles.summaryValue}>{formatCurrency(totalMonthlyBudgeted)}</span>
          </div>
          <div className={styles.summaryItem}>
            <span className={styles.summaryLabel}>Income less budget</span>
            <span
              className={`${styles.summaryValue} ${
                incomeLessBudget !== null && incomeLessBudget < 0 ? styles.danger : ''
              }`}
            >
              {incomeLessBudget === null ? '—' : formatCurrency(incomeLessBudget)}
            </span>
          </div>
        </div>

        {/* Month status */}
        <Card padding="md">
          <MonthStatusStrip months={statuses ?? []} selected={month} onSelect={setMonth} />
          <div className={styles.statusRow}>
            <p className={styles.statusText}>{statusText}</p>
            <div className={styles.buttonGroup}>
              {!confirmed && (
                <Button size="sm" onClick={handleKeepAsIs} disabled={busy || !plan}>
                  Keep as is
                </Button>
              )}
              <Button size="sm" variant="ghost" onClick={handleEdit}>
                Edit
              </Button>
            </div>
          </div>
        </Card>

        {/* Lines */}
        <div className={styles.section}>
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>Budget Lines</h2>
            {selectedKeys.size > 0 && (
              <Button
                variant="danger"
                size="sm"
                onClick={handleDeleteSelected}
                disabled={busy || !!scopeError}
              >
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
                      No budget lines for {monthLabelText}.
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
