/**
 * API Client
 * Handles all communication with the backend Lambda function
 */

import { API_BASE_URL, API_ROUTES, REQUEST_TIMEOUT, RETRY_CONFIG } from './config';
import { generateCorrelationId } from '../utils/correlation';

/**
 * Sleep utility for retry backoff
 */
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Generic fetch wrapper with error handling, timeout, and retry logic
 */
async function apiFetch(endpoint, options = {}, retryCount = 0) {
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
      const errorData = await response.json().catch(() => ({}));
      const error = new Error(
        errorData.error || errorData.message || `HTTP ${response.status}: ${response.statusText}`
      );
      error.status = response.status;
      error.code = errorData.code;
      throw error;
    }

    return await response.json();
  } catch (error) {
    clearTimeout(timeoutId);

    // Handle timeout errors
    if (error.name === 'AbortError') {
      const timeoutError = new Error('Request timeout - server took too long to respond');
      timeoutError.code = 'TIMEOUT';
      throw timeoutError;
    }

    // Retry on network errors (not HTTP errors)
    if (retryCount < RETRY_CONFIG.maxRetries && !error.status) {
      const delay = Math.min(
        RETRY_CONFIG.initialDelay * Math.pow(2, retryCount),
        RETRY_CONFIG.maxDelay
      );

      console.log(`Retrying request (attempt ${retryCount + 1}/${RETRY_CONFIG.maxRetries}) after ${delay}ms...`);
      await sleep(delay);

      // Pass correlation ID to retry
      return apiFetch(endpoint, { ...options, correlationId }, retryCount + 1);
    }

    // Add correlation ID to error for logging
    error.correlationId = correlationId;

    // Log and rethrow error
    console.error('API request failed:', error);
    throw error;
  }
}

/**
 * Generate images from prompt and parameters
 * @param {string} prompt - The text prompt
 * @param {Object} params - Generation parameters (steps, guidance, etc.)
 * @returns {Promise<Object>} Response with jobId
 */
export async function generateImages(prompt, params = {}) {
  return apiFetch(API_ROUTES.GENERATE, {
    method: 'POST',
    body: JSON.stringify({
      prompt,
      steps: params.steps ?? 28,
      guidance: params.guidance ?? 5,
      control: params.control ?? 1.0,
    }),
  });
}

/**
 * Get job status by job ID
 * @param {string} jobId - The job ID to check
 * @returns {Promise<Object>} Job status object
 */
export async function getJobStatus(jobId) {
  return apiFetch(`${API_ROUTES.STATUS}/${jobId}`, {
    method: 'GET',
  });
}

/**
 * Enhance prompt using LLM
 * @param {string} prompt - The prompt to enhance
 * @returns {Promise<Object>} Enhanced prompt response
 */
export async function enhancePrompt(prompt) {
  return apiFetch(API_ROUTES.ENHANCE, {
    method: 'POST',
    body: JSON.stringify({ prompt }),
  });
}

/**
 * List all galleries
 * @returns {Promise<Object>} Gallery list with previews
 */
export async function listGalleries() {
  return apiFetch(API_ROUTES.GALLERY_LIST, {
    method: 'GET',
  });
}

/**
 * Get gallery details and all images
 * @param {string} galleryId - The gallery ID (timestamp folder name)
 * @returns {Promise<Object>} Gallery details with all images
 */
export async function getGallery(galleryId) {
  return apiFetch(`${API_ROUTES.GALLERY_DETAIL}/${galleryId}`, {
    method: 'GET',
  });
}

// Export configuration for testing
export { API_BASE_URL, API_ROUTES };
