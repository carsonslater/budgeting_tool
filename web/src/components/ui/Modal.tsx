import React, { useEffect, useCallback } from 'react';
import { X } from 'lucide-react';
import styles from './Modal.module.css';

type ModalSize = 'sm' | 'md' | 'lg' | 'xl';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  size?: ModalSize;
  closeOnOverlay?: boolean;
}

const sizeMap: Record<ModalSize, string> = {
  sm: styles.panelSm,
  md: '',
  lg: styles.panelLg,
  xl: styles.panelXl,
};

export const Modal: React.FC<ModalProps> = ({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
  size = 'md',
  closeOnOverlay = true,
}) => {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    },
    [onClose]
  );

  useEffect(() => {
    if (!open) return;
    document.addEventListener('keydown', handleKeyDown);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [open, handleKeyDown]);

  if (!open) return null;

  return (
    <div
      className={styles.overlay}
      onClick={closeOnOverlay ? onClose : undefined}
      role="dialog"
      aria-modal="true"
      aria-labelledby={title ? 'modal-title' : undefined}
    >
      <div
        className={`${styles.panel} ${sizeMap[size]}`}
        onClick={(e) => e.stopPropagation()}
      >
        {(title || true) && (
          <div className={styles.header}>
            <div>
              {title && <div id="modal-title" className={styles.title}>{title}</div>}
              {subtitle && <div className={styles.subtitle}>{subtitle}</div>}
            </div>
            <button
              className={styles.closeBtn}
              onClick={onClose}
              aria-label="Close modal"
            >
              <X size={16} />
            </button>
          </div>
        )}
        <div className={styles.body}>{children}</div>
        {footer && <div className={styles.footer}>{footer}</div>}
      </div>
    </div>
  );
};

export default Modal;
