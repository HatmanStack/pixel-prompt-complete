/**
 * API Configuration
 * Loads API endpoint from environment variables
 */

// Load API endpoint from environment variable
const apiEndpoint = import.meta.env.VITE_API_ENDPOINT;

// Validate API endpoint is configured
if (!apiEndpoint) {
  if (import.meta.env.PROD) {
    throw new Error(
      'VITE_API_ENDPOINT environment variable is not configured. ' +
      'Please set it to your API Gateway URL before building for production.'
    );
  } else {
    console.warn(
      'VITE_API_ENDPOINT is not set. API calls will fail. ' +
      'Set VITE_API_ENDPOINT in your .env file.'
    );
  }
}

export const API_BASE_URL = apiEndpoint || '';

// API Routes
export const API_ROUTES = {
  GENERATE: '/generate',
  STATUS: '/status',
  ENHANCE: '/enhance',
  GALLERY_LIST: '/gallery/list',
  GALLERY_DETAIL: '/gallery',
};

// Request timeout in milliseconds
export const REQUEST_TIMEOUT = 30000; // 30 seconds

// Retry configuration
export const RETRY_CONFIG = {
  maxRetries: 3,
  initialDelay: 1000, // 1 second
  maxDelay: 4000, // 4 seconds
};
