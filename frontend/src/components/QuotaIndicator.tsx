/**
 * QuotaIndicator
 * Compact used/limit display with a progress bar. Hidden when AUTH_ENABLED is
 * false or when no /me payload has loaded yet.
 */

import type { FC } from 'react';
import { AUTH_ENABLED } from '@/api/config';
import { useBillingStore } from '@/stores/useBillingStore';

export const QuotaIndicator: FC = () => {
  const me = useBillingStore((s) => s.me);

  if (!AUTH_ENABLED) return null;
  if (!me) return null;

  const { used, limit } = me.quota.refine;
  const pct = limit > 0 ? Math.min((used / limit) * 100, 100) : 0;

  return (
    <div className="w-full text-xs text-text-secondary" aria-label="Quota usage">
      <div className="flex justify-between mb-1">
        <span>Refinements</span>
        <span>
          {used}/{limit}
        </span>
      </div>
      <div className="h-1 bg-primary/40 rounded">
        <div className="h-1 bg-accent rounded" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
};

export default QuotaIndicator;
