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
  refresh: () => Promise<void>;
  clear: () => void;
}

export const useBillingStore = create<BillingState>((set) => ({
  me: null,
  isLoading: false,
  error: null,

  refresh: async () => {
    set({ isLoading: true, error: null });
    try {
      const me = await fetchMe();
      set({ me, isLoading: false });
    } catch (err) {
      set({
        isLoading: false,
        error: err instanceof Error ? err.message : 'Failed to load account info',
      });
    }
  },

  clear: () => set({ me: null, error: null, isLoading: false }),
}));
