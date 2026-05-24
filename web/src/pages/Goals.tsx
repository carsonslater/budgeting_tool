import React, { useState, useMemo } from 'react';
import { format, parseISO, startOfMonth, endOfMonth, addMonths } from 'date-fns';
import { Check, X, Target, ChevronDown, ChevronRight } from 'lucide-react';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { useCategories } from '../hooks/useExpenses';
import { useGoals, useGoalLinks, useGoalActions } from '../hooks/useGoals';
import { useExpenses } from '../hooks/useExpenses';
import { useIncome } from '../hooks/useIncome';
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
  const { data: allExpenses } = useExpenses();
  const { data: incomeData } = useIncome();
  const { data: categories } = useCategories();
  const { create, update, remove, createLink, removeLink } = useGoalActions();

  // Goal Form
  const nextMonth = startOfMonth(addMonths(new Date(), 1));
  const [name, setName] = useState('');
  const [targetAmount, setTargetAmount] = useState('');
  const [targetMonth, setTargetMonth] = useState(format(nextMonth, 'yyyy-MM-dd'));

  // UI State
  const [showCompleted, setShowCompleted] = useState(false);
  const [expandedGoalId, setExpandedGoalId] = useState<number | null>(null);
  const [deleteGoalId, setDeleteGoalId] = useState<number | null>(null);

  // Link Form
  const [linkCategory, setLinkCategory] = useState('');
  const [linkSubcategory, setLinkSubcategory] = useState('');
  const [linkStart, setLinkStart] = useState('');
  const [linkEnd, setLinkEnd] = useState('');

  const handleCreateGoal = (e: React.FormEvent) => {
    e.preventDefault();
    create.mutate({
      name,
      target_amount: parseFloat(targetAmount) || 0,
      target_month: targetMonth,
      completed: 0,
      created_date: format(new Date(), 'yyyy-MM-dd')
    }, {
      onSuccess: () => {
        setName('');
        setTargetAmount('');
        setTargetMonth(format(nextMonth, 'yyyy-MM-dd'));
      }
    });
  };

  const handleComplete = (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    update.mutate({ id, data: { completed: 1 } });
  };

  const handleDelete = async () => {
    if (deleteGoalId !== null) {
      await remove.mutateAsync(deleteGoalId);
      setDeleteGoalId(null);
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

  // Derivations
  const { activeGoals, completedGoals, monthlyGoalSpending } = useMemo(() => {
    if (!goals) return { activeGoals: [], completedGoals: [], monthlyGoalSpending: 0 };

    const now = new Date();
    const currentStart = format(startOfMonth(now), 'yyyy-MM-dd');
    const currentEnd = format(endOfMonth(now), 'yyyy-MM-dd');

    let monthAllocated = 0;
    allExpenses?.forEach(e => {
      if (e.expense_type === 'Goal' && e.date >= currentStart && e.date <= currentEnd) {
        monthAllocated += e.amount;
      }
    });

    const mapped = goals.map(g => {
      const links = goalLinks?.filter(l => l.goal_name === g.name) || [];
      const saved = allExpenses?.reduce((sum, e) => {
        const matchesLink = links.some(l => 
          l.category === e.category && 
          l.subcategory === e.subcategory && 
          (!l.start_date || e.date >= l.start_date) &&
          (!l.end_date || e.date <= l.end_date)
        );
        if (matchesLink) return sum + e.amount;
        return sum;
      }, 0) || 0;

      return { ...g, saved, links };
    });

    return {
      activeGoals: mapped.filter(g => g.completed === 0),
      completedGoals: mapped.filter(g => g.completed === 1),
      monthlyGoalSpending: monthAllocated,
    };
  }, [goals, goalLinks, allExpenses]);

  const totalIncome = typeof incomeData === 'number' ? incomeData : 0;
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
              value={targetMonth.substring(0, 7)}
              onChange={(e) => setTargetMonth(`${e.target.value}-01`)}
              required
            />
            <Button type="submit" loading={create.isPending}>Save Goal</Button>
          </form>

          <div className={styles.summaryBox}>
            <div className={styles.summaryTitle}>Monthly Allocation Summary</div>
            <div className={styles.summaryValue}>{formatCurrency(monthlyGoalSpending)}</div>
            <div className={styles.summarySubtext}>
              {pctIncomeAllocated}% of {formatCurrency(totalIncome)} income
            </div>
          </div>
        </Card>
      </div>

      {/* Main Area */}
      <div className={styles.mainArea}>
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
                      <Button variant="ghost" size="sm" onClick={(e) => handleComplete(g.id, e)} style={{ color: 'var(--color-success)' }}>
                        <Check size={16} style={{ marginRight: 4 }} /> Complete
                      </Button>
                      <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); setDeleteGoalId(g.id); }} style={{ color: 'var(--color-danger)' }}>
                        <X size={16} />
                      </Button>
                    </div>
                  </div>

                  <div className={styles.goalStats}>
                    <b>{formatCurrency(g.saved)}</b> spent of {formatCurrency(g.target_amount)} target
                  </div>

                  <div className={styles.progressWrapper}>
                    <div className={styles.progressBarContainer}>
                      <div className={styles.progressBarFill} style={{ width: `${pct}%` }} />
                    </div>
                    <div className={styles.progressText}>{pct.toFixed(0)}%</div>
                  </div>

                  <div className={styles.goalMeta}>
                    Due: {format(parseISO(g.target_month), 'MMMM yyyy')}
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
                    <Card key={g.id} padding="lg">
                      <div className={styles.goalHeader}>
                        <div className={styles.goalTitle}>
                          {g.name}
                          <Badge variant="muted">Completed</Badge>
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

      {/* Delete Modal */}
      {deleteGoalId && (
        <div className={styles.modalOverlay}>
          <div className={styles.modalContent}>
            <h3 style={{ marginTop: 0 }}>Delete Goal?</h3>
            <p style={{ color: 'var(--color-text-muted)', marginBottom: '1rem' }}>
              Are you sure you want to delete this goal? Linked expenses will remain in the database.
            </p>
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
