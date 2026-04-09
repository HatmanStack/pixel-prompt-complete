/**
 * useAuthStore tests.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

// Build a fake JWT with base64url payload containing sub/email.
function makeJwt(sub: string, email: string): string {
  const header = btoa(JSON.stringify({ alg: 'none', typ: 'JWT' }));
  const payload = btoa(JSON.stringify({ sub, email }))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
  return `${header}.${payload}.sig`;
}

describe('useAuthStore', () => {
  const storage: Record<string, string> = {};

  beforeEach(() => {
    for (const k of Object.keys(storage)) delete storage[k];
    vi.stubGlobal('sessionStorage', {
      getItem: (k: string) => (k in storage ? storage[k] : null),
      setItem: (k: string, v: string) => {
        storage[k] = v;
      },
      removeItem: (k: string) => {
        delete storage[k];
      },
      clear: () => {
        for (const k of Object.keys(storage)) delete storage[k];
      },
    });
    vi.resetModules();
  });

  it('setTokens stores tokens, decodes user, persists to sessionStorage', async () => {
    const { useAuthStore } = await import('../../../src/stores/useAuthStore');
    const jwt = makeJwt('abc-123', 'user@example.com');
    useAuthStore.getState().setTokens({
      idToken: jwt,
      accessToken: 'at',
      refreshToken: 'rt',
      expiresIn: 3600,
    });
    const state = useAuthStore.getState();
    expect(state.idToken).toBe(jwt);
    expect(state.user).toEqual({ sub: 'abc-123', email: 'user@example.com' });
    expect(state.isAuthenticated()).toBe(true);
    expect(storage.pp_auth).toBeDefined();
  });

  it('clearTokens wipes state and storage', async () => {
    const { useAuthStore } = await import('../../../src/stores/useAuthStore');
    useAuthStore.getState().setTokens({
      idToken: makeJwt('s', 'e@e'),
      accessToken: 'at',
      expiresIn: 3600,
    });
    useAuthStore.getState().clearTokens();
    expect(useAuthStore.getState().idToken).toBeNull();
    expect(useAuthStore.getState().isAuthenticated()).toBe(false);
    expect(storage.pp_auth).toBeUndefined();
  });

  it('rehydrates unexpired tokens from sessionStorage on import', async () => {
    storage.pp_auth = JSON.stringify({
      idToken: 'id',
      accessToken: 'at',
      refreshToken: null,
      expiresAt: Date.now() + 60_000,
      user: { sub: 's', email: 'e@e' },
    });
    const { useAuthStore } = await import('../../../src/stores/useAuthStore');
    expect(useAuthStore.getState().idToken).toBe('id');
    expect(useAuthStore.getState().isAuthenticated()).toBe(true);
  });

  it('drops expired tokens on rehydrate', async () => {
    storage.pp_auth = JSON.stringify({
      idToken: 'id',
      accessToken: 'at',
      refreshToken: null,
      expiresAt: Date.now() - 1000,
      user: { sub: 's', email: 'e@e' },
    });
    const { useAuthStore } = await import('../../../src/stores/useAuthStore');
    expect(useAuthStore.getState().idToken).toBeNull();
    expect(storage.pp_auth).toBeUndefined();
  });
});
