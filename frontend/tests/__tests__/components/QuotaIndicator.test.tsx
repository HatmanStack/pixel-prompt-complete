/**
 * QuotaIndicator tests.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

let AUTH_ENABLED_MOCK = true;
vi.mock('../../../src/api/config', () => ({
  get AUTH_ENABLED() {
    return AUTH_ENABLED_MOCK;
  },
}));

let me: unknown = null;
vi.mock('../../../src/stores/useBillingStore', () => ({
  useBillingStore: (selector: (s: { me: unknown }) => unknown) => selector({ me }),
}));

import { QuotaIndicator } from '../../../src/components/QuotaIndicator';

describe('QuotaIndicator', () => {
  beforeEach(() => {
    AUTH_ENABLED_MOCK = true;
    me = null;
  });

  it('renders nothing when auth is disabled', () => {
    AUTH_ENABLED_MOCK = false;
    const { container } = render(<QuotaIndicator />);
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when me is not loaded', () => {
    const { container } = render(<QuotaIndicator />);
    expect(container.firstChild).toBeNull();
  });

  it('renders used/limit from me.quota.refine', () => {
    me = {
      tier: 'free',
      quota: { refine: { used: 1, limit: 2 }, generate: { used: 0, limit: 1 } },
    };
    render(<QuotaIndicator />);
    expect(screen.getByText('1/2')).toBeInTheDocument();
  });
});
