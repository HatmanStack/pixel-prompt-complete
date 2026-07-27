/**
 * API Client
 * Handles all communication with the backend Lambda function
 */

import {
  API_BASE_URL,
  API_ROUTES,
  AUTH_ENABLED,
  REQUEST_TIMEOUT,
  RETRY_CONFIG,
  hostedUiLoginUrl,
} from './config';
import { generateCorrelationId } from '../utils/correlation';
import { useAuthStore } from '../stores/useAuthStore';
import { useToastStore } from '../stores/useToastStore';
import type {
  EnhanceResponse,
  ApiError,
  Session,
  SessionGenerateResponse,
  IterateResponse,
  OutpaintResponse,
  OutpaintPreset,
  ModelName,
  SessionGalleryListResponse,
  SessionGalleryDetailResponse,
  PromptHistoryResponse,
  DownloadResponse,
} from '@/types';

interface FetchOptions extends RequestInit {
  correlationId?: string;
}

interface ApiErrorWithMeta extends Error {
  status?: number;
  code?: string;
  correlationId?: string;
  /** Seconds parsed off the response's `Retry-After` header, when it had one. */
  retryAfter?: number;
}

// HTTP status codes that are safe to retry.
//
// 429 is deliberately absent. A rolling-window quota cannot succeed a second
// later, and every retry re-enters enforce_quota on the backend -- DynamoDB
// writes on a request already known to be denied, inflating the quota-rejection
// alarm with traffic the client generated after being told no.
const RETRYABLE_STATUS_CODES = [502, 503, 504];

// Only these may be retried. Every other method may have changed server state
// before the failure reached us: POST /generate, /iterate and /outpaint are
// credit-charged and provider-billed, and a 504 means the gateway gave up
// while the Lambda kept going.
const IDEMPOTENT_METHODS = ['GET', 'HEAD'];

/**
 * Parse a `Retry-After` header into milliseconds.
 *
 * The backend emits delay-seconds. The HTTP-date form is legal but unused
 * here, so anything non-numeric is ignored in favour of the exponential
 * backoff rather than guessed at.
 */
function parseRetryAfter(header: string | null): number | undefined {
  if (!header) return undefined;
  const seconds = Number(header);
  if (!Number.isFinite(seconds) || seconds <= 0) return undefined;
  return seconds * 1000;
}

// In-flight redirect promise to prevent duplicate PKCE/state creation on concurrent 401s
let redirectPromise: Promise<void> | null = null;

/**
 * Sleep utility for retry backoff
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Generic fetch wrapper with error handling, timeout, and retry logic
 */
async function apiFetch<T>(
  endpoint: string,
  options: FetchOptions = {},
  retryCount = 0,
): Promise<T> {
  // Create abort controller for timeout
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);

  // Generate correlation ID for request tracing (or use provided one)
  const correlationId = options.correlationId || generateCorrelationId();

  // `fetch` defaults to GET when no method is given.
  const method = (options.method ?? 'GET').toUpperCase();

  try {
    // Attach Authorization header when signed in
    const authHeaders: Record<string, string> = {};
    try {
      const idToken = useAuthStore.getState().idToken;
      if (idToken) authHeaders.Authorization = `Bearer ${idToken}`;
    } catch {
      // store unavailable (e.g. during tests) — ignore
    }

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-Correlation-ID': correlationId,
        ...authHeaders,
        ...options.headers,
      },
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    // Handle HTTP errors
    if (!response.ok) {
      const errorData: Partial<ApiError> = await response.json().catch(() => ({}));
      const error: ApiErrorWithMeta = new Error(
        errorData.error || errorData.message || `HTTP ${response.status}: ${response.statusText}`,
      );
      error.status = response.status;
      // The backend puts its machine-readable code in `error`; `code` is a
      // field it never emits. Without this fallback, every caller matching on
      // a specific failure has to string-match the human-readable message.
      error.code = errorData.code ?? errorData.error;
      // Read off the response here: the retry decision is made in the catch
      // block, where the Response object is out of scope.
      error.retryAfter = parseRetryAfter(response.headers.get('Retry-After'));

      // Auth/billing response interceptors
      if (response.status === 401) {
        try {
          useAuthStore.getState().clearTokens();
        } catch {
          // ignore
        }
        if (AUTH_ENABLED && typeof window !== 'undefined' && !redirectPromise) {
          redirectPromise = hostedUiLoginUrl()
            .then((url) => window.location.assign(url))
            .catch((err) => console.error('Failed to generate login URL:', err))
            .finally(() => {
              redirectPromise = null;
            });
        }
      } else if (response.status === 402) {
        try {
          useToastStore.getState().warning(error.message || 'Upgrade required to continue.');
        } catch {
          // ignore
        }
      }

      throw error;
    }

    return (await response.json()) as T;
  } catch (error) {
    clearTimeout(timeoutId);

    const apiError = error as ApiErrorWithMeta;

    // Handle timeout errors
    if (apiError.name === 'AbortError') {
      const timeoutError: ApiErrorWithMeta = new Error(
        'Request timeout - server took too long to respond',
      );
      timeoutError.code = 'TIMEOUT';
      throw timeoutError;
    }

    // Determine if we should retry. A non-idempotent request is never
    // retried, whatever it failed with -- including a network error, which is
    // exactly the case where the server may already have done the work.
    const isIdempotent = IDEMPOTENT_METHODS.includes(method);
    const isRetryableStatus = apiError.status && RETRYABLE_STATUS_CODES.includes(apiError.status);
    const isNetworkError =
      !apiError.status &&
      (apiError.name === 'TypeError' || Boolean(apiError.message?.includes('fetch')));
    const shouldRetry =
      isIdempotent && retryCount < RETRY_CONFIG.maxRetries && (isRetryableStatus || isNetworkError);

    if (shouldRetry) {
      const backoff = Math.min(
        RETRY_CONFIG.initialDelay * Math.pow(2, retryCount),
        RETRY_CONFIG.maxDelay,
      );
      // A server that says when to come back knows better than our backoff
      // curve does -- but clamp it, so a hostile or mistaken header cannot
      // hang the UI for minutes.
      const delay =
        apiError.retryAfter !== undefined
          ? Math.min(apiError.retryAfter, RETRY_CONFIG.maxDelay)
          : backoff;

      await sleep(delay);

      // Pass correlation ID to retry
      return apiFetch<T>(endpoint, { ...options, correlationId }, retryCount + 1);
    }

    // 429 is not retried at all, so this fires on the first response
    if (apiError.status === 429) {
      try {
        useToastStore
          .getState()
          .warning(apiError.message || 'Quota exceeded. Please try again later.');
      } catch {
        // ignore
      }
    }

    // Add correlation ID to error for logging
    apiError.correlationId = correlationId;

    // Log and rethrow error
    console.error('API request failed:', apiError);
    throw apiError;
  }
}

// ====================
// Session-based API Methods (New)
// ====================

/**
 * Generate images from prompt (session-based)
 */
export async function generateSession(
  prompt: string,
  captchaToken?: string,
  ageAffirmed?: boolean,
): Promise<SessionGenerateResponse> {
  const body: Record<string, string | boolean> = { prompt };
  if (captchaToken) {
    body.captchaToken = captchaToken;
  }
  // Sent only on the request that follows the user actually confirming. The
  // backend records it against their identity, so it is not sent again.
  if (ageAffirmed) {
    body.ageAffirmed = true;
  }
  return apiFetch<SessionGenerateResponse>(API_ROUTES.GENERATE, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/**
 * Get session status by session ID
 */
export async function getSessionStatus(sessionId: string): Promise<Session> {
  return apiFetch<Session>(`${API_ROUTES.STATUS}/${sessionId}`, {
    method: 'GET',
  });
}

/**
 * Iterate on a single model's image
 */
export async function iterateImage(
  sessionId: string,
  model: ModelName,
  prompt: string,
): Promise<IterateResponse> {
  return apiFetch<IterateResponse>(API_ROUTES.ITERATE, {
    method: 'POST',
    body: JSON.stringify({ sessionId, model, prompt }),
  });
}

/**
 * Outpaint an image with a preset aspect ratio
 */
export async function outpaintImage(
  sessionId: string,
  model: ModelName,
  iterationIndex: number,
  preset: OutpaintPreset,
  prompt: string,
): Promise<OutpaintResponse> {
  return apiFetch<OutpaintResponse>(API_ROUTES.OUTPAINT, {
    method: 'POST',
    body: JSON.stringify({
      sessionId,
      model,
      iterationIndex,
      preset,
      prompt,
    }),
  });
}

/**
 * Iterate on multiple models at once (batch operation)
 */
export async function iterateMultiple(
  sessionId: string,
  models: ModelName[],
  prompt: string,
): Promise<IterateResponse[]> {
  const results = await Promise.allSettled(
    models.map((model) => iterateImage(sessionId, model, prompt)),
  );

  // Return successful results, log failures
  return results
    .map((result, index) => {
      if (result.status === 'fulfilled') {
        return result.value;
      } else {
        console.error(`Failed to iterate on ${models[index]}:`, result.reason);
        return null;
      }
    })
    .filter((r): r is IterateResponse => r !== null);
}

/**
 * List a page of gallery sessions, newest first.
 *
 * `limit` is optional on purpose: the backend clamps it to 1..50 and defaults
 * it to 20, so the bound is the server's guarantee rather than this client's
 * good behaviour.
 */
export async function listSessions(limit?: number): Promise<SessionGalleryListResponse> {
  const query = limit === undefined ? '' : `?limit=${limit}`;
  return apiFetch<SessionGalleryListResponse>(`${API_ROUTES.GALLERY_LIST}${query}`, {
    method: 'GET',
  });
}

/**
 * Get full session details from gallery
 */
export async function getSessionDetail(sessionId: string): Promise<SessionGalleryDetailResponse> {
  return apiFetch<SessionGalleryDetailResponse>(`${API_ROUTES.GALLERY_DETAIL}/${sessionId}`, {
    method: 'GET',
  });
}

/**
 * Enhance prompt using LLM
 */
export async function enhancePrompt(prompt: string): Promise<EnhanceResponse> {
  return apiFetch<EnhanceResponse>(API_ROUTES.ENHANCE, {
    method: 'POST',
    body: JSON.stringify({ prompt }),
  });
}

/**
 * Get recent prompts (global feed)
 */
export async function getRecentPrompts(limit = 20): Promise<PromptHistoryResponse> {
  return apiFetch<PromptHistoryResponse>(`${API_ROUTES.PROMPTS_RECENT}?limit=${limit}`, {
    method: 'GET',
  });
}

/**
 * Get prompt history for authenticated user
 */
export async function getPromptHistory(limit = 20, query?: string): Promise<PromptHistoryResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (query) params.set('q', query);
  return apiFetch<PromptHistoryResponse>(`${API_ROUTES.PROMPTS_HISTORY}?${params.toString()}`, {
    method: 'GET',
  });
}

/**
 * Get presigned download URL for an iteration's image
 */
export async function getDownloadUrl(
  sessionId: string,
  model: ModelName,
  iterationIndex: number,
): Promise<DownloadResponse> {
  return apiFetch<DownloadResponse>(
    `${API_ROUTES.DOWNLOAD}/${encodeURIComponent(sessionId)}/${encodeURIComponent(model)}/${iterationIndex}`,
    { method: 'GET' },
  );
}

// Export configuration for testing
export { API_BASE_URL, API_ROUTES };
