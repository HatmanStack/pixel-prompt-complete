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
  iterateMultiple,
  enhancePrompt,
} from '../../../src/api/client';

// Helper to create a mock Response
function mockResponse(body: unknown, status = 200, statusText = 'OK'): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
    json: () => Promise.resolve(body),
    headers: new Headers(),
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
  // Retry on 429 with backoff
  // =============================================
  describe('retry on 429 with backoff', () => {
    it('retries on 429 and eventually succeeds', async () => {
      const successBody = { sessionId: 'abc', status: 'created' };

      fetchMock
        .mockResolvedValueOnce(mockResponse({ error: 'Rate limited' }, 429, 'Too Many Requests'))
        .mockResolvedValueOnce(mockResponse({ error: 'Rate limited' }, 429, 'Too Many Requests'))
        .mockResolvedValueOnce(mockResponse(successBody, 200));

      const promise = generateSession('test prompt');

      // First retry: delay = max(1000 * 2^0, 1000) = 1000ms (429 minimum)
      await vi.advanceTimersByTimeAsync(1000);
      // Second retry: delay = max(1000 * 2^1, 1000) = 2000ms
      await vi.advanceTimersByTimeAsync(2000);

      const result = await promise;

      expect(result).toEqual(successBody);
      expect(fetchMock).toHaveBeenCalledTimes(3);
    });

    it('applies minimum 1000ms delay for 429 responses', async () => {
      // Even though initialDelay * 2^0 = 1000 already, for 429 the minimum
      // enforced is 1000ms. The key point: 429 delay >= 1000ms always.
      const successBody = { sessionId: 'abc', status: 'created' };

      fetchMock
        .mockResolvedValueOnce(mockResponse({ error: 'Rate limited' }, 429, 'Too Many Requests'))
        .mockResolvedValueOnce(mockResponse(successBody, 200));

      const promise = generateSession('test prompt');

      // Advance less than the minimum 429 delay -- should NOT have retried yet
      await vi.advanceTimersByTimeAsync(500);
      expect(fetchMock).toHaveBeenCalledTimes(1);

      // Advance to complete the 1000ms delay
      await vi.advanceTimersByTimeAsync(500);

      const result = await promise;
      expect(result).toEqual(successBody);
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
  });

  // =============================================
  // Retry on network error
  // =============================================
  describe('retry on network error', () => {
    it('retries when fetch throws a network error (no status)', async () => {
      const networkError = new TypeError('Failed to fetch');
      const successBody = { sessionId: 'abc', status: 'created' };

      fetchMock
        .mockRejectedValueOnce(networkError)
        .mockResolvedValueOnce(mockResponse(successBody, 200));

      const promise = generateSession('test prompt');

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

      const promise = generateSession('test prompt');

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

    it('on final 429 surfaces a quota warning toast', async () => {
      const { useToastStore } = await import('../../../src/stores/useToastStore');
      const warnSpy = vi.spyOn(useToastStore.getState(), 'warning');
      // 4 retries will all be 429, eventually rejecting
      fetchMock.mockResolvedValue(mockResponse({ error: 'quota exceeded' }, 429));

      const p = generateSession('hi').catch(() => null);
      await vi.advanceTimersByTimeAsync(10_000);
      await p;
      expect(warnSpy).toHaveBeenCalled();
    });
  });
});
