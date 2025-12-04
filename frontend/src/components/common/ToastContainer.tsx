/**
 * ToastContainer Component
 * Displays toast notifications in a fixed position
 * Renders all active toasts from ToastContext
 */

import { useEffect, type FC } from 'react';
import { createPortal } from 'react-dom';
import { useToast } from '@/context/ToastContext';
import { useSound } from '@/hooks/useSound';
import { Toast } from './Toast';

export const ToastContainer: FC = () => {
  const { toasts, removeToast } = useToast();
  const { playSound } = useSound();

  // Play sound when new toast is added
  useEffect(() => {
    if (toasts.length > 0) {
      playSound('swoosh');
    }
  }, [toasts.length, playSound]);

  if (toasts.length === 0) {
    return null;
  }

  const container = (
    <div
      className="
        fixed bottom-4 right-4 z-50
        flex flex-col gap-2
        max-w-sm w-full
        pointer-events-none
      "
      aria-live="polite"
      aria-atomic="false"
    >
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto">
          <Toast
            id={toast.id}
            message={toast.message}
            type={toast.type}
            onDismiss={removeToast}
          />
        </div>
      ))}
    </div>
  );

  return createPortal(container, document.body);
};

export default ToastContainer;
