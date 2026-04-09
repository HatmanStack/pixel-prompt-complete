/**
 * Header sign-in / sign-out control tests.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

let AUTH_ENABLED_MOCK = true;
vi.mock('../../../../src/api/config', () => ({
  get AUTH_ENABLED() {
    return AUTH_ENABLED_MOCK;
  },
  hostedUiLoginUrl: () => Promise.resolve('https://auth.test.com/login'),
  hostedUiLogoutUrl: () => 'https://auth.test.com/logout',
}));

let authed = false;
const clearTokens = vi.fn();
vi.mock('../../../../src/stores/useAuthStore', () => ({
  useAuthStore: (
    selector: (s: {
      isAuthenticated: () => boolean;
      user: { email: string } | null;
      clearTokens: () => void;
    }) => unknown,
  ) =>
    selector({
      isAuthenticated: () => authed,
      user: authed ? { email: 'me@test.com' } : null,
      clearTokens,
    }),
}));

vi.mock('../../../../src/stores/useAppStore', () => ({
  useAppStore: () => ({
    currentView: 'generation',
    setCurrentView: vi.fn(),
  }),
}));

import { Header } from '../../../../src/components/common/Header';

describe('Header auth controls', () => {
  beforeEach(() => {
    AUTH_ENABLED_MOCK = true;
    authed = false;
    clearTokens.mockReset();
  });

  it('hides auth controls when AUTH_ENABLED is false', () => {
    AUTH_ENABLED_MOCK = false;
    render(<Header />);
    expect(screen.queryByTestId('auth-controls')).toBeNull();
  });

  it('shows Sign in button when signed out', async () => {
    const assignMock = vi.fn();
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { ...window.location, assign: assignMock },
    });
    render(<Header />);
    const btn = screen.getByRole('button', { name: /sign in/i });
    expect(btn).toBeInTheDocument();
    await userEvent.click(btn);
    // Allow the async hostedUiLoginUrl promise to resolve
    await vi.waitFor(() => {
      expect(assignMock).toHaveBeenCalledWith('https://auth.test.com/login');
    });
  });

  it('shows email and Sign out when signed in', async () => {
    authed = true;
    const assignMock = vi.fn();
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { ...window.location, assign: assignMock },
    });

    render(<Header />);
    expect(screen.getByText('me@test.com')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /sign out/i }));
    expect(clearTokens).toHaveBeenCalled();
    expect(assignMock).toHaveBeenCalledWith('https://auth.test.com/logout');
  });
});
