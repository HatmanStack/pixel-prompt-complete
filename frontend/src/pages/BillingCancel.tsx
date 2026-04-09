/**
 * BillingCancel page.
 * Simple message shown when the user cancels Stripe Checkout.
 */

import type { FC } from 'react';

export const BillingCancel: FC = () => (
  <div className="min-h-screen flex items-center justify-center p-6 text-center">
    <div>
      <h1 className="text-2xl font-semibold mb-2">Checkout canceled</h1>
      <p className="text-sm text-gray-400 mb-4">No charges were made.</p>
      <a href="/" className="underline text-accent">
        Return home
      </a>
    </div>
  </div>
);

export default BillingCancel;
