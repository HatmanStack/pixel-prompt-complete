/**
 * AuthCallback tests.
 *
 * This page holds the OAuth CSRF defence: it refuses to exchange a code when
 * the returned state nonce does not verify. That check was untested.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const mockExchange = vi.fn();
const mockVerifyState = vi.fn();
const mockSetTokens = vi.fn();

vi.mock('../../../src/api/cognito', () => ({
  exchangeCodeForTokens: (...a: unknown[]) => mockExchange(...a),
}));

vi.mock('../../../src/api/config', () => ({
  verifyStateNonce: (...a: unknown[]) => mockVerifyState(...a),
}));

vi.mock('../../../src/stores/useAuthStore', () => ({
  useAuthStore: (selector: (s: { setTokens: unknown }) => unknown) =>
    selector({ setTokens: mockSetTokens }),
}));

import { AuthCallback } from '../../../src/pages/AuthCallback';

function setUrl(search: string) {
  Object.defineProperty(window, 'location', {
    writable: true,
    value: { ...window.location, search, replace: vi.fn() },
  });
}

describe('AuthCallback', () => {
  beforeEach(() => {
    mockExchange.mockReset();
    mockVerifyState.mockReset();
    mockSetTokens.mockReset();
    mockVerifyState.mockReturnValue(true);
    mockExchange.mockResolvedValue({ idToken: 'id', accessToken: 'acc' });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('exchanges the code and stores the tokens', async () => {
    setUrl('?code=abc123&state=nonce');
    render(<AuthCallback />);

    await waitFor(() => expect(mockExchange).toHaveBeenCalledWith('abc123'));
    // Assert the payload, not just the call: forwarding mangled tokens to the
    // auth store would leave the user signed in with credentials that do not
    // work, and the weaker assertion passes either way.
    await waitFor(() =>
      expect(mockSetTokens).toHaveBeenCalledWith({ idToken: 'id', accessToken: 'acc' }),
    );
  });

  it('redirects home after a successful exchange', async () => {
    setUrl('?code=abc123&state=nonce');
    render(<AuthCallback />);
    await waitFor(() => expect(window.location.replace).toHaveBeenCalledWith('/'));
  });

  it('refuses to exchange when the state nonce does not verify', async () => {
    // The CSRF defence. Without it an attacker can have a victim's browser
    // complete a sign-in the attacker started.
    mockVerifyState.mockReturnValue(false);
    setUrl('?code=abc123&state=forged');
    render(<AuthCallback />);

    expect(await screen.findByText(/Possible CSRF attack/)).toBeInTheDocument();
    expect(mockExchange).not.toHaveBeenCalled();
    expect(mockSetTokens).not.toHaveBeenCalled();
  });

  it('rejects a missing code without calling the token endpoint', async () => {
    setUrl('?state=nonce');
    render(<AuthCallback />);

    expect(await screen.findByText(/Missing authorization code/)).toBeInTheDocument();
    expect(mockExchange).not.toHaveBeenCalled();
  });

  it('never stores tokens when the exchange fails', async () => {
    mockExchange.mockRejectedValue(new Error('token endpoint down'));
    setUrl('?code=abc123&state=nonce');
    render(<AuthCallback />);

    expect(await screen.findByText('token endpoint down')).toBeInTheDocument();
    expect(mockSetTokens).not.toHaveBeenCalled();
  });

  it('shows a way out when sign-in fails', async () => {
    mockVerifyState.mockReturnValue(false);
    setUrl('?code=abc&state=bad');
    render(<AuthCallback />);

    const link = await screen.findByRole('link', { name: /Return home/i });
    expect(link).toHaveAttribute('href', '/');
  });

  it('shows progress while the exchange is in flight', () => {
    mockExchange.mockReturnValue(new Promise(() => {}));
    setUrl('?code=abc123&state=nonce');
    render(<AuthCallback />);
    expect(screen.getByText(/Signing you in/)).toBeInTheDocument();
  });
});
