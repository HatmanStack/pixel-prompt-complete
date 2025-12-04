/**
 * Toast Component
 * Individual toast notification with variants
 */

import type { FC } from 'react';
import type { ToastType } from '@/context/ToastContext';

interface ToastProps {
  id: number;
  message: string;
  type: ToastType;
  onDismiss: (id: number) => void;
}

const typeStyles: Record<ToastType, string> = {
  success: 'bg-success text-text-dark border-success',
  error: 'bg-error text-white border-error',
  warning: 'bg-warning text-text-dark border-warning',
  info: 'bg-info text-text-dark border-info',
};

const icons: Record<ToastType, string> = {
  success: '✓',
  error: '✕',
  warning: '⚠',
  info: 'ℹ',
};

export const Toast: FC<ToastProps> = ({ id, message, type, onDismiss }) => {
  return (
    <div
      className={`
        flex items-center gap-3
        px-4 py-3
        rounded-lg border-l-4 shadow-lg
        animate-[slideIn_300ms_ease-out]
        motion-reduce:animate-none
        ${typeStyles[type]}
      `}
      role="status"
    >
      <span className="text-lg font-bold" aria-hidden="true">
        {icons[type]}
      </span>
      <span className="flex-1 text-sm font-medium">{message}</span>
      <button
        onClick={() => onDismiss(id)}
        className="
          p-1 rounded
          opacity-70 hover:opacity-100
          focus:outline-none focus:ring-2 focus:ring-current
          transition-opacity
        "
        aria-label="Close notification"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={2}
          stroke="currentColor"
          className="w-4 h-4"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M6 18L18 6M6 6l12 12"
          />
        </svg>
      </button>
    </div>
  );
};

export default Toast;
