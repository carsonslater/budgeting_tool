import React, { useState, useMemo } from 'react';
import { format, subMonths, parseISO, startOfMonth, endOfMonth, parse } from 'date-fns';
import { ChevronDown, ChevronUp } from 'lucide-react';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts';

import { Card } from '../components/ui/Card';
import { Select } from '../components/ui/Select';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { useReportSummary, useCategoryBreakdown } from '../hooks/useReporting';
import { useExpenses } from '../hooks/useExpenses';
import styles from './Reporting.module.css';
import type { Expense } from '../types';

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(amount);
}

// Custom Tooltip for Recharts
const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className={styles.customTooltip}>
        <div className={styles.tooltipLabel}>{label}</div>
        {payload.map((entry: any, index: number) => (
          <div key={index} className={styles.tooltipValue} style={{ color: entry.color }}>
            {entry.name}: {formatCurrency(entry.value)}
          </div>
        ))}
      </div>
    );
  }
  return null;
};

export const Reporting: React.FC = () => {
  // Period Selection
  const [period, setPeriod] = useState<string>('current'); // 'current', 'all', or 'YYYY-MM'
  
  const monthOptions = useMemo(() => {
    const opts = [{ value: 'all', label: 'All Time' }];
    const now = new Date();
    for (let i = 0; i < 12; i++) {
      const d = subMonths(now, i);
      const val = format(d, 'yyyy-MM');
      const label = i === 0 ? 'Current Month' : format(d, 'MMMM yyyy');
      opts.push({ value: val, label });
    }
    return opts;
  }, []);

  const selectedMonth = period === 'all' ? undefined : (period === 'current' ? format(new Date(), 'yyyy-MM') : period);
  const start = selectedMonth ? format(startOfMonth(parse(selectedMonth, 'yyyy-MM', new Date())), 'yyyy-MM-dd') : undefined;
  const end = selectedMonth ? format(endOfMonth(parse(selectedMonth, 'yyyy-MM', new Date())), 'yyyy-MM-dd') : undefined;

  // Data fetching
  const { data: summary } = useReportSummary(selectedMonth);
  const { data: categoryBreakdown } = useCategoryBreakdown(start, end);
  const { data: allExpenses } = useExpenses();

  // Toggles & State
  const [trendPeriod, setTrendPeriod] = useState<'monthly' | 'weekly'>('monthly');
  const [trendType, setTrendType] = useState<'total' | 'category'>('total');
  const [txPage, setTxPage] = useState(1);
  const [txSortCol, setTxSortCol] = useState<keyof Expense>('date');
  const [txSortDesc, setTxSortDesc] = useState(true);

  // ── Section 1: Budget Performance ──
  const sortedSummary = useMemo(() => {
    if (!summary) return [];
    const list = [...summary];
    // Sort worst first: remaining ascending (most negative first)
    list.sort((a, b) => a.remaining - b.remaining);
    return list;
  }, [summary]);

  const totalBudget = sortedSummary.reduce((sum, s) => sum + s.budget, 0);
  const totalBudgetSpent = sortedSummary.reduce((sum, s) => sum + s.spent, 0);

  // ── Section 2: Goal Project Spending ──
  const goalSpending = useMemo(() => {
    if (!allExpenses) return [];
    let list = allExpenses.filter(e => e.expense_type === 'Goal');
    if (start && end) {
      list = list.filter(e => e.date >= start && e.date <= end);
    }
    const grouped = list.reduce((acc, e) => {
      // For goals, subcategory stores the goal name based on our mapping in Expenses form
      const goal = e.category === 'Goals' ? e.subcategory : (e.category || 'Unknown Goal');
      if (!acc[goal]) acc[goal] = { spent: 0, count: 0 };
      acc[goal].spent += e.amount;
      acc[goal].count += 1;
      return acc;
    }, {} as Record<string, { spent: number, count: number }>);
    
    return Object.entries(grouped)
      .map(([goal, data]) => ({ goal, ...data }))
      .sort((a, b) => b.spent - a.spent);
  }, [allExpenses, start, end]);

  // ── Section 3: Spending Trends (Computed locally for flexibility) ──
  const trendsData = useMemo(() => {
    if (!allExpenses) return { data: [], categories: [] };
    
    const list = allExpenses.filter(e => e.expense_type === 'Monthly');
    const categoriesSet = new Set<string>();

    const grouped = list.reduce((acc, e) => {
      const d = parseISO(e.date);
      let key = '';
      if (trendPeriod === 'monthly') {
        key = format(d, 'MMM yyyy');
      } else {
        // Simple week string
        const weekStart = new Date(d);
        weekStart.setDate(d.getDate() - d.getDay()); // Start of week (Sunday)
        key = format(weekStart, 'MMM d');
      }

      if (!acc[key]) acc[key] = { name: key, Total: 0 };
      
      acc[key].Total += e.amount;
      
      if (trendType === 'category') {
        const cat = e.category || 'Uncategorized';
        categoriesSet.add(cat);
        acc[key][cat] = (acc[key][cat] || 0) + e.amount;
      }
      
      return acc;
    }, {} as Record<string, any>);

    // Sort chronologically (assuming keys are chronological enough, or we should sort by Date)
    // To properly sort, we parse the keys back
    const sortedData = Object.values(grouped).sort((a, b) => {
      if (trendPeriod === 'monthly') {
        return parse(a.name, 'MMM yyyy', new Date()).getTime() - parse(b.name, 'MMM yyyy', new Date()).getTime();
      } else {
        return parse(a.name, 'MMM d', new Date()).getTime() - parse(b.name, 'MMM d', new Date()).getTime();
      }
    });

    return { data: sortedData, categories: Array.from(categoriesSet) };
  }, [allExpenses, trendPeriod, trendType]);

  const COLORS = ['#8A867F', '#4CAF79', '#E05252', '#3498db', '#9b59b6', '#f1c40f', '#e67e22', '#1abc9c'];

  // ── Section 4: Spending by Category ──
  const catChartData = useMemo(() => {
    if (!categoryBreakdown) return [];
    // Group by primary category
    const grouped = categoryBreakdown.reduce((acc, row) => {
      if (!acc[row.category]) acc[row.category] = 0;
      acc[row.category] += row.total;
      return acc;
    }, {} as Record<string, number>);

    return Object.entries(grouped)
      .map(([name, amount]) => ({ name, amount }))
      .sort((a, b) => b.amount - a.amount);
  }, [categoryBreakdown]);

  // ── Section 5: Transaction Detail ──
  const filteredTxs = useMemo(() => {
    if (!allExpenses) return [];
    let list = [...allExpenses];
    if (start && end) {
      list = list.filter(e => e.date >= start && e.date <= end);
    }
    list.sort((a, b) => {
      if (a[txSortCol] < b[txSortCol]) return txSortDesc ? 1 : -1;
      if (a[txSortCol] > b[txSortCol]) return txSortDesc ? -1 : 1;
      return 0;
    });
    return list;
  }, [allExpenses, start, end, txSortCol, txSortDesc]);

  const TX_PAGE_SIZE = 50;
  const txTotalPages = Math.max(1, Math.ceil(filteredTxs.length / TX_PAGE_SIZE));
  const pagedTxs = filteredTxs.slice((txPage - 1) * TX_PAGE_SIZE, txPage * TX_PAGE_SIZE);

  const handleTxSort = (col: keyof Expense) => {
    if (txSortCol === col) setTxSortDesc(!txSortDesc);
    else {
      setTxSortCol(col);
      setTxSortDesc(true);
    }
  };

  return (
    <div className={styles.container}>
      {/* Controls Bar */}
      <div className={styles.controlsBar}>
        <div className={styles.controlsLeft}>
          <div style={{ fontWeight: 600 }}>Reporting Period:</div>
          <Select
            value={period}
            onChange={(e) => { setPeriod(e.target.value); setTxPage(1); }}
            options={monthOptions}
            style={{ width: '200px' }}
          />
        </div>
      </div>

      {/* Section 1: Budget Performance */}
      <Card title="Budget Performance" padding="md">
        <div className={styles.tableContainer} style={{ maxHeight: '400px' }}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Category</th>
                <th>Subcategory</th>
                <th className={styles.amountCell}>Budget</th>
                <th className={styles.amountCell}>Spent</th>
                <th className={styles.amountCell}>Remaining</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {sortedSummary.length === 0 ? (
                <tr><td colSpan={6} style={{ textAlign: 'center', padding: '1rem' }}>No budget data for this period.</td></tr>
              ) : (
                sortedSummary.map((s, i) => (
                  <tr key={i} className={s.status === 'Over' ? styles.rowOver : ''}>
                    <td>{s.category}</td>
                    <td>{s.subcategory}</td>
                    <td className={styles.amountCell}>{formatCurrency(s.budget)}</td>
                    <td className={styles.amountCell}>{formatCurrency(s.spent)}</td>
                    <td className={`${styles.amountCell} ${s.remaining < 0 ? styles.rowOver : ''}`} style={{ color: s.remaining < 0 ? 'var(--color-danger)' : 'inherit' }}>
                      {formatCurrency(s.remaining)}
                    </td>
                    <td>
                      <Badge variant={s.status === 'Over' ? 'danger' : (s.status === 'On Track' ? 'accent' : 'muted')}>
                        {s.status}
                      </Badge>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
            {sortedSummary.length > 0 && (
              <tfoot>
                <tr style={{ background: 'var(--color-surface-raised)', fontWeight: 600 }}>
                  <td colSpan={2}>Total</td>
                  <td className={styles.amountCell}>{formatCurrency(totalBudget)}</td>
                  <td className={styles.amountCell}>{formatCurrency(totalBudgetSpent)}</td>
                  <td className={styles.amountCell} style={{ color: totalBudget - totalBudgetSpent < 0 ? 'var(--color-danger)' : 'var(--color-success)' }}>
                    {formatCurrency(totalBudget - totalBudgetSpent)}
                  </td>
                  <td></td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      </Card>

      <div className={styles.row}>
        {/* Section 3: Spending Trends */}
        <div className={styles.col2}>
          <Card padding="md">
            <div className={styles.chartHeader}>
              <h3 style={{ margin: 0, fontSize: '1.1rem' }}>Spending Trends</h3>
              <div className={styles.toggles}>
                <label className={styles.toggleLabel}>
                  <input type="radio" checked={trendPeriod === 'monthly'} onChange={() => setTrendPeriod('monthly')} /> Monthly
                </label>
                <label className={styles.toggleLabel}>
                  <input type="radio" checked={trendPeriod === 'weekly'} onChange={() => setTrendPeriod('weekly')} /> Weekly
                </label>
                <div style={{ width: '1px', background: 'var(--color-border)', margin: '0 0.5rem' }} />
                <label className={styles.toggleLabel}>
                  <input type="radio" checked={trendType === 'total'} onChange={() => setTrendType('total')} /> Total
                </label>
                <label className={styles.toggleLabel}>
                  <input type="radio" checked={trendType === 'category'} onChange={() => setTrendType('category')} /> By Category
                </label>
              </div>
            </div>
            
            <div className={styles.chartContainer}>
              <ResponsiveContainer width="100%" height="100%">
                {trendType === 'total' ? (
                  <LineChart data={trendsData.data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
                    <XAxis dataKey="name" stroke="var(--color-text-muted)" fontSize={12} tickLine={false} axisLine={false} />
                    <YAxis stroke="var(--color-text-muted)" fontSize={12} tickLine={false} axisLine={false} tickFormatter={(val) => `$${val}`} />
                    <Tooltip content={<CustomTooltip />} />
                    <Line type="monotone" dataKey="Total" stroke="var(--color-accent)" strokeWidth={3} dot={{ r: 4, fill: 'var(--color-surface)', strokeWidth: 2 }} activeDot={{ r: 6 }} animationDuration={1000} />
                  </LineChart>
                ) : (
                  <BarChart data={trendsData.data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
                    <XAxis dataKey="name" stroke="var(--color-text-muted)" fontSize={12} tickLine={false} axisLine={false} />
                    <YAxis stroke="var(--color-text-muted)" fontSize={12} tickLine={false} axisLine={false} tickFormatter={(val) => `$${val}`} />
                    <Tooltip content={<CustomTooltip />} />
                    <Legend iconType="circle" wrapperStyle={{ fontSize: '12px' }} />
                    {trendsData.categories.map((cat, idx) => (
                      <Bar key={cat} dataKey={cat} stackId="a" fill={idx === 0 ? 'var(--color-accent)' : COLORS[idx % COLORS.length]} animationDuration={1000} />
                    ))}
                  </BarChart>
                )}
              </ResponsiveContainer>
            </div>
          </Card>
        </div>

        {/* Section 4: Spending by Category */}
        <div className={styles.col1}>
          <Card padding="md">
            <div className={styles.chartHeader}>
              <h3 style={{ margin: 0, fontSize: '1.1rem' }}>Spending by Category</h3>
            </div>
            <div className={styles.chartContainer}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart layout="vertical" data={catChartData} margin={{ top: 5, right: 30, left: 40, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" horizontal={false} />
                  <XAxis type="number" stroke="var(--color-text-muted)" fontSize={12} tickLine={false} axisLine={false} tickFormatter={(val) => `$${val}`} />
                  <YAxis dataKey="name" type="category" stroke="var(--color-text-muted)" fontSize={12} tickLine={false} axisLine={false} width={80} />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar dataKey="amount" fill="var(--color-accent)" radius={[0, 4, 4, 0]} animationDuration={1000} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>
      </div>

      {/* Section 2: Goal Project Spending */}
      <Card title="Goal Project Spending" padding="md">
        <div className={styles.tableContainer}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Goal</th>
                <th className={styles.amountCell}>Total Spent</th>
                <th className={styles.amountCell} style={{ textAlign: 'center' }}># Transactions</th>
              </tr>
            </thead>
            <tbody>
              {goalSpending.length === 0 ? (
                <tr><td colSpan={3} style={{ textAlign: 'center', padding: '1rem' }}>No goal spending in this period.</td></tr>
              ) : (
                goalSpending.map((g, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 500 }}>{g.goal}</td>
                    <td className={styles.amountCell}>{formatCurrency(g.spent)}</td>
                    <td className={styles.amountCell} style={{ textAlign: 'center' }}>{g.count}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Section 5: Transaction Detail */}
      <Card title="Transaction Detail" padding="md">
        <div className={styles.tableContainer}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th onClick={() => handleTxSort('date')} style={{ cursor: 'pointer' }}>
                  Date {txSortCol === 'date' && (txSortDesc ? <ChevronDown size={14} style={{ verticalAlign: 'middle' }}/> : <ChevronUp size={14} style={{ verticalAlign: 'middle' }}/>)}
                </th>
                <th onClick={() => handleTxSort('description')} style={{ cursor: 'pointer' }}>
                  Description {txSortCol === 'description' && (txSortDesc ? <ChevronDown size={14} style={{ verticalAlign: 'middle' }}/> : <ChevronUp size={14} style={{ verticalAlign: 'middle' }}/>)}
                </th>
                <th onClick={() => handleTxSort('category')} style={{ cursor: 'pointer' }}>
                  Category {txSortCol === 'category' && (txSortDesc ? <ChevronDown size={14} style={{ verticalAlign: 'middle' }}/> : <ChevronUp size={14} style={{ verticalAlign: 'middle' }}/>)}
                </th>
                <th onClick={() => handleTxSort('subcategory')} style={{ cursor: 'pointer' }}>
                  Subcategory {txSortCol === 'subcategory' && (txSortDesc ? <ChevronDown size={14} style={{ verticalAlign: 'middle' }}/> : <ChevronUp size={14} style={{ verticalAlign: 'middle' }}/>)}
                </th>
                <th onClick={() => handleTxSort('amount')} className={styles.amountCell} style={{ cursor: 'pointer' }}>
                  Amount {txSortCol === 'amount' && (txSortDesc ? <ChevronDown size={14} style={{ verticalAlign: 'middle' }}/> : <ChevronUp size={14} style={{ verticalAlign: 'middle' }}/>)}
                </th>
                <th onClick={() => handleTxSort('expense_type')} style={{ cursor: 'pointer' }}>
                  Type {txSortCol === 'expense_type' && (txSortDesc ? <ChevronDown size={14} style={{ verticalAlign: 'middle' }}/> : <ChevronUp size={14} style={{ verticalAlign: 'middle' }}/>)}
                </th>
              </tr>
            </thead>
            <tbody>
              {pagedTxs.length === 0 ? (
                <tr><td colSpan={6} style={{ textAlign: 'center', padding: '2rem' }}>No transactions found.</td></tr>
              ) : (
                pagedTxs.map(t => (
                  <tr key={t.id}>
                    <td>{format(parseISO(t.date), 'MMM d, yyyy')}</td>
                    <td style={{ fontWeight: 500 }}>{t.description}</td>
                    <td>{t.category}</td>
                    <td>{t.subcategory}</td>
                    <td className={styles.amountCell}>{formatCurrency(t.amount)}</td>
                    <td>
                      {t.expense_type === 'Goal' ? <Badge variant="accent">Goal</Badge> : <span style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>Monthly</span>}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
          {txTotalPages > 1 && (
            <div className={styles.pagination}>
              <div className={styles.pageInfo}>
                Showing {(txPage - 1) * TX_PAGE_SIZE + 1} - {Math.min(txPage * TX_PAGE_SIZE, filteredTxs.length)} of {filteredTxs.length}
              </div>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <Button variant="ghost" size="sm" disabled={txPage === 1} onClick={() => setTxPage(txPage - 1)}>Prev</Button>
                <Button variant="ghost" size="sm" disabled={txPage === txTotalPages} onClick={() => setTxPage(txPage + 1)}>Next</Button>
              </div>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
};

export default Reporting;
