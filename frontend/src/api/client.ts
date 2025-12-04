/**
 * API Client
 * Handles all communication with the backend Lambda function
 */

import { API_BASE_URL, API_ROUTES, REQUEST_TIMEOUT, RETRY_CONFIG } from './config';
import { generateCorrelationId } from '../utils/correlation';
import type {
  GenerateResponse,
  StatusResponse,
  EnhanceResponse,
  GalleryListResponse,
  GalleryDetailResponse,
  ApiError,
} from '@/types';

interface FetchOptions extends RequestInit {
  correlationId?: string;
}

interface ApiErrorWithMeta extends Error {
  status?: number;
  code?: string;
  correlationId?: string;
}

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
  retryCount = 0
): Promise<T> {
  // Create abort controller for timeout
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);

  // Generate correlation ID for request tracing (or use provided one)
  const correlationId = options.correlationId || generateCorrelationId();

  try {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'X-Correlation-ID': correlationId,
        ...options.headers,
      },
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    // Handle HTTP errors
    if (!response.ok) {
      const errorData: Partial<ApiError> = await response.json().catch(() => ({}));
      const error: ApiErrorWithMeta = new Error(
        errorData.error || errorData.message || `HTTP ${response.status}: ${response.statusText}`
      );
      error.status = response.status;
      error.code = errorData.code;
      throw error;
    }

    return (await response.json()) as T;
  } catch (error) {
    clearTimeout(timeoutId);

    const apiError = error as ApiErrorWithMeta;

    // Handle timeout errors
    if (apiError.name === 'AbortError') {
      const timeoutError: ApiErrorWithMeta = new Error(
        'Request timeout - server took too long to respond'
      );
      timeoutError.code = 'TIMEOUT';
      throw timeoutError;
    }

    // Retry on network errors (not HTTP errors)
    if (retryCount < RETRY_CONFIG.maxRetries && !apiError.status) {
      const delay = Math.min(
        RETRY_CONFIG.initialDelay * Math.pow(2, retryCount),
        RETRY_CONFIG.maxDelay
      );

      await sleep(delay);

      // Pass correlation ID to retry
      return apiFetch<T>(endpoint, { ...options, correlationId }, retryCount + 1);
    }

    // Add correlation ID to error for logging
    apiError.correlationId = correlationId;

    // Log and rethrow error
    console.error('API request failed:', apiError);
    throw apiError;
  }
}

/**
 * Generate images from prompt
 */
export async function generateImages(prompt: string): Promise<GenerateResponse> {
  return apiFetch<GenerateResponse>(API_ROUTES.GENERATE, {
    method: 'POST',
    body: JSON.stringify({
      prompt,
    }),
  });
}

/**
 * Get job status by job ID
 */
export async function getJobStatus(jobId: string): Promise<StatusResponse> {
  return apiFetch<StatusResponse>(`${API_ROUTES.STATUS}/${jobId}`, {
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
 * List all galleries
 */
export async function listGalleries(): Promise<GalleryListResponse> {
  return apiFetch<GalleryListResponse>(API_ROUTES.GALLERY_LIST, {
    method: 'GET',
  });
}

/**
 * Get gallery details and all images
 */
export async function getGallery(galleryId: string): Promise<GalleryDetailResponse> {
  return apiFetch<GalleryDetailResponse>(`${API_ROUTES.GALLERY_DETAIL}/${galleryId}`, {
    method: 'GET',
  });
}

// Export configuration for testing
export { API_BASE_URL, API_ROUTES };
