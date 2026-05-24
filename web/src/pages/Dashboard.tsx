import React, { useMemo } from 'react';
import { startOfMonth, endOfMonth, subMonths, format, parseISO } from 'date-fns';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { useExpenses } from '../hooks/useExpenses';
import { useBudgets } from '../hooks/useBudgets';
import { useIncome } from '../hooks/useIncome';
import { useGoals, useGoalLinks } from '../hooks/useGoals';
import { useCountUp } from '../hooks/useCountUp';
import styles from './Dashboard.module.css';
import type { Budget } from '../types';

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(amount);
}

function getMonthlyLimit(b: Budget) {
  switch (b.frequency) {
    case 'Quarterly': return b.limit_amount / 3;
    case 'Bi-annually': return b.limit_amount / 6;
    case 'Annually': return b.limit_amount / 12;
    default: return b.limit_amount;
  }
}

export const Dashboard: React.FC = () => {
  const { data: allExpenses, isLoading: loadingExpenses } = useExpenses();
  const { data: incomeData, isLoading: loadingIncome } = useIncome();
  const { data: budgets, isLoading: loadingBudgets } = useBudgets();
  const { data: goals, isLoading: loadingGoals } = useGoals();
  const { data: goalLinks, isLoading: loadingLinks } = useGoalLinks();

  const isLoading = loadingExpenses || loadingIncome || loadingBudgets || loadingGoals || loadingLinks;

  const {
    totalSpentThisMonth,
    totalSpentLastMonth,
    totalIncome,
    netIncome,
    pctChange,
    spendPct,
    budgetHealth,
    overCount,
    onTrackCount,
    underCount,
    recentExpenses,
    goalsProgress
  } = useMemo(() => {
    if (isLoading) return {} as any;

    const now = new Date();
    const currentMonthStart = format(startOfMonth(now), 'yyyy-MM-dd');
    const currentMonthEnd = format(endOfMonth(now), 'yyyy-MM-dd');

    const lastMonthStart = format(startOfMonth(subMonths(now, 1)), 'yyyy-MM-dd');
    const lastMonthEnd = format(endOfMonth(subMonths(now, 1)), 'yyyy-MM-dd');

    const expensesThisMonth = allExpenses?.filter(e => e.date >= currentMonthStart && e.date <= currentMonthEnd) || [];
    const expensesLastMonth = allExpenses?.filter(e => e.date >= lastMonthStart && e.date <= lastMonthEnd) || [];

    const spentThis = expensesThisMonth.reduce((sum, e) => sum + e.amount, 0);
    const spentLast = expensesLastMonth.reduce((sum, e) => sum + e.amount, 0);

    const income = typeof incomeData === 'number' ? incomeData : 0;
    const net = income - spentThis;
    const pct = spentLast === 0 ? 0 : ((spentThis - spentLast) / spentLast) * 100;
    const arcPct = income === 0 ? 0 : Math.min(spentThis / income, 1);

    // Budget Health
    const categorySpending = expensesThisMonth.reduce((acc, exp) => {
      const key = `${exp.category}|${exp.subcategory}`;
      acc[key] = (acc[key] || 0) + exp.amount;
      return acc;
    }, {} as Record<string, number>);

    const health = budgets?.map((b: Budget) => {
      const spent = categorySpending[`${b.category}|${b.subcategory}`] || 0;
      const limit = getMonthlyLimit(b);
      let status: 'Over' | 'On Track' | 'Under' = 'Under';
      if (spent > limit) status = 'Over';
      else if (spent >= limit * 0.85) status = 'On Track';
      
      return { ...b, spent, limit, status };
    }) || [];

    // Sort: Over first, then On Track, then Under
    health.sort((a, b) => {
      const rank = { 'Over': 0, 'On Track': 1, 'Under': 2 };
      if (rank[a.status] !== rank[b.status]) return rank[a.status] - rank[b.status];
      return (b.spent / b.limit) - (a.spent / a.limit); // desc by % spent
    });

    const oCount = health.filter(b => b.status === 'Over').length;
    const tCount = health.filter(b => b.status === 'On Track').length;
    const uCount = health.filter(b => b.status === 'Under').length;

    // Recent Expenses
    const recent = [...(allExpenses || [])]
      .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime() || b.id - a.id)
      .slice(0, 5);

    // Goals Progress
    const gProgress = goals?.filter(g => g.completed === 0).map(g => {
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
      return { ...g, saved };
    }) || [];

    return {
      totalSpentThisMonth: spentThis,
      totalSpentLastMonth: spentLast,
      totalIncome: income,
      netIncome: net,
      pctChange: pct,
      spendPct: arcPct,
      budgetHealth: health,
      overCount: oCount,
      onTrackCount: tCount,
      underCount: uCount,
      recentExpenses: recent,
      goalsProgress: gProgress
    };
  }, [allExpenses, incomeData, budgets, goals, goalLinks, isLoading]);

  const animatedSpent = useCountUp(totalSpentThisMonth || 0, 1000);
  const animatedIncome = useCountUp(totalIncome || 0, 1000);
  const animatedNet = useCountUp(Math.abs(netIncome || 0), 1000);

  if (isLoading) {
    return (
      <div className={styles.container}>
        <Card>
          <div className={`${styles.skeleton} ${styles.skeletonArc}`} style={{ margin: '0 auto' }} />
        </Card>
        <div className={styles.statsRow}>
          <Card><div className={`${styles.skeleton} ${styles.skeletonAmount}`} /></Card>
          <Card><div className={`${styles.skeleton} ${styles.skeletonAmount}`} /></Card>
          <Card><div className={`${styles.skeleton} ${styles.skeletonAmount}`} /></Card>
        </div>
      </div>
    );
  }

  const arcRadius = 100;
  const arcLength = Math.PI * arcRadius;
  const arcOffset = arcLength * (1 - (spendPct || 0));

  return (
    <div className={styles.container}>
      {/* Row 1: Hero */}
      <Card>
        <div className={styles.heroContent}>
          <div className={styles.arcContainer}>
            <svg className={styles.arcSvg} viewBox="0 0 250 125">
              <path className={styles.arcBackground} d="M 25 125 A 100 100 0 0 1 225 125" />
              <path 
                className={`${styles.arcForeground} ${spendPct >= 1 ? styles.over : ''}`} 
                d="M 25 125 A 100 100 0 0 1 225 125" 
                style={{ strokeDasharray: arcLength, strokeDashoffset: arcOffset }}
              />
            </svg>
            <div className={styles.heroAmount}>{formatCurrency(animatedSpent)}</div>
          </div>
          <div className={styles.heroLabel}>Total Spent This Month</div>
        </div>
      </Card>

      {/* Row 2: Stat Cards */}
      <div className={styles.statsRow}>
        <Card hoverable padding="lg">
          <div className={styles.heroLabel}>Monthly Income</div>
          <div className={styles.statValue}>{formatCurrency(animatedIncome)}</div>
        </Card>
        
        <Card hoverable padding="lg">
          <div className={styles.heroLabel}>Net (Income - Spend)</div>
          <div className={`${styles.statValue} ${netIncome >= 0 ? styles.success : styles.danger}`}>
            {netIncome < 0 ? '-' : ''}{formatCurrency(animatedNet)}
          </div>
        </Card>

        <Card hoverable padding="lg">
          <div className={styles.heroLabel}>vs Last Month</div>
          <div className={`${styles.statValue} ${pctChange > 0 ? styles.danger : styles.success}`}>
            {pctChange > 0 ? '+' : ''}{pctChange.toFixed(1)}%
          </div>
          <div className={styles.statSubtitle}>Spent {formatCurrency(totalSpentLastMonth)} last month</div>
        </Card>
      </div>

      {/* Row 3: Budget Health & Recent Expenses */}
      <div className={styles.columnsRow}>
        {/* Left: Budget Health */}
        <Card title="Budget Health" subtitle={`${overCount} Over / ${onTrackCount} On Track / ${underCount} Under`} hoverable>
          {budgetHealth.length === 0 ? (
            <div className={styles.emptyState}>No budgets defined.</div>
          ) : (
            <table className={styles.budgetTable}>
              <thead>
                <tr>
                  <th>Category</th>
                  <th className={styles.amountCell}>Spent</th>
                  <th className={styles.amountCell}>Limit</th>
                  <th className={styles.badgeCell}>Status</th>
                </tr>
              </thead>
              <tbody>
                {budgetHealth.map((b: any) => (
                  <tr key={b.id}>
                    <td>
                      <div>{b.category}</div>
                      <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>{b.subcategory}</div>
                    </td>
                    <td className={styles.amountCell}>{formatCurrency(b.spent)}</td>
                    <td className={styles.amountCell}>{formatCurrency(b.limit)}</td>
                    <td className={styles.badgeCell}>
                      <Badge variant={b.status === 'Over' ? 'danger' : b.status === 'On Track' ? 'accent' : 'muted'}>
                        {b.status}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        {/* Right: Recent Expenses */}
        <Card title="Recent Expenses" hoverable>
          {recentExpenses.length === 0 ? (
            <div className={styles.emptyState}>No recent expenses.</div>
          ) : (
            <div className={styles.expenseList}>
              {recentExpenses.map((e: any) => (
                <div key={e.id} className={styles.expenseItem}>
                  <div>
                    <div className={styles.expenseDesc}>{e.description || 'Unknown'}</div>
                    <div className={styles.expenseMeta}>
                      {format(parseISO(e.date), 'MMM d, yyyy')} • {e.category}
                    </div>
                  </div>
                  <div className={styles.expenseAmount}>{formatCurrency(e.amount)}</div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Row 4: Goals Progress */}
      {goalsProgress.length > 0 && (
        <div className={styles.goalsRow}>
          {goalsProgress.map((g: any) => {
            const pct = Math.min((g.saved / g.target_amount) * 100, 100);
            return (
              <Card key={g.id} padding="lg" hoverable>
                <div className={styles.goalCard}>
                  <div className={styles.goalHeader}>
                    <div className={styles.goalName}>{g.name}</div>
                    <div className={styles.goalTarget}>{formatCurrency(g.target_amount)}</div>
                  </div>
                  <div className={styles.progressBarContainer}>
                    <div 
                      className={`${styles.progressBarFill} ${pct >= 100 ? styles.complete : ''}`} 
                      style={{ width: `${pct}%` }} 
                    />
                  </div>
                  <div className={styles.goalMeta}>
                    <span>{formatCurrency(g.saved)} saved</span>
                    <span>{pct.toFixed(0)}%</span>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default Dashboard;
