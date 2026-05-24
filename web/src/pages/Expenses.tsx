import React, { useState, useMemo, useEffect, useRef } from 'react';
import { format, parseISO, startOfMonth, endOfMonth } from 'date-fns';
import { ChevronUp, ChevronDown, Trash2 } from 'lucide-react';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { useExpenses, useExpenseActions, useCategories, usePayers, useSubcategories } from '../hooks/useExpenses';
import { useGoals } from '../hooks/useGoals';
import { EmptyState } from '../components/ui/EmptyState';
import styles from './Expenses.module.css';
import type { Expense } from '../types';

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(amount);
}

const PAGE_SIZE = 25;

export const Expenses: React.FC = () => {
  // Form State
  const [editId, setEditId] = useState<number | null>(null);
  const [date, setDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [description, setDescription] = useState('');
  const [type, setType] = useState<'Monthly' | 'Goal'>('Monthly');
  const [category, setCategory] = useState('');
  const [subcategory, setSubcategory] = useState('');
  const [goalName, setGoalName] = useState('');
  const [amount, setAmount] = useState('');
  const [payer, setPayer] = useState('Joint');

  // Table State
  const [page, setPage] = useState(1);
  const [sortCol, setSortCol] = useState<keyof Expense>('date');
  const [sortDesc, setSortDesc] = useState(true);
  const [filterText, setFilterText] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  
  // Modal State
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  // Queries & Mutations
  const { data: allExpenses, isLoading } = useExpenses();
  const { data: categories } = useCategories();
  const { data: payers } = usePayers();
  const { data: subcategories } = useSubcategories(category);
  const { data: goals } = useGoals();
  const { create, update, remove } = useExpenseActions();

  const resetForm = () => {
    setEditId(null);
    setDate(format(new Date(), 'yyyy-MM-dd'));
    setDescription('');
    setType('Monthly');
    setCategory('');
    setSubcategory('');
    setGoalName('');
    setAmount('');
    setPayer('Joint');
  };

  const descRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'n' && document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') {
        e.preventDefault();
        descRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleRowClick = (e: Expense) => {
    setEditId(e.id);
    setDate(e.date);
    setDescription(e.description);
    setType(e.expense_type);
    if (e.expense_type === 'Goal') {
      setGoalName(e.subcategory);
      setCategory('');
      setSubcategory('');
    } else {
      setCategory(e.category);
      setSubcategory(e.subcategory);
      setGoalName('');
    }
    setAmount(e.amount.toString());
    setPayer(e.payer);
  };

  const toggleSelect = (id: number) => {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedIds(next);
  };

  const handleDeleteSelected = async () => {
    const ids = Array.from(selectedIds);
    // Ideally use Promise.all or a batch delete endpoint, but loop works for now
    for (const id of ids) {
      await remove.mutateAsync(id);
    }
    setSelectedIds(new Set());
    setShowDeleteModal(false);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload = {
      date,
      description,
      expense_type: type,
      category: type === 'Goal' ? 'Goals' : category,
      subcategory: type === 'Goal' ? goalName : subcategory,
      amount: parseFloat(amount) || 0,
      payer,
    };

    if (editId) {
      update.mutate({ id: editId, data: payload }, { onSuccess: resetForm });
    } else {
      create.mutate(payload, { onSuccess: resetForm });
    }
  };

  // Derive Table Data
  const { filteredSorted, totalPages } = useMemo(() => {
    let list = [...(allExpenses || [])];

    if (filterText) {
      const lower = filterText.toLowerCase();
      list = list.filter(
        (e) =>
          e.description.toLowerCase().includes(lower) ||
          e.category.toLowerCase().includes(lower) ||
          e.subcategory.toLowerCase().includes(lower) ||
          e.payer.toLowerCase().includes(lower)
      );
    }

    list.sort((a, b) => {
      const valA = a[sortCol];
      const valB = b[sortCol];
      if (valA < valB) return sortDesc ? 1 : -1;
      if (valA > valB) return sortDesc ? -1 : 1;
      return 0;
    });

    return {
      filteredSorted: list,
      totalPages: Math.max(1, Math.ceil(list.length / PAGE_SIZE)),
    };
  }, [allExpenses, filterText, sortCol, sortDesc]);

  const pagedRows = filteredSorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const handleSort = (col: keyof Expense) => {
    if (sortCol === col) setSortDesc(!sortDesc);
    else {
      setSortCol(col);
      setSortDesc(true);
    }
  };

  // Derive running totals for current month
  const payerTotals = useMemo(() => {
    const now = new Date();
    const start = format(startOfMonth(now), 'yyyy-MM-dd');
    const end = format(endOfMonth(now), 'yyyy-MM-dd');
    const currentMonth = allExpenses?.filter((e) => e.date >= start && e.date <= end) || [];
    
    return currentMonth.reduce((acc, e) => {
      acc[e.payer] = (acc[e.payer] || 0) + e.amount;
      return acc;
    }, {} as Record<string, number>);
  }, [allExpenses]);

  return (
    <div className={styles.container}>
      {/* Sidebar Form */}
      <div className={styles.sidebar}>
        <Card title={editId ? "Update Expense" : "Log an Expense"} padding="lg">
          <form onSubmit={handleSubmit} className={styles.formCard}>
            <Input
              type="date"
              label="Date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              required
            />
            <Input
              ref={descRef}
              label="Description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              required
            />

            <div className={styles.formRow}>
              <label style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>Expense Type</label>
              <div className={styles.radioGroup}>
                <label className={styles.radioLabel}>
                  <input
                    type="radio"
                    checked={type === 'Monthly'}
                    onChange={() => setType('Monthly')}
                  /> Monthly
                </label>
                <label className={styles.radioLabel}>
                  <input
                    type="radio"
                    checked={type === 'Goal'}
                    onChange={() => setType('Goal')}
                  /> Goal
                </label>
              </div>
            </div>

            {type === 'Goal' ? (
              <Input
                label="Goal"
                list="goals-list"
                value={goalName}
                onChange={(e) => setGoalName(e.target.value)}
                required
              />
            ) : (
              <>
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
                  required
                />
              </>
            )}

            <Input
              label="Amount"
              type="number"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
            />

            <Input
              label="Payer"
              list="payers-list"
              value={payer}
              onChange={(e) => setPayer(e.target.value)}
              required
            />

            <div className={styles.buttonGroup}>
              <Button type="submit" loading={create.isPending || update.isPending} style={{ flex: 1 }}>
                {editId ? 'Update' : 'Add Expense'}
              </Button>
              {editId && (
                <Button type="button" variant="ghost" onClick={resetForm}>
                  Cancel
                </Button>
              )}
            </div>
          </form>

          {/* Datalists for autocomplete */}
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
          <datalist id="payers-list">
            {payers?.map((p) => (
              <option key={p} value={p} />
            ))}
          </datalist>
          <datalist id="goals-list">
            {goals?.map((g) => (
              <option key={g.name} value={g.name} />
            ))}
          </datalist>

          <div className={styles.payerTotals}>
            <div className={styles.payerTotalsTitle}>This Month's Spending</div>
            {Object.entries(payerTotals).length > 0 ? (
              Object.entries(payerTotals).map(([p, total]) => (
                <div key={p} className={styles.payerTotalRow}>
                  <span>{p}</span>
                  <span className={styles.payerTotalAmount}>{formatCurrency(total)}</span>
                </div>
              ))
            ) : (
              <div style={{ fontSize: '0.9rem', color: 'var(--color-text-muted)' }}>No spending yet.</div>
            )}
          </div>
        </Card>
      </div>

      {/* Main Area Table */}
      <div className={styles.mainArea}>
        <div className={styles.toolbar}>
          <div className={styles.toolbarLeft}>
            <Input
              placeholder="Search expenses..."
              value={filterText}
              onChange={(e) => {
                setFilterText(e.target.value);
                setPage(1); // reset to page 1 on search
              }}
              style={{ width: '300px' }}
            />
          </div>
          <div className={styles.toolbarRight}>
            {selectedIds.size > 0 && (
              <Button
                variant="danger"
                size="sm"
                onClick={() => setShowDeleteModal(true)}
              >
                <Trash2 size={16} style={{ marginRight: 6 }} />
                Delete Selected ({selectedIds.size})
              </Button>
            )}
          </div>
        </div>

        <div className={styles.tableContainer}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th style={{ width: '40px' }}>
                  <input
                    type="checkbox"
                    className={styles.checkbox}
                    checked={selectedIds.size === pagedRows.length && pagedRows.length > 0}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setSelectedIds(new Set(pagedRows.map((r) => r.id)));
                      } else {
                        setSelectedIds(new Set());
                      }
                    }}
                  />
                </th>
                <th onClick={() => handleSort('date')}>
                  Date {sortCol === 'date' && (sortDesc ? <ChevronDown size={14} className={styles.sortIcon}/> : <ChevronUp size={14} className={styles.sortIcon}/>)}
                </th>
                <th onClick={() => handleSort('description')}>
                  Description {sortCol === 'description' && (sortDesc ? <ChevronDown size={14} className={styles.sortIcon}/> : <ChevronUp size={14} className={styles.sortIcon}/>)}
                </th>
                <th onClick={() => handleSort('category')}>
                  Category {sortCol === 'category' && (sortDesc ? <ChevronDown size={14} className={styles.sortIcon}/> : <ChevronUp size={14} className={styles.sortIcon}/>)}
                </th>
                <th onClick={() => handleSort('subcategory')}>
                  Subcategory {sortCol === 'subcategory' && (sortDesc ? <ChevronDown size={14} className={styles.sortIcon}/> : <ChevronUp size={14} className={styles.sortIcon}/>)}
                </th>
                <th onClick={() => handleSort('amount')} className={styles.amountCell} style={{ textAlign: 'right' }}>
                  Amount {sortCol === 'amount' && (sortDesc ? <ChevronDown size={14} className={styles.sortIcon}/> : <ChevronUp size={14} className={styles.sortIcon}/>)}
                </th>
                <th onClick={() => handleSort('payer')}>
                  Payer {sortCol === 'payer' && (sortDesc ? <ChevronDown size={14} className={styles.sortIcon}/> : <ChevronUp size={14} className={styles.sortIcon}/>)}
                </th>
                <th onClick={() => handleSort('expense_type')}>
                  Type {sortCol === 'expense_type' && (sortDesc ? <ChevronDown size={14} className={styles.sortIcon}/> : <ChevronUp size={14} className={styles.sortIcon}/>)}
                </th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={8} style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-muted)' }}>
                    Loading expenses...
                  </td>
                </tr>
              ) : pagedRows.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ padding: 0 }}>
                    <EmptyState title="No expenses found" message="Try adjusting your search filters or add a new expense." />
                  </td>
                </tr>
              ) : (
                pagedRows.map((e) => (
                  <tr
                    key={e.id}
                    className={`${selectedIds.has(e.id) ? styles.selected : ''} ${styles.rowEntering}`}
                    onClick={() => handleRowClick(e)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td onClick={(ev) => ev.stopPropagation()}>
                      <input
                        type="checkbox"
                        className={styles.checkbox}
                        checked={selectedIds.has(e.id)}
                        onChange={() => toggleSelect(e.id)}
                      />
                    </td>
                    <td>{format(parseISO(e.date), 'MMM d, yyyy')}</td>
                    <td style={{ fontWeight: 500 }}>{e.description}</td>
                    <td>{e.category}</td>
                    <td>{e.subcategory}</td>
                    <td className={styles.amountCell}>{formatCurrency(e.amount)}</td>
                    <td>{e.payer}</td>
                    <td>
                      {e.expense_type === 'Goal' ? (
                        <Badge variant="accent">Goal</Badge>
                      ) : (
                        <span style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>Monthly</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        
        {/* Pagination */}
        {totalPages > 1 && (
          <div className={styles.pagination}>
            <div className={styles.pageInfo}>
              Showing {(page - 1) * PAGE_SIZE + 1} - {Math.min(page * PAGE_SIZE, filteredSorted.length)} of {filteredSorted.length}
            </div>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <Button variant="ghost" size="sm" disabled={page === 1} onClick={() => setPage(page - 1)}>
                Prev
              </Button>
              <Button variant="ghost" size="sm" disabled={page === totalPages} onClick={() => setPage(page + 1)}>
                Next
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Delete Confirmation Modal */}
      {showDeleteModal && (
        <div className={styles.modalOverlay}>
          <div className={styles.modalContent}>
            <h3 style={{ marginTop: 0 }}>Delete Expenses?</h3>
            <p style={{ color: 'var(--color-text-muted)', marginBottom: '1rem' }}>
              Are you sure you want to delete {selectedIds.size} expense{selectedIds.size > 1 ? 's' : ''}? This action cannot be undone.
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

export default Expenses;
