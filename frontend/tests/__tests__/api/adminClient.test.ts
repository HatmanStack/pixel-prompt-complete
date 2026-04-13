/**
 * Admin API client tests.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('../../../src/stores/useAuthStore', () => ({
  useAuthStore: {
    getState: () => ({ idToken: 'test-jwt-token' }),
  },
}));

vi.mock('../../../src/api/config', () => ({
  API_BASE_URL: 'https://api.test.com',
  API_ROUTES: {
    ADMIN_USERS: '/admin/users',
    ADMIN_MODELS: '/admin/models',
    ADMIN_METRICS: '/admin/metrics',
    ADMIN_REVENUE: '/admin/revenue',
  },
}));

import {
  fetchAdminUsers,
  fetchAdminUserDetail,
  suspendUser,
  unsuspendUser,
  notifyUser,
  fetchAdminModels,
  disableModel,
  enableModel,
  fetchAdminMetrics,
  fetchAdminRevenue,
} from '../../../src/api/adminClient';

function mockResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    json: () => Promise.resolve(body),
    headers: new Headers(),
    redirected: false,
    type: 'basic' as ResponseType,
    url: '',
    clone: vi.fn(),
    body: null,
    bodyUsed: false,
    arrayBuffer: vi.fn(),
    blob: vi.fn(),
    formData: vi.fn(),
    text: vi.fn(),
    bytes: vi.fn(),
  } as unknown as Response;
}

describe('Admin API Client', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  describe('fetchAdminUsers', () => {
    it('calls GET /admin/users with auth header', async () => {
      const body = { users: [], nextKey: null };
      fetchMock.mockResolvedValueOnce(mockResponse(body));

      const result = await fetchAdminUsers();

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, options] = fetchMock.mock.calls[0];
      expect(url).toBe('https://api.test.com/admin/users');
      expect(options.method).toBe('GET');
      expect(options.headers.Authorization).toBe('Bearer test-jwt-token');
      expect(result).toEqual(body);
    });

    it('passes query parameters for pagination and filters', async () => {
      fetchMock.mockResolvedValueOnce(mockResponse({ users: [], nextKey: null }));

      await fetchAdminUsers({ limit: 25, lastKey: 'abc', tier: 'paid', suspended: true });

      const [url] = fetchMock.mock.calls[0];
      expect(url).toContain('limit=25');
      expect(url).toContain('lastKey=abc');
      expect(url).toContain('tier=paid');
      expect(url).toContain('suspended=true');
    });
  });

  describe('fetchAdminUserDetail', () => {
    it('calls GET /admin/users/{userId}', async () => {
      const user = { userId: 'u1', email: 'a@b.com', tier: 'free' };
      fetchMock.mockResolvedValueOnce(mockResponse(user));

      const result = await fetchAdminUserDetail('u1');

      const [url, options] = fetchMock.mock.calls[0];
      expect(url).toBe('https://api.test.com/admin/users/u1');
      expect(options.method).toBe('GET');
      expect(options.headers.Authorization).toBe('Bearer test-jwt-token');
      expect(result).toEqual(user);
    });
  });

  describe('suspendUser', () => {
    it('calls POST /admin/users/{userId}/suspend with reason', async () => {
      fetchMock.mockResolvedValueOnce(mockResponse({ status: 'suspended' }));

      await suspendUser('u1', 'abuse');

      const [url, options] = fetchMock.mock.calls[0];
      expect(url).toBe('https://api.test.com/admin/users/u1/suspend');
      expect(options.method).toBe('POST');
      expect(JSON.parse(options.body)).toEqual({ reason: 'abuse' });
      expect(options.headers.Authorization).toBe('Bearer test-jwt-token');
    });
  });

  describe('unsuspendUser', () => {
    it('calls POST /admin/users/{userId}/unsuspend', async () => {
      fetchMock.mockResolvedValueOnce(mockResponse({ status: 'active' }));

      await unsuspendUser('u1');

      const [url, options] = fetchMock.mock.calls[0];
      expect(url).toBe('https://api.test.com/admin/users/u1/unsuspend');
      expect(options.method).toBe('POST');
    });
  });

  describe('notifyUser', () => {
    it('calls POST /admin/users/{userId}/notify with type, message, and subject', async () => {
      fetchMock.mockResolvedValueOnce(mockResponse({ status: 'sent' }));

      await notifyUser('u1', 'warning', 'Please stop', 'Notice');

      const [url, options] = fetchMock.mock.calls[0];
      expect(url).toBe('https://api.test.com/admin/users/u1/notify');
      expect(options.method).toBe('POST');
      expect(JSON.parse(options.body)).toEqual({
        type: 'warning',
        message: 'Please stop',
        subject: 'Notice',
      });
    });
  });

  describe('fetchAdminModels', () => {
    it('calls GET /admin/models', async () => {
      const body = { models: [] };
      fetchMock.mockResolvedValueOnce(mockResponse(body));

      const result = await fetchAdminModels();

      const [url, options] = fetchMock.mock.calls[0];
      expect(url).toBe('https://api.test.com/admin/models');
      expect(options.method).toBe('GET');
      expect(result).toEqual(body);
    });
  });

  describe('disableModel', () => {
    it('calls POST /admin/models/{model}/disable', async () => {
      fetchMock.mockResolvedValueOnce(mockResponse({ status: 'disabled' }));

      await disableModel('gemini');

      const [url, options] = fetchMock.mock.calls[0];
      expect(url).toBe('https://api.test.com/admin/models/gemini/disable');
      expect(options.method).toBe('POST');
    });
  });

  describe('enableModel', () => {
    it('calls POST /admin/models/{model}/enable', async () => {
      fetchMock.mockResolvedValueOnce(mockResponse({ status: 'enabled' }));

      await enableModel('gemini');

      const [url, options] = fetchMock.mock.calls[0];
      expect(url).toBe('https://api.test.com/admin/models/gemini/enable');
      expect(options.method).toBe('POST');
    });
  });

  describe('fetchAdminMetrics', () => {
    it('calls GET /admin/metrics with days param', async () => {
      const body = { today: {}, history: [] };
      fetchMock.mockResolvedValueOnce(mockResponse(body));

      const result = await fetchAdminMetrics(7);

      const [url] = fetchMock.mock.calls[0];
      expect(url).toContain('days=7');
      expect(result).toEqual(body);
    });

    it('calls GET /admin/metrics without days param when omitted', async () => {
      fetchMock.mockResolvedValueOnce(mockResponse({ today: {}, history: [] }));

      await fetchAdminMetrics();

      const [url] = fetchMock.mock.calls[0];
      expect(url).toBe('https://api.test.com/admin/metrics');
    });
  });

  describe('fetchAdminRevenue', () => {
    it('calls GET /admin/revenue', async () => {
      const body = { current: { activeSubscribers: 10, monthlyChurn: 2 }, history: [] };
      fetchMock.mockResolvedValueOnce(mockResponse(body));

      const result = await fetchAdminRevenue();

      const [url, options] = fetchMock.mock.calls[0];
      expect(url).toBe('https://api.test.com/admin/revenue');
      expect(options.method).toBe('GET');
      expect(result).toEqual(body);
    });
  });

  describe('error handling', () => {
    it('throws on non-ok response', async () => {
      fetchMock.mockResolvedValueOnce(mockResponse({ error: 'forbidden' }, 403));

      await expect(fetchAdminUsers()).rejects.toThrow('GET /admin/users failed: 403');
    });
  });
});
