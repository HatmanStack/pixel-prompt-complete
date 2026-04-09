/**
 * useMePolling hook.
 * Refreshes `/me` on mount (if signed in) and whenever the session ID changes
 * (i.e. after a successful generate creates a new session).
 */

import { useEffect } from 'react';
import { useAuthStore } from '@/stores/useAuthStore';
import { useBillingStore } from '@/stores/useBillingStore';
import { useAppStore } from '@/stores/useAppStore';

export function useMePolling(): void {
  const isAuthed = useAuthStore((s) => s.isAuthenticated());
  const refresh = useBillingStore((s) => s.refresh);
  const sessionId = useAppStore((s) => s.currentSession?.sessionId);

  useEffect(() => {
    if (!isAuthed) return;
    void refresh();
  }, [isAuthed, refresh, sessionId]);
}
