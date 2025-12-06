/**
 * Toast Store
 * Toast notification state using Zustand
 */

import { create } from 'zustand';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface Toast {
  id: number;
  message: string;
  type: ToastType;
  duration: number;
}

interface ToastStore {
  toasts: Toast[];
  showToast: (message: string, type?: ToastType, duration?: number) => number;
  removeToast: (id: number) => void;
  success: (message: string, duration?: number) => number;
  error: (message: string, duration?: number) => number;
  warning: (message: string, duration?: number) => number;
  info: (message: string, duration?: number) => number;
}

let toastIdCounter = 0;
// Track timeout IDs to allow cleanup on manual dismiss
const toastTimeouts = new Map<number, ReturnType<typeof setTimeout>>();

export const useToastStore = create<ToastStore>((set, get) => ({
  toasts: [],

  showToast: (message: string, type: ToastType = 'info', duration: number = 3000) => {
    const id = toastIdCounter++;
    const toast: Toast = { id, message, type, duration };

    set((state) => ({ toasts: [...state.toasts, toast] }));

    // Auto-dismiss after duration
    if (duration > 0) {
      const timeoutId = setTimeout(() => {
        toastTimeouts.delete(id);
        get().removeToast(id);
      }, duration);
      toastTimeouts.set(id, timeoutId);
    }

    return id;
  },

  removeToast: (id: number) => {
    // Clear any pending timeout for this toast
    const timeoutId = toastTimeouts.get(id);
    if (timeoutId) {
      clearTimeout(timeoutId);
      toastTimeouts.delete(id);
    }
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }));
  },

  success: (message: string, duration?: number) => {
    return get().showToast(message, 'success', duration);
  },

  error: (message: string, duration?: number) => {
    return get().showToast(message, 'error', duration);
  },

  warning: (message: string, duration?: number) => {
    return get().showToast(message, 'warning', duration);
  },

  info: (message: string, duration?: number) => {
    return get().showToast(message, 'info', duration);
  },
}));

/**
 * useToast Hook
 * Convenience hook for accessing toast store
 */
export function useToast() {
  const store = useToastStore();
  return {
    toasts: store.toasts,
    showToast: store.showToast,
    removeToast: store.removeToast,
    success: store.success,
    error: store.error,
    warning: store.warning,
    info: store.info,
  };
}
