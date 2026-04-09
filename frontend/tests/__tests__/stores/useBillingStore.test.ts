/**
 * useBillingStore tests.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('../../../src/api/me', () => ({
  fetchMe: vi.fn(),
}));

import { useBillingStore } from '../../../src/stores/useBillingStore';
import { fetchMe } from '../../../src/api/me';

describe('useBillingStore', () => {
  beforeEach(() => {
    useBillingStore.getState().clear();
    vi.mocked(fetchMe).mockReset();
  });

  it('refresh populates me on success', async () => {
    const mePayload = {
      userId: 'u',
      email: 'e@e',
      tier: 'free' as const,
      quota: {
        windowSeconds: 3600,
        windowStart: 0,
        generate: { used: 0, limit: 1 },
        refine: { used: 0, limit: 2 },
      },
      billing: { subscriptionStatus: null, portalAvailable: false },
    };
    vi.mocked(fetchMe).mockResolvedValue(mePayload);

    await useBillingStore.getState().refresh();

    expect(useBillingStore.getState().me).toEqual(mePayload);
    expect(useBillingStore.getState().error).toBeNull();
  });

  it('refresh sets error on failure', async () => {
    vi.mocked(fetchMe).mockRejectedValue(new Error('boom'));
    await useBillingStore.getState().refresh();
    expect(useBillingStore.getState().me).toBeNull();
    expect(useBillingStore.getState().error).toBe('boom');
  });
});
