/**
 * Admin API client.
 * Typed functions for all admin dashboard endpoints.
 * All requests include the JWT Authorization header.
 */

import { API_BASE_URL, API_ROUTES } from './config';
import { useAuthStore } from '@/stores/useAuthStore';

// ---- Response types ----

export interface AdminUser {
  userId: string;
  email: string;
  tier: string;
  isSuspended?: boolean;
  generateCount?: number;
  refineCount?: number;
  dailyCount?: number;
  createdAt?: number;
  updatedAt?: number;
  stripeCustomerId?: string;
  subscriptionStatus?: string;
}

export interface AdminUsersResponse {
  users: AdminUser[];
  nextKey: string | null;
}

export interface AdminModel {
  name: string;
  provider: string;
  enabled: boolean;
  dailyCount: number;
  dailyCap: number;
}

export interface AdminModelsResponse {
  models: AdminModel[];
}

export interface MetricsSnapshot {
  date: string;
  modelCounts: Record<string, number>;
  usersByTier: Record<string, number>;
  suspendedCount: number;
  revenue?: Record<string, number>;
}

export interface AdminMetricsResponse {
  today: MetricsSnapshot | null;
  history: MetricsSnapshot[];
}

export interface RevenueCurrent {
  activeSubscribers: number;
  mrr: number;
  monthlyChurn: number;
  updatedAt: number;
}

export interface AdminRevenueResponse {
  current: RevenueCurrent;
  history: MetricsSnapshot[];
}

// ---- Helpers ----

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  try {
    const token = useAuthStore.getState().idToken;
    if (token) headers.Authorization = `Bearer ${token}`;
  } catch {
    // store unavailable
  }
  return headers;
}

async function adminGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'GET',
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw new Error(`GET ${path} failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

async function adminPost<T>(path: string, body?: Record<string, unknown>): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(body ?? {}),
  });
  if (!response.ok) {
    throw new Error(`POST ${path} failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

// ---- User endpoints ----

export async function fetchAdminUsers(params?: {
  limit?: number;
  lastKey?: string;
  tier?: string;
  suspended?: boolean;
}): Promise<AdminUsersResponse> {
  const query = new URLSearchParams();
  if (params?.limit !== undefined) query.set('limit', String(params.limit));
  if (params?.lastKey) query.set('lastKey', params.lastKey);
  if (params?.tier) query.set('tier', params.tier);
  if (params?.suspended !== undefined) query.set('suspended', String(params.suspended));
  const qs = query.toString();
  const path = `${API_ROUTES.ADMIN_USERS}${qs ? `?${qs}` : ''}`;
  return adminGet<AdminUsersResponse>(path);
}

export async function fetchAdminUserDetail(userId: string): Promise<AdminUser> {
  return adminGet<AdminUser>(`${API_ROUTES.ADMIN_USERS}/${userId}`);
}

export async function suspendUser(userId: string, reason?: string): Promise<void> {
  await adminPost(`${API_ROUTES.ADMIN_USERS}/${userId}/suspend`, { reason });
}

export async function unsuspendUser(userId: string): Promise<void> {
  await adminPost(`${API_ROUTES.ADMIN_USERS}/${userId}/unsuspend`);
}

export async function notifyUser(
  userId: string,
  type: string,
  message: string,
  subject?: string,
): Promise<void> {
  await adminPost(`${API_ROUTES.ADMIN_USERS}/${userId}/notify`, { type, message, subject });
}

// ---- Model endpoints ----

export async function fetchAdminModels(): Promise<AdminModelsResponse> {
  return adminGet<AdminModelsResponse>(API_ROUTES.ADMIN_MODELS);
}

export async function disableModel(model: string): Promise<void> {
  await adminPost(`${API_ROUTES.ADMIN_MODELS}/${model}/disable`);
}

export async function enableModel(model: string): Promise<void> {
  await adminPost(`${API_ROUTES.ADMIN_MODELS}/${model}/enable`);
}

// ---- Metrics and revenue endpoints ----

export async function fetchAdminMetrics(days?: number): Promise<AdminMetricsResponse> {
  const query = days !== undefined ? `?days=${days}` : '';
  return adminGet<AdminMetricsResponse>(`${API_ROUTES.ADMIN_METRICS}${query}`);
}

export async function fetchAdminRevenue(): Promise<AdminRevenueResponse> {
  return adminGet<AdminRevenueResponse>(API_ROUTES.ADMIN_REVENUE);
}
