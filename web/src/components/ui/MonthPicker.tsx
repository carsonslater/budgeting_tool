import React, { useState, useRef, useEffect } from 'react';
import { Calendar, ChevronLeft, ChevronRight, X } from 'lucide-react';
import { parseISO, format } from 'date-fns';
import styles from './MonthPicker.module.css';

interface MonthPickerProps {
  label?: string;
  value: string; // Expected format: "yyyy-MM" (or empty string)
  onChange: (value: string) => void;
  required?: boolean;
  error?: string;
  placeholder?: string;
}

const MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
];

export const MonthPicker: React.FC<MonthPickerProps> = ({
  label,
  value,
  onChange,
  required = false,
  error,
  placeholder = 'Select month...',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [navYear, setNavYear] = useState(() => {
    if (value) {
      const year = parseInt(value.split('-')[0], 10);
      if (!isNaN(year)) return year;
    }
    return new Date().getFullYear();
  });

  const containerRef = useRef<HTMLDivElement>(null);

  // Sync navYear with external value when dropdown opens or value changes
  useEffect(() => {
    if (value) {
      const year = parseInt(value.split('-')[0], 10);
      if (!isNaN(year)) {
        setNavYear(year);
      }
    }
  }, [value]);

  // Handle click outside to close dropdown
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const handleToggle = () => {
    setIsOpen((prev) => !prev);
  };

  const handlePrevYear = (e: React.MouseEvent) => {
    e.stopPropagation();
    setNavYear((prev) => prev - 1);
  };

  const handleNextYear = (e: React.MouseEvent) => {
    e.stopPropagation();
    setNavYear((prev) => prev + 1);
  };

  const handleMonthSelect = (monthIndex: number, e: React.MouseEvent) => {
    e.stopPropagation();
    const formattedMonth = String(monthIndex + 1).padStart(2, '0');
    const newValue = `${navYear}-${formattedMonth}`;
    onChange(newValue);
    setIsOpen(false);
  };

  const handleClear = (e: React.MouseEvent) => {
    e.stopPropagation();
    onChange('');
    setIsOpen(false);
  };

  // Format value for trigger display (e.g. "2026-05" -> "May 2026")
  const getDisplayValue = () => {
    if (!value) return '';
    try {
      const date = parseISO(`${value}-01`);
      return format(date, 'MMMM yyyy');
    } catch {
      return value;
    }
  };

  const displayVal = getDisplayValue();
  const selectedYear = value ? parseInt(value.split('-')[0], 10) : null;
  const selectedMonthIdx = value ? parseInt(value.split('-')[1], 10) - 1 : null;

  return (
    <div className={`${styles.wrapper} ${error ? styles.error : ''}`} ref={containerRef}>
      {label && (
        <span className={styles.label}>
          {label}
        </span>
      )}
      
      <div className={styles.triggerWrapper}>
        <button
          type="button"
          onClick={handleToggle}
          className={`${styles.trigger} ${isOpen ? styles.active : ''}`}
          aria-haspopup="dialog"
          aria-expanded={isOpen}
        >
          <div className={styles.triggerContent}>
            <Calendar className={styles.iconCalendar} size={16} />
            <span className={displayVal ? styles.valueText : styles.placeholderText}>
              {displayVal || placeholder}
            </span>
          </div>
          
          <div className={styles.actionIcons} onClick={(e) => e.stopPropagation()}>
            {!required && value && (
              <button
                type="button"
                className={styles.btnClear}
                onClick={handleClear}
                aria-label="Clear date"
              >
                <X size={14} />
              </button>
            )}
            <span className={`${styles.chevron} ${isOpen ? styles.chevronOpen : ''}`}>▼</span>
          </div>
        </button>

        {isOpen && (
          <div className={styles.dropdown} role="dialog">
            <div className={styles.header}>
              <button
                type="button"
                className={styles.navButton}
                onClick={handlePrevYear}
                aria-label="Previous year"
              >
                <ChevronLeft size={16} />
              </button>
              
              <span className={styles.yearDisplay}>{navYear}</span>
              
              <button
                type="button"
                className={styles.navButton}
                onClick={handleNextYear}
                aria-label="Next year"
              >
                <ChevronRight size={16} />
              </button>
            </div>

            <div className={styles.grid}>
              {MONTHS.map((m, idx) => {
                const isSelected = selectedYear === navYear && selectedMonthIdx === idx;
                const isCurrentMonth = new Date().getFullYear() === navYear && new Date().getMonth() === idx;
                
                return (
                  <button
                    key={m}
                    type="button"
                    className={`${styles.monthButton} ${
                      isSelected ? styles.selectedMonth : ''
                    } ${isCurrentMonth && !isSelected ? styles.currentMonth : ''}`}
                    onClick={(e) => handleMonthSelect(idx, e)}
                  >
                    {m}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>
      {error && <span className={styles.errorMsg}>{error}</span>}
    </div>
  );
};

export default MonthPicker;
