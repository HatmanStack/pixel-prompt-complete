/**
 * Configuration validation must reach a screen, not a blank page.
 *
 * `api/config.ts` threw at module scope when `VITE_API_ENDPOINT` was missing
 * in a production build, or when `VITE_AUTH_ENABLED=true` without the four
 * `VITE_COGNITO_*` variables. Those run during `main.tsx`'s import chain,
 * before `createRoot` and before any `ErrorBoundary` mounts — so a
 * misconfigured build rendered nothing at all, with no diagnostic anywhere a
 * human would look.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const COGNITO_VARS = [
  'VITE_COGNITO_DOMAIN',
  'VITE_COGNITO_CLIENT_ID',
  'VITE_COGNITO_REDIRECT_URI',
  'VITE_COGNITO_LOGOUT_URI',
];

async function loadConfig() {
  vi.resetModules();
  return import('../../../src/api/config');
}

describe('configErrors', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_API_ENDPOINT', 'https://api.test');
    vi.stubEnv('VITE_AUTH_ENABLED', 'false');
    for (const name of COGNITO_VARS) vi.stubEnv(name, '');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it('importing the module never throws, in any combination', async () => {
    // The regression this whole task is about. Every combination below used
    // to be a module-scope throw during main.tsx's import chain.
    const combinations = [
      { PROD: true, VITE_API_ENDPOINT: '', VITE_AUTH_ENABLED: 'false' },
      { PROD: true, VITE_API_ENDPOINT: '', VITE_AUTH_ENABLED: 'true' },
      { PROD: false, VITE_API_ENDPOINT: '', VITE_AUTH_ENABLED: 'true' },
      { PROD: true, VITE_API_ENDPOINT: 'https://api.test', VITE_AUTH_ENABLED: 'true' },
    ];

    for (const combination of combinations) {
      vi.stubEnv('PROD', combination.PROD);
      vi.stubEnv('VITE_API_ENDPOINT', combination.VITE_API_ENDPOINT);
      vi.stubEnv('VITE_AUTH_ENABLED', combination.VITE_AUTH_ENABLED);
      await expect(loadConfig()).resolves.toBeDefined();
    }
  });

  it('is empty when every variable is set', async () => {
    vi.stubEnv('PROD', true);
    vi.stubEnv('VITE_AUTH_ENABLED', 'true');
    for (const name of COGNITO_VARS) vi.stubEnv(name, 'set');

    const { configErrors } = await loadConfig();
    expect(configErrors).toEqual([]);
  });

  it('lists all four missing Cognito variables by name', async () => {
    vi.stubEnv('VITE_AUTH_ENABLED', 'true');

    const { configErrors } = await loadConfig();
    expect(configErrors).toHaveLength(4);
    for (const name of COGNITO_VARS) {
      expect(configErrors.some((e: string) => e.includes(name))).toBe(true);
    }
  });

  it('lists only the Cognito variables that are actually missing', async () => {
    vi.stubEnv('VITE_AUTH_ENABLED', 'true');
    vi.stubEnv('VITE_COGNITO_DOMAIN', 'https://auth.test');
    vi.stubEnv('VITE_COGNITO_CLIENT_ID', 'abc');

    const { configErrors } = await loadConfig();
    expect(configErrors).toHaveLength(2);
    expect(configErrors.join(' ')).not.toContain('VITE_COGNITO_DOMAIN');
    expect(configErrors.join(' ')).toContain('VITE_COGNITO_REDIRECT_URI');
  });

  it('reports a missing VITE_API_ENDPOINT in a production build', async () => {
    vi.stubEnv('PROD', true);
    vi.stubEnv('VITE_API_ENDPOINT', '');

    const { configErrors } = await loadConfig();
    expect(configErrors).toHaveLength(1);
    expect(configErrors[0]).toContain('VITE_API_ENDPOINT');
  });

  it('keeps the dev-mode console.warn instead of reporting an error', async () => {
    // Only the PROD path changed. A dev server with no endpoint is a normal
    // state, not a build that must refuse to start.
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.stubEnv('PROD', false);
    vi.stubEnv('VITE_API_ENDPOINT', '');

    const { configErrors } = await loadConfig();
    expect(configErrors).toEqual([]);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});

describe('renderConfigDiagnostic', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('renders every error into the element', async () => {
    const { renderConfigDiagnostic } =
      await import('../../../src/components/errors/configDiagnostic');
    const root = document.createElement('div');
    document.body.appendChild(root);

    renderConfigDiagnostic(
      ['VITE_API_ENDPOINT is missing', 'VITE_COGNITO_DOMAIN is missing'],
      root,
    );

    expect(root.textContent).toContain('VITE_API_ENDPOINT is missing');
    expect(root.textContent).toContain('VITE_COGNITO_DOMAIN is missing');
    expect(root.querySelectorAll('li')).toHaveLength(2);
  });

  it('replaces whatever was in the element rather than appending to it', async () => {
    const { renderConfigDiagnostic } =
      await import('../../../src/components/errors/configDiagnostic');
    const root = document.createElement('div');
    root.textContent = 'loading...';

    renderConfigDiagnostic(['boom'], root);

    expect(root.textContent).not.toContain('loading...');
  });

  it('escapes the error text rather than interpreting it as markup', async () => {
    // The strings come from environment variables, which are build inputs.
    const { renderConfigDiagnostic } =
      await import('../../../src/components/errors/configDiagnostic');
    const root = document.createElement('div');

    renderConfigDiagnostic(['<img src=x onerror=alert(1)>'], root);

    expect(root.querySelector('img')).toBeNull();
    expect(root.textContent).toContain('<img src=x onerror=alert(1)>');
  });

  it('marks the panel as an alert so it is announced', async () => {
    const { renderConfigDiagnostic } =
      await import('../../../src/components/errors/configDiagnostic');
    const root = document.createElement('div');

    renderConfigDiagnostic(['boom'], root);

    expect(root.querySelector('[role="alert"]')).not.toBeNull();
  });
});
