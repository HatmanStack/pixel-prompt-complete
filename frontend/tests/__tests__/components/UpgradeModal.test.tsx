/**
 * UpgradeModal tests.
 *
 * The modal previously read "Upgrade to Pro" with no figure anywhere. These
 * cover that it now renders real numbers served by the backend, and that a
 * pricing fetch failure degrades to generic copy rather than blocking the
 * upgrade path.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockFetchPricing = vi.fn();
const mockStartCheckout = vi.fn();

vi.mock('../../../src/api/pricing', async () => {
  const actual = await vi.importActual<typeof import('../../../src/api/pricing')>(
    '../../../src/api/pricing',
  );
  return { ...actual, fetchPricing: () => mockFetchPricing() };
});

vi.mock('../../../src/api/billing', () => ({
  startCheckout: () => mockStartCheckout(),
}));

import { UpgradeModal } from '../../../src/components/UpgradeModal';

const PRICING = {
  currency: 'usd',
  creditsEnabled: true,
  billingEnabled: true,
  centiCreditsPerCredit: 100,
  creditCosts: { generate: 100, refine: 25, outpaint: 25 },
  overageUsdCentsPerCredit: 50,
  tiers: [
    {
      id: 'free' as const,
      name: 'Free',
      priceUsdCents: 0,
      monthlyCredits: 500,
      allModels: true,
      renewal: 'fixed_window' as const,
    },
    {
      id: 'paid' as const,
      name: 'Pro',
      priceUsdCents: 1900,
      monthlyCredits: 6500,
      allModels: true,
      renewal: 'stripe_billing_period' as const,
    },
  ],
};

describe('UpgradeModal', () => {
  beforeEach(() => {
    mockFetchPricing.mockReset();
    mockStartCheckout.mockReset();
    mockFetchPricing.mockResolvedValue(PRICING);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the price served by the backend', async () => {
    render(<UpgradeModal onClose={vi.fn()} />);
    expect(await screen.findByText('$19')).toBeInTheDocument();
  });

  it('names the tier from the backend rather than hardcoding it', async () => {
    render(<UpgradeModal onClose={vi.fn()} />);
    expect(await screen.findByText(/Upgrade to Pro/)).toBeInTheDocument();
  });

  it('translates credits into generations the user can understand', async () => {
    render(<UpgradeModal onClose={vi.fn()} />);
    // 6500 centi-credits / 100 per generate = 65 generations
    expect(await screen.findByText(/65 generations/)).toBeInTheDocument();
    // and 6500 / 25 = 260 refinements
    expect(screen.getByText(/260 refinements/)).toBeInTheDocument();
  });

  it('shows a different price when the backend serves one', async () => {
    mockFetchPricing.mockResolvedValue({
      ...PRICING,
      tiers: [
        PRICING.tiers[0],
        { ...PRICING.tiers[1], priceUsdCents: 2900, monthlyCredits: 10000 },
      ],
    });
    render(<UpgradeModal onClose={vi.fn()} />);
    expect(await screen.findByText('$29')).toBeInTheDocument();
  });

  it('falls back to generic copy when pricing cannot be fetched', async () => {
    mockFetchPricing.mockRejectedValue(new Error('network'));
    render(<UpgradeModal onClose={vi.fn()} />);
    expect(await screen.findByText(/Unlock higher refinement limits/)).toBeInTheDocument();
  });

  it('still allows upgrading when pricing is unavailable', async () => {
    mockFetchPricing.mockRejectedValue(new Error('network'));
    mockStartCheckout.mockResolvedValue('https://stripe.test/session');
    render(<UpgradeModal onClose={vi.fn()} />);

    const button = await screen.findByRole('button', { name: 'Upgrade' });
    await userEvent.click(button);
    await waitFor(() => expect(mockStartCheckout).toHaveBeenCalled());
  });

  it('redirects the browser to the Stripe checkout URL', async () => {
    // Preserved from the original suite: the modal's whole job is to get the
    // user to Stripe, so asserting startCheckout ran is not sufficient.
    mockStartCheckout.mockResolvedValue('https://checkout.stripe.com/abc');
    const assignMock = vi.fn();
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { ...window.location, assign: assignMock },
    });

    render(<UpgradeModal onClose={vi.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Upgrade' }));

    expect(mockStartCheckout).toHaveBeenCalled();
    await waitFor(() => expect(assignMock).toHaveBeenCalledWith('https://checkout.stripe.com/abc'));
  });

  it('surfaces a checkout failure instead of failing silently', async () => {
    mockStartCheckout.mockRejectedValue(new Error('Checkout exploded'));
    render(<UpgradeModal onClose={vi.fn()} />);

    await userEvent.click(await screen.findByRole('button', { name: 'Upgrade' }));
    expect(await screen.findByText('Checkout exploded')).toBeInTheDocument();
  });

  it('closes on Cancel', async () => {
    const onClose = vi.fn();
    render(<UpgradeModal onClose={onClose} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalled();
  });

  it('closes on Escape', async () => {
    const onClose = vi.fn();
    render(<UpgradeModal onClose={onClose} />);
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalled();
  });
});
