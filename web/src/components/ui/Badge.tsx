import React from 'react';
import styles from './Badge.module.css';

type BadgeVariant = 'accent' | 'muted' | 'danger' | 'success';

interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  variant = 'accent',
  children,
  className = '',
}) => {
  return (
    <span className={`${styles.badge} ${styles[variant]} ${className}`}>
      {children}
    </span>
  );
};

export default Badge;
