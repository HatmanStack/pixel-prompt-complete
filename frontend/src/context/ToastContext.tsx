/**
 * ToastContext
 * Provides toast notification system throughout the app
 * Manages toast queue and auto-dismissal
 */

import {
  createContext,
  useContext,
  useState,
  useCallback,
  type FC,
  type ReactNode,
} from 'react';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface Toast {
  id: number;
  message: string;
  type: ToastType;
  duration: number;
}

interface ToastContextValue {
  toasts: Toast[];
  showToast: (message: string, type?: ToastType, duration?: number) => number;
  removeToast: (id: number) => void;
  success: (message: string, duration?: number) => number;
  error: (message: string, duration?: number) => number;
  warning: (message: string, duration?: number) => number;
  info: (message: string, duration?: number) => number;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let toastIdCounter = 0;

interface ToastProviderProps {
  children: ReactNode;
}

export const ToastProvider: FC<ToastProviderProps> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);

  // Remove a toast by ID
  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // Add a new toast
  const showToast = useCallback(
    (message: string, type: ToastType = 'info', duration: number = 3000) => {
      const id = toastIdCounter++;
      const toast: Toast = { id, message, type, duration };

      setToasts((prev) => [...prev, toast]);

      // Auto-dismiss after duration
      if (duration > 0) {
        setTimeout(() => {
          removeToast(id);
        }, duration);
      }

      return id;
    },
    [removeToast]
  );

  // Helper methods for different toast types
  const success = useCallback(
    (message: string, duration?: number) => {
      return showToast(message, 'success', duration);
    },
    [showToast]
  );

  const error = useCallback(
    (message: string, duration?: number) => {
      return showToast(message, 'error', duration);
    },
    [showToast]
  );

  const warning = useCallback(
    (message: string, duration?: number) => {
      return showToast(message, 'warning', duration);
    },
    [showToast]
  );

  const info = useCallback(
    (message: string, duration?: number) => {
      return showToast(message, 'info', duration);
    },
    [showToast]
  );

  const value: ToastContextValue = {
    toasts,
    showToast,
    removeToast,
    success,
    error,
    warning,
    info,
  };

  return (
    <ToastContext.Provider value={value}>{children}</ToastContext.Provider>
  );
};

/**
 * useToast Hook
 * Access toast context
 */
// eslint-disable-next-line react-refresh/only-export-components
export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);

  if (!context) {
    throw new Error('useToast must be used within ToastProvider');
  }

  return context;
}

export default ToastContext;
