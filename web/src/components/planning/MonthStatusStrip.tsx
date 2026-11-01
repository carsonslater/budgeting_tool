import React from 'react';
import { Badge } from '../ui/Badge';
import type { MonthPlanStatus } from '../../types';
import { monthLabel } from '../../lib/monthMath';
import styles from './MonthStatusStrip.module.css';

interface MonthStatusStripProps {
  months: MonthPlanStatus[];
  selected: string;
  onSelect: (month: string) => void;
}

/**
 * One chip per month in a window: its name and whether it is still inherited
 * (not yet confirmed) or confirmed. Clicking a chip selects that month.
 */
export const MonthStatusStrip: React.FC<MonthStatusStripProps> = ({
  months,
  selected,
  onSelect,
}) => (
  <div className={styles.strip} role="group" aria-label="Budget months">
    {months.map((m) => {
      const confirmed = m.status === 'confirmed';
      const isSelected = m.month === selected;
      return (
        <button
          key={m.month}
          type="button"
          aria-pressed={isSelected}
          className={`${styles.chip} ${isSelected ? styles.selected : ''}`}
          onClick={() => onSelect(m.month)}
        >
          <span className={styles.month}>{monthLabel(m.month)}</span>
          <Badge variant={confirmed ? 'success' : 'muted'}>
            {confirmed ? 'Confirmed' : 'Inherited'}
          </Badge>
        </button>
      );
    })}
  </div>
);

export default MonthStatusStrip;
