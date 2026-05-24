import React from 'react';
import styles from './Button.module.css';

type Variant = 'primary' | 'ghost' | 'danger';
type Size = 'sm' | 'md' | 'lg';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  as?: 'button' | 'a';
  href?: string;
}

export const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  loading = false,
  children,
  className = '',
  disabled,
  as: Tag = 'button',
  ...props
}) => {
  const sizeClass = size !== 'md' ? styles[size] : '';
  const classes = [styles.btn, styles[variant], sizeClass, className]
    .filter(Boolean)
    .join(' ');

  return (
    <button
      className={classes}
      disabled={disabled || loading}
      {...(props as React.ButtonHTMLAttributes<HTMLButtonElement>)}
    >
      {loading && <span className={styles.spinner} aria-hidden="true" />}
      {children}
    </button>
  );
};

export default Button;
