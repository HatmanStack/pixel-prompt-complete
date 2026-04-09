/**
 * TierBanner
 * Shows a contextual message based on the current auth/tier state with a
 * primary CTA (Sign in / Upgrade). Hidden entirely when AUTH_ENABLED is false.
 */

import { useState, type FC } from 'react';
import { AUTH_ENABLED, hostedUiLoginUrl } from '@/api/config';
import { useAuthStore } from '@/stores/useAuthStore';
import { useBillingStore } from '@/stores/useBillingStore';
import { UpgradeModal } from './UpgradeModal';

export const TierBanner: FC = () => {
  const [showUpgrade, setShowUpgrade] = useState(false);
  const isAuthed = useAuthStore((s) => s.isAuthenticated());
  const me = useBillingStore((s) => s.me);

  if (!AUTH_ENABLED) return null;

  if (!isAuthed) {
    const handleSignIn = () => {
      hostedUiLoginUrl()
        .then((url) => window.location.assign(url))
        .catch(() => {});
    };
    return (
      <div className="w-full text-center py-2 px-4 bg-secondary/60 text-sm">
        You're using your free taste.{' '}
        <button type="button" onClick={handleSignIn} className="underline text-accent">
          Sign in for more
        </button>
        .
      </div>
    );
  }

  const tier = me?.tier ?? 'free';

  if (tier === 'paid') {
    return (
      <div className="w-full text-center py-2 px-4 bg-accent/10 text-xs uppercase tracking-wider text-accent">
        Pro
      </div>
    );
  }

  const refineLeft = me ? Math.max(me.quota.refine.limit - me.quota.refine.used, 0) : 0;

  return (
    <>
      <div className="w-full text-center py-2 px-4 bg-secondary/60 text-sm flex items-center justify-center gap-3">
        <span>
          Free tier: {refineLeft} of {me?.quota.refine.limit ?? 0} refinements left.
        </span>
        <button
          type="button"
          className="underline text-accent"
          onClick={() => setShowUpgrade(true)}
        >
          Upgrade
        </button>
      </div>
      {showUpgrade && <UpgradeModal onClose={() => setShowUpgrade(false)} />}
    </>
  );
};

export default TierBanner;
