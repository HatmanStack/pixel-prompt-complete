/**
 * Billing API client (Stripe checkout + customer portal).
 */

import { API_BASE_URL, API_ROUTES } from './config';
import { useAuthStore } from '@/stores/useAuthStore';

interface RedirectResponse {
  url: string;
}

async function postRedirect(path: string): Promise<string> {
  const token = useAuthStore.getState().idToken;
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify({}),
  });
  if (!response.ok) {
    throw new Error(`POST ${path} failed: ${response.status}`);
  }
  const data = (await response.json()) as RedirectResponse;
  return data.url;
}

export function startCheckout(): Promise<string> {
  return postRedirect(API_ROUTES.BILLING_CHECKOUT);
}

export function openBillingPortal(): Promise<string> {
  return postRedirect(API_ROUTES.BILLING_PORTAL);
}
