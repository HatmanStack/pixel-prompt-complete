/**
 * Admin dashboard store.
 * Manages users, models, metrics, and revenue state for the admin panel.
 * Follows the same patterns as useBillingStore (requestEpoch stale-response guard).
 */

import { create } from 'zustand';
import {
  fetchAdminUsers as apiFetchUsers,
  fetchAdminUserDetail as apiFetchUserDetail,
  suspendUser as apiSuspendUser,
  unsuspendUser as apiUnsuspendUser,
  notifyUser as apiNotifyUser,
  fetchAdminModels as apiFetchModels,
  disableModel as apiDisableModel,
  enableModel as apiEnableModel,
  fetchAdminMetrics as apiFetchMetrics,
  fetchAdminRevenue as apiFetchRevenue,
  type AdminUser,
  type AdminModel,
  type AdminMetricsResponse,
  type AdminRevenueResponse,
} from '@/api/adminClient';

interface AdminState {
  // Users
  users: AdminUser[];
  usersLoading: boolean;
  usersNextKey: string | null;
  selectedUser: AdminUser | null;
  userDetailLoading: boolean;

  // Models
  models: AdminModel[];
  modelsLoading: boolean;

  // Metrics
  metrics: AdminMetricsResponse | null;
  metricsLoading: boolean;

  // Revenue
  revenue: AdminRevenueResponse | null;
  revenueLoading: boolean;

  // Filters
  tierFilter: string | null;
  suspendedFilter: boolean | null;
  searchQuery: string;

  // Stale-response guard
  requestEpoch: number;

  // Actions
  fetchUsers: (reset?: boolean) => Promise<void>;
  fetchUserDetail: (userId: string) => Promise<void>;
  suspendUser: (userId: string, reason?: string) => Promise<void>;
  unsuspendUser: (userId: string) => Promise<void>;
  notifyUser: (userId: string, type: string, message: string, subject?: string) => Promise<void>;
  fetchModels: () => Promise<void>;
  disableModel: (model: string) => Promise<void>;
  enableModel: (model: string) => Promise<void>;
  fetchMetrics: (days?: number) => Promise<void>;
  fetchRevenue: () => Promise<void>;
  setTierFilter: (tier: string | null) => void;
  setSuspendedFilter: (suspended: boolean | null) => void;
  setSearchQuery: (query: string) => void;
}

export const useAdminStore = create<AdminState>((set, get) => ({
  users: [],
  usersLoading: false,
  usersNextKey: null,
  selectedUser: null,
  userDetailLoading: false,
  models: [],
  modelsLoading: false,
  metrics: null,
  metricsLoading: false,
  revenue: null,
  revenueLoading: false,
  tierFilter: null,
  suspendedFilter: null,
  searchQuery: '',
  requestEpoch: 0,

  fetchUsers: async (reset = true) => {
    const epoch = get().requestEpoch + 1;
    set({ usersLoading: true, requestEpoch: epoch });
    if (reset) {
      set({ usersNextKey: null });
    }
    try {
      const { tierFilter, suspendedFilter, usersNextKey } = get();
      const result = await apiFetchUsers({
        tier: tierFilter ?? undefined,
        suspended: suspendedFilter ?? undefined,
        lastKey: reset ? undefined : (usersNextKey ?? undefined),
      });
      if (get().requestEpoch !== epoch) return;
      set((state) => ({
        users: reset ? result.users : [...state.users, ...result.users],
        usersNextKey: result.nextKey,
        usersLoading: false,
      }));
    } catch {
      if (get().requestEpoch !== epoch) return;
      set({ usersLoading: false });
    }
  },

  fetchUserDetail: async (userId: string) => {
    set({ userDetailLoading: true });
    try {
      const user = await apiFetchUserDetail(userId);
      set({ selectedUser: user, userDetailLoading: false });
    } catch {
      set({ userDetailLoading: false });
    }
  },

  suspendUser: async (userId: string, reason?: string) => {
    await apiSuspendUser(userId, reason);
    await get().fetchUsers(true);
  },

  unsuspendUser: async (userId: string) => {
    await apiUnsuspendUser(userId);
    await get().fetchUsers(true);
  },

  notifyUser: async (userId: string, type: string, message: string, subject?: string) => {
    await apiNotifyUser(userId, type, message, subject);
  },

  fetchModels: async () => {
    set({ modelsLoading: true });
    try {
      const result = await apiFetchModels();
      set({ models: result.models, modelsLoading: false });
    } catch {
      set({ modelsLoading: false });
    }
  },

  disableModel: async (model: string) => {
    await apiDisableModel(model);
    await get().fetchModels();
  },

  enableModel: async (model: string) => {
    await apiEnableModel(model);
    await get().fetchModels();
  },

  fetchMetrics: async (days?: number) => {
    set({ metricsLoading: true });
    try {
      const metrics = await apiFetchMetrics(days);
      set({ metrics, metricsLoading: false });
    } catch {
      set({ metricsLoading: false });
    }
  },

  fetchRevenue: async () => {
    set({ revenueLoading: true });
    try {
      const revenue = await apiFetchRevenue();
      set({ revenue, revenueLoading: false });
    } catch {
      set({ revenueLoading: false });
    }
  },

  setTierFilter: (tier: string | null) => set({ tierFilter: tier }),
  setSuspendedFilter: (suspended: boolean | null) => set({ suspendedFilter: suspended }),
  setSearchQuery: (query: string) => set({ searchQuery: query }),
}));
