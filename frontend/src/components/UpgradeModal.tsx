/**
 * UpgradeModal
 * Opens a Stripe Checkout session and redirects the browser to the
 * returned URL.
 */

import { useState, useEffect, useRef, useCallback, type FC } from 'react';
import { startCheckout } from '@/api/billing';

interface UpgradeModalProps {
  onClose: () => void;
}

export const UpgradeModal: FC<UpgradeModalProps> = ({ onClose }) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const modalRef = useRef<HTMLDivElement>(null);

  const handleUpgrade = async () => {
    setLoading(true);
    setError(null);
    try {
      const url = await startCheckout();
      window.location.assign(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Checkout failed');
      setLoading(false);
    }
  };

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }
      if (e.key === 'Tab' && modalRef.current) {
        const focusable = modalRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    },
    [onClose],
  );

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    modalRef.current?.focus();
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Upgrade to paid tier"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
    >
      <div
        ref={modalRef}
        tabIndex={-1}
        className="bg-primary border border-primary/50 rounded-lg p-6 max-w-sm w-full outline-none"
      >
        <h2 className="text-lg font-semibold mb-2">Upgrade to Pro</h2>
        <p className="text-sm text-text-secondary mb-4">
          Unlock higher refinement limits with a subscription.
        </p>
        {error && <p className="text-sm text-red-500 mb-3">{error}</p>}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded text-sm border border-primary/50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleUpgrade}
            disabled={loading}
            className="px-3 py-1.5 rounded bg-accent text-white text-sm disabled:opacity-50"
          >
            {loading ? 'Redirecting...' : 'Upgrade'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default UpgradeModal;
