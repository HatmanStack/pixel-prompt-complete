# Phase 2 -- Frontend Provider Swap and Column Focus UI

## Phase Goal

Update the frontend to use the new 4-model lineup (Gemini, Nova Canvas, DALL-E 3, Firefly), implement the column focus/expand interaction for desktop, migrate legacy test files from `.jsx` to `.tsx`, and address frontend-specific audit findings.

**Success criteria:**

1. `ModelName` type is `'gemini' | 'nova' | 'openai' | 'firefly'`
1. `MODELS` array ordering is `['gemini', 'nova', 'openai', 'firefly']`
1. Column focus/expand works: clicking a column expands it to 60% width, others compress to 13%
1. Focused column shows full controls; compressed columns show thumbnail + iteration input
1. All `.jsx` test files migrated to `.tsx`
1. Stale fixtures removed from `src/`
1. Phantom env vars removed
1. `npm run typecheck && npm run lint && npm test` passes

**Estimated tokens:** ~35,000

## Prerequisites

- Phase 1 complete (backend serves new model names)
- Node.js 24+ with npm
- `cd frontend && npm install`

## Task 1: Update ModelName Type and MODELS Array

**Goal:** Change the `ModelName` type union and `MODELS` array to reflect the new provider lineup. This is the foundational change -- all other frontend tasks depend on it.

**Files to Modify/Create:**

- `frontend/src/types/api.ts` -- Update `ModelName`, `MODEL_DISPLAY_NAMES`, `MODELS`
- `frontend/src/stores/useAppStore.ts` -- Update `INITIAL_ITERATION_WARNINGS`
- `frontend/src/hooks/useIteration.ts` -- No changes needed (uses ModelName generically)

**Prerequisites:** None

**Implementation Steps:**

1. In `frontend/src/types/api.ts`:

   Update the `ModelName` type:

   ```typescript
   export type ModelName = 'gemini' | 'nova' | 'openai' | 'firefly';
   ```

   Update `MODEL_DISPLAY_NAMES`:

   ```typescript
   export const MODEL_DISPLAY_NAMES: Record<ModelName, string> = {
     gemini: 'Gemini',
     nova: 'Nova Canvas',
     openai: 'DALL-E 3',
     firefly: 'Firefly',
   };
   ```

   Update `MODELS` array:

   ```typescript
   export const MODELS: ModelName[] = ['gemini', 'nova', 'openai', 'firefly'];
   ```

1. In `frontend/src/stores/useAppStore.ts`, update `INITIAL_ITERATION_WARNINGS`:

   ```typescript
   const INITIAL_ITERATION_WARNINGS: Record<ModelName, boolean> = {
     gemini: false,
     nova: false,
     openai: false,
     firefly: false,
   };
   ```

1. Run `npm run typecheck` -- this will reveal every file that references old model names like `'flux'` or `'recraft'`. Fix each one.

**Verification Checklist:**

- [ ] `ModelName` only allows `'gemini' | 'nova' | 'openai' | 'firefly'`
- [ ] `MODELS` array has 4 entries in correct order
- [ ] `npm run typecheck` passes with zero errors
- [ ] `grep -r "'flux'\|'recraft'" frontend/src/` returns no matches

**Testing Instructions:**

- Run `npm run typecheck` after changes. TypeScript will catch any remaining old model name references as compile errors.
- Fix all errors before proceeding.

**Commit Message Template:**

```text
feat(frontend): update ModelName type for new provider lineup

- Change ModelName to 'gemini' | 'nova' | 'openai' | 'firefly'
- Update MODEL_DISPLAY_NAMES and MODELS array ordering
- Update INITIAL_ITERATION_WARNINGS in useAppStore
```

---

## Task 2: Update API Response Types

**Goal:** Tighten the `SessionGenerateResponse` type (MED-15 from health audit), update `GalleryListItem` to use `previewUrl` instead of `previewData`, and remove `output` from `GalleryDetailImage`.

**Files to Modify/Create:**

- `frontend/src/types/api.ts` -- Update response types
- `frontend/src/components/gallery/GalleryBrowser.tsx` -- Update to use `previewUrl`
- Any component that accesses `GalleryDetailImage.output` -- Remove references

**Prerequisites:** Task 1 complete, Phase 1 Task 9 complete (backend gallery fix)

**Implementation Steps:**

1. Update `SessionGenerateResponse` in `api.ts`:

   ```typescript
   export interface SessionGenerateResponse {
     sessionId: string;
     status: string;
     prompt: string;
     models: Record<string, { status: string; imageKey?: string; imageUrl?: string }>;
   }
   ```

1. Update `GalleryListItem`:

   ```typescript
   export interface GalleryListItem {
     id: string;
     timestamp: string;
     previewUrl?: string;  // Changed from previewData (base64)
     imageCount: number;
   }
   ```

1. Update `GalleryDetailImage`:

   ```typescript
   export interface GalleryDetailImage {
     key: string;
     url: string;
     model: string;
     prompt: string;
     timestamp?: string;
     // output field removed - use url for image display
   }
   ```

1. Search all components that reference `previewData` or `output` on gallery types and update them to use `previewUrl` or `url` respectively. The gallery browser likely renders preview images using `previewData` as a base64 data URI -- change this to an `<img src={item.previewUrl}>` tag.

**Verification Checklist:**

- [ ] `GalleryListItem` has `previewUrl` not `previewData`
- [ ] `GalleryDetailImage` does not have `output` field
- [ ] `npm run typecheck` passes
- [ ] Gallery components display images via CloudFront URLs, not base64

**Testing Instructions:**

- Update any gallery component tests that reference `previewData` to use `previewUrl`
- Verify gallery browser renders images from URLs

**Commit Message Template:**

```text
feat(frontend): update gallery types to use CloudFront URLs

- Replace previewData (base64) with previewUrl in GalleryListItem
- Remove output field from GalleryDetailImage
- Tighten SessionGenerateResponse types (resolves MED-15)
```

---

## Task 3: Add Column Focus State to UI Store

**Goal:** Add `focusedModel` state and actions to the UI store for the column focus/expand feature.

**Files to Modify/Create:**

- `frontend/src/stores/useUIStore.ts` -- Add `focusedModel` state and `setFocusedModel`, `clearFocus`, `toggleFocus` actions
- `frontend/src/types/store.ts` -- Update `UIState` and `UIActions` types (the `UIStore` type is defined here at line 82 and re-exported via `frontend/src/types/index.ts`)
- `frontend/tests/__tests__/stores/useUIStore.test.ts` -- Add focus state tests

**Prerequisites:** Task 1 complete

**Implementation Steps:**

1. Add to `useUIStore`:

   ```typescript
   focusedModel: ModelName | null;
   setFocusedModel: (model: ModelName | null) => void;
   toggleFocus: (model: ModelName) => void;
   ```

   Implementation:

   ```typescript
   focusedModel: null,
   setFocusedModel: (model) => set({ focusedModel: model }),
   toggleFocus: (model) =>
     set((state) => ({
       focusedModel: state.focusedModel === model ? null : model,
     })),
   ```

1. The focus state is desktop-only. Mobile layout ignores `focusedModel`.

**Verification Checklist:**

- [ ] `useUIStore` has `focusedModel` state (default null)
- [ ] `toggleFocus` toggles between focused and null
- [ ] `npm run typecheck` passes

**Testing Instructions:**

Add to `frontend/tests/__tests__/stores/useUIStore.test.ts`:

- `test_focusedModel_defaults_to_null` -- Assert initial `focusedModel` is null.
- `test_toggleFocus_sets_model` -- Call `toggleFocus('gemini')`. Assert `focusedModel` is `'gemini'`.
- `test_toggleFocus_clears_same_model` -- Call `toggleFocus('gemini')` twice. Assert `focusedModel` is null.
- `test_toggleFocus_switches_model` -- Call `toggleFocus('gemini')` then `toggleFocus('nova')`. Assert `focusedModel` is `'nova'`.
- `test_setFocusedModel_null_clears` -- Call `setFocusedModel(null)`. Assert null.

**Commit Message Template:**

```text
feat(ui): add column focus state to UI store

- Add focusedModel, setFocusedModel, toggleFocus to useUIStore
- Focus state is desktop-only (mobile ignores it)
- Add unit tests for focus state management
```

---

## Task 4: Implement Column Focus Layout

**Goal:** Implement the column focus/expand CSS transition behavior in the generation panel and model column components.

**Files to Modify/Create:**

- `frontend/src/components/generation/GenerationPanel.tsx` -- Add focus behavior to column container
- `frontend/src/components/generation/ModelColumn.tsx` -- Accept `isFocused` and `isCompressed` props, adjust layout
- `frontend/src/hooks/useBreakpoint.ts` -- May need to check for desktop breakpoint

**Prerequisites:** Task 3 complete (focus state in store)

**Implementation Steps:**

1. In `GenerationPanel.tsx`:
   - Import `useUIStore` and get `focusedModel` and `toggleFocus`
   - Import `useBreakpoint` to detect desktop vs mobile
   - In the 4-column layout section, pass focus props to each `ModelColumn`:

     ```typescript
     const { focusedModel, toggleFocus } = useUIStore();
     const { isDesktop } = useBreakpoint();

     // In the MODELS.map:
     <ModelColumn
       model={model}
       column={column}
       isSelected={selectedModels.has(model)}
       onToggleSelect={() => toggleModelSelection(model)}
       onImageExpand={handleImageExpand}
       isFocused={isDesktop && focusedModel === model}
       isCompressed={isDesktop && focusedModel !== null && focusedModel !== model}
       onFocusToggle={() => isDesktop && toggleFocus(model)}
     />
     ```

   - Update the column container `<div>` wrapper to apply width classes based on focus state:

     ```typescript
     <div
       key={model}
       className={`snap-center transition-all duration-300 ease-in-out ${
         isDesktop && focusedModel === model
           ? 'w-[60%] flex-shrink-0'
           : isDesktop && focusedModel !== null
             ? 'w-[13%] flex-shrink-0'
             : '' // default: existing equal-width behavior
       }`}
     >
     ```

   - Remove the fixed `min-w-[250px] max-w-[300px]` from the column wrapper when focus is active

1. In `ModelColumn.tsx`:
   - Add props: `isFocused?: boolean`, `isCompressed?: boolean`, `onFocusToggle?: () => void`
   - Make the header clickable to toggle focus:

     ```typescript
     <div
       className="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-900 rounded-lg sticky top-0 z-20 cursor-pointer"
       onClick={onFocusToggle}
       role="button"
       tabIndex={0}
       aria-expanded={isFocused}
       aria-label={`${isFocused ? 'Collapse' : 'Expand'} ${MODEL_DISPLAY_NAMES[model]} column`}
     >
     ```

   - When `isCompressed`:
     - Hide the iteration history (show only the latest image)
     - Hide outpaint controls
     - Hide the checkbox and iteration counter from the header
     - Keep iteration input visible
     - Show a smaller thumbnail of the latest image

   - When `isFocused`:
     - Show all controls: full iteration history, outpaint controls, download button, iteration counter, checkbox
     - The column has more horizontal space, so images display larger

   - When neither (no focus active):
     - Keep the current default layout (equal columns)

1. Ensure the transitions are smooth:
   - Use `transition-all duration-300 ease-in-out` on the column wrapper
   - Images inside compressed columns use `object-cover` to fill the narrower space
   - Overflow hidden on compressed columns to prevent content from overflowing

**Verification Checklist:**

- [ ] Clicking a column header on desktop expands it to ~60% width
- [ ] Other columns compress to ~13% width with only thumbnail + input visible
- [ ] Clicking the focused column header again returns to equal layout
- [ ] Mobile layout is unaffected (no focus behavior)
- [ ] CSS transitions are smooth (no layout jumps)
- [ ] `npm run typecheck` passes
- [ ] `npm run lint` passes

**Testing Instructions:**

Add to `frontend/tests/__tests__/components/generation/ModelColumn.test.tsx` (create if needed):

- `test_column_renders_full_controls_when_focused` -- Render with `isFocused={true}`. Assert outpaint controls, iteration history, and checkbox are visible.
- `test_column_hides_controls_when_compressed` -- Render with `isCompressed={true}`. Assert outpaint controls are not visible. Assert iteration input IS visible.
- `test_column_default_shows_all_controls` -- Render with neither focused nor compressed. Assert all controls visible (existing behavior).
- `test_column_header_click_calls_onFocusToggle` -- Simulate click on header. Assert `onFocusToggle` callback was called.

**Commit Message Template:**

```text
feat(ui): implement column focus/expand interaction

- Click column header to expand to 60% width (desktop only)
- Compressed columns show thumbnail + iteration input at 13% width
- Smooth CSS transitions with duration-300 ease-in-out
- Mobile layout unchanged (snap-scroll preserved)
```

---

## Task 5: Sync MAX_ITERATIONS with Backend

**Goal:** Replace the hardcoded `MAX_ITERATIONS = 7` and `WARNING_THRESHOLD = 5` in the frontend with values from the backend session response. This resolves HIGH-7 from the health audit.

**Files to Modify/Create:**

- `frontend/src/hooks/useIteration.ts` -- Fetch limits from session data or API config
- `frontend/src/types/api.ts` -- Add limits to Session type if backend exposes them
- `frontend/src/components/generation/ModelColumn.tsx` -- Import from updated hook

**Prerequisites:** Task 1 complete

**Implementation Steps:**

The simplest approach that doesn't require backend API changes: keep the constants in the frontend but move them to a single shared config file and add a clear comment that they must match `backend/src/config.py`.

1. Create the directory `frontend/src/config/` (it does not exist yet) and create the file `constants.ts` inside it:

   ```bash
   mkdir -p frontend/src/config
   ```

   Then create `frontend/src/config/constants.ts`:

   ```typescript
   /**
    * Iteration limits — must match backend/src/config.py:112-113.
    * If the backend values change via environment variable,
    * these must be updated to match.
    */
   export const MAX_ITERATIONS = 7;
   export const WARNING_THRESHOLD = 5;
   ```

1. Update `frontend/src/hooks/useIteration.ts` to import from the shared config:

   ```typescript
   import { MAX_ITERATIONS, WARNING_THRESHOLD } from '@/config/constants';
   ```

   Remove the local `export const MAX_ITERATIONS = 7;` and `export const WARNING_THRESHOLD = 5;`.

1. Update `frontend/src/components/generation/ModelColumn.tsx` to import from the shared config instead of `useIteration`:

   ```typescript
   import { MAX_ITERATIONS } from '@/config/constants';
   ```

1. Search for any other files importing `MAX_ITERATIONS` from `useIteration` and update them.

**Verification Checklist:**

- [ ] `MAX_ITERATIONS` and `WARNING_THRESHOLD` are defined in exactly one place: `config/constants.ts`
- [ ] `useIteration.ts` no longer exports these constants
- [ ] All imports of these constants point to `@/config/constants`
- [ ] Comment in `constants.ts` references the backend file and line numbers
- [ ] `npm run typecheck` passes

**Testing Instructions:**

- Update any test that imports `MAX_ITERATIONS` from `useIteration` to import from `@/config/constants`
- Verify `npm test` passes

**Commit Message Template:**

```text
refactor(frontend): centralize MAX_ITERATIONS in shared config

- Move MAX_ITERATIONS and WARNING_THRESHOLD to config/constants.ts
- Add comment linking to backend/src/config.py:112-113
- Update all imports (resolves HIGH-7 sync issue)
```

---

## Task 6: Migrate Legacy Test Files and Clean Up Fixtures

**Goal:** Convert `.jsx` test files to `.tsx`, remove the duplicate `GenerateButton.test.jsx`, remove stale fixtures from `src/`, and clean up test organization. This addresses MED-10, MED-11, and the `.jsx` migration from the eval.

**Files to Modify/Create:**

- `frontend/tests/__tests__/components/GenerateButton.test.jsx` -- Delete (duplicate of `generation/GenerateButton.test.tsx`)
- `frontend/tests/__tests__/components/GalleryBrowser.test.jsx` -- Rename to `.tsx`, update model names
- `frontend/tests/__tests__/components/GalleryPreview.test.jsx` -- Rename to `.tsx`, update model names
- `frontend/tests/__tests__/components/ImageGrid.test.jsx` -- Rename to `.tsx`, update model names
- `frontend/tests/__tests__/components/PromptEnhancer.test.jsx` -- Rename to `.tsx`, update model names
- `frontend/tests/__tests__/components/PromptInput.test.jsx` -- Rename to `.tsx`, update model names
- `frontend/tests/__tests__/components/ImageCard.test.jsx` -- Rename to `.tsx`, update model names
- `frontend/tests/__tests__/integration/galleryFlow.test.jsx` -- Rename to `.tsx`
- `frontend/tests/__tests__/utils/correlation.test.js` -- Rename to `.ts`
- `frontend/src/fixtures/apiResponses.ts` -- Delete (stale mock types from old job-based API)
- `frontend/tests/__tests__/fixtures/apiResponses.ts` -- Update or create with current session-based types

**Prerequisites:** Task 1 complete (new model names needed in tests)

**Implementation Steps:**

1. Delete `frontend/tests/__tests__/components/GenerateButton.test.jsx` -- it is a duplicate of `frontend/tests/__tests__/components/generation/GenerateButton.test.tsx`
1. For each `.jsx` test file:
   - Rename the file from `.jsx` to `.tsx`
   - Add TypeScript type imports at the top
   - Replace any old model names (`flux`, `recraft`) with new names (`gemini`, `nova`, `openai`, `firefly`)
   - Fix any type errors that TypeScript catches
1. Rename `correlation.test.js` to `correlation.test.ts`
1. Delete `frontend/src/fixtures/apiResponses.ts` -- this contains stale `MockJobStatus` and `MockResult` types from the old API
1. If any test imports from `frontend/src/fixtures/apiResponses.ts`, update it to use inline fixtures or the test fixtures at `frontend/tests/__tests__/fixtures/`
1. Update `frontend/tests/__tests__/fixtures/apiResponses.ts` to use current types with new model names

**Verification Checklist:**

- [ ] No `.jsx` files remain in `frontend/tests/`
- [ ] No `.js` files remain in `frontend/tests/` (only `.ts` and `.tsx`)
- [ ] `frontend/src/fixtures/` directory is deleted or empty
- [ ] `frontend/tests/__tests__/components/GenerateButton.test.jsx` is deleted
- [ ] `npm run typecheck` passes
- [ ] `npm test` passes with all test files

**Testing Instructions:**

- Run `npm test` after all renames. All tests should pass.
- The rename itself does not change test logic -- just file extensions and model name references.

**Commit Message Template:**

```text
chore(tests): migrate .jsx tests to .tsx and clean up stale fixtures

- Delete duplicate GenerateButton.test.jsx (resolves MED-10)
- Rename 7 .jsx test files to .tsx
- Rename correlation.test.js to .ts
- Delete stale src/fixtures/apiResponses.ts (resolves MED-11)
- Update all test model names for new provider lineup
```

---

## Task 7: Fix Frontend API Client Network Error Check

**Goal:** Make the `isNetworkError` check in `api/client.ts` more specific so it does not retry programming bugs. This addresses the eval Code Quality finding.

**Files to Modify/Create:**

- `frontend/src/api/client.ts` -- Update `isNetworkError` logic
- `frontend/tests/__tests__/api/client.test.ts` -- Add test for specific network error detection

**Prerequisites:** None

**Implementation Steps:**

1. In `api/client.ts`, replace:

   ```typescript
   const isNetworkError = !apiError.status;
   ```

   With a more specific check:

   ```typescript
   const isNetworkError =
     !apiError.status &&
     (apiError.name === 'TypeError' || apiError.message?.includes('fetch'));
   ```

   This ensures only actual network failures (TypeError from fetch, or errors mentioning fetch) are retried, not arbitrary programming bugs that happen to lack a status.

**Verification Checklist:**

- [ ] `isNetworkError` check requires `name === 'TypeError'` or message containing `'fetch'`
- [ ] `npm run typecheck` passes
- [ ] `npm test` passes

**Testing Instructions:**

Add to `frontend/tests/__tests__/api/client.test.ts`:

- `test_retries_on_network_error` -- Mock fetch to throw `TypeError('Failed to fetch')`. Assert the request is retried.
- `test_does_not_retry_on_programming_error` -- Mock fetch to throw `ReferenceError('x is not defined')`. Assert the error is thrown immediately without retry.

**Commit Message Template:**

```text
fix(api): narrow network error detection for retry logic

- Only retry on TypeError or fetch-related errors, not all status-less errors
- Prevents masking programming bugs with retry loops (resolves eval Code Quality)
```

---

## Task 8: Remove Phantom Frontend Env Vars

**Goal:** Remove `VITE_DEBUG` and `VITE_API_TIMEOUT` from `frontend/.env.example` since no frontend code reads them. This addresses the config drift findings from the doc audit.

**Files to Modify/Create:**

- `frontend/.env.example` -- Remove `VITE_DEBUG` and `VITE_API_TIMEOUT` entries
- `frontend/src/vite-env.d.ts` -- Remove type declarations for `VITE_CLOUDFRONT_DOMAIN`, `VITE_S3_BUCKET`, `VITE_ENVIRONMENT` if they are also phantom (only `VITE_API_ENDPOINT` is used)

**Prerequisites:** None

**Implementation Steps:**

1. Remove the following lines from `frontend/.env.example`:

   ```text
   # Optional: Enable debug logging in development
   # VITE_DEBUG=true

   # Optional: Custom API timeout (milliseconds)
   # VITE_API_TIMEOUT=30000
   ```

1. Check `frontend/src/vite-env.d.ts` for phantom type declarations. If `VITE_CLOUDFRONT_DOMAIN`, `VITE_S3_BUCKET`, and `VITE_ENVIRONMENT` are declared but never read by any source file in `frontend/src/`, remove their declarations too.
1. Search `frontend/src/` for any usage of these variables to confirm they are phantom:

   ```bash
   grep -r "VITE_DEBUG\|VITE_API_TIMEOUT\|VITE_CLOUDFRONT_DOMAIN\|VITE_S3_BUCKET\|VITE_ENVIRONMENT" frontend/src/
   ```

**Verification Checklist:**

- [ ] `VITE_DEBUG` and `VITE_API_TIMEOUT` are not in `.env.example`
- [ ] `vite-env.d.ts` only declares types for env vars that are actually used
- [ ] `npm run typecheck` passes
- [ ] `npm run build` succeeds

**Commit Message Template:**

```text
chore(frontend): remove phantom env var declarations

- Remove VITE_DEBUG and VITE_API_TIMEOUT from .env.example
- Remove unused type declarations from vite-env.d.ts
- Resolves doc-audit config drift findings
```

---

## Phase Verification

After completing all tasks in Phase 2:

1. Run: `npm run typecheck` -- zero errors
1. Run: `npm run lint` -- zero errors
1. Run: `npm test` -- all tests pass
1. Run: `npm run build` -- production build succeeds
1. Verify: `grep -r "'flux'\|'recraft'" frontend/src/` returns no matches
1. Verify: `grep -r "'flux'\|'recraft'" frontend/tests/` returns no matches
1. Verify: No `.jsx` or `.js` files in `frontend/tests/`
1. Verify: `frontend/src/fixtures/` does not exist
1. Verify: Column focus works visually (manual check in dev server)
1. Verify: `focusedModel` state in `useUIStore` controls column widths

**Known limitations after Phase 2:**

- CLAUDE.md and ADRs not yet updated (Phase 3)
- CI coverage gate still at 60% (Phase 3)
- No .devcontainer yet (Phase 3)
- No markdownlint/lychee in CI yet (Phase 3)
