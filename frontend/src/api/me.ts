/**
 * /me endpoint client.
 * Shape matches ADR-10 in docs/plans/2026-04-08-paid-tier/Phase-0.md.
 */

import { API_BASE_URL, API_ROUTES } from './config';
import { useAuthStore } from '@/stores/useAuthStore';

export interface QuotaCounter {
  used: number;
  limit: number;
}

export interface MeQuota {
  windowSeconds: number;
  windowStart: number;
  generate?: QuotaCounter;
  refine: QuotaCounter;
}

export interface MeBilling {
  subscriptionStatus: string | null;
  portalAvailable: boolean;
}

export interface MeResponse {
  userId: string;
  email: string;
  tier: 'guest' | 'free' | 'paid';
  quota: MeQuota;
  billing: MeBilling;
  groups?: string[];
}

export async function fetchMe(): Promise<MeResponse> {
  const token = useAuthStore.getState().idToken;
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE_URL}${API_ROUTES.ME}`, {
    method: 'GET',
    headers,
  });
  if (!response.ok) {
    throw new Error(`GET /me failed: ${response.status}`);
  }
  return (await response.json()) as MeResponse;
}
