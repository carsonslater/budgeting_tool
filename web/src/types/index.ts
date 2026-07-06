/**
 * types/index.ts — Shared TypeScript interfaces mirroring the FastAPI response shapes.
 */

// ── Expenses ──────────────────────────────────────────────────────────────────

export interface Expense {
  id: number;
  date: string;              // ISO YYYY-MM-DD
  description: string;
  category: string;
  subcategory: string;
  amount: number;
  payer: string;
  expense_type: 'Monthly' | 'Goal';
}

export interface ExpenseFilters {
  start?: string;
  end?: string;
  category?: string;
  payer?: string;
}

export type ExpenseCreate = Omit<Expense, 'id'>;
export type ExpenseUpdate = Partial<Omit<Expense, 'id'>>;

// ── Budgets ───────────────────────────────────────────────────────────────────

export interface Budget {
  id: number;
  category: string;
  subcategory: string;
  limit_amount: number;
  frequency: 'Monthly' | 'Quarterly' | 'Bi-annually' | 'Annually';
  effective_date: string;    // ISO YYYY-MM-DD
  conclusion_date: string | null;
}

export type BudgetCreate = Omit<Budget, 'id'>;
export type BudgetUpdate = Partial<Omit<Budget, 'id'>>;

export interface BudgetDraft {
  id: number;
  target_month: string;
  category: string;
  subcategory: string;
  limit_amount: number;
  frequency: 'Monthly' | 'Quarterly' | 'Bi-annually' | 'Annually';
}

export type BudgetDraftCreate = Omit<BudgetDraft, 'id'>;
export type BudgetDraftUpdate = Partial<Omit<BudgetDraft, 'id' | 'target_month'>>;

export interface SuggestedBudget {
  budget_id: number;
  category: string;
  subcategory: string;
  current_limit: number;
  current_monthly_equiv: number;
  frequency: string;
  hasty: number;
  conservative: number;
  recent_month_spent: number;
}

// ── Income ────────────────────────────────────────────────────────────────────

export interface IncomeTotal {
  total: number;
}

// ── Goals ─────────────────────────────────────────────────────────────────────

export interface Goal {
  id: number;
  name: string;
  target_amount: number;
  target_month: string;      // ISO YYYY-MM-DD (first of month)
  created_date: string;
  completed: 0 | 1;
}

export type GoalCreate = Omit<Goal, 'id'>;
export type GoalUpdate = Partial<Omit<Goal, 'id'>>;

export interface GoalLink {
  id: number;
  goal_name: string;
  category: string;
  subcategory: string;
  start_date: string;
  end_date: string | null;
}

export type GoalLinkCreate = Omit<GoalLink, 'id'>;

// ── Reporting ─────────────────────────────────────────────────────────────────

/** One row from GET /api/reporting/summary */
export interface ReportSummary {
  budget_id: number;
  category: string;
  subcategory: string;
  budget: number;
  spent: number;
  remaining: number;
  status: 'Over' | 'On Track' | 'Under' | 'No Budget';
  frequency: string;
}

/** One point from GET /api/reporting/trends */
export interface TrendPoint {
  period: string;   // "YYYY-MM" or "YYYY-Www"
  total: number;
}

/** One row from GET /api/reporting/categories */
export interface CategoryTotal {
  category: string;
  subcategory: string;
  total: number;
  transaction_count: number;
}

// ── CSV Import ────────────────────────────────────────────────────────────────

export interface StagedRow {
  original_index: number | null;
  date: string;
  description: string;
  amount: number;
  category: string;
  subcategory: string;
  payer: string;
  expense_type: 'Monthly' | 'Goal';
  is_duplicate: boolean;
}

export interface ImportResult {
  imported: number;
  skipped: number;
}
