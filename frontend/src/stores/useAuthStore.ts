/**
 * Auth Store
 * Zustand store for Cognito Hosted UI auth tokens and user identity.
 * Tokens are persisted to sessionStorage so closing the tab signs the user out.
 */

import { create } from 'zustand';

export interface AuthTokens {
  idToken: string;
  accessToken: string;
  refreshToken?: string;
  expiresIn: number;
}

export interface AuthUser {
  sub: string;
  email: string;
}

interface AuthState {
  idToken: string | null;
  accessToken: string | null;
  refreshToken: string | null;
  expiresAt: number | null;
  user: AuthUser | null;
  setTokens: (tokens: AuthTokens) => void;
  clearTokens: () => void;
  isAuthenticated: () => boolean;
}

const STORAGE_KEY = 'pp_auth';

interface PersistedAuth {
  idToken: string;
  accessToken: string;
  refreshToken: string | null;
  expiresAt: number;
  user: AuthUser | null;
}

/**
 * Best-effort JWT decode (no signature verification) to pull `sub` and `email`
 * out of the ID token for UI display. Server-side verification is authoritative.
 */
export function decodeJwt(token: string): AuthUser | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const payload = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = payload.padEnd(payload.length + ((4 - (payload.length % 4)) % 4), '=');
    const json = atob(padded);
    const claims = JSON.parse(json) as { sub?: string; email?: string };
    if (!claims.sub) return null;
    return { sub: claims.sub, email: claims.email ?? '' };
  } catch {
    return null;
  }
}

function readPersisted(): PersistedAuth | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PersistedAuth;
    if (!parsed.expiresAt || parsed.expiresAt <= Date.now()) {
      sessionStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function writePersisted(data: PersistedAuth): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch {
    // ignore
  }
}

function clearPersisted(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}

const hydrated = readPersisted();

export const useAuthStore = create<AuthState>((set, get) => ({
  idToken: hydrated?.idToken ?? null,
  accessToken: hydrated?.accessToken ?? null,
  refreshToken: hydrated?.refreshToken ?? null,
  expiresAt: hydrated?.expiresAt ?? null,
  user: hydrated?.user ?? null,

  setTokens: (tokens: AuthTokens) => {
    const expiresAt = Date.now() + tokens.expiresIn * 1000;
    const user = decodeJwt(tokens.idToken);
    const persisted: PersistedAuth = {
      idToken: tokens.idToken,
      accessToken: tokens.accessToken,
      refreshToken: tokens.refreshToken ?? null,
      expiresAt,
      user,
    };
    writePersisted(persisted);
    set({
      idToken: tokens.idToken,
      accessToken: tokens.accessToken,
      refreshToken: tokens.refreshToken ?? null,
      expiresAt,
      user,
    });
  },

  clearTokens: () => {
    clearPersisted();
    set({
      idToken: null,
      accessToken: null,
      refreshToken: null,
      expiresAt: null,
      user: null,
    });
  },

  isAuthenticated: () => {
    const { idToken, expiresAt } = get();
    return Boolean(idToken && expiresAt && expiresAt > Date.now());
  },
}));
