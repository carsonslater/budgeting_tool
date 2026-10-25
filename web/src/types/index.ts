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

export type BudgetFrequency = 'Monthly' | 'Quarterly' | 'Bi-annually' | 'Annually';

/**
 * How far a budget write reaches (see the backend's `budget_store`):
 * `forward` = from the month until the next explicit change (the server default),
 * `month` = that month only, `through` = that month through `through` (inclusive).
 */
export type ApplyMode = 'forward' | 'month' | 'through';

export interface ApplyScope {
  apply?: ApplyMode;
  through?: string;          // YYYY-MM, required when apply === 'through'
}

/**
 * One budget line as it stands in a month. Lines are identified across months by
 * `line_key`, the UUID assigned once at creation. `inherited` is true until the
 * month is confirmed; `effective_since` is the month this value took effect.
 */
export interface Budget {
  line_key: string;
  category: string;
  subcategory: string;
  limit_amount: number;
  frequency: BudgetFrequency;
  category_id?: number | null;
  subcategory_id?: number | null;
  month: string;             // YYYY-MM the line was read for
  inherited: boolean;
  effective_since?: string | null;   // YYYY-MM this value took effect
}

export interface BudgetCreate extends ApplyScope {
  month: string;             // YYYY-MM
  category: string;
  subcategory?: string;
  limit_amount: number;
  frequency: BudgetFrequency;
}

export interface BudgetUpdate {
  category?: string;
  subcategory?: string;
  limit_amount?: number;
  frequency?: BudgetFrequency;
}

export interface SuggestedBudget {
  line_key: string;
  month: string;
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

export interface GoalCreate extends Omit<Goal, 'id'> {
  category?: string;
  subcategory?: string;
}
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

/** One budget line in GET /api/reporting/summary (either partition). */
export interface ReportSummaryRow {
  budget_id: number;
  line_key: string;
  category: string;
  subcategory: string;
  budget: number;
  spent: number;
  remaining: number;
  status: 'Over' | 'On Track' | 'Under' | 'No Budget';
  frequency: string;
}

/** A non-monthly line also carries the calendar period it accrues over. */
export interface NonMonthlySummaryRow extends ReportSummaryRow {
  period_start: string;   // ISO YYYY-MM-DD — start of the calendar period
  period_end: string;     // ISO YYYY-MM-DD — end of the calendar period
}

/**
 * The partitioned body of GET /api/reporting/summary.
 * `monthly` holds only Monthly lines; `non_monthly` holds the rest, each
 * accruing spend across its calendar period and compared to the full
 * per-period limit.
 */
export interface ReportSummary {
  monthly: ReportSummaryRow[];
  non_monthly: NonMonthlySummaryRow[];
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

// ── Categories ────────────────────────────────────────────────────────────────

export interface ActiveCategory {
  budget_id: number;
  line_key: string;
  category: string;
  subcategory: string;
  frequency: BudgetFrequency;
  category_id?: number | null;
  subcategory_id?: number | null;
}

export interface CategoryRow {
  id: number;
  name: string;
  kind: 'category' | 'subcategory';
  created_date?: string | null;
}

export interface CategoryUpdate {
  name: string;
}
