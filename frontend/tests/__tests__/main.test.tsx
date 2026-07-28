/**
 * The entry point must not mount a misconfigured app.
 *
 * `main.tsx` is excluded from coverage (`vite.config.ts`), which is not the
 * same as being excluded from testing — and the branch that decides whether
 * the app starts at all is exactly the one worth an assertion. Mounting an
 * app that is missing `VITE_API_ENDPOINT` would trade a blank page for a
 * confusing one: every request fails with an unexplained network error and
 * nothing on screen says why.
 */

import { describe, it, expect, vi, afterEach } from 'vitest';

async function loadMain(configErrors: string[]) {
  vi.resetModules();

  const render = vi.fn();
  const createRoot = vi.fn(() => ({ render, unmount: vi.fn() }));

  vi.doMock('react-dom/client', () => ({ createRoot, default: { createRoot } }));
  vi.doMock('@/api/config', async () => {
    const actual = await vi.importActual<Record<string, unknown>>('@/api/config');
    return { ...actual, configErrors };
  });

  document.body.innerHTML = '<div id="root"></div>';
  await import('../../src/main');

  return { createRoot, render, root: document.getElementById('root')! };
}

afterEach(() => {
  vi.doUnmock('react-dom/client');
  vi.doUnmock('@/api/config');
  vi.resetModules();
  document.body.innerHTML = '';
});

describe('main entry point', () => {
  it('mounts the app when the configuration is complete', async () => {
    const { createRoot, render } = await loadMain([]);

    expect(createRoot).toHaveBeenCalledTimes(1);
    expect(render).toHaveBeenCalledTimes(1);
  });

  it('does not mount the app when configErrors is non-empty', async () => {
    const { createRoot, render } = await loadMain(['VITE_API_ENDPOINT is not configured']);

    expect(createRoot).not.toHaveBeenCalled();
    expect(render).not.toHaveBeenCalled();
  });

  it('renders the diagnostic naming every problem instead', async () => {
    const { root } = await loadMain([
      'VITE_API_ENDPOINT is not configured',
      'AUTH_ENABLED is true but the Cognito env var VITE_COGNITO_DOMAIN is missing',
    ]);

    expect(root.querySelector('[data-testid="config-diagnostic"]')).not.toBeNull();
    expect(root.textContent).toContain('VITE_API_ENDPOINT is not configured');
    expect(root.textContent).toContain('VITE_COGNITO_DOMAIN');
  });
});
