/**
 * Pricing API client.
 *
 * Prices come from the backend rather than VITE_ build-time variables so a
 * price experiment is a config change instead of a frontend rebuild, and so
 * the UI cannot advertise a number the backend does not enforce.
 */

import { API_BASE_URL, API_ROUTES } from './config';

export interface PricingTier {
  id: 'free' | 'paid';
  name: string;
  priceUsdCents: number;
  monthlyCredits: number;
  allModels: boolean;
  renewal: 'fixed_window' | 'stripe_billing_period';
}

export interface Pricing {
  currency: string;
  creditsEnabled: boolean;
  billingEnabled: boolean;
  centiCreditsPerCredit: number;
  creditCosts: { generate: number; refine: number; outpaint: number };
  overageUsdCentsPerCredit: number;
  tiers: PricingTier[];
}

export async function fetchPricing(): Promise<Pricing> {
  const response = await fetch(`${API_BASE_URL}${API_ROUTES.PRICING}`);
  if (!response.ok) {
    throw new Error(`GET ${API_ROUTES.PRICING} failed: ${response.status}`);
  }
  return (await response.json()) as Pricing;
}

/** Render whole-cent prices as e.g. "$19" or "$19.50". */
export function formatUsdCents(cents: number): string {
  return cents % 100 === 0 ? `$${cents / 100}` : `$${(cents / 100).toFixed(2)}`;
}

/** Centi-credits to a display credit count, e.g. 6500 -> "65". */
export function formatCredits(centiCredits: number, scale = 100): string {
  const credits = centiCredits / scale;
  return Number.isInteger(credits) ? String(credits) : credits.toFixed(2);
}
