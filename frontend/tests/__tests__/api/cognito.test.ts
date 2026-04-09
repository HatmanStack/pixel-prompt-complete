/**
 * Cognito token exchange tests.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('../../../src/api/config', () => ({
  COGNITO_DOMAIN: 'https://auth.test.com',
  COGNITO_CLIENT_ID: 'client123',
  COGNITO_REDIRECT_URI: 'https://app.test.com/auth/callback',
}));

import { exchangeCodeForTokens } from '../../../src/api/cognito';

describe('exchangeCodeForTokens', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('POSTs to the Cognito token endpoint and maps the response', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          id_token: 'id',
          access_token: 'at',
          refresh_token: 'rt',
          expires_in: 3600,
          token_type: 'Bearer',
        }),
    } as unknown as Response);
    vi.stubGlobal('fetch', fetchMock);

    const tokens = await exchangeCodeForTokens('abc');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://auth.test.com/oauth2/token');
    expect((init as RequestInit).method).toBe('POST');
    const body = (init as RequestInit).body as string;
    expect(body).toContain('grant_type=authorization_code');
    expect(body).toContain('client_id=client123');
    expect(body).toContain('code=abc');
    expect(tokens).toEqual({
      idToken: 'id',
      accessToken: 'at',
      refreshToken: 'rt',
      expiresIn: 3600,
    });
  });

  it('throws on non-2xx responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 400 } as unknown as Response),
    );
    await expect(exchangeCodeForTokens('bad')).rejects.toThrow(/400/);
  });
});
