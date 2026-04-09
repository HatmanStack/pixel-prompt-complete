/**
 * Cognito token exchange client.
 * Public-client (no secret) authorization-code flow with PKCE against the
 * Cognito Hosted UI `/oauth2/token` endpoint.
 */

import { COGNITO_CLIENT_ID, COGNITO_DOMAIN, COGNITO_REDIRECT_URI } from './config';

export interface CognitoTokens {
  idToken: string;
  accessToken: string;
  refreshToken?: string;
  expiresIn: number;
}

interface CognitoTokenResponse {
  id_token: string;
  access_token: string;
  refresh_token?: string;
  expires_in: number;
  token_type: string;
}

/**
 * Generate a PKCE code verifier and store it in sessionStorage.
 * Returns the code_challenge (SHA-256, base64url-encoded).
 */
export async function generatePkceChallenge(): Promise<string> {
  const array = new Uint8Array(32);
  crypto.getRandomValues(array);
  const verifier = Array.from(array, (b) => b.toString(16).padStart(2, '0')).join('');
  sessionStorage.setItem('pkce_verifier', verifier);

  const encoder = new TextEncoder();
  const digest = await crypto.subtle.digest('SHA-256', encoder.encode(verifier));
  const base64 = btoa(String.fromCharCode(...new Uint8Array(digest)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
  return base64;
}

/**
 * Retrieve and consume the stored PKCE code verifier.
 */
function consumePkceVerifier(): string | null {
  const v = sessionStorage.getItem('pkce_verifier');
  sessionStorage.removeItem('pkce_verifier');
  return v;
}

export async function exchangeCodeForTokens(code: string): Promise<CognitoTokens> {
  const codeVerifier = consumePkceVerifier();

  const params: Record<string, string> = {
    grant_type: 'authorization_code',
    client_id: COGNITO_CLIENT_ID,
    code,
    redirect_uri: COGNITO_REDIRECT_URI,
  };
  if (codeVerifier) {
    params.code_verifier = codeVerifier;
  }

  const body = new URLSearchParams(params);

  const response = await fetch(`${COGNITO_DOMAIN}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });

  if (!response.ok) {
    throw new Error(`Cognito token exchange failed: ${response.status}`);
  }

  const data = (await response.json()) as CognitoTokenResponse;
  if (!data.id_token || !data.access_token) {
    throw new Error('Cognito token response missing required fields (id_token, access_token)');
  }
  return {
    idToken: data.id_token,
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
    expiresIn: data.expires_in,
  };
}
