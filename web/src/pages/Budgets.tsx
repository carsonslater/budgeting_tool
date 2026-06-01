import React, { useState, useEffect } from 'react';
import { format, startOfMonth, endOfMonth, parseISO } from 'date-fns';
import { Trash2, ChevronDown, ChevronRight } from 'lucide-react';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { Select } from '../components/ui/Select';
import { MonthPicker } from '../components/ui/MonthPicker';
import { useCategories, useSubcategories } from '../hooks/useExpenses';
import { useBudgets, useBudgetActions, useSuggestedBudgets } from '../hooks/useBudgets';
import { useIncome, useSetIncome } from '../hooks/useIncome';
import styles from './Budgets.module.css';
import type { Budget } from '../types';

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(amount);
}

function getMonthlyEquivalent(limit: number, frequency: string) {
  switch (frequency) {
    case 'Quarterly': return limit / 3;
    case 'Bi-annually': return limit / 6;
    case 'Annually': return limit / 12;
    default: return limit;
  }
}

function toPeriodLimit(monthlyAmount: number, frequency: string) {
  switch (frequency) {
    case 'Quarterly': return monthlyAmount * 3;
    case 'Bi-annually': return monthlyAmount * 6;
    case 'Annually': return monthlyAmount * 12;
    default: return monthlyAmount;
  }
}

export const Budgets: React.FC = () => {
  // Income State
  const [incomeInput, setIncomeInput] = useState('');

  // Form State
  const [editId, setEditId] = useState<number | null>(null);
  const [effectiveDate, setEffectiveDate] = useState(format(startOfMonth(new Date()), 'yyyy-MM-dd'));
  const [conclusionDate, setConclusionDate] = useState('');
  const [category, setCategory] = useState('');
  const [subcategory, setSubcategory] = useState('');
  const [frequency, setFrequency] = useState('Monthly');
  const [limit, setLimit] = useState('');

  // UI State
  const [showUpcoming, setShowUpcoming] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  // Queries & Mutations
  const { data: budgets, isLoading: loadingBudgets } = useBudgets();
  const { data: suggestions } = useSuggestedBudgets();
  const { data: incomeData } = useIncome();
  const setIncomeMutation = useSetIncome();
  const { data: categories } = useCategories();
  const { data: subcategories } = useSubcategories(category);
  const { create, update, remove } = useBudgetActions();

  useEffect(() => {
    if (typeof incomeData === 'number') {
      setIncomeInput(incomeData.toString());
    }
  }, [incomeData]);

  const resetForm = () => {
    setEditId(null);
    setEffectiveDate(format(startOfMonth(new Date()), 'yyyy-MM-dd'));
    setConclusionDate('');
    setCategory('');
    setSubcategory('');
    setFrequency('Monthly');
    setLimit('');
  };

  const handleRowClick = (b: Budget) => {
    setEditId(b.id);
    setEffectiveDate(b.effective_date);
    setConclusionDate(b.conclusion_date ? b.conclusion_date.substring(0, 7) : '');
    setCategory(b.category);
    setSubcategory(b.subcategory);
    setFrequency(b.frequency);
    setLimit(b.limit_amount.toString());
  };

  const toggleSelect = (id: number) => {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedIds(next);
  };

  const handleDeleteSelected = async () => {
    const ids = Array.from(selectedIds);
    for (const id of ids) {
      await remove.mutateAsync(id);
    }
    setSelectedIds(new Set());
    setShowDeleteModal(false);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload = {
      effective_date: effectiveDate,
      category,
      subcategory,
      frequency: frequency as Budget['frequency'],
      limit_amount: parseFloat(limit) || 0,
      conclusion_date: conclusionDate ? format(endOfMonth(parseISO(`${conclusionDate}-01`)), 'yyyy-MM-dd') : null,
    };

    if (editId) {
      update.mutate({ id: editId, data: payload }, { onSuccess: resetForm });
    } else {
      create.mutate(payload, { onSuccess: resetForm });
    }
  };

  const handleSaveIncome = () => {
    const val = parseFloat(incomeInput);
    if (!isNaN(val)) {
      setIncomeMutation.mutate(val);
    }
  };

  const handleApplySuggestions = async (type: 'hasty' | 'conservative') => {
    if (!suggestions) return;
    for (const s of suggestions) {
      const newMonthly = type === 'hasty' ? s.hasty : s.conservative;
      const newLimit = toPeriodLimit(newMonthly, s.frequency);
      
      if (Math.abs(newLimit - s.current_limit) > 0.01) {
        await update.mutateAsync({ id: s.budget_id, data: { limit_amount: newLimit } });
      }
    }
  };

  // Derive Table Data
  const today = format(new Date(), 'yyyy-MM-dd');
  const activeBudgets = budgets?.filter(b => b.effective_date <= today && (!b.conclusion_date || b.conclusion_date >= today)) || [];
  const upcomingBudgets = budgets?.filter(b => b.effective_date > today) || [];

  const totalMonthlyBudgeted = activeBudgets.reduce((sum, b) => sum + getMonthlyEquivalent(b.limit_amount, b.frequency), 0);
  const currentIncome = typeof incomeData === 'number' ? incomeData : 0;
  const remaining = currentIncome - totalMonthlyBudgeted;

  return (
    <div className={styles.container}>
      {/* Sidebar Form */}
      <div className={styles.sidebar}>
        <Card padding="lg">
          <div className={styles.incomeHeader}>
            <div style={{ flex: 1 }}>
              <Input
                label="Monthly Income"
                type="number"
                step="0.01"
                value={incomeInput}
                onChange={(e) => setIncomeInput(e.target.value)}
              />
            </div>
            <Button onClick={handleSaveIncome} loading={setIncomeMutation.isPending}>Save</Button>
          </div>

          <h3 style={{ marginTop: '0.5rem', marginBottom: '1rem', fontSize: '1.1rem' }}>
            {editId ? "Update Budget" : "Add Budget"}
          </h3>
          <form onSubmit={handleSubmit} className={styles.formCard}>
            <MonthPicker
              label="Effective Month"
              value={effectiveDate.substring(0, 7)}
              onChange={(val) => setEffectiveDate(`${val}-01`)}
              required
            />

            <MonthPicker
              label="Termination Month (Optional)"
              value={conclusionDate}
              onChange={(val) => setConclusionDate(val)}
            />

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
              onChange={(e) => setFrequency(e.target.value)}
              options={[
                { value: 'Monthly', label: 'Monthly' },
                { value: 'Quarterly', label: 'Quarterly' },
                { value: 'Bi-annually', label: 'Bi-annually' },
                { value: 'Annually', label: 'Annually' }
              ]}
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
              <Button type="submit" loading={create.isPending || update.isPending} style={{ flex: 1 }}>
                {editId ? 'Update Budget' : 'Save Budget'}
              </Button>
              {editId && (
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
            <span className={styles.summaryLabel}>Monthly Income</span>
            <span className={styles.summaryValue}>{formatCurrency(currentIncome)}</span>
          </div>
          <div className={styles.summaryItem}>
            <span className={styles.summaryLabel}>Total Budgeted</span>
            <span className={styles.summaryValue}>{formatCurrency(totalMonthlyBudgeted)}</span>
          </div>
          <div className={styles.summaryItem}>
            <span className={styles.summaryLabel}>Remaining</span>
            <span className={`${styles.summaryValue} ${remaining >= 0 ? styles.success : styles.danger}`}>
              {remaining < 0 ? '-' : ''}{formatCurrency(Math.abs(remaining))}
            </span>
          </div>
        </div>

        {/* Section 1: Active Budgets */}
        <div className={styles.section}>
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>Active Budgets</h2>
            {selectedIds.size > 0 && (
              <Button variant="danger" size="sm" onClick={() => setShowDeleteModal(true)}>
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
                      checked={selectedIds.size === activeBudgets.length && activeBudgets.length > 0}
                      onChange={(e) => {
                        if (e.target.checked) setSelectedIds(new Set(activeBudgets.map((b) => b.id)));
                        else setSelectedIds(new Set());
                      }}
                    />
                  </th>
                  <th>Category</th>
                  <th>Subcategory</th>
                  <th>Frequency</th>
                  <th className={styles.amountCell}>Monthly Equiv</th>
                  <th>Effective Date</th>
                </tr>
              </thead>
              <tbody>
                {loadingBudgets ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', padding: '1rem' }}>Loading...</td></tr>
                ) : activeBudgets.length === 0 ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', padding: '1rem' }}>No active budgets.</td></tr>
                ) : (
                  activeBudgets.map(b => (
                    <tr key={b.id} className={selectedIds.has(b.id) ? styles.selected : ''} onClick={() => handleRowClick(b)}>
                      <td onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          className={styles.checkbox}
                          checked={selectedIds.has(b.id)}
                          onChange={() => toggleSelect(b.id)}
                        />
                      </td>
                      <td>{b.category}</td>
                      <td>{b.subcategory}</td>
                      <td>{b.frequency}</td>
                      <td className={styles.amountCell}>{formatCurrency(getMonthlyEquivalent(b.limit_amount, b.frequency))}</td>
                      <td>{format(parseISO(b.effective_date), 'MMM yyyy')}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Section 2: Upcoming Budgets */}
        {upcomingBudgets.length > 0 && (
          <div className={styles.section} style={{ marginTop: '1rem' }}>
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle} onClick={() => setShowUpcoming(!showUpcoming)}>
                {showUpcoming ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
                Upcoming Budgets ({upcomingBudgets.length})
              </h2>
            </div>
            {showUpcoming && (
              <div className={styles.tableContainer}>
                <table className={`${styles.table} ${styles.interactive}`}>
                  <thead>
                    <tr>
                      <th>Category</th>
                      <th>Subcategory</th>
                      <th>Frequency</th>
                      <th className={styles.amountCell}>Monthly Equiv</th>
                      <th>Effective Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {upcomingBudgets.map(b => (
                      <tr key={b.id} onClick={() => handleRowClick(b)}>
                        <td>{b.category}</td>
                        <td>{b.subcategory}</td>
                        <td>{b.frequency}</td>
                        <td className={styles.amountCell}>{formatCurrency(getMonthlyEquivalent(b.limit_amount, b.frequency))}</td>
                        <td>{format(parseISO(b.effective_date), 'MMM yyyy')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Section 3: Suggested Budgets */}
        {suggestions && suggestions.length > 0 && (
          <div className={styles.section} style={{ marginTop: '1rem' }}>
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>Suggested Adjustments</h2>
              <div style={{ display: 'flex', gap: '0.75rem' }}>
                <Button size="sm" onClick={() => handleApplySuggestions('conservative')}>Apply Conservative</Button>
                <Button size="sm" onClick={() => handleApplySuggestions('hasty')}>Apply Hasty</Button>
              </div>
            </div>
            <p className={styles.explainerText}>
              Suggestions based on the last 3 months of spending. <strong>Hasty</strong> weights recent months heavily (0.6/0.3/0.1), while <strong>Conservative</strong> applies an even spread (0.4/0.4/0.2). Only shows deviations &gt; $50.
            </p>
            <div className={styles.tableContainer}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Category</th>
                    <th>Subcategory</th>
                    <th className={styles.amountCell}>Current Equiv Limit</th>
                    <th className={styles.amountCell}>Hasty Suggestion</th>
                    <th className={styles.amountCell}>Conservative Suggestion</th>
                  </tr>
                </thead>
                <tbody>
                  {suggestions.map((s, idx) => (
                    <tr key={idx}>
                      <td>{s.category}</td>
                      <td>{s.subcategory}</td>
                      <td className={styles.amountCell}>{formatCurrency(s.current_monthly_equiv)}</td>
                      <td className={`${styles.amountCell} ${s.hasty > s.current_monthly_equiv ? styles.suggestionUp : styles.suggestionDown}`}>
                        {formatCurrency(s.hasty)}
                      </td>
                      <td className={`${styles.amountCell} ${s.conservative > s.current_monthly_equiv ? styles.suggestionUp : styles.suggestionDown}`}>
                        {formatCurrency(s.conservative)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

      </div>

      {/* Delete Modal */}
      {showDeleteModal && (
        <div className={styles.modalOverlay}>
          <div className={styles.modalContent}>
            <h3 style={{ marginTop: 0 }}>Delete Budgets?</h3>
            <p style={{ color: 'var(--color-text-muted)', marginBottom: '1rem' }}>
              Are you sure you want to delete {selectedIds.size} budget{selectedIds.size > 1 ? 's' : ''}?
            </p>
            <div className={styles.modalActions}>
              <Button variant="ghost" onClick={() => setShowDeleteModal(false)}>Cancel</Button>
              <Button variant="danger" loading={remove.isPending} onClick={handleDeleteSelected}>
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Budgets;
