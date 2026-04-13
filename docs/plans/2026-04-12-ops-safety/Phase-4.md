# Phase 4: Admin Frontend Dashboard

## Phase Goal

Build the admin frontend dashboard as a lazy-loaded `/admin` route in the React app. The dashboard provides visibility into platform operations: user management (search, filter, suspend, notify), model status and controls, operational metrics with charts, and revenue reporting. Gated by `VITE_ADMIN_ENABLED` and Cognito `admins` group membership.

**Success criteria:**

- `/admin` route lazy-loads without bloating the user bundle
- Admin layout with sidebar navigation across 5 sections
- User list with search, filter, suspend/unsuspend, and notify actions
- Model status with daily counts vs caps and disable/enable toggles
- Metrics overview with charts (recharts)
- Revenue section with subscriber count and churn
- CAPTCHA widget integrated on generation page for guests
- All components have unit tests

**Estimated tokens:** ~45,000

## Prerequisites

- Phase 3 complete (all admin API endpoints operational)
- All Phase 1-3 tests passing
- `recharts` package added to frontend dependencies

## Task 1: Frontend Config and API Client

**Goal:** Add admin feature flag to frontend config and create the admin API client.

**Files to Modify:**

- `frontend/src/api/config.ts` - Add `ADMIN_ENABLED`, `CAPTCHA_ENABLED`, `VITE_TURNSTILE_SITE_KEY` exports

**Files to Create:**

- `frontend/src/api/adminClient.ts` - Admin API client with typed methods

**Prerequisites:** None

**Implementation Steps:**

1. Add to `frontend/src/api/config.ts`:
   - `ADMIN_ENABLED` boolean from `VITE_ADMIN_ENABLED`
   - `CAPTCHA_ENABLED` boolean from `VITE_CAPTCHA_ENABLED`
   - `TURNSTILE_SITE_KEY` string from `VITE_TURNSTILE_SITE_KEY`
   - Add admin API routes to `API_ROUTES`:

     ```typescript
     ADMIN_USERS: '/admin/users',
     ADMIN_MODELS: '/admin/models',
     ADMIN_METRICS: '/admin/metrics',
     ADMIN_REVENUE: '/admin/revenue',
     ```

1. Create `frontend/src/api/adminClient.ts`:
   - Import the authenticated fetch helper from the existing auth client (or use the same pattern as `useBillingStore` for adding the Authorization header).
   - Typed functions for each admin endpoint:
     - `fetchAdminUsers(params?: {limit?, lastKey?, tier?, suspended?}) -> Promise<AdminUsersResponse>`
     - `fetchAdminUserDetail(userId: string) -> Promise<AdminUser>`
     - `suspendUser(userId: string, reason?: string) -> Promise<void>`
     - `unsuspendUser(userId: string) -> Promise<void>`
     - `notifyUser(userId: string, type: string, message: string, subject?: string) -> Promise<void>`
     - `fetchAdminModels() -> Promise<AdminModelsResponse>`
     - `disableModel(model: string) -> Promise<void>`
     - `enableModel(model: string) -> Promise<void>`
     - `fetchAdminMetrics(days?: number) -> Promise<AdminMetricsResponse>`
     - `fetchAdminRevenue() -> Promise<AdminRevenueResponse>`
   - Define TypeScript interfaces for all response types in the same file.
   - All functions include the JWT token in the Authorization header (same pattern as billing checkout/portal calls).

**Verification Checklist:**

- [x] `ADMIN_ENABLED` exports correctly from config
- [x] `CAPTCHA_ENABLED` and `TURNSTILE_SITE_KEY` export correctly
- [x] All admin API client functions exist with correct types
- [x] Authorization header is included in all requests
- [x] API routes are correctly defined

**Testing Instructions:**

Create `frontend/tests/__tests__/api/adminClient.test.ts`:

- Mock `fetch` and verify each function calls the correct endpoint
- Verify Authorization header is included
- Verify query parameters are passed correctly for `fetchAdminUsers`
- Verify POST body for suspend, unsuspend, notify

Run: `cd frontend && npm test -- tests/__tests__/api/adminClient.test.ts`

**Commit Message Template:**

```text
feat(admin): add frontend config and admin API client

- ADMIN_ENABLED, CAPTCHA_ENABLED, TURNSTILE_SITE_KEY config exports
- Typed admin API client with all 10 endpoint methods
- Admin API routes in config
```

## Task 2: Admin Zustand Store

**Goal:** Create a Zustand store for admin dashboard state management.

**Files to Create:**

- `frontend/src/stores/useAdminStore.ts` - Admin state management

**Prerequisites:** Task 1 (admin API client)

**Implementation Steps:**

1. Create `frontend/src/stores/useAdminStore.ts` following the pattern of `useBillingStore.ts`:
   - State:

     ```typescript
     interface AdminState {
       // Users
       users: AdminUser[];
       usersLoading: boolean;
       usersNextKey: string | null;
       selectedUser: AdminUser | null;
       userDetailLoading: boolean;

       // Models
       models: AdminModel[];
       modelsLoading: boolean;

       // Metrics
       metrics: AdminMetrics | null;
       metricsLoading: boolean;

       // Revenue
       revenue: AdminRevenue | null;
       revenueLoading: boolean;

       // Filters
       tierFilter: string | null;
       suspendedFilter: boolean | null;
       searchQuery: string;
     }
     ```

   - Actions:
     - `fetchUsers(reset?: boolean)` - load/paginate users with current filters
     - `fetchUserDetail(userId: string)` - load single user
     - `suspendUser(userId: string, reason?: string)` - suspend and refresh
     - `unsuspendUser(userId: string)` - unsuspend and refresh
     - `notifyUser(userId: string, type: string, message: string, subject?: string)` - send notification
     - `fetchModels()` - load model status
     - `disableModel(model: string)` - disable and refresh
     - `enableModel(model: string)` - enable and refresh
     - `fetchMetrics(days?: number)` - load metrics
     - `fetchRevenue()` - load revenue
     - `setTierFilter(tier: string | null)` - update filter
     - `setSuspendedFilter(suspended: boolean | null)` - update filter
     - `setSearchQuery(query: string)` - update search (client-side filter on loaded users)
   - Use the `requestEpoch` stale-response guard pattern from `useBillingStore.ts` to prevent stale data from overwriting fresh data.

**Verification Checklist:**

- [x] Store initializes with empty state
- [x] `fetchUsers` calls API and populates users array
- [x] Pagination works with `usersNextKey`
- [x] Filter actions update state and trigger refetch
- [x] Suspend/unsuspend actions call API and refresh user list
- [x] Stale-response guard prevents race conditions

**Testing Instructions:**

Create `frontend/tests/__tests__/stores/useAdminStore.test.ts`:

- Mock admin API client
- Test initial state
- Test `fetchUsers` populates users
- Test pagination appends users
- Test `suspendUser` calls API and refreshes
- Test filter changes trigger refetch
- Test stale-response guard

Run: `cd frontend && npm test -- tests/__tests__/stores/useAdminStore.test.ts`

**Commit Message Template:**

```text
feat(admin): add Zustand admin store for dashboard state

- Users, models, metrics, revenue state management
- Pagination, filtering, and search support
- Stale-response guard following billing store pattern
```

## Task 3: Admin Layout and Route Registration

**Goal:** Create the admin layout shell with sidebar navigation and register the `/admin` route in `App.tsx`.

**Files to Create:**

- `frontend/src/components/admin/AdminLayout.tsx` - Admin shell with sidebar
- `frontend/src/pages/Admin.tsx` - Admin page component (wraps AdminLayout)

**Files to Modify:**

- `backend/src/lambda_function.py` - Add `groups` field to `handle_me` response (import `extract_admin_groups` from `auth.claims`)
- `frontend/src/App.tsx` - Add `/admin` route with lazy loading

**Prerequisites:** Task 2 (admin store), Phase 3 Task 1 (auth/claims.py must exist)

**Implementation Steps:**

1. Create `frontend/src/pages/Admin.tsx`:
   - Default export component.
   - Determine admin status from the `/me` endpoint response. The existing `handle_me` function (in `backend/src/lambda_function.py`, line 905) does not currently include admin group membership. This task adds a `groups` field to the response.
   - **Required backend change** (do this first): modify `handle_me` in `backend/src/lambda_function.py`:
     1. Add import at the top of the file: `from auth.claims import extract_admin_groups` (this module is created in Phase 3 Task 1).
     1. In the response dict built at lines 951-960, add `"groups": extract_admin_groups(event)` after the `"billing": billing` entry. The updated `/me` response schema becomes:

        ```text
        {
          "userId": "sub-xxx",
          "email": "user@example.com",
          "tier": "paid",
          "quota": { ... },
          "billing": { ... },
          "groups": ["admins"]   // or [] if not admin
        }
        ```

   - On the frontend: fetch `/me` (using the existing `useMePolling` hook or `useAuthStore`), check if the response `groups` array contains `"admins"`. Store the `groups` array in the auth store alongside existing user info. If the user is not in the `"admins"` group, show an "Access denied" message instead of the admin layout.
   - Render `AdminLayout` when the user is confirmed as admin.
1. Create `frontend/src/components/admin/AdminLayout.tsx`:
   - Sidebar with navigation links: Overview, Users, Models, Notifications, Revenue.
   - Main content area that renders the active section.
   - Use state to track active section (or simple conditional rendering based on internal state; no need for a full router since admin is a single page with sections).
   - Responsive: sidebar collapses to top tabs on mobile.
   - Use Tailwind CSS classes consistent with existing component styles.
1. Modify `frontend/src/App.tsx`:
   - Add lazy import: `const Admin = lazy(() => import('@/pages/Admin'));`
   - Add route check before `AppMain`: if `pathname.startsWith('/admin')`, render `<Admin />` wrapped in `<Suspense>`.
   - Only add the route when `ADMIN_ENABLED` is true (import from config). When false, `/admin` falls through to `AppMain` (normal app behavior).

**Verification Checklist:**

- [x] `/admin` route lazy-loads the Admin page
- [x] Admin bundle is separate from user bundle (code splitting works)
- [x] Non-admin users see "Access denied" message
- [x] Sidebar navigation switches between sections
- [x] `ADMIN_ENABLED=false` disables the route entirely
- [x] Layout is responsive

**Testing Instructions:**

Create `frontend/tests/__tests__/components/admin/AdminLayout.test.tsx`:

- Test sidebar renders all 5 navigation items
- Test clicking a nav item switches the active section
- Test non-admin user sees access denied

Run: `cd frontend && npm test -- tests/__tests__/components/admin/AdminLayout.test.tsx`

**Commit Message Template:**

```text
feat(admin): add admin layout, routing, and lazy-loaded /admin page

- AdminLayout with sidebar navigation (5 sections)
- Lazy-loaded /admin route in App.tsx
- Access denied for non-admin users
- Code splitting keeps admin out of user bundle
```

## Task 4: Admin Overview Section

**Goal:** Build the overview dashboard showing real-time model status, key metrics, and recent activity.

**Files to Create:**

- `frontend/src/components/admin/AdminOverview.tsx` - Overview dashboard

**Prerequisites:** Task 2 (admin store), Task 3 (admin layout)

**Implementation Steps:**

1. Create `frontend/src/components/admin/AdminOverview.tsx`:
   - On mount, call `fetchModels()` and `fetchMetrics(7)` from the admin store.
   - Display cards:
     - **Model Status**: 4 cards (one per model) showing daily count vs cap as a progress bar, enabled/disabled status. Color-coded: green (under 50%), yellow (50-80%), red (over 80% of cap).
     - **Today's Totals**: total generations across all models, total errors (from metrics).
     - **Active Subscribers**: from revenue data (fetch on mount).
   - If metrics history is available, show a small sparkline chart (recharts `<LineChart>`) of daily generation counts over the last 7 days.
   - Loading skeleton while data loads (use `LoadingSpinner` or Tailwind pulse animation).

**Verification Checklist:**

- [x] Overview fetches models and metrics on mount
- [x] Model status cards show count vs cap with progress bars
- [x] Color coding works for utilization levels
- [x] Sparkline chart renders with 7-day history
- [x] Loading state shows while data fetches

**Testing Instructions:**

Create `frontend/tests/__tests__/components/admin/AdminOverview.test.tsx`:

- Mock admin store with pre-populated data
- Test model status cards render for all 4 models
- Test progress bar reflects correct utilization
- Test loading state renders when data is loading
- Test handles empty metrics gracefully

Run: `cd frontend && npm test -- tests/__tests__/components/admin/AdminOverview.test.tsx`

**Commit Message Template:**

```text
feat(admin): add overview dashboard with model status and metrics

- Model status cards with utilization progress bars
- Generation sparkline chart (recharts)
- Active subscriber count from revenue data
```

## Task 5: Admin Users Section

**Goal:** Build the user management section with search, filter, pagination, and action buttons.

**Files to Create:**

- `frontend/src/components/admin/AdminUsers.tsx` - User list and management
- `frontend/src/components/admin/AdminUserDetail.tsx` - User detail modal/panel

**Prerequisites:** Task 2 (admin store), Task 3 (admin layout)

**Implementation Steps:**

1. Create `frontend/src/components/admin/AdminUsers.tsx`:
   - Search input at top (filters client-side on email/userId).
   - Filter dropdowns: Tier (all, free, paid), Suspended (all, yes, no).
   - Table with columns: Email, Tier, Status (active/suspended), Generate Count, Refine Count, Created.
   - Pagination: "Load more" button when `usersNextKey` is not null.
   - Row click opens user detail panel.
   - Action buttons inline: Suspend/Unsuspend toggle, Send Notice.
1. Create `frontend/src/components/admin/AdminUserDetail.tsx`:
   - Modal or slide-over panel (follow the pattern from `UpgradeModal.tsx` for focus trap and Escape key handling).
   - Shows full user record: all DynamoDB fields formatted for readability.
   - Action buttons: Suspend/Unsuspend, Send Warning, Send Custom Email.
   - Send notification form: type dropdown, message textarea, optional subject (for custom type).
   - Confirmation dialog before suspend action.

**Verification Checklist:**

- [x] User list renders with correct columns
- [x] Search filters users by email
- [x] Tier filter works
- [x] Suspended filter works
- [x] Pagination loads more users
- [x] Suspend/unsuspend toggles update immediately (optimistic UI)
- [x] User detail shows full record
- [x] Notification form validates required fields
- [x] Escape key closes detail panel

**Testing Instructions:**

Create `frontend/tests/__tests__/components/admin/AdminUsers.test.tsx`:

- Mock admin store with sample users
- Test table renders all users
- Test search filter reduces visible users
- Test tier filter works
- Test suspend button calls store action
- Test user detail modal opens on click
- Test notification form submission

Run: `cd frontend && npm test -- tests/__tests__/components/admin/AdminUsers.test.tsx`

**Commit Message Template:**

```text
feat(admin): add user management section with search, filter, and actions

- Searchable user table with tier and suspension filters
- User detail panel with full record display
- Suspend/unsuspend and notification actions
- Pagination with load-more button
```

## Task 6: Admin Models Section

**Goal:** Build the model management section showing per-model stats and control toggles.

**Files to Create:**

- `frontend/src/components/admin/AdminModels.tsx` - Model management

**Prerequisites:** Task 2 (admin store), Task 3 (admin layout)

**Implementation Steps:**

1. Create `frontend/src/components/admin/AdminModels.tsx`:
   - On mount, call `fetchModels()` from admin store.
   - Display a card for each model with:
     - Model name and provider
     - Daily count vs cap as a large progress bar with numeric labels
     - Enabled/Disabled status badge
     - Disable/Enable toggle button with confirmation
     - If metrics history is available, show a 7-day daily count chart (recharts `<BarChart>`)
   - Auto-refresh every 30 seconds (use `useEffect` with `setInterval`; clear on unmount).

**Verification Checklist:**

- [x] Model cards render for all 4 models
- [x] Progress bar shows correct count vs cap
- [x] Disable/enable toggle calls API and refreshes
- [x] Confirmation dialog before disable action
- [x] Auto-refresh updates model data
- [x] Historical chart renders when data available

**Testing Instructions:**

Create `frontend/tests/__tests__/components/admin/AdminModels.test.tsx`:

- Mock admin store with model data
- Test all 4 model cards render
- Test disable button shows confirmation
- Test enable button calls store action
- Test progress bar reflects correct values

Run: `cd frontend && npm test -- tests/__tests__/components/admin/AdminModels.test.tsx`

**Commit Message Template:**

```text
feat(admin): add model management section with status and controls

- Per-model cards with daily count progress bars
- Disable/enable toggles with confirmation
- Historical daily count bar charts
- Auto-refresh every 30 seconds
```

## Task 7: Admin Revenue Section

**Goal:** Build the revenue reporting section showing subscriber counts, churn, and historical trends.

**Files to Create:**

- `frontend/src/components/admin/AdminRevenue.tsx` - Revenue reporting

**Prerequisites:** Task 2 (admin store), Task 3 (admin layout)

**Implementation Steps:**

1. Create `frontend/src/components/admin/AdminRevenue.tsx`:
   - On mount, call `fetchRevenue()` from admin store.
   - Key metric cards:
     - Active Subscribers (from `revenue.current.activeSubscribers`)
     - Monthly Churn (from `revenue.current.monthlyChurn`)
     - Churn Rate (computed: `monthlyChurn / activeSubscribers * 100` if subscribers > 0)
   - Historical chart: recharts `<AreaChart>` showing active subscribers over time (from daily snapshots).
   - Date range selector: 7 days, 14 days, 30 days.

**Verification Checklist:**

- [x] Revenue cards show current metrics
- [x] Churn rate computed correctly
- [x] Historical chart renders with snapshot data
- [x] Date range selector works
- [x] Handles zero subscribers gracefully (no division by zero)

**Testing Instructions:**

Create `frontend/tests/__tests__/components/admin/AdminRevenue.test.tsx`:

- Mock admin store with revenue data
- Test metric cards render with correct values
- Test churn rate calculation
- Test zero subscribers does not crash
- Test date range selector updates chart

Run: `cd frontend && npm test -- tests/__tests__/components/admin/AdminRevenue.test.tsx`

**Commit Message Template:**

```text
feat(admin): add revenue reporting section with charts

- Active subscriber and churn metric cards
- Historical subscriber trend area chart
- Configurable date range (7/14/30 days)
```

## Task 8: CAPTCHA Widget for Guest Generation

**Goal:** Integrate Cloudflare Turnstile widget on the generation page for guest users.

**Files to Create:**

- `frontend/src/components/features/CaptchaWidget.tsx` - Turnstile widget wrapper

**Files to Modify:**

- `frontend/src/api/client.ts` - Add optional `captchaToken` parameter to `generateSession` function (line 194)
- `frontend/src/components/generation/GenerationPanel.tsx` - Add CAPTCHA widget and pass token to `generateSession` call (line 190)

**Prerequisites:** Task 1 (config with `CAPTCHA_ENABLED`, `TURNSTILE_SITE_KEY`)

**Implementation Steps:**

1. Install `@marsidev/react-turnstile` (lightweight React wrapper for Turnstile) or implement a minimal wrapper using the Turnstile script tag directly. The minimal approach avoids a new dependency:
   - Create `frontend/src/components/features/CaptchaWidget.tsx`:
     - Load the Turnstile script (`https://challenges.cloudflare.com/turnstile/v0/api.js`) dynamically on mount.
     - Render a `<div>` container. Call `turnstile.render(container, {sitekey, callback})` after script loads.
     - `callback` receives the token string. Pass it up via an `onVerify(token: string)` prop.
     - Expose a `reset()` method (via `useImperativeHandle` or callback) to re-render the widget after submission.
   - Only render when `CAPTCHA_ENABLED` is true and user is not authenticated.
1. Modify the generation flow. There are two files to change:

   **API client** (`frontend/src/api/client.ts`): The `/generate` POST body is built in the `generateSession` function at line 194. Currently the signature is `generateSession(prompt: string): Promise<SessionGenerateResponse>` and it sends `JSON.stringify({ prompt })`. Update the signature to accept an optional CAPTCHA token: `generateSession(prompt: string, captchaToken?: string)`. When `captchaToken` is provided, include it in the body: `JSON.stringify({ prompt, captchaToken })`. When omitted, send only `{ prompt }` (preserving existing behavior).

   **Generation panel** (`frontend/src/components/generation/GenerationPanel.tsx`): The generate button click handler calls `generateSession(prompt)` at line 190. Modify this call site:
   - If `CAPTCHA_ENABLED` (from `api/config.ts`) and user is a guest (not authenticated):
     - Render `<CaptchaWidget>` near the generate button.
     - Store the CAPTCHA token in local component state via the `onVerify` callback.
     - Change the call at line 190 to: `generateSession(prompt, captchaToken)`.
     - Disable the generate button until the CAPTCHA widget calls `onVerify`.
     - After generation completes (success or failure), reset the widget for the next attempt.
   - If `CAPTCHA_ENABLED` is false or user is authenticated, skip the widget entirely and call `generateSession(prompt)` without the token (existing behavior, no changes to this path).

**Verification Checklist:**

- [ ] Turnstile widget renders for guest users when CAPTCHA is enabled
- [ ] Widget does not render for authenticated users
- [ ] Widget does not render when CAPTCHA is disabled
- [ ] Token is included in `/generate` request body
- [ ] Widget resets after generation attempt
- [ ] Generate button is disabled until CAPTCHA is completed

**Testing Instructions:**

Create `frontend/tests/__tests__/components/CaptchaWidget.test.tsx`:

- Mock the Turnstile script loading
- Test widget renders when CAPTCHA enabled and user is guest
- Test widget does not render when disabled
- Test widget does not render for authenticated user
- Test `onVerify` callback is called with token
- Test reset functionality

Run: `cd frontend && npm test -- tests/__tests__/components/CaptchaWidget.test.tsx`

**Commit Message Template:**

```text
feat(captcha): add Turnstile CAPTCHA widget for guest generation

- Dynamic Turnstile script loading
- Widget renders only for guests when CAPTCHA_ENABLED
- Token included in /generate request body
- Auto-reset after generation attempt
```

## Task 9: Install recharts and Final Integration

**Goal:** Install the recharts dependency and verify the full admin dashboard works end-to-end.

**Files to Modify:**

- `frontend/package.json` - Add recharts dependency

**Prerequisites:** Tasks 1-8

**Implementation Steps:**

1. Install recharts: `cd frontend && npm install recharts`
1. Verify TypeScript types are included (recharts ships its own types).
1. Run the full frontend test suite: `cd frontend && npm test`
1. Run the full frontend build: `cd frontend && npm run build`
1. Verify the admin bundle is separate from the main bundle by checking the build output for code-split chunks.
1. Run lint and typecheck: `cd frontend && npm run lint && npm run typecheck`

**Verification Checklist:**

- [ ] `recharts` installed and importable
- [ ] All frontend tests pass
- [ ] Frontend builds without errors
- [ ] Admin code is in a separate chunk (code splitting works)
- [ ] Lint passes
- [ ] Typecheck passes
- [ ] No new console warnings

**Testing Instructions:**

```bash
cd frontend
npm test
npm run build
npm run lint
npm run typecheck
```

**Commit Message Template:**

```text
feat(admin): install recharts and verify admin dashboard integration

- recharts dependency for admin charts
- All frontend tests, lint, and typecheck passing
- Admin code split into separate bundle chunk
```

## Phase Verification

After all 9 tasks are complete:

1. All backend tests pass: `PYTHONPATH=backend/src pytest tests/backend/unit/ -v`
1. All frontend tests pass: `cd frontend && npm test`
1. Frontend lint passes: `cd frontend && npm run lint`
1. Frontend typecheck passes: `cd frontend && npm run typecheck`
1. Frontend builds: `cd frontend && npm run build`
1. Backend SAM build: `cd backend && sam build`
1. With `ADMIN_ENABLED=false`, `/admin` route is not accessible
1. With `CAPTCHA_ENABLED=false`, no CAPTCHA widget is rendered
1. Admin dashboard is code-split from user bundle

## Known Limitations

- The admin dashboard does not have real-time WebSocket updates. Data refreshes on navigation and via 30-second polling (models section only).
- Charts are basic. No custom tooltips, zoom, or export. Sufficient for v1 operational visibility.
- User search is client-side only (filters the loaded page of users). Server-side search would require a GSI or OpenSearch, deferred per ADR-19.
- The CAPTCHA widget requires JavaScript enabled in the browser. Users with JS disabled cannot complete guest generation when CAPTCHA is enabled. This is an acceptable tradeoff.
- No dark mode support for admin dashboard in v1. Uses the same Tailwind theme as the main app.
