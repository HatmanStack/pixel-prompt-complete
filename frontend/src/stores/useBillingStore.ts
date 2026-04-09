/**
 * Billing store.
 * Holds the last `/me` payload describing the user's tier and quota window.
 */

import { create } from 'zustand';
import { fetchMe, type MeResponse } from '@/api/me';

interface BillingState {
  me: MeResponse | null;
  isLoading: boolean;
  error: string | null;
  requestEpoch: number;
  refresh: () => Promise<void>;
  clear: () => void;
}

export const useBillingStore = create<BillingState>((set, get) => ({
  me: null,
  isLoading: false,
  error: null,
  requestEpoch: 0,

  refresh: async () => {
    const epoch = get().requestEpoch;
    set({ isLoading: true, error: null });
    try {
      const me = await fetchMe();
      if (get().requestEpoch !== epoch) return;
      set({ me, isLoading: false });
    } catch (err) {
      if (get().requestEpoch !== epoch) return;
      set({
        isLoading: false,
        error: err instanceof Error ? err.message : 'Failed to load account info',
      });
    }
  },

  clear: () =>
    set((s) => ({ me: null, error: null, isLoading: false, requestEpoch: s.requestEpoch + 1 })),
}));
