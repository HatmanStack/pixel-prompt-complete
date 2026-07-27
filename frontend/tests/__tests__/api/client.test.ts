/**
 * Tests for API client functions
 * Covers retry logic, timeout, correlation IDs, and endpoint payloads
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock correlation ID generation before importing client
vi.mock('../../../src/utils/correlation', () => ({
  generateCorrelationId: () => 'test-corr-id',
}));

// Mock config to avoid import.meta.env issues and provide deterministic values
vi.mock('../../../src/api/config', () => ({
  API_BASE_URL: 'https://api.test.com',
  API_ROUTES: {
    GENERATE: '/generate',
    ITERATE: '/iterate',
    OUTPAINT: '/outpaint',
    STATUS: '/status',
    ENHANCE: '/enhance',
    GALLERY_LIST: '/gallery/list',
    GALLERY_DETAIL: '/gallery',
    PROMPTS_RECENT: '/prompts/recent',
    PROMPTS_HISTORY: '/prompts/history',
    DOWNLOAD: '/download',
  },
  REQUEST_TIMEOUT: 30000,
  RETRY_CONFIG: {
    maxRetries: 3,
    initialDelay: 1000,
    maxDelay: 4000,
  },
  AUTH_ENABLED: true,
  hostedUiLoginUrl: () => Promise.resolve('https://auth.test.com/login'),
}));

import {
  generateSession,
  getSessionStatus,
  iterateImage,
  outpaintImage,
  iterateMultiple,
  enhancePrompt,
  getRecentPrompts,
  getPromptHistory,
  getDownloadUrl,
} from '../../../src/api/client';

// Helper to create a mock Response
function mockResponse(
  body: unknown,
  status = 200,
  statusText = 'OK',
  headers: Record<string, string> = {},
): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
    json: () => Promise.resolve(body),
    headers: new Headers(headers),
    redirected: false,
    type: 'basic' as ResponseType,
    url: '',
    clone: vi.fn(),
    body: null,
    bodyUsed: false,
    arrayBuffer: vi.fn(),
    blob: vi.fn(),
    formData: vi.fn(),
    text: vi.fn(),
    bytes: vi.fn(),
  } as unknown as Response;
}

describe('API Client', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    vi.useFakeTimers();
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  // =============================================
  // 429 is never retried
  // =============================================
  describe('no retry on 429', () => {
    it('does not retry a 429 on a POST', async () => {
      fetchMock.mockResolvedValue(mockResponse({ error: 'quota exceeded' }, 429, 'Too Many Requests'));

      const p = generateSession('test prompt').catch((e: Error) => e);
      await vi.advanceTimersByTimeAsync(10_000);
      await p;

      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it('does not retry a 429 on a GET either', async () => {
      // A rolling-window quota cannot succeed a second later, and every retry
      // re-enters enforce_quota -- DynamoDB writes on a request already denied.
      fetchMock.mockResolvedValue(mockResponse({ error: 'quota exceeded' }, 429, 'Too Many Requests'));

      const p = getSessionStatus('s1').catch((e: Error) => e);
      await vi.advanceTimersByTimeAsync(10_000);
      await p;

      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
  });

  // =============================================
  // Retry on network error, idempotent methods only
  // =============================================
  describe('retry on network error', () => {
    it('retries a GET when fetch throws a network error (no status)', async () => {
      const networkError = new TypeError('Failed to fetch');
      const successBody = { sessionId: 'abc', status: 'complete' };

      fetchMock
        .mockRejectedValueOnce(networkError)
        .mockResolvedValueOnce(mockResponse(successBody, 200));

      const promise = getSessionStatus('abc');

      // Network error retry: delay = 1000 * 2^0 = 1000ms
      await vi.advanceTimersByTimeAsync(1000);

      const result = await promise;
      expect(result).toEqual(successBody);
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });

    it('exhausts retries on persistent network errors and throws', async () => {
      const networkError = new TypeError('Failed to fetch');

      fetchMock
        .mockRejectedValueOnce(networkError)  // initial
        .mockRejectedValueOnce(networkError)  // retry 1
        .mockRejectedValueOnce(networkError)  // retry 2
        .mockRejectedValueOnce(networkError); // retry 3 (maxRetries=3)

      const promise = getSessionStatus('abc');

      // Attach rejection handler early to prevent unhandled rejection
      const resultPromise = promise.catch((e: Error) => e);

      // Advance through all retry delays: 1000, 2000, 4000
      await vi.advanceTimersByTimeAsync(1000);
      await vi.advanceTimersByTimeAsync(2000);
      await vi.advanceTimersByTimeAsync(4000);

      const error = await resultPromise;
      expect(error).toBeInstanceOf(TypeError);
      expect((error as Error).message).toBe('Failed to fetch');
      expect(fetchMock).toHaveBeenCalledTimes(4); // 1 initial + 3 retries
    });

    it('does not retry a POST that fails with a network error', async () => {
      // The server may already have done the work: a network error on
      // POST /generate is exactly the case a retry cannot distinguish.
      fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));

      const p = generateSession('test prompt').catch((e: Error) => e);
      await vi.advanceTimersByTimeAsync(10_000);
      await p;

      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
  });

  // =============================================
  // Non-idempotent methods are never retried
  // =============================================
  describe('retries are restricted to idempotent methods', () => {
    it('does not re-dispatch a POST /generate after a 504', async () => {
      // The money test. A 504 means the gateway gave up, not that the Lambda
      // did: it is still generating. Three retries meant one click billing
      // twelve provider calls and charging four generations.
      fetchMock.mockResolvedValue(mockResponse({ error: 'timeout' }, 504, 'Gateway Timeout'));

      const p = generateSession('a cat').catch((e: Error) => e);
      await vi.advanceTimersByTimeAsync(10_000);
      await p;

      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it('does not retry POST /iterate on a 503', async () => {
      fetchMock.mockResolvedValue(mockResponse({ error: 'unavailable' }, 503, 'Service Unavailable'));

      const p = iterateImage('s1', 'gemini', 'brighter').catch((e: Error) => e);
      await vi.advanceTimersByTimeAsync(10_000);
      await p;

      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it('does not retry POST /outpaint on a 502', async () => {
      fetchMock.mockResolvedValue(mockResponse({ error: 'bad gateway' }, 502, 'Bad Gateway'));

      const p = outpaintImage('s1', 'gemini', 0, '16:9', 'wider').catch((e: Error) => e);
      await vi.advanceTimersByTimeAsync(10_000);
      await p;

      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it('still retries a GET on 503 and resolves', async () => {
      const successBody = { sessionId: 's1', status: 'complete' };
      fetchMock
        .mockResolvedValueOnce(mockResponse({ error: 'unavailable' }, 503, 'Service Unavailable'))
        .mockResolvedValueOnce(mockResponse(successBody, 200));

      const promise = getSessionStatus('s1');
      await vi.advanceTimersByTimeAsync(1000);

      expect(await promise).toEqual(successBody);
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
  });

  // =============================================
  // Retry-After is honoured on retryable GETs
  // =============================================
  describe('Retry-After header', () => {
    it('waits the header interval instead of the exponential backoff', async () => {
      const successBody = { sessionId: 's1', status: 'complete' };
      fetchMock
        .mockResolvedValueOnce(
          mockResponse({ error: 'unavailable' }, 503, 'Service Unavailable', {
            'Retry-After': '2',
          }),
        )
        .mockResolvedValueOnce(mockResponse(successBody, 200));

      const promise = getSessionStatus('s1');

      // The exponential first delay is 1000ms; the header says 2000ms.
      await vi.advanceTimersByTimeAsync(1500);
      expect(fetchMock).toHaveBeenCalledTimes(1);

      await vi.advanceTimersByTimeAsync(500);
      expect(await promise).toEqual(successBody);
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });

    it('clamps a Retry-After larger than maxDelay', async () => {
      // A hostile or mistaken header must not be able to hang the UI.
      const successBody = { sessionId: 's1', status: 'complete' };
      fetchMock
        .mockResolvedValueOnce(
          mockResponse({ error: 'unavailable' }, 503, 'Service Unavailable', {
            'Retry-After': '600',
          }),
        )
        .mockResolvedValueOnce(mockResponse(successBody, 200));

      const promise = getSessionStatus('s1');

      await vi.advanceTimersByTimeAsync(3999);
      expect(fetchMock).toHaveBeenCalledTimes(1);

      await vi.advanceTimersByTimeAsync(1);
      expect(await promise).toEqual(successBody);
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });

    it('ignores an unparseable Retry-After and falls back to backoff', async () => {
      const successBody = { sessionId: 's1', status: 'complete' };
      fetchMock
        .mockResolvedValueOnce(
          mockResponse({ error: 'unavailable' }, 503, 'Service Unavailable', {
            'Retry-After': 'Wed, 21 Oct 2026 07:28:00 GMT',
          }),
        )
        .mockResolvedValueOnce(mockResponse(successBody, 200));

      const promise = getSessionStatus('s1');
      await vi.advanceTimersByTimeAsync(1000);

      expect(await promise).toEqual(successBody);
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
  });

  // =============================================
  // No retry on 400/404 client errors
  // =============================================
  describe('no retry on client errors', () => {
    it('does not retry on 400 Bad Request', async () => {
      fetchMock.mockResolvedValueOnce(
        mockResponse({ error: 'Bad request' }, 400, 'Bad Request')
      );

      await expect(generateSession('bad prompt')).rejects.toThrow('Bad request');
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it('does not retry on 404 Not Found', async () => {
      fetchMock.mockResolvedValueOnce(
        mockResponse({ error: 'Not found' }, 404, 'Not Found')
      );

      await expect(getSessionStatus('nonexistent')).rejects.toThrow('Not found');
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
  });

  // =============================================
  // Timeout via AbortController
  // =============================================
  describe('timeout via AbortController', () => {
    it('passes an AbortSignal to fetch', async () => {
      fetchMock.mockResolvedValueOnce(mockResponse({ ok: true }, 200));

      const promise = generateSession('test');
      await vi.advanceTimersByTimeAsync(0);
      await promise;

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const callArgs = fetchMock.mock.calls[0];
      const requestOptions = callArgs[1];
      expect(requestOptions.signal).toBeInstanceOf(AbortSignal);
    });

    it('throws a timeout error when the request exceeds REQUEST_TIMEOUT', async () => {
      // Make fetch hang indefinitely by never resolving, but abort when signal fires
      fetchMock.mockImplementation(
        (_url: string, options: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            options.signal?.addEventListener('abort', () => {
              reject(new DOMException('The operation was aborted.', 'AbortError'));
            });
          })
      );

      const promise = generateSession('slow prompt');

      // Attach rejection handler early to prevent unhandled rejection
      const resultPromise = promise.catch((e: Error) => e);

      // Advance past the 30s timeout
      await vi.advanceTimersByTimeAsync(30000);

      const error = await resultPromise;
      expect(error).toBeInstanceOf(Error);
      expect((error as Error).message).toBe('Request timeout - server took too long to respond');
    });
  });

  // =============================================
  // Correlation ID added to headers
  // =============================================
  describe('correlation ID in headers', () => {
    it('includes X-Correlation-ID header on every request', async () => {
      fetchMock.mockResolvedValueOnce(mockResponse({ sessionId: 'abc', status: 'ok' }, 200));

      await generateSession('test');

      const callArgs = fetchMock.mock.calls[0];
      const requestOptions = callArgs[1];
      expect(requestOptions.headers['X-Correlation-ID']).toBe('test-corr-id');
    });
  });

  // =============================================
  // generateSession sends correct payload
  // =============================================
  describe('generateSession', () => {
    it('sends POST to /generate with prompt in body', async () => {
      const responseBody = { sessionId: 'session-123', status: 'created' };
      fetchMock.mockResolvedValueOnce(mockResponse(responseBody, 200));

      const result = await generateSession('a beautiful landscape');

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, options] = fetchMock.mock.calls[0];
      expect(url).toBe('https://api.test.com/generate');
      expect(options.method).toBe('POST');
      expect(JSON.parse(options.body)).toEqual({ prompt: 'a beautiful landscape' });
      expect(options.headers['Content-Type']).toBe('application/json');
      expect(result).toEqual(responseBody);
    });
  });

  // =============================================
  // iterateMultiple returns only successful results
  // =============================================
  describe('iterateMultiple', () => {
    it('returns only successful results from Promise.allSettled', async () => {
      // First model succeeds, second fails, third succeeds
      const successResult1 = { sessionId: 's1', model: 'gemini', iteration: 1, status: 'success' };
      const successResult2 = { sessionId: 's1', model: 'openai', iteration: 1, status: 'success' };

      // gemini succeeds
      fetchMock.mockResolvedValueOnce(mockResponse(successResult1, 200));
      // nova fails with 500
      fetchMock.mockResolvedValueOnce(mockResponse({ error: 'Internal error' }, 500, 'Internal Server Error'));
      // openai succeeds
      fetchMock.mockResolvedValueOnce(mockResponse(successResult2, 200));

      const result = await iterateMultiple('s1', ['gemini', 'nova', 'openai'], 'refine this');

      expect(result).toHaveLength(2);
      expect(result[0]).toEqual(successResult1);
      expect(result[1]).toEqual(successResult2);
    });

    it('returns empty array when all requests fail', async () => {
      fetchMock
        .mockResolvedValueOnce(mockResponse({ error: 'fail' }, 500, 'Internal Server Error'))
        .mockResolvedValueOnce(mockResponse({ error: 'fail' }, 500, 'Internal Server Error'));

      const result = await iterateMultiple('s1', ['gemini', 'nova'], 'refine');

      expect(result).toHaveLength(0);
    });
  });

  // =============================================
  // enhancePrompt sends correct payload
  // =============================================
  describe('enhancePrompt', () => {
    it('sends POST to /enhance with prompt in body', async () => {
      const responseBody = {
        enhanced_prompt: 'a beautiful landscape with mountains',
        original_prompt: 'landscape',
      };
      fetchMock.mockResolvedValueOnce(mockResponse(responseBody, 200));

      const result = await enhancePrompt('landscape');

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, options] = fetchMock.mock.calls[0];
      expect(url).toBe('https://api.test.com/enhance');
      expect(options.method).toBe('POST');
      expect(JSON.parse(options.body)).toEqual({ prompt: 'landscape' });
      expect(result).toEqual(responseBody);
    });
  });

  // =============================================
  // Auth/billing interceptors
  // =============================================
  describe('auth and billing interceptors', () => {
    it('attaches Authorization header when idToken is present', async () => {
      const { useAuthStore } = await import('../../../src/stores/useAuthStore');
      useAuthStore.setState({
        idToken: 'jwt-abc',
        accessToken: 'at',
        refreshToken: null,
        expiresAt: Date.now() + 60_000,
        user: { sub: 's', email: 'e@e' },
      });
      fetchMock.mockResolvedValueOnce(mockResponse({ sessionId: 'x', status: 'created' }, 200));

      await generateSession('hi');

      const [, options] = fetchMock.mock.calls[0];
      expect((options.headers as Record<string, string>).Authorization).toBe('Bearer jwt-abc');
      useAuthStore.getState().clearTokens();
    });

    it('on 401 clears tokens and redirects to hosted UI login', async () => {
      const { useAuthStore } = await import('../../../src/stores/useAuthStore');
      useAuthStore.setState({
        idToken: 'jwt-abc',
        accessToken: 'at',
        refreshToken: null,
        expiresAt: Date.now() + 60_000,
        user: { sub: 's', email: 'e@e' },
      });
      const assignMock = vi.fn();
      vi.stubGlobal('window', {
        ...window,
        location: { ...window.location, assign: assignMock },
      } as unknown as Window);
      fetchMock.mockResolvedValueOnce(mockResponse({ error: 'unauthorized' }, 401));

      await expect(generateSession('hi')).rejects.toThrow();
      expect(useAuthStore.getState().idToken).toBeNull();
      expect(assignMock).toHaveBeenCalledWith('https://auth.test.com/login');
    });

    it('on 402 surfaces an upgrade warning toast', async () => {
      const { useToastStore } = await import('../../../src/stores/useToastStore');
      const warnSpy = vi.spyOn(useToastStore.getState(), 'warning');
      fetchMock.mockResolvedValueOnce(
        mockResponse({ error: 'subscription required', code: 'subscription_required' }, 402),
      );

      await expect(generateSession('hi')).rejects.toThrow();
      expect(warnSpy).toHaveBeenCalled();
    });

    it('on 429 surfaces a quota warning toast immediately', async () => {
      const { useToastStore } = await import('../../../src/stores/useToastStore');
      const warnSpy = vi.spyOn(useToastStore.getState(), 'warning');
      // 429 is no longer retried, so the toast fires on the first response
      // rather than after the retries are exhausted.
      fetchMock.mockResolvedValue(mockResponse({ error: 'quota exceeded' }, 429));

      await generateSession('hi').catch(() => null);

      expect(warnSpy).toHaveBeenCalled();
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
  });

  // =============================================
  // getRecentPrompts
  // =============================================
  describe('getRecentPrompts', () => {
    it('sends GET to /prompts/recent with limit param', async () => {
      const responseBody = { prompts: [{ prompt: 'test', sessionId: 's1', createdAt: 1000 }], total: 1 };
      fetchMock.mockResolvedValueOnce(mockResponse(responseBody, 200));

      const result = await getRecentPrompts(20);

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, options] = fetchMock.mock.calls[0];
      expect(url).toBe('https://api.test.com/prompts/recent?limit=20');
      expect(options.method).toBe('GET');
      expect(result).toEqual(responseBody);
    });

    it('uses default limit when not specified', async () => {
      const responseBody = { prompts: [], total: 0 };
      fetchMock.mockResolvedValueOnce(mockResponse(responseBody, 200));

      await getRecentPrompts();

      const [url] = fetchMock.mock.calls[0];
      expect(url).toBe('https://api.test.com/prompts/recent?limit=20');
    });
  });

  // =============================================
  // getPromptHistory
  // =============================================
  describe('getPromptHistory', () => {
    it('sends GET to /prompts/history with limit', async () => {
      const responseBody = { prompts: [], total: 0 };
      fetchMock.mockResolvedValueOnce(mockResponse(responseBody, 200));

      await getPromptHistory(10);

      const [url, options] = fetchMock.mock.calls[0];
      expect(url).toBe('https://api.test.com/prompts/history?limit=10');
      expect(options.method).toBe('GET');
    });

    it('includes query param when provided', async () => {
      const responseBody = { prompts: [], total: 0 };
      fetchMock.mockResolvedValueOnce(mockResponse(responseBody, 200));

      await getPromptHistory(10, 'landscape');

      const [url] = fetchMock.mock.calls[0];
      expect(url).toBe('https://api.test.com/prompts/history?limit=10&q=landscape');
    });
  });

  // =============================================
  // getDownloadUrl
  // =============================================
  describe('getDownloadUrl', () => {
    it('sends GET to /download/{sessionId}/{model}/{iterationIndex}', async () => {
      const responseBody = { url: 'https://s3.example.com/presigned', filename: 'gemini-1.png' };
      fetchMock.mockResolvedValueOnce(mockResponse(responseBody, 200));

      const result = await getDownloadUrl('session-123', 'gemini', 2);

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, options] = fetchMock.mock.calls[0];
      expect(url).toBe('https://api.test.com/download/session-123/gemini/2');
      expect(options.method).toBe('GET');
      expect(result).toEqual(responseBody);
    });
  });
});

describe('error code contract', () => {
  /**
   * The backend puts its machine-readable code in `error` and never emits a
   * `code` field. Callers match on `code`, so apiFetch has to fall back to
   * `error` -- without it, every such match is permanently false. That is
   * exactly how the age gate shipped broken: the panel checked for
   * AGE_VERIFICATION_REQUIRED against a field nothing ever populated, so the
   * modal never opened and the user saw a raw error string instead.
   */
  it('exposes the backend error code as .code', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      statusText: 'Forbidden',
      headers: new Headers(),
      json: async () => ({
        error: 'AGE_VERIFICATION_REQUIRED',
        message: 'You must confirm you are 18 or older to use this service.',
      }),
    }) as unknown as typeof fetch;

    await expect(generateSession('a cat')).rejects.toMatchObject({
      status: 403,
      code: 'AGE_VERIFICATION_REQUIRED',
    });
  });

  it('prefers an explicit code field when the backend sends one', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      statusText: 'Bad Request',
      headers: new Headers(),
      json: async () => ({ error: 'OUTER', code: 'INNER', message: 'x' }),
    }) as unknown as typeof fetch;

    await expect(generateSession('a cat')).rejects.toMatchObject({ code: 'INNER' });
  });
});
