/**
 * BillingSuccess page.
 * Simple confirmation shown after a successful Stripe Checkout redirect.
 */

import type { FC } from 'react';

export const BillingSuccess: FC = () => (
  <div className="min-h-screen flex items-center justify-center p-6 text-center">
    <div>
      <h1 className="text-2xl font-semibold mb-2">Subscription active</h1>
      <p className="text-sm text-gray-400 mb-4">Thanks for upgrading.</p>
      <a href="/" className="underline text-accent">
        Return home
      </a>
    </div>
  </div>
);

export default BillingSuccess;
