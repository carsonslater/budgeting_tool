import React, { useState, useMemo } from 'react';
import { format, addMonths, parseISO, startOfMonth } from 'date-fns';
import { Trash2 } from 'lucide-react';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { Select } from '../components/ui/Select';
import { MonthPicker } from '../components/ui/MonthPicker';
import { useCategories, useSubcategories } from '../hooks/useExpenses';
import { useBudgetDrafts } from '../hooks/useBudgetDrafts';
import { useBudgets } from '../hooks/useBudgets';
import { useToast } from '../contexts/ToastContext';
import styles from './Budgets.module.css'; // Reuse Budgets styling
import type { BudgetDraft } from '../types';

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

export const Planning: React.FC = () => {
  const { showToast } = useToast();
  
  // Start with next month
  const [targetMonth, setTargetMonth] = useState(format(startOfMonth(addMonths(new Date(), 1)), 'yyyy-MM-dd'));

  // Form State
  const [editId, setEditId] = useState<number | null>(null);
  const [category, setCategory] = useState('');
  const [subcategory, setSubcategory] = useState('');
  const [frequency, setFrequency] = useState('Monthly');
  const [limit, setLimit] = useState('');

  // UI State
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  // Queries
  const { data: categories } = useCategories();
  const { data: subcategories } = useSubcategories(category);
  const { drafts, isLoading, createDraft, updateDraft, deleteDraft, commitDrafts, isCommitting } = useBudgetDrafts(targetMonth);
  const { data: activeBudgets } = useBudgets();

  const activeBudgetMap = useMemo(() => {
    const map = new Map<string, number>();
    if (!activeBudgets) return map;
    const today = format(new Date(), 'yyyy-MM-dd');
    for (const b of activeBudgets) {
      if (b.effective_date <= today && (!b.conclusion_date || b.conclusion_date >= today)) {
        map.set(`${b.category}|${b.subcategory}`, getMonthlyEquivalent(b.limit_amount, b.frequency));
      }
    }
    return map;
  }, [activeBudgets]);

  const resetForm = () => {
    setEditId(null);
    setCategory('');
    setSubcategory('');
    setFrequency('Monthly');
    setLimit('');
  };

  const handleRowClick = (d: BudgetDraft) => {
    setEditId(d.id);
    setCategory(d.category);
    setSubcategory(d.subcategory);
    setFrequency(d.frequency);
    setLimit(d.limit_amount.toString());
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
      await deleteDraft(id);
    }
    setSelectedIds(new Set());
    showToast('Drafts deleted', 'success');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const payload = {
      target_month: targetMonth,
      category,
      subcategory,
      frequency: frequency as BudgetDraft['frequency'],
      limit_amount: parseFloat(limit) || 0,
    };

    if (editId) {
      await updateDraft({ id: editId, data: payload });
    } else {
      await createDraft(payload);
    }
    resetForm();
  };

  const handleCommit = async () => {
    try {
      await commitDrafts();
      showToast(`Final budget submitted for ${format(parseISO(targetMonth), 'MMM yyyy')}`, 'success');
    } catch (e: any) {
      showToast(e.message || 'Error committing drafts', 'error');
    }
  };

  const totalMonthlyBudgeted = drafts.reduce((sum, b) => sum + getMonthlyEquivalent(b.limit_amount, b.frequency), 0);

  return (
    <div className={styles.container}>
      {/* Sidebar Form */}
      <div className={styles.sidebar}>
        <Card padding="lg">
          <div style={{ marginBottom: '1.5rem' }}>
            <MonthPicker
              label="Planning Month"
              value={targetMonth.substring(0, 7)}
              onChange={(val) => setTargetMonth(`${val}-01`)}
              required
            />
          </div>

          <h3 style={{ marginTop: '0.5rem', marginBottom: '1rem', fontSize: '1.1rem' }}>
            {editId ? "Update Draft" : "Add to Draft"}
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
              <Button type="submit" style={{ flex: 1 }}>
                {editId ? 'Update Draft' : 'Add Draft'}
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
          <div className={styles.summaryItem} style={{ flex: 2 }}>
            <span className={styles.summaryLabel}>Draft Total for {format(parseISO(targetMonth), 'MMMM yyyy')}</span>
            <span className={styles.summaryValue}>{formatCurrency(totalMonthlyBudgeted)}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', flex: 1 }}>
            <Button onClick={handleCommit} loading={isCommitting} style={{ width: '100%' }}>
              Submit Final Budget
            </Button>
          </div>
        </div>

        {/* Section 1: Active Drafts */}
        <div className={styles.section}>
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>Budget Drafts</h2>
            {selectedIds.size > 0 && (
              <Button variant="danger" size="sm" onClick={handleDeleteSelected}>
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
                      checked={selectedIds.size === drafts.length && drafts.length > 0}
                      onChange={(e) => {
                        if (e.target.checked) setSelectedIds(new Set(drafts.map((d) => d.id)));
                        else setSelectedIds(new Set());
                      }}
                    />
                  </th>
                  <th>Category</th>
                  <th>Subcategory</th>
                  <th>Frequency</th>
                  <th className={styles.amountCell}>Monthly Equiv</th>
                  <th className={styles.amountCell}>Change</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', padding: '1rem' }}>Loading...</td></tr>
                ) : drafts.length === 0 ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', padding: '1rem' }}>No drafts.</td></tr>
                ) : (
                  drafts.map(d => {
                    const equiv = getMonthlyEquivalent(d.limit_amount, d.frequency);
                    const activeEquiv = activeBudgetMap.get(`${d.category}|${d.subcategory}`) || 0;
                    const diff = equiv - activeEquiv;

                    return (
                      <tr key={d.id} className={selectedIds.has(d.id) ? styles.selected : ''} onClick={() => handleRowClick(d)}>
                        <td onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            className={styles.checkbox}
                            checked={selectedIds.has(d.id)}
                            onChange={() => toggleSelect(d.id)}
                          />
                        </td>
                        <td>{d.category}</td>
                        <td>{d.subcategory}</td>
                        <td>{d.frequency}</td>
                        <td className={styles.amountCell}>{formatCurrency(equiv)}</td>
                        <td className={styles.amountCell}>
                          {diff > 0.01 && <span style={{ color: 'var(--color-danger)' }}>+{formatCurrency(diff)}</span>}
                          {diff < -0.01 && <span style={{ color: 'var(--color-success)' }}>{formatCurrency(diff)}</span>}
                          {Math.abs(diff) <= 0.01 && <span style={{ color: 'var(--color-text-muted)' }}>No change</span>}
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
