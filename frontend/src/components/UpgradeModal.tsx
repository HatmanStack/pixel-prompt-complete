/**
 * UpgradeModal
 * Opens a Stripe Checkout session and redirects the browser to the
 * returned URL.
 */

import { useState, type FC } from 'react';
import { startCheckout } from '@/api/billing';

interface UpgradeModalProps {
  onClose: () => void;
}

export const UpgradeModal: FC<UpgradeModalProps> = ({ onClose }) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Upgrade to paid tier"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
    >
      <div className="bg-primary border border-primary/50 rounded-lg p-6 max-w-sm w-full">
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
