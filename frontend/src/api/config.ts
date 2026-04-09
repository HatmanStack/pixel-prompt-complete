/**
 * API Configuration
 * Loads API endpoint from environment variables
 */

// Load API endpoint from environment variable
const apiEndpoint = import.meta.env.VITE_API_ENDPOINT as string | undefined;

// Validate API endpoint is configured
if (!apiEndpoint) {
  if (import.meta.env.PROD) {
    throw new Error(
      'VITE_API_ENDPOINT environment variable is not configured. ' +
        'Please set it to your API Gateway URL before building for production.',
    );
  } else {
    console.warn(
      'VITE_API_ENDPOINT is not set. API calls will fail. ' +
        'Set VITE_API_ENDPOINT in your .env file.',
    );
  }
}

export const API_BASE_URL: string = apiEndpoint || '';

// Auth / billing feature flags and Cognito config
export const AUTH_ENABLED: boolean =
  (import.meta.env.VITE_AUTH_ENABLED as string | undefined) === 'true';
export const BILLING_ENABLED: boolean =
  (import.meta.env.VITE_BILLING_ENABLED as string | undefined) === 'true';
export const COGNITO_DOMAIN: string =
  (import.meta.env.VITE_COGNITO_DOMAIN as string | undefined) ?? '';
export const COGNITO_CLIENT_ID: string =
  (import.meta.env.VITE_COGNITO_CLIENT_ID as string | undefined) ?? '';
export const COGNITO_REDIRECT_URI: string =
  (import.meta.env.VITE_COGNITO_REDIRECT_URI as string | undefined) ?? '';
export const COGNITO_LOGOUT_URI: string =
  (import.meta.env.VITE_COGNITO_LOGOUT_URI as string | undefined) ?? '';

/**
 * Build the Cognito Hosted UI login URL for the authorization-code flow.
 */
export function hostedUiLoginUrl(): string {
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: COGNITO_CLIENT_ID,
    redirect_uri: COGNITO_REDIRECT_URI,
    scope: 'openid email profile',
  });
  return `${COGNITO_DOMAIN}/login?${params.toString()}`;
}

/**
 * Build the Cognito Hosted UI logout URL.
 */
export function hostedUiLogoutUrl(): string {
  const params = new URLSearchParams({
    client_id: COGNITO_CLIENT_ID,
    logout_uri: COGNITO_LOGOUT_URI,
  });
  return `${COGNITO_DOMAIN}/logout?${params.toString()}`;
}

// API Routes
export const API_ROUTES = {
  // Session-based endpoints (new)
  GENERATE: '/generate',
  ITERATE: '/iterate',
  OUTPAINT: '/outpaint',
  STATUS: '/status',

  // Prompt enhancement
  ENHANCE: '/enhance',

  // Gallery endpoints
  GALLERY_LIST: '/gallery/list',
  GALLERY_DETAIL: '/gallery',

  // Auth / billing endpoints
  ME: '/me',
  BILLING_CHECKOUT: '/billing/checkout',
  BILLING_PORTAL: '/billing/portal',
} as const;

// Request timeout in milliseconds — image generation can take 120+ seconds
// for some providers (e.g., BFL polling), so allow 180s of headroom.
export const REQUEST_TIMEOUT = 180000; // 180 seconds

// Retry configuration
export const RETRY_CONFIG = {
  maxRetries: 3,
  initialDelay: 1000, // 1 second
  maxDelay: 4000, // 4 seconds
} as const;
