/**
 * useAdminStore tests.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('../../../src/api/adminClient', () => ({
  fetchAdminUsers: vi.fn(),
  fetchAdminUserDetail: vi.fn(),
  suspendUser: vi.fn(),
  unsuspendUser: vi.fn(),
  notifyUser: vi.fn(),
  fetchAdminModels: vi.fn(),
  disableModel: vi.fn(),
  enableModel: vi.fn(),
  fetchAdminMetrics: vi.fn(),
  fetchAdminRevenue: vi.fn(),
}));

import { useAdminStore } from '../../../src/stores/useAdminStore';
import {
  fetchAdminUsers,
  fetchAdminUserDetail,
  suspendUser,
  unsuspendUser,
  fetchAdminModels,
  disableModel,
  enableModel,
  fetchAdminMetrics,
  fetchAdminRevenue,
} from '../../../src/api/adminClient';

describe('useAdminStore', () => {
  beforeEach(() => {
    useAdminStore.setState({
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
    });
    vi.mocked(fetchAdminUsers).mockReset();
    vi.mocked(fetchAdminUserDetail).mockReset();
    vi.mocked(suspendUser).mockReset();
    vi.mocked(unsuspendUser).mockReset();
    vi.mocked(fetchAdminModels).mockReset();
    vi.mocked(disableModel).mockReset();
    vi.mocked(enableModel).mockReset();
    vi.mocked(fetchAdminMetrics).mockReset();
    vi.mocked(fetchAdminRevenue).mockReset();
  });

  describe('initial state', () => {
    it('starts with empty state', () => {
      const state = useAdminStore.getState();
      expect(state.users).toEqual([]);
      expect(state.usersLoading).toBe(false);
      expect(state.usersNextKey).toBeNull();
      expect(state.models).toEqual([]);
      expect(state.metrics).toBeNull();
      expect(state.revenue).toBeNull();
      expect(state.tierFilter).toBeNull();
      expect(state.suspendedFilter).toBeNull();
      expect(state.searchQuery).toBe('');
    });
  });

  describe('fetchUsers', () => {
    it('populates users on success', async () => {
      const users = [
        { userId: 'u1', email: 'a@b.com', tier: 'free' },
        { userId: 'u2', email: 'c@d.com', tier: 'paid' },
      ];
      vi.mocked(fetchAdminUsers).mockResolvedValue({ users, nextKey: 'next123' });

      await useAdminStore.getState().fetchUsers();

      expect(useAdminStore.getState().users).toEqual(users);
      expect(useAdminStore.getState().usersNextKey).toBe('next123');
      expect(useAdminStore.getState().usersLoading).toBe(false);
    });

    it('appends users on pagination (reset=false)', async () => {
      useAdminStore.setState({
        users: [{ userId: 'u1', email: 'a@b.com', tier: 'free' }],
        usersNextKey: 'key1',
      });
      vi.mocked(fetchAdminUsers).mockResolvedValue({
        users: [{ userId: 'u2', email: 'c@d.com', tier: 'paid' }],
        nextKey: null,
      });

      await useAdminStore.getState().fetchUsers(false);

      expect(useAdminStore.getState().users).toHaveLength(2);
      expect(useAdminStore.getState().usersNextKey).toBeNull();
    });

    it('resets users when reset=true', async () => {
      useAdminStore.setState({
        users: [{ userId: 'u1', email: 'a@b.com', tier: 'free' }],
        usersNextKey: 'key1',
      });
      vi.mocked(fetchAdminUsers).mockResolvedValue({
        users: [{ userId: 'u2', email: 'c@d.com', tier: 'paid' }],
        nextKey: null,
      });

      await useAdminStore.getState().fetchUsers(true);

      expect(useAdminStore.getState().users).toHaveLength(1);
      expect(useAdminStore.getState().users[0].userId).toBe('u2');
    });

    it('passes filters to API', async () => {
      useAdminStore.setState({ tierFilter: 'paid', suspendedFilter: true });
      vi.mocked(fetchAdminUsers).mockResolvedValue({ users: [], nextKey: null });

      await useAdminStore.getState().fetchUsers(true);

      expect(fetchAdminUsers).toHaveBeenCalledWith({
        tier: 'paid',
        suspended: true,
        lastKey: undefined,
      });
    });
  });

  describe('fetchUserDetail', () => {
    it('populates selectedUser on success', async () => {
      const user = { userId: 'u1', email: 'a@b.com', tier: 'free' };
      vi.mocked(fetchAdminUserDetail).mockResolvedValue(user);

      await useAdminStore.getState().fetchUserDetail('u1');

      expect(useAdminStore.getState().selectedUser).toEqual(user);
      expect(useAdminStore.getState().userDetailLoading).toBe(false);
    });
  });

  describe('suspendUser', () => {
    it('calls API and refreshes users', async () => {
      vi.mocked(suspendUser).mockResolvedValue(undefined);
      vi.mocked(fetchAdminUsers).mockResolvedValue({ users: [], nextKey: null });

      await useAdminStore.getState().suspendUser('u1', 'abuse');

      expect(suspendUser).toHaveBeenCalledWith('u1', 'abuse');
      expect(fetchAdminUsers).toHaveBeenCalled();
    });
  });

  describe('unsuspendUser', () => {
    it('calls API and refreshes users', async () => {
      vi.mocked(unsuspendUser).mockResolvedValue(undefined);
      vi.mocked(fetchAdminUsers).mockResolvedValue({ users: [], nextKey: null });

      await useAdminStore.getState().unsuspendUser('u1');

      expect(unsuspendUser).toHaveBeenCalledWith('u1');
      expect(fetchAdminUsers).toHaveBeenCalled();
    });
  });

  describe('fetchModels', () => {
    it('populates models on success', async () => {
      const models = [
        { name: 'gemini', provider: 'google_gemini', enabled: true, dailyCount: 10, dailyCap: 500 },
      ];
      vi.mocked(fetchAdminModels).mockResolvedValue({ models });

      await useAdminStore.getState().fetchModels();

      expect(useAdminStore.getState().models).toEqual(models);
      expect(useAdminStore.getState().modelsLoading).toBe(false);
    });
  });

  describe('disableModel', () => {
    it('calls API and refreshes models', async () => {
      vi.mocked(disableModel).mockResolvedValue(undefined);
      vi.mocked(fetchAdminModels).mockResolvedValue({ models: [] });

      await useAdminStore.getState().disableModel('gemini');

      expect(disableModel).toHaveBeenCalledWith('gemini');
      expect(fetchAdminModels).toHaveBeenCalled();
    });
  });

  describe('enableModel', () => {
    it('calls API and refreshes models', async () => {
      vi.mocked(enableModel).mockResolvedValue(undefined);
      vi.mocked(fetchAdminModels).mockResolvedValue({ models: [] });

      await useAdminStore.getState().enableModel('gemini');

      expect(enableModel).toHaveBeenCalledWith('gemini');
      expect(fetchAdminModels).toHaveBeenCalled();
    });
  });

  describe('fetchMetrics', () => {
    it('populates metrics on success', async () => {
      const metrics = { today: { date: '2026-04-12', modelCounts: {}, usersByTier: {}, suspendedCount: 0 }, history: [] };
      vi.mocked(fetchAdminMetrics).mockResolvedValue(metrics);

      await useAdminStore.getState().fetchMetrics(7);

      expect(useAdminStore.getState().metrics).toEqual(metrics);
      expect(fetchAdminMetrics).toHaveBeenCalledWith(7);
    });
  });

  describe('fetchRevenue', () => {
    it('populates revenue on success', async () => {
      const revenue = {
        current: { activeSubscribers: 10, mrr: 5000, monthlyChurn: 1, updatedAt: 0 },
        history: [],
      };
      vi.mocked(fetchAdminRevenue).mockResolvedValue(revenue);

      await useAdminStore.getState().fetchRevenue();

      expect(useAdminStore.getState().revenue).toEqual(revenue);
      expect(useAdminStore.getState().revenueLoading).toBe(false);
    });
  });

  describe('filter actions', () => {
    it('setTierFilter updates state', () => {
      useAdminStore.getState().setTierFilter('paid');
      expect(useAdminStore.getState().tierFilter).toBe('paid');
    });

    it('setSuspendedFilter updates state', () => {
      useAdminStore.getState().setSuspendedFilter(true);
      expect(useAdminStore.getState().suspendedFilter).toBe(true);
    });

    it('setSearchQuery updates state', () => {
      useAdminStore.getState().setSearchQuery('test');
      expect(useAdminStore.getState().searchQuery).toBe('test');
    });
  });

  describe('stale-response guard', () => {
    it('discards stale responses when epoch changes', async () => {
      let resolveFirst: (value: { users: never[]; nextKey: null }) => void;
      const firstCall = new Promise<{ users: never[]; nextKey: null }>((r) => {
        resolveFirst = r;
      });
      vi.mocked(fetchAdminUsers)
        .mockImplementationOnce(() => firstCall)
        .mockResolvedValueOnce({ users: [{ userId: 'u2', email: 'b@c.com', tier: 'paid' }], nextKey: null });

      // Start first fetch
      const p1 = useAdminStore.getState().fetchUsers(true);
      // Start second fetch (bumps epoch)
      const p2 = useAdminStore.getState().fetchUsers(true);

      // Resolve first after second
      resolveFirst!({ users: [], nextKey: null });
      await p1;
      await p2;

      // The second fetch result should win; the first should be discarded
      expect(useAdminStore.getState().users).toHaveLength(1);
      expect(useAdminStore.getState().users[0].userId).toBe('u2');
    });
  });
});
