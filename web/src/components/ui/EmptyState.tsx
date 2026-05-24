import React from 'react';
import { Database } from 'lucide-react';

interface EmptyStateProps {
  title?: string;
  message?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({ title = "No data yet", message }) => {
  return (
    <div style={{ padding: '4rem 1rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
      <Database size={48} color="var(--color-accent)" style={{ margin: '0 auto 1rem', opacity: 0.8 }} />
      <div style={{ fontSize: '1.1rem', fontWeight: 500, color: 'var(--color-text)', marginBottom: '0.5rem' }}>
        {title}
      </div>
      {message && <div style={{ fontSize: '0.95rem' }}>{message}</div>}
    </div>
  );
};
