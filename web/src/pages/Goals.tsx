import React, { useState, useMemo } from 'react';
import { format, parseISO, startOfMonth, addMonths } from 'date-fns';
import { Check, X, Target, ChevronDown, ChevronRight } from 'lucide-react';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { useCategories, useSubcategories } from '../hooks/useExpenses';
import { useGoals, useGoalLinks, useGoalActions } from '../hooks/useGoals';
import { SweepPanel } from '../components/sweeps/SweepPanel';
import { useMonthPlan } from '../hooks/useMonthPlans';
import styles from './Goals.module.css';

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(amount);
}

export const Goals: React.FC = () => {
  const { data: goals, isLoading: loadingGoals } = useGoals();
  const { data: goalLinks } = useGoalLinks();
  const { data: plan } = useMonthPlan(format(new Date(), 'yyyy-MM'));
  const { data: categories } = useCategories();
  const { create, update, remove, createLink, removeLink, withdraw } = useGoalActions();

  // Goal Form
  const nextMonth = startOfMonth(addMonths(new Date(), 1));
  const [name, setName] = useState('');
  const [targetAmount, setTargetAmount] = useState('');
  const [targetMonth, setTargetMonth] = useState(format(nextMonth, 'yyyy-MM'));
  const [categoryInput, setCategoryInput] = useState('');
  const [subcategoryInput, setSubcategoryInput] = useState('');

  // UI State
  const [showCompleted, setShowCompleted] = useState(false);
  const [expandedGoalId, setExpandedGoalId] = useState<number | null>(null);
  const [deleteGoalId, setDeleteGoalId] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Withdrawal
  const [withdrawGoalId, setWithdrawGoalId] = useState<number | null>(null);
  const [withdrawAmount, setWithdrawAmount] = useState('');
  const [withdrawError, setWithdrawError] = useState<string | null>(null);

  // Link Form
  const [linkCategory, setLinkCategory] = useState('');
  const [linkSubcategory, setLinkSubcategory] = useState('');
  const [linkStart, setLinkStart] = useState('');
  const [linkEnd, setLinkEnd] = useState('');

  // Queries
  const { data: subcategories } = useSubcategories(categoryInput);

  // Robust date normalization helper to ensure we store clean YYYY-MM-01 format
  const normalizeTargetMonth = (val: string): string => {
    if (!val) {
      return format(new Date(), 'yyyy-MM-01');
    }
    const parts = val.split('-').filter(Boolean);
    if (parts.length >= 2) {
      const year = parts[0];
      const month = parts[1].padStart(2, '0');
      return `${year}-${month}-01`;
    }
    return val;
  };

  const handleCreateGoal = (e: React.FormEvent) => {
    e.preventDefault();
    create.mutate({
      name,
      target_amount: parseFloat(targetAmount) || 0,
      target_month: normalizeTargetMonth(targetMonth),
      completed: 0,
      created_date: format(new Date(), 'yyyy-MM-dd'),
      category: categoryInput || undefined,
      subcategory: subcategoryInput || undefined
    }, {
      onSuccess: () => {
        setName('');
        setTargetAmount('');
        setTargetMonth(format(nextMonth, 'yyyy-MM'));
        setCategoryInput('');
        setSubcategoryInput('');
      }
    });
  };

  const handleComplete = (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    update.mutate({ id, data: { completed: 1 } });
  };

  const handleDelete = async () => {
    if (deleteGoalId === null) return;
    setDeleteError(null);
    try {
      await remove.mutateAsync(deleteGoalId);
      setDeleteGoalId(null);
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : 'Delete failed');
    }
  };

  const handleWithdraw = async (goalId: number) => {
    setWithdrawError(null);
    try {
      await withdraw.mutateAsync({ id: goalId, amount: parseFloat(withdrawAmount) });
      setWithdrawGoalId(null);
      setWithdrawAmount('');
    } catch (err) {
      setWithdrawError(err instanceof Error ? err.message : 'Withdrawal failed');
    }
  };

  const handleCreateLink = (goalName: string) => {
    createLink.mutate({
      goal_name: goalName,
      category: linkCategory,
      subcategory: linkSubcategory,
      start_date: linkStart || format(startOfMonth(new Date()), 'yyyy-MM-dd'),
      end_date: linkEnd || null,
    }, {
      onSuccess: () => {
        setLinkCategory('');
        setLinkSubcategory('');
        setLinkStart('');
        setLinkEnd('');
      }
    });
  };

  // Derivations: saved amounts come from the goal ledger, not from expenses.
  const { activeGoals, completedGoals, monthlyGoalSpending } = useMemo(() => {
    if (!goals) return { activeGoals: [], completedGoals: [], monthlyGoalSpending: 0 };

    const mapped = goals.map(g => {
      const links = goalLinks?.filter(l => l.goal_name === g.name) || [];
      return { ...g, saved: g.balance ?? 0, links };
    });

    const monthSwept = goals.reduce((sum, g) => sum + (g.contributed_this_month ?? 0), 0);

    return {
      activeGoals: mapped.filter(g => g.completed === 0),
      completedGoals: mapped.filter(g => g.completed === 1),
      monthlyGoalSpending: monthSwept,
    };
  }, [goals, goalLinks]);

  const totalIncome = plan?.expected_income ?? 0;
  const pctIncomeAllocated = totalIncome ? Math.round((monthlyGoalSpending / totalIncome) * 100) : 0;

  return (
    <div className={styles.container}>
      {/* Sidebar Form */}
      <div className={styles.sidebar}>
        <Card title="New Goal" padding="lg">
          <form onSubmit={handleCreateGoal} className={styles.formCard}>
            <Input
              label="Goal Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
            <Input
              label="Target Amount"
              type="number"
              step="0.01"
              value={targetAmount}
              onChange={(e) => setTargetAmount(e.target.value)}
              required
            />
            <Input
              label="Target Month"
              type="month"
              value={targetMonth}
              onChange={(e) => setTargetMonth(e.target.value)}
              required
            />
            <Input
              label="Category (Optional)"
              list="cat-list"
              value={categoryInput}
              onChange={(e) => setCategoryInput(e.target.value)}
              placeholder="e.g. Auto, Gifts, Travel"
            />
            <Input
              label="Subcategory (Optional)"
              list="goal-subcat-list"
              value={subcategoryInput}
              onChange={(e) => setSubcategoryInput(e.target.value)}
              placeholder="e.g. Maintenance, Baby Shower"
            />
            <Button type="submit" loading={create.isPending}>Save Goal</Button>
          </form>

          <div className={styles.summaryBox}>
            <div className={styles.summaryTitle}>Swept to goals this month</div>
            <div className={styles.summaryValue}>{formatCurrency(monthlyGoalSpending)}</div>
            <div className={styles.summarySubtext}>
              {pctIncomeAllocated}% of {formatCurrency(totalIncome)} income
            </div>
          </div>
        </Card>
      </div>

      {/* Main Area */}
      <div className={styles.mainArea}>
        <SweepPanel />

        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>Active Goals</h2>
        </div>

        {loadingGoals ? (
          <div style={{ color: 'var(--color-text-muted)' }}>Loading goals...</div>
        ) : activeGoals.length === 0 ? (
          <div style={{ color: 'var(--color-text-muted)' }}>No active goals.</div>
        ) : (
          <div className={styles.goalList}>
            {activeGoals.map(g => {
              const pct = Math.min((g.saved / g.target_amount) * 100, 100);
              const isExpanded = expandedGoalId === g.id;

              return (
                <Card
                  key={g.id}
                  padding="lg"
                  className={`${styles.goalCard} ${isExpanded ? styles.goalCardExpanded : ''}`}
                >
                  <div className={styles.goalHeader}>
                    <div className={styles.goalTitle} onClick={() => setExpandedGoalId(isExpanded ? null : g.id)}>
                      <Target size={20} color="var(--color-accent)" />
                      {g.name}
                    </div>
                    <div className={styles.goalActions}>
                      <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); setWithdrawError(null); setWithdrawGoalId(withdrawGoalId === g.id ? null : g.id); }}>
                        Withdraw
                      </Button>
                      <Button variant="ghost" size="sm" onClick={(e) => handleComplete(g.id, e)} style={{ color: 'var(--color-success)' }}>
                        <Check size={16} style={{ marginRight: 4 }} /> Complete
                      </Button>
                      <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); setDeleteGoalId(g.id); }} style={{ color: 'var(--color-danger)' }}>
                        <X size={16} />
                      </Button>
                    </div>
                  </div>

                  <div className={styles.goalStats}>
                    <b>{formatCurrency(g.saved)}</b> saved of {formatCurrency(g.target_amount)} target
                    {g.needs_per_month != null && g.needs_per_month > 0 && (
                      <> &middot; needs {formatCurrency(g.needs_per_month)}/month</>
                    )}
                  </div>

                  {withdrawGoalId === g.id && (
                    <div className={styles.linksForm}>
                      <Input
                        label="Withdraw amount"
                        type="number"
                        step="0.01"
                        min="0"
                        value={withdrawAmount}
                        onChange={e => setWithdrawAmount(e.target.value)}
                      />
                      <div className={styles.linkButtonWrapper}>
                        <Button size="sm" loading={withdraw.isPending} onClick={() => handleWithdraw(g.id)}>
                          Confirm withdrawal
                        </Button>
                      </div>
                      {withdrawError && (
                        <div style={{ color: 'var(--color-danger)', fontSize: '0.85rem' }}>{withdrawError}</div>
                      )}
                    </div>
                  )}

                  <div className={styles.progressWrapper}>
                    <div className={styles.progressBarContainer}>
                      <div className={styles.progressBarFill} style={{ width: `${pct}%` }} />
                    </div>
                    <div className={styles.progressText}>{pct.toFixed(0)}%</div>
                  </div>

                  <div className={styles.goalMeta}>
                    Due: {(() => {
                      try {
                        const parsed = parseISO(g.target_month);
                        if (isNaN(parsed.getTime())) {
                          return g.target_month;
                        }
                        return format(parsed, 'MMMM yyyy');
                      } catch {
                        return g.target_month;
                      }
                    })()}
                  </div>

                  <div className={styles.linkChips}>
                    <span style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>Linked:</span>
                    {g.links.length === 0 && <span style={{ fontSize: '0.85rem' }}>None</span>}
                    {g.links.map(l => (
                      <div key={l.id} className={styles.chip}>
                        {l.category} {l.subcategory ? `> ${l.subcategory}` : ''}
                        <X
                          size={14}
                          className={styles.chipRemove}
                          onClick={(e) => { e.stopPropagation(); removeLink.mutate(l.id); }}
                        />
                      </div>
                    ))}
                  </div>

                  {/* Expanded Links Form */}
                  {isExpanded && (
                    <div className={styles.linksEditor}>
                      <div className={styles.linksTitle}>Add Budget Link</div>
                      <div className={styles.linksForm}>
                        <Input
                          label="Category"
                          list="cat-list"
                          value={linkCategory}
                          onChange={e => setLinkCategory(e.target.value)}
                        />
                        <Input
                          label="Subcategory"
                          value={linkSubcategory}
                          onChange={e => setLinkSubcategory(e.target.value)}
                        />
                        <Input
                          label="Start Date"
                          type="date"
                          value={linkStart}
                          onChange={e => setLinkStart(e.target.value)}
                        />
                        <Input
                          label="End Date (Optional)"
                          type="date"
                          value={linkEnd}
                          onChange={e => setLinkEnd(e.target.value)}
                        />
                        <div className={styles.linkButtonWrapper}>
                          <Button
                            size="sm"
                            disabled={!linkCategory}
                            loading={createLink.isPending}
                            onClick={() => handleCreateLink(g.name)}
                          >
                            Link Category
                          </Button>
                        </div>
                      </div>
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        )}

        {/* Completed Goals */}
        {completedGoals.length > 0 && (
          <div style={{ marginTop: '1rem' }}>
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle} onClick={() => setShowCompleted(!showCompleted)}>
                {showCompleted ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
                Completed Goals ({completedGoals.length})
              </h2>
            </div>

            {showCompleted && (
              <div className={styles.goalList} style={{ marginTop: '0.5rem', opacity: 0.8 }}>
                {completedGoals.map(g => {
                  const pct = Math.min((g.saved / g.target_amount) * 100, 100);
                  return (
                    <Card key={g.id} padding="lg" className={styles.goalCard}>
                      <div className={styles.goalHeader}>
                        <div className={styles.goalTitle}>
                          {g.name}
                          <Badge variant="muted">Completed</Badge>
                        </div>
                        <div className={styles.goalActions}>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(e) => { e.stopPropagation(); setDeleteGoalId(g.id); }}
                            style={{ color: 'var(--color-danger)' }}
                          >
                            <X size={16} />
                          </Button>
                        </div>
                      </div>
                      <div className={styles.goalStats}>
                        <b>{formatCurrency(g.saved)}</b> spent of {formatCurrency(g.target_amount)} target
                      </div>
                      <div className={styles.progressWrapper}>
                        <div className={styles.progressBarContainer}>
                          <div className={styles.progressBarFill} style={{ width: `${pct}%`, backgroundColor: 'var(--color-success)' }} />
                        </div>
                        <div className={styles.progressText}>{pct.toFixed(0)}%</div>
                      </div>
                    </Card>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      <datalist id="cat-list">
        {categories?.map(c => <option key={c} value={c} />)}
      </datalist>

      <datalist id="goal-subcat-list">
        {subcategories?.map(s => <option key={s} value={s} />)}
      </datalist>

      {/* Delete Modal */}
      {deleteGoalId && (
        <div className={styles.modalOverlay}>
          <div className={styles.modalContent}>
            <h3 style={{ marginTop: 0 }}>Delete Goal?</h3>
            <p style={{ color: 'var(--color-text-muted)', marginBottom: '1rem' }}>
              Are you sure you want to delete this goal? A goal with sweep or withdrawal history
              cannot be deleted; mark it complete instead.
            </p>
            {deleteError && (
              <p style={{ color: 'var(--color-danger)', marginBottom: '1rem' }}>{deleteError}</p>
            )}
            <div className={styles.modalActions}>
              <Button variant="ghost" onClick={() => setDeleteGoalId(null)}>Cancel</Button>
              <Button variant="danger" loading={remove.isPending} onClick={handleDelete}>
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Goals;
