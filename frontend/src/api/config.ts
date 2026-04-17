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

// Admin and CAPTCHA feature flags
export const ADMIN_ENABLED: boolean =
  (import.meta.env.VITE_ADMIN_ENABLED as string | undefined) === 'true';
export const CAPTCHA_ENABLED: boolean =
  (import.meta.env.VITE_CAPTCHA_ENABLED as string | undefined) === 'true';
export const TURNSTILE_SITE_KEY: string =
  (import.meta.env.VITE_TURNSTILE_SITE_KEY as string | undefined) ?? '';

// Validate required Cognito vars when auth is enabled
if (AUTH_ENABLED) {
  const missing = [
    ['VITE_COGNITO_DOMAIN', COGNITO_DOMAIN],
    ['VITE_COGNITO_CLIENT_ID', COGNITO_CLIENT_ID],
    ['VITE_COGNITO_REDIRECT_URI', COGNITO_REDIRECT_URI],
    ['VITE_COGNITO_LOGOUT_URI', COGNITO_LOGOUT_URI],
  ]
    .filter(([, v]) => !v)
    .map(([k]) => k);
  if (missing.length > 0) {
    throw new Error(
      `AUTH_ENABLED is true but the following Cognito env vars are missing: ${missing.join(', ')}`,
    );
  }
}

/**
 * Generate a random state nonce, store it in sessionStorage, and return it.
 */
function generateStateNonce(): string {
  const array = new Uint8Array(24);
  crypto.getRandomValues(array);
  const nonce = Array.from(array, (b) => b.toString(16).padStart(2, '0')).join('');
  sessionStorage.setItem('oauth_state', nonce);
  return nonce;
}

/**
 * Verify and consume the state nonce from sessionStorage.
 * Returns true if valid, false otherwise.
 */
export function verifyStateNonce(state: string | null): boolean {
  if (!state) return false;
  const expected = sessionStorage.getItem('oauth_state');
  sessionStorage.removeItem('oauth_state');
  return expected !== null && expected === state;
}

/**
 * Build the Cognito Hosted UI login URL for the authorization-code flow
 * with PKCE and a CSRF state nonce.
 */
export async function hostedUiLoginUrl(): Promise<string> {
  const { generatePkceChallenge } = await import('./cognito');
  const state = generateStateNonce();
  const codeChallenge = await generatePkceChallenge();
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: COGNITO_CLIENT_ID,
    redirect_uri: COGNITO_REDIRECT_URI,
    scope: 'openid email profile',
    state,
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
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

  // Prompt history endpoints
  PROMPTS_RECENT: '/prompts/recent',
  PROMPTS_HISTORY: '/prompts/history',

  // Download endpoint
  DOWNLOAD: '/download',

  // Admin endpoints
  ADMIN_USERS: '/admin/users',
  ADMIN_MODELS: '/admin/models',
  ADMIN_METRICS: '/admin/metrics',
  ADMIN_REVENUE: '/admin/revenue',
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
