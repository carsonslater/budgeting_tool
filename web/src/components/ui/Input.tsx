import React from 'react';
import styles from './Input.module.css';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, className = '', id, ...props }, ref) => {
    const inputId = id ?? label?.toLowerCase().replace(/\s+/g, '-');
    return (
      <div className={`${styles.wrapper} ${error ? styles.error : ''}`}>
        {label && (
          <label className={styles.label} htmlFor={inputId}>
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={`${styles.input} ${className}`}
          {...props}
        />
        {error && <span className={styles.errorMsg}>{error}</span>}
      </div>
    );
  }
);

Input.displayName = 'Input';
export default Input;
