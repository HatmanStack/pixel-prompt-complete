/**
 * Billing redirect page tests.
 *
 * Static pages, but they are where Stripe lands the user, so a broken link
 * strands someone who has just paid.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { BillingSuccess } from '../../../src/pages/BillingSuccess';
import { BillingCancel } from '../../../src/pages/BillingCancel';

describe('BillingSuccess', () => {
  it('confirms the subscription is active', () => {
    render(<BillingSuccess />);
    expect(screen.getByRole('heading', { name: /Subscription active/i })).toBeInTheDocument();
  });

  it('offers a way back to the app', () => {
    render(<BillingSuccess />);
    expect(screen.getByRole('link', { name: /Return home/i })).toHaveAttribute('href', '/');
  });
});

describe('BillingCancel', () => {
  it('renders without claiming the payment succeeded', () => {
    render(<BillingCancel />);
    expect(screen.queryByText(/Subscription active/i)).not.toBeInTheDocument();
  });

  it('offers a way back to the app', () => {
    render(<BillingCancel />);
    expect(screen.getByRole('link', { name: /Return home/i })).toHaveAttribute('href', '/');
  });
});
