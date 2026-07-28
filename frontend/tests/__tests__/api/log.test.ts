/**
 * Client-side error reporting.
 *
 * The SPA's entire client-side error strategy was `console.error`. For a
 * static app on a CDN that is not an observability channel: a production
 * crash is visible only in the browser that suffered it, while a
 * purpose-built, tested, deployed `/log` endpoint sat unused on the other
 * side of the API.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../../../src/api/config', () => ({
  API_BASE_URL: 'https://api.test',
  API_ROUTES: { LOG: '/log' },
}));

import { reportError, MAX_LOG_BODY_BYTES } from '../../../src/api/log';

function fetchMock() {
  return globalThis.fetch as ReturnType<typeof vi.fn>;
}

function lastCall() {
  const call = fetchMock().mock.calls[0];
  return { url: call[0] as string, init: call[1] as RequestInit };
}

function lastBody() {
  return JSON.parse(lastCall().init.body as string);
}

describe('reportError', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200 }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('posts to the log endpoint with the level and message', async () => {
    await reportError('ERROR', 'boom');

    expect(fetchMock()).toHaveBeenCalledTimes(1);
    expect(lastCall().url).toBe('https://api.test/log');
    expect(lastCall().init.method).toBe('POST');
    expect(lastBody()).toMatchObject({ level: 'ERROR', message: 'boom' });
  });

  it('sends the correlation id as a header so the two records share an id', async () => {
    await reportError('ERROR', 'boom', { correlationId: 'err_123_abc' });

    const headers = lastCall().init.headers as Record<string, string>;
    expect(headers['X-Correlation-ID']).toBe('err_123_abc');
  });

  it('sends the stack and metadata when given', async () => {
    await reportError('WARNING', 'careful', {
      stack: '\n    in Thing',
      metadata: { component: 'Thing' },
    });

    expect(lastBody()).toMatchObject({
      level: 'WARNING',
      stack: '\n    in Thing',
      metadata: { component: 'Thing' },
    });
  });

  it('truncates a deep component stack to fit the 10 KB body limit', async () => {
    // The backend rejects anything over MAX_LOG_BODY_SIZE with a 413, and a
    // React componentStack for a deep tree exceeds it on its own -- so an
    // untruncated report is not a large report, it is no report at all.
    const stack = '\n    in DeepComponent'.repeat(3000);
    await reportError('ERROR', 'boom', { stack });

    const body = lastCall().init.body as string;
    expect(stack.length).toBeGreaterThan(MAX_LOG_BODY_BYTES);
    expect(body.length).toBeLessThan(MAX_LOG_BODY_BYTES);
    expect(lastBody().stack.length).toBeLessThan(stack.length);
  });

  it('truncates an enormous message too', async () => {
    await reportError('ERROR', 'x'.repeat(50_000));

    const body = lastCall().init.body as string;
    expect(body.length).toBeLessThan(MAX_LOG_BODY_BYTES);
  });

  it('never throws when fetch rejects', async () => {
    fetchMock().mockRejectedValue(new Error('offline'));

    await expect(reportError('ERROR', 'boom')).resolves.toBeUndefined();
  });

  it('never throws when fetch is missing entirely', async () => {
    vi.stubGlobal('fetch', undefined);

    await expect(reportError('ERROR', 'boom')).resolves.toBeUndefined();
  });

  it('never throws when the response is an error status', async () => {
    fetchMock().mockResolvedValue({ ok: false, status: 413 });

    await expect(reportError('ERROR', 'boom')).resolves.toBeUndefined();
  });

  it('does not send a stack or metadata key when none was given', async () => {
    await reportError('INFO', 'hello');

    const body = lastBody();
    expect(body).not.toHaveProperty('stack');
    expect(body).not.toHaveProperty('metadata');
  });
});
