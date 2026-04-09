/**
 * TierBanner tests.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

let AUTH_ENABLED_MOCK = true;
vi.mock('../../../src/api/config', () => ({
  get AUTH_ENABLED() {
    return AUTH_ENABLED_MOCK;
  },
  hostedUiLoginUrl: () => 'https://auth.test.com/login',
}));

let authed = false;
vi.mock('../../../src/stores/useAuthStore', () => ({
  useAuthStore: (selector: (s: { isAuthenticated: () => boolean }) => unknown) =>
    selector({ isAuthenticated: () => authed }),
}));

let me: unknown = null;
vi.mock('../../../src/stores/useBillingStore', () => ({
  useBillingStore: (selector: (s: { me: unknown }) => unknown) => selector({ me }),
}));

vi.mock('../../../src/components/UpgradeModal', () => ({
  UpgradeModal: () => <div data-testid="upgrade-modal" />,
}));

import { TierBanner } from '../../../src/components/TierBanner';

describe('TierBanner', () => {
  beforeEach(() => {
    AUTH_ENABLED_MOCK = true;
    authed = false;
    me = null;
  });

  it('renders nothing when auth is disabled', () => {
    AUTH_ENABLED_MOCK = false;
    const { container } = render(<TierBanner />);
    expect(container.firstChild).toBeNull();
  });

  it('shows sign-in CTA for guests', () => {
    render(<TierBanner />);
    expect(screen.getByText(/sign in for more/i)).toBeInTheDocument();
  });

  it('shows Pro badge for paid tier', () => {
    authed = true;
    me = {
      tier: 'paid',
      quota: { refine: { used: 0, limit: 0 }, generate: { used: 0, limit: 0 } },
    };
    render(<TierBanner />);
    expect(screen.getByText(/pro/i)).toBeInTheDocument();
  });

  it('shows upgrade CTA for free tier', () => {
    authed = true;
    me = {
      tier: 'free',
      quota: { refine: { used: 1, limit: 2 }, generate: { used: 0, limit: 1 } },
    };
    render(<TierBanner />);
    expect(screen.getByText(/1 of 2 refinements left/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /upgrade/i })).toBeInTheDocument();
  });
});
