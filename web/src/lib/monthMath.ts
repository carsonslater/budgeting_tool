import { format, parseISO } from 'date-fns';

/** Shift a YYYY-MM month by whole months (negative goes back). */
export function shiftMonth(month: string, delta: number): string {
  const index = Number(month.slice(0, 4)) * 12 + (Number(month.slice(5, 7)) - 1) + delta;
  const year = Math.floor(index / 12);
  const monthNumber = (index % 12) + 1;
  return `${year}-${String(monthNumber).padStart(2, '0')}`;
}

/** "Oct 2026" for a YYYY-MM month. */
export function monthLabel(month: string): string {
  return format(parseISO(`${month}-01`), 'MMM yyyy');
}
