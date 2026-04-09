/**
 * Cognito token exchange client.
 * Public-client (no secret) authorization-code flow against the Cognito
 * Hosted UI `/oauth2/token` endpoint.
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

export async function exchangeCodeForTokens(code: string): Promise<CognitoTokens> {
  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: COGNITO_CLIENT_ID,
    code,
    redirect_uri: COGNITO_REDIRECT_URI,
  });

  const response = await fetch(`${COGNITO_DOMAIN}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });

  if (!response.ok) {
    throw new Error(`Cognito token exchange failed: ${response.status}`);
  }

  const data = (await response.json()) as CognitoTokenResponse;
  return {
    idToken: data.id_token,
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
    expiresIn: data.expires_in,
  };
}
