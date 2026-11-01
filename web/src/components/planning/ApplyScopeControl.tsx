import React, { useId } from 'react';
import { MonthPicker } from '../ui/MonthPicker';
import type { ApplyMode } from '../../types';
import type { ApplyChoice } from '../../lib/applyScope';
import { monthLabel } from '../../lib/monthMath';
import styles from './ApplyScopeControl.module.css';

interface ApplyScopeControlProps {
  /** The month the edit is made from. */
  month: string;
  value: ApplyChoice;
  onChange: (choice: ApplyChoice) => void;
  /** A validation message for the current choice, or null. */
  error: string | null;
}

const OPTIONS: { mode: ApplyMode; label: string }[] = [
  { mode: 'forward', label: 'Until changed' },
  { mode: 'month', label: 'This month only' },
  { mode: 'through', label: 'Through a month' },
];

/**
 * Chooses how far a budget or income change reaches from the selected month.
 * The default is "until changed", which is how the server applies a write when no
 * scope is given.
 */
export const ApplyScopeControl: React.FC<ApplyScopeControlProps> = ({
  month,
  value,
  onChange,
  error,
}) => {
  const groupName = useId();
  const from = monthLabel(month);

  const pickMode = (mode: ApplyMode) => {
    onChange({
      mode,
      through: mode === 'through' && !value.through ? month : value.through,
    });
  };

  const description =
    value.mode === 'forward'
      ? `From ${from} until the next explicit change.`
      : value.mode === 'month'
        ? `${from} only. Other months keep their values.`
        : `From ${from} through the last month chosen below. The value that was in force returns the month after.`;

  return (
    <fieldset className={styles.fieldset}>
      <legend className={styles.legend}>Applies to</legend>
      {OPTIONS.map((option) => (
        <label key={option.mode} className={styles.option}>
          <input
            type="radio"
            name={groupName}
            checked={value.mode === option.mode}
            onChange={() => pickMode(option.mode)}
          />
          {option.label}
        </label>
      ))}
      {value.mode === 'through' && (
        <div className={styles.through}>
          <MonthPicker
            label="Last month"
            value={value.through}
            onChange={(through) => onChange({ ...value, through })}
            error={error ?? undefined}
          />
        </div>
      )}
      <p className={styles.hint}>{description}</p>
      {value.mode !== 'through' && error && <p className={styles.error}>{error}</p>}
    </fieldset>
  );
};

export default ApplyScopeControl;
