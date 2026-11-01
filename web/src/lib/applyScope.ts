import type { ApplyMode, ApplyScope } from '../types';

/**
 * The Applies-to control's state. `through` is read only when `mode` is `through`.
 * It is kept as a YYYY-MM string so it can go straight into the month picker.
 */
export interface ApplyChoice {
  mode: ApplyMode;
  through: string;
}

/** The server's default: from the month until the next explicit change. */
export const DEFAULT_APPLY_CHOICE: ApplyChoice = { mode: 'forward', through: '' };

export function toApplyScope(choice: ApplyChoice): ApplyScope {
  if (choice.mode === 'through') {
    return { apply: 'through', through: choice.through };
  }
  return { apply: choice.mode };
}

/** Why the choice cannot be sent for `month`, or null when it can. */
export function applyScopeError(month: string, choice: ApplyChoice): string | null {
  if (choice.mode !== 'through') return null;
  if (!choice.through) return 'Choose the last month this change reaches.';
  // YYYY-MM strings order correctly as plain strings.
  if (choice.through < month) return `Choose ${month} or a later month.`;
  return null;
}
