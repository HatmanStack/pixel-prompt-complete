/**
 * UpgradeModal tests.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../../../src/api/billing', () => ({
  startCheckout: vi.fn(),
}));

import { UpgradeModal } from '../../../src/components/UpgradeModal';
import { startCheckout } from '../../../src/api/billing';

describe('UpgradeModal', () => {
  beforeEach(() => {
    vi.mocked(startCheckout).mockReset();
  });

  it('calls startCheckout and redirects on upgrade', async () => {
    vi.mocked(startCheckout).mockResolvedValue('https://checkout.stripe.com/abc');
    const assignMock = vi.fn();
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { ...window.location, assign: assignMock },
    });

    render(<UpgradeModal onClose={() => {}} />);
    await userEvent.click(screen.getByRole('button', { name: /upgrade/i }));

    expect(startCheckout).toHaveBeenCalled();
    expect(assignMock).toHaveBeenCalledWith('https://checkout.stripe.com/abc');
  });

  it('shows error message on checkout failure', async () => {
    vi.mocked(startCheckout).mockRejectedValue(new Error('nope'));
    render(<UpgradeModal onClose={() => {}} />);
    await userEvent.click(screen.getByRole('button', { name: /upgrade/i }));
    expect(await screen.findByText('nope')).toBeInTheDocument();
  });

  it('calls onClose when cancel clicked', async () => {
    const onClose = vi.fn();
    render(<UpgradeModal onClose={onClose} />);
    await userEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
