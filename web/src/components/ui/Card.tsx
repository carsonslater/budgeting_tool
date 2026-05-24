import React from 'react';
import styles from './Card.module.css';

type Padding = 'none' | 'sm' | 'md' | 'lg';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  padding?: Padding;
  hoverable?: boolean;
  title?: string;
  subtitle?: string;
  headerRight?: React.ReactNode;
  style?: React.CSSProperties;
}

const padMap: Record<Padding, string> = {
  none: styles.padNone,
  sm: styles.padSm,
  md: styles.padMd,
  lg: styles.padLg,
};

export const Card: React.FC<CardProps> = ({
  children,
  className = '',
  padding = 'md',
  hoverable = false,
  title,
  subtitle,
  headerRight,
  style,
}) => {
  const classes = [
    styles.card,
    padMap[padding],
    hoverable ? styles.hoverable : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={classes} style={style}>
      {(title || headerRight) && (
        <div className={styles.header}>
          <div>
            {title && <div className={styles.title}>{title}</div>}
            {subtitle && <div className={styles.subtitle}>{subtitle}</div>}
          </div>
          {headerRight && <div>{headerRight}</div>}
        </div>
      )}
      {children}
    </div>
  );
};

export default Card;
