# Phase 4: Frontend Auth and Billing UX

## Phase Goal

Add Cognito Hosted UI sign-in, ID-token storage, Stripe Checkout redirect, tier-aware UI components, and graceful handling of 401/402/429 responses. Preserve the unauthenticated experience when `VITE_AUTH_ENABLED` is false.

**Success criteria:**

- Signed-out user can still hit `/generate` once (guest flow).
- "Sign in" button redirects to Cognito Hosted UI and back.
- Upgrade button redirects to Stripe Checkout.
- `/me` is polled after login and after generate/refine to keep the quota indicator fresh.
- All new components have Vitest coverage clearing the frontend coverage gate.

**Token estimate:** ~55k

## Prerequisites

- Phases 1–3 complete; backend deployed to a dev environment that the frontend dev server can hit (or mocked via MSW for local dev).
- Phase-0 ADRs 1, 7, 10.

## Task 4.1: Add Frontend Env Vars and Runtime Config

### Files to Modify

- `frontend/.env.example`
- `frontend/src/api/config.ts`

### Implementation Steps

1. Add env vars:

    ```text
    VITE_AUTH_ENABLED=false
    VITE_BILLING_ENABLED=false
    VITE_COGNITO_DOMAIN=
    VITE_COGNITO_CLIENT_ID=
    VITE_COGNITO_REDIRECT_URI=http://localhost:5173/auth/callback
    VITE_COGNITO_LOGOUT_URI=http://localhost:5173/
    ```

1. Expose them through `api/config.ts` as typed constants. Derive a `hostedUiLoginUrl()` helper that builds `https://{domain}/login?response_type=code&client_id={id}&redirect_uri={redirect}&scope=openid+email+profile`.

### Commit Message Template

```text
feat(frontend): add cognito env vars and runtime config
```

## Task 4.2: Auth Callback Route and PKCE-Less Code Exchange

### Goal

Handle the `/auth/callback?code=...` redirect from Cognito. Exchange the code for tokens via Cognito's token endpoint (public client, no secret), store the ID token in `sessionStorage`, redirect home.

### Files to Create

- `frontend/src/pages/AuthCallback.tsx`
- `frontend/src/api/cognito.ts`
- `frontend/tests/__tests__/api/cognito.test.ts`

### Implementation Steps

1. `cognito.ts` exports `exchangeCodeForTokens(code: string): Promise<{idToken, accessToken, refreshToken, expiresIn}>` — POSTs to `${VITE_COGNITO_DOMAIN}/oauth2/token` with `grant_type=authorization_code`, `client_id`, `code`, `redirect_uri`.
1. `AuthCallback.tsx` reads `?code=` from `window.location`, calls the exchange, stores tokens via a new `useAuthStore` action, then `window.location.replace("/")`.
1. Wire the route in `App.tsx` (or wherever routing is handled — the project uses a minimal state-driven layout; add a simple check on `window.location.pathname === "/auth/callback"`).
1. Tests mock `fetch` and verify token storage.

### Commit Message Template

```text
feat(frontend): add cognito auth callback and token exchange
```

## Task 4.3: useAuthStore (Zustand)

### Files to Create

- `frontend/src/stores/useAuthStore.ts`
- `frontend/tests/__tests__/stores/useAuthStore.test.ts`

### Implementation Steps

1. State: `{ idToken: string | null, accessToken: string | null, expiresAt: number | null, user: {sub, email} | null }`.
1. Actions: `setTokens(tokens)`, `clearTokens()`, `isAuthenticated()`.
1. Persist tokens in `sessionStorage` (`key: "pp_auth"`) — not `localStorage`, so closing the tab signs the user out.
1. On store creation, rehydrate from `sessionStorage` if present and unexpired.
1. Decode the JWT (no verification — purely to extract `sub` and `email` for UI; verification happens server-side).
1. Tests: set, clear, rehydrate, expired rehydrate is cleared.

### Commit Message Template

```text
feat(frontend): add auth store with session-scoped tokens
```

## Task 4.4: useBillingStore and /me Polling

### Files to Create

- `frontend/src/stores/useBillingStore.ts`
- `frontend/src/hooks/useMePolling.ts`
- `frontend/tests/__tests__/stores/useBillingStore.test.ts`
- `frontend/tests/__tests__/hooks/useMePolling.test.ts`

### Implementation Steps

1. `useBillingStore` holds the last `/me` payload and `refresh()` action that calls the API.
1. `useMePolling` runs `refresh()` on mount (if authenticated) and after each successful generate/iterate/outpaint (subscribes to `useAppStore`).
1. Tests use `vi.useFakeTimers` and mock the API.

### Commit Message Template

```text
feat(frontend): add billing store and /me polling
```

## Task 4.5: API Client Authorization Header and Error Handling

### Files to Modify

- `frontend/src/api/client.ts`

### Implementation Steps

1. Inject a request interceptor (or a small wrapper) that reads the current ID token from `useAuthStore` and adds `Authorization: Bearer <token>` when present.
1. Add a response interceptor that, on 401, clears auth tokens and redirects to `hostedUiLoginUrl()`; on 402 (`code: subscription_required`), opens the upgrade modal (via a toast action); on 429/402 with quota codes, surfaces a toast with the reset time from `/me`.
1. Update or add tests: `frontend/tests/__tests__/api/client.test.ts` covering all three interceptor branches.

### Commit Message Template

```text
feat(frontend): attach auth header and handle 401/402/429
```

## Task 4.6: TierBanner and QuotaIndicator Components

### Files to Create

- `frontend/src/components/TierBanner.tsx`
- `frontend/src/components/QuotaIndicator.tsx`
- `frontend/tests/__tests__/components/TierBanner.test.tsx`
- `frontend/tests/__tests__/components/QuotaIndicator.test.tsx`

### Implementation Steps

1. `TierBanner` reads `useBillingStore().me` and `useAuthStore().isAuthenticated()`:
    - Guest: "You're using your free taste. Sign in for more." + Sign In button.
    - Free: "Free tier: X of Y refinements left. Upgrade" + Upgrade button.
    - Paid: nothing (or a subtle "Pro" badge).
1. `QuotaIndicator` shows numeric `used/limit` and a progress bar. Hidden when `VITE_AUTH_ENABLED=false`.
1. Mount `TierBanner` in `ResponsiveLayout`.
1. Mount `QuotaIndicator` in `IterationInput`.
1. Tests cover each tier variant and the flags-off hidden state.

### Commit Message Template

```text
feat(frontend): add tier banner and quota indicator
```

## Task 4.7: Checkout Flow

### Files to Create

- `frontend/src/api/billing.ts`
- `frontend/src/components/UpgradeModal.tsx`
- `frontend/tests/__tests__/components/UpgradeModal.test.tsx`

### Implementation Steps

1. `billing.ts` exposes `startCheckout(): Promise<string>` that POSTs `/billing/checkout` and returns the redirect URL.
1. `UpgradeModal` has an "Upgrade" button that calls `startCheckout()` and `window.location.assign(url)`. Shows a spinner during the API call.
1. Wire: the "Upgrade" button in `TierBanner` opens `UpgradeModal`.
1. Add success/cancel pages (`/billing/success` and `/billing/cancel`) — simple static components that show a message and navigate home. The backend `STRIPE_SUCCESS_URL` / `STRIPE_CANCEL_URL` point to these paths.
1. Tests mock the API and verify `window.location.assign` is called.

### Commit Message Template

```text
feat(frontend): add upgrade modal and checkout redirect
```

## Task 4.8: Sign-In / Sign-Out UI

### Files to Modify

- `frontend/src/components/common/Header.tsx` (verified to exist; this is the top-level chrome component, mounted via `ResponsiveLayout` -> `DesktopLayout` / `MobileLayout`)

### Implementation Steps

1. When `VITE_AUTH_ENABLED=true`:
    - Signed out: show "Sign in" button linking to `hostedUiLoginUrl()`.
    - Signed in: show email + "Sign out" which clears `useAuthStore` and redirects to `${VITE_COGNITO_DOMAIN}/logout?client_id=...&logout_uri=${VITE_COGNITO_LOGOUT_URI}`.
1. When `VITE_AUTH_ENABLED=false`, show nothing auth-related (preserves OSS experience).
1. Component test.

### Commit Message Template

```text
feat(frontend): add sign-in and sign-out controls
```

## Phase Verification

- [x] All 8 tasks committed.
- [x] `cd frontend && npm run lint && npm run typecheck && npm test` all pass.
- [x] Frontend coverage gate holds.
- [x] With `VITE_AUTH_ENABLED=false` (default), UI is visually and functionally identical to pre-phase.
- [ ] With flags on and a mocked backend (MSW), the full guest to sign-in to upgrade flow is exercised in one integration test in `frontend/tests/__tests__/integration/`.
