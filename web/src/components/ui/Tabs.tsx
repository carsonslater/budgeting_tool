import React, { useState } from 'react';
import styles from './Tabs.module.css';

interface Tab {
  id: string;
  label: string;
  icon?: React.ReactNode;
}

interface TabsProps {
  tabs: Tab[];
  defaultTab?: string;
  onChange?: (tabId: string) => void;
  children: (activeTab: string) => React.ReactNode;
}

export const Tabs: React.FC<TabsProps> = ({
  tabs,
  defaultTab,
  onChange,
  children,
}) => {
  const [active, setActive] = useState(defaultTab ?? tabs[0]?.id ?? '');

  const handleClick = (id: string) => {
    setActive(id);
    onChange?.(id);
  };

  return (
    <div>
      <div className={styles.tabList} role="tablist">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={active === tab.id}
            className={`${styles.tab} ${active === tab.id ? styles.active : ''}`}
            onClick={() => handleClick(tab.id)}
            id={`tab-${tab.id}`}
            aria-controls={`panel-${tab.id}`}
          >
            {tab.icon && tab.icon}
            {tab.label}
          </button>
        ))}
      </div>
      <div
        className={styles.panel}
        role="tabpanel"
        id={`panel-${active}`}
        aria-labelledby={`tab-${active}`}
      >
        {children(active)}
      </div>
    </div>
  );
};

export default Tabs;
