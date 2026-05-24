import React from 'react';
import { ChevronDown } from 'lucide-react';
import styles from './Select.module.css';

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  options: { value: string; label: string }[];
  placeholder?: string;
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, error, options, placeholder, className = '', id, ...props }, ref) => {
    const selectId = id ?? label?.toLowerCase().replace(/\s+/g, '-');
    return (
      <div className={`${styles.wrapper} ${error ? styles.error : ''}`}>
        {label && (
          <label className={styles.label} htmlFor={selectId}>
            {label}
          </label>
        )}
        <div className={styles.selectWrap}>
          <select
            ref={ref}
            id={selectId}
            className={`${styles.select} ${className}`}
            {...props}
          >
            {placeholder && (
              <option value="" disabled>
                {placeholder}
              </option>
            )}
            {options.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <ChevronDown className={styles.chevron} aria-hidden="true" />
        </div>
        {error && <span className={styles.errorMsg}>{error}</span>}
      </div>
    );
  }
);

Select.displayName = 'Select';
export default Select;
