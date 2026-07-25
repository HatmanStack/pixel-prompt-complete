/**
 * Pricing API client tests.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../../../src/api/config', () => ({
  API_BASE_URL: 'https://api.test',
  API_ROUTES: { PRICING: '/pricing' },
}));

import { fetchPricing, formatUsdCents, formatCredits } from '../../../src/api/pricing';

describe('formatUsdCents', () => {
  it('drops cents when the price is whole dollars', () => {
    expect(formatUsdCents(1900)).toBe('$19');
    expect(formatUsdCents(4900)).toBe('$49');
  });

  it('keeps cents when the price is not whole', () => {
    expect(formatUsdCents(1950)).toBe('$19.50');
    expect(formatUsdCents(999)).toBe('$9.99');
  });

  it('handles zero', () => {
    expect(formatUsdCents(0)).toBe('$0');
  });
});

describe('formatCredits', () => {
  it('converts centi-credits to whole credits', () => {
    expect(formatCredits(6500)).toBe('65');
    expect(formatCredits(500)).toBe('5');
  });

  it('shows fractions for partial credits', () => {
    expect(formatCredits(25)).toBe('0.25');
  });

  it('respects a non-default scale', () => {
    expect(formatCredits(65, 1)).toBe('65');
  });
});

describe('fetchPricing', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('requests the pricing endpoint', async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ tiers: [] }),
    });
    await fetchPricing();
    expect(globalThis.fetch).toHaveBeenCalledWith('https://api.test/pricing');
  });

  it('returns the parsed payload', async () => {
    const payload = { currency: 'usd', tiers: [{ id: 'paid', priceUsdCents: 1900 }] };
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => payload,
    });
    await expect(fetchPricing()).resolves.toEqual(payload);
  });

  it('throws on a non-ok response so callers can fall back', async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      status: 503,
    });
    await expect(fetchPricing()).rejects.toThrow('503');
  });
});
