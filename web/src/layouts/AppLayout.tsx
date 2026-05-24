import React from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { format, parseISO } from 'date-fns';
import {
  LayoutDashboard,
  Receipt,
  Wallet,
  Target,
  BarChart2,
  Settings,
} from 'lucide-react';
import { apiFetch } from '../api/client';
import styles from './AppLayout.module.css';

interface NavItem {
  to: string;
  label: string;
  icon: React.FC<{ size?: number; className?: string }>;
  end?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: '/',          label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/expenses',  label: 'Expenses',  icon: Receipt },
  { to: '/budgets',   label: 'Budgets',   icon: Wallet },
  { to: '/goals',     label: 'Goals',     icon: Target },
  { to: '/reporting', label: 'Reporting', icon: BarChart2 },
  { to: '/settings',  label: 'Settings',  icon: Settings },
];

export const AppLayout: React.FC = () => {
  const location = useLocation();

  const { data: lastSaved } = useQuery({
    queryKey: ['system', 'last-saved'],
    queryFn: () => apiFetch<{last_saved: string | null}>('/api/system/last-saved'),
    refetchInterval: 5000,
  });

  return (
    <div className={styles.shell}>
      {/* ── Sidebar ── */}
      <aside className={styles.sidebar}>
        <div className={styles.sidebarTop}>
          <div className={styles.appTitle}>
            Household<br />
            <span className={styles.appTitleAccent}>Budgeting</span>
          </div>
          <div className={styles.appSubtitle}>local-first · private</div>
        </div>

        <nav className={styles.nav} aria-label="Main navigation">
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `${styles.navLink} ${isActive ? styles.active : ''}`
              }
            >
              <Icon size={16} className={styles.navIcon} />
              <span className={styles.navLabel}>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className={styles.sidebarFooter}>
          <div className={styles.footerText}>100% local · no cloud</div>
          {lastSaved?.last_saved && (
            <div className={styles.footerText} style={{ marginTop: 4, opacity: 0.8 }}>
              Saved {format(parseISO(lastSaved.last_saved), 'MMM d, h:mm a')}
            </div>
          )}
        </div>
      </aside>

      {/* ── Main ── */}
      <main className={styles.main}>
        <div className={styles.mainInner}>
          <div key={location.pathname} className={styles.pageTransition}>
            <Outlet />
          </div>
        </div>
      </main>
    </div>
  );
};

export default AppLayout;
