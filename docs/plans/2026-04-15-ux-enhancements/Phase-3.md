# Phase 3: Frontend Features

## Phase Goal

Implement all frontend features: download button on iteration cards, adapted prompt display, prompt history panel with recent feed, and comparison modal with iteration picker. Update types and API client to match backend changes from Phases 1 and 2.

**Success criteria:**

- Download button on completed iteration cards triggers presigned URL download
- Adapted prompt shown in expandable section on iteration cards
- Prompt history panel shows per-user history (authenticated) and recent feed (all users)
- Re-run from history populates prompt input
- Comparison modal opens from multi-select, shows equal-size images with iteration picker
- All new components have tests
- `npm run lint && npm run typecheck && npm test` pass

**Token estimate:** ~50,000

## Prerequisites

- Phase 1 complete (storage refactor -- images served as raw PNG via CloudFront)
- Phase 2 complete (prompt adaptation + history endpoints available)

## Task 3.1: Update Types and API Client

### Goal

Add TypeScript types for new API responses and add API client functions for the new endpoints.

### Files to Modify

- `frontend/src/types/api.ts` -- Add new types
- `frontend/src/api/client.ts` -- Add new API functions
- `frontend/src/api/config.ts` -- Add new route constants

### Implementation Steps

1. In `frontend/src/types/api.ts`:

   - Add `adaptedPrompt?: string` to the `Iteration` interface (line 35). This is an optional field -- old iterations won't have it, and iterations where adaptation was identical to the original won't have it.

   - Add new response types:

     ```typescript
     export interface PromptHistoryItem {
       prompt: string;
       sessionId: string;
       createdAt: number;
     }

     export interface PromptHistoryResponse {
       prompts: PromptHistoryItem[];
       total: number;
     }

     export interface DownloadResponse {
       url: string;
       filename: string;
     }
     ```

1. In `frontend/src/types/index.ts`, re-export the new types:
   - Add `PromptHistoryItem`, `PromptHistoryResponse`, `DownloadResponse` to the API types export

1. In `frontend/src/api/config.ts`, add to `API_ROUTES` (around line 119):

   ```typescript
   PROMPTS_RECENT: '/prompts/recent',
   PROMPTS_HISTORY: '/prompts/history',
   DOWNLOAD: '/download',
   ```

1. In `frontend/src/api/client.ts`, add new functions:

   - `getRecentPrompts(limit?: number): Promise<PromptHistoryResponse>` -- GET to `/prompts/recent?limit=N`
   - `getPromptHistory(limit?: number, query?: string): Promise<PromptHistoryResponse>` -- GET to `/prompts/history?limit=N&q=query`
   - `getDownloadUrl(sessionId: string, model: ModelName, iterationIndex: number): Promise<DownloadResponse>` -- GET to `/download/{sessionId}/{model}/{iterationIndex}`

### Verification Checklist

- [x] `Iteration` type includes optional `adaptedPrompt`
- [x] New response types are defined and exported
- [x] API client functions call correct endpoints
- [x] `npm run typecheck` passes

### Testing Instructions

Add to `frontend/tests/__tests__/api/client.test.ts` (or create if not present):

- `test_getRecentPrompts_calls_correct_endpoint` -- mock fetch, verify URL and method
- `test_getPromptHistory_includes_query_param` -- mock fetch, verify `?q=` is included when query is provided
- `test_getDownloadUrl_constructs_path` -- mock fetch, verify path includes sessionId/model/index

Run: `cd frontend && npm test -- tests/__tests__/api/`

### Commit Message Template

```text
feat(types): add types and API client for prompts, download, adaptation

- Iteration type gains optional adaptedPrompt field
- new PromptHistoryResponse, DownloadResponse types
- API client functions for /prompts/recent, /prompts/history, /download
```

## Task 3.2: Add Download Button to IterationCard

### Goal

Add a download button to completed iteration cards that fetches a presigned URL and opens it in a new tab (triggering browser download).

### Files to Modify

- `frontend/src/components/generation/IterationCard.tsx` -- Add download button

### Implementation Steps

1. Read `IterationCard.tsx` (already read above). The component receives `model` and `iteration` props. It renders an image when `iteration.status === 'completed'`.

1. Add a download button in the card footer (the `p-2 bg-gray-50` div at line 145):
   - Position it to the right of the iteration number/prompt text
   - Use a download icon (SVG arrow-down-tray or similar)
   - On click (stop propagation so it doesn't trigger `onExpand`):
     - Call `getDownloadUrl(sessionId, model, iteration.index)`
     - Open the returned URL in a new tab: `window.open(url, '_blank')`
   - Only show when `iteration.status === 'completed'`

1. The `IterationCard` does not currently have access to `sessionId`. It needs to be passed as a prop.
   - Add `sessionId?: string` to `IterationCardProps`
   - Thread it through from `ModelColumn` -> `IterationCard`. `ModelColumn` does not have `sessionId` either -- it gets `column` (which is `ModelColumnType`). The session ID comes from `useAppStore.currentSession.sessionId`.
   - In `ModelColumn`, read `sessionId` from the app store: `const sessionId = useAppStore((s) => s.currentSession?.sessionId)`
   - Pass `sessionId={sessionId}` to each `IterationCard`

1. Import `getDownloadUrl` from `@/api/client` in `IterationCard.tsx`.

1. Add loading state for the download button (brief spinner while fetching the presigned URL).

### Verification Checklist

- [x] Download button appears on completed iteration cards
- [x] Clicking download opens presigned URL in new tab
- [x] Download click does not trigger image expand
- [x] Button not shown on non-completed iterations
- [x] Loading state shown while fetching URL

### Testing Instructions

Create `frontend/tests/__tests__/components/IterationCard.test.tsx`:

- `test_download_button_visible_on_completed` -- render with completed iteration, verify button exists
- `test_download_button_hidden_on_error` -- render with error iteration, verify no button
- `test_download_click_calls_api` -- mock `getDownloadUrl`, click button, verify called with correct args
- `test_download_click_stops_propagation` -- click download, verify `onExpand` not called

Run: `cd frontend && npm test -- tests/__tests__/components/IterationCard`

### Commit Message Template

```text
feat(frontend): add download button to iteration cards

- fetches presigned URL via /download endpoint
- opens in new tab for browser download
- loading state while URL is generated
```

## Task 3.3: Add Adapted Prompt Display to IterationCard

### Goal

Show the adapted prompt (the model-specific version) in an expandable section on each iteration card, when the `adaptedPrompt` field is present and differs from the session-level prompt.

### Files to Modify

- `frontend/src/components/generation/IterationCard.tsx` -- Add expandable adapted prompt section

### Implementation Steps

1. The `Iteration` type now has optional `adaptedPrompt` (from Task 3.1). The iteration card already shows `#{iteration.index}: {truncate(iteration.prompt, 50)}` in the footer.

1. Add an expandable section below the existing prompt text:
   - Only render if `iteration.adaptedPrompt` exists and is different from `iteration.prompt`
   - Default state: collapsed, showing a small "Adapted prompt" toggle link/button
   - Expanded state: shows the full `adaptedPrompt` text in a slightly different style (e.g., smaller text, muted color, italic)
   - Toggle is local state (`useState`) within the card

1. UI layout in the footer div (line 145):
   - Keep existing: `#{iteration.index}: {truncate(iteration.prompt, 50)}`
   - Below it (conditionally): expandable adapted prompt
   - Use a chevron icon or "Show adapted" / "Hide adapted" text toggle

1. Keep it minimal -- this is informational, not interactive. No editing of adapted prompts.

### Verification Checklist

- [x] Adapted prompt section appears when `adaptedPrompt` differs from `prompt`
- [x] Section is collapsed by default
- [x] Toggle expands/collapses the adapted prompt text
- [x] Section does not appear when `adaptedPrompt` is absent or identical to `prompt`

### Testing Instructions

Add to `frontend/tests/__tests__/components/IterationCard.test.tsx`:

- `test_adapted_prompt_shown_when_different` -- render with `adaptedPrompt` different from `prompt`, verify toggle exists
- `test_adapted_prompt_hidden_when_absent` -- render without `adaptedPrompt`, verify no toggle
- `test_adapted_prompt_hidden_when_same` -- render with `adaptedPrompt` equal to `prompt`, verify no toggle
- `test_adapted_prompt_toggles` -- click toggle, verify full text appears, click again, verify collapsed

Run: `cd frontend && npm test -- tests/__tests__/components/IterationCard`

### Commit Message Template

```text
feat(frontend): show adapted prompt on iteration cards

- expandable section when model-specific prompt differs
- collapsed by default, toggle to reveal
```

## Task 3.4: Add Prompt History Panel

### Goal

Add a prompt history section to the generation panel that shows the user's prompt history (when authenticated) and the global recent feed (always). Clicking a prompt populates the prompt input.

### Files to Create

- `frontend/src/components/generation/PromptHistory.tsx` -- History panel component

### Files to Modify

- `frontend/src/components/generation/GenerationPanel.tsx` -- Include PromptHistory

### Implementation Steps

1. Create `PromptHistory.tsx` component:
   - Tabs or toggle: "My History" (authenticated only) and "Recent" (always)
   - If not authenticated, only show "Recent" tab
   - Use `useAuthStore((s) => s.isAuthenticated())` to check auth state

1. "Recent" tab:
   - On mount, call `getRecentPrompts(20)` (show 20 items)
   - Display as a scrollable list of prompt text snippets
   - Each item shows truncated prompt text and relative timestamp (e.g., "2h ago")
   - Clicking an item calls `useAppStore.getState().setPrompt(item.prompt)` to populate the input
   - Optional: "Load more" button if total > displayed

1. "My History" tab (authenticated only):
   - On mount, call `getPromptHistory(20)`
   - Same list UI as recent
   - Add a search input at the top: debounced text input that calls `getPromptHistory(20, searchQuery)` when the user types
   - Clicking an item populates the prompt input

1. Integrate into `GenerationPanel.tsx`:
   - Add `<PromptHistory />` after the input section and before the 4-column layout (between lines 358 and 360)
   - Wrap in `<ErrorBoundary componentName="PromptHistory">`
   - The section should be collapsible (default collapsed to not clutter the main flow). Use a header like "Prompt History" with a toggle.

1. Styling: keep it compact. The history panel should not dominate the page. Use a max height with scroll, muted colors, and small text.

### Verification Checklist

- [x] Recent feed loads and displays for all users
- [x] History tab only appears when authenticated
- [x] Clicking a prompt populates the input field
- [x] Search filters history results
- [x] Panel is collapsible
- [x] Loading state shown while fetching

### Testing Instructions

Create `frontend/tests/__tests__/components/PromptHistory.test.tsx`:

- `test_recent_tab_renders_for_unauthenticated` -- mock auth as not authenticated, verify "Recent" tab visible, "My History" not visible
- `test_both_tabs_render_for_authenticated` -- mock auth, verify both tabs visible
- `test_recent_fetches_on_mount` -- mock API, verify `getRecentPrompts` called
- `test_click_prompt_sets_input` -- click a prompt item, verify `setPrompt` called with correct text
- `test_search_filters_history` -- type in search, verify `getPromptHistory` called with query param
- `test_panel_collapses` -- click toggle, verify content hidden

Run: `cd frontend && npm test -- tests/__tests__/components/PromptHistory`

### Commit Message Template

```text
feat(frontend): add prompt history panel with recent feed

- "Recent" tab for all users (global feed)
- "My History" tab for authenticated users with search
- click to re-use prompt in input field
- collapsible panel in generation view
```

## Task 3.5: Add Comparison Modal

### Goal

Build a full-screen comparison modal that shows 2-4 selected models' images side-by-side at equal size, with a per-slot iteration picker.

### Files to Create

- `frontend/src/components/generation/CompareModal.tsx` -- Modal component

### Files to Modify

- `frontend/src/stores/useUIStore.ts` -- Add compare state
- `frontend/src/types/store.ts` -- Add compare state types
- `frontend/src/components/generation/GenerationPanel.tsx` -- Add Compare button and modal

### Implementation Steps

1. Update `useUIStore` and its types:
   - Add to `UIState`: `isCompareOpen: boolean` (default `false`)
   - Add to `UIActions`: `openCompare: () => void`, `closeCompare: () => void`
   - Implement: `openCompare` sets `isCompareOpen: true`, `closeCompare` sets `isCompareOpen: false`

1. Create `CompareModal.tsx`:
   - Props: `models: ModelName[]`, `session: Session`, `onClose: () => void`
   - Renders a full-screen modal overlay (similar pattern to existing `ImageModal` at `frontend/src/components/features/generation/ImageModal.tsx`)
   - Grid layout: `grid grid-cols-2` for 2 models, `grid-cols-3` for 3, `grid-cols-2 lg:grid-cols-4` for 4
   - Each slot:
     - Model name header
     - Image at full width (`<img>` tag with CloudFront URL)
     - Iteration picker: `<select>` dropdown listing all completed iterations for that model (default: latest completed)
     - Local state: `Record<ModelName, number>` mapping model to selected iteration index
   - Close on ESC key (add `useEffect` with `keydown` listener)
   - Close on clicking the backdrop (outside the content area)
   - Close button (X) in the top-right corner

1. Add "Compare" button to `GenerationPanel.tsx`:
   - Show when `selectedModels.size >= 2` and there is a `currentSession`
   - Place next to the `MultiIterateInput` (around line 344)
   - On click: call `openCompare()` from UI store
   - Button text: "Compare ({selectedModels.size})"

1. Render `CompareModal` in `GenerationPanel.tsx`:
   - After the `ImageModal` (around line 418)
   - `{isCompareOpen && currentSession && (<CompareModal models={Array.from(selectedModels)} session={currentSession} onClose={closeCompare} />)}`
   - Read `isCompareOpen` and `closeCompare` from `useUIStore`

1. Accessibility:
   - Modal has `role="dialog"` and `aria-modal="true"`
   - Focus trap within the modal (use `tabIndex` on close button, auto-focus on open)
   - `aria-label` on each image slot

### Verification Checklist

- [x] Compare button appears when 2+ models selected and session exists
- [x] Modal shows selected models' images at equal size
- [x] Iteration picker changes the displayed image per slot
- [x] ESC key closes the modal
- [x] Clicking backdrop closes the modal
- [x] Works with 2, 3, and 4 models selected
- [x] Default iteration is the latest completed

### Testing Instructions

Create `frontend/tests/__tests__/components/CompareModal.test.tsx`:

- `test_compare_modal_renders_selected_models` -- render with 2 models, verify both slots appear with model names
- `test_compare_modal_shows_latest_iteration` -- render with session data containing multiple iterations, verify latest image shown
- `test_iteration_picker_changes_image` -- change select value, verify displayed image URL changes
- `test_escape_closes_modal` -- simulate ESC keypress, verify `onClose` called
- `test_backdrop_click_closes` -- click backdrop, verify `onClose` called
- `test_compare_button_appears_with_selection` -- render GenerationPanel with 2 models selected, verify Compare button visible
- `test_compare_button_hidden_with_one_model` -- render with 1 model selected, verify no Compare button

Run: `cd frontend && npm test -- tests/__tests__/components/CompareModal`

### Commit Message Template

```text
feat(frontend): add side-by-side comparison modal

- full-screen modal with equal-size image slots
- per-slot iteration picker (defaults to latest)
- activated via multi-select checkboxes + Compare button
- close via ESC, backdrop click, or close button
```

## Task 3.6: Verify Image Rendering with New Storage Format

### Goal

Verify that the frontend correctly renders images served as raw PNG files from CloudFront (after the backend storage refactor). The current code uses `iteration.imageUrl` as the `src` for `<img>` tags -- this should work since CloudFront now serves real images instead of JSON.

### Files to Verify (read-only)

- `frontend/src/components/generation/IterationCard.tsx` -- `<img src={iteration.imageUrl}>` at line 131
- `frontend/src/components/features/generation/ImageModal.tsx` -- Image display in modal
- `frontend/src/components/gallery/GalleryBrowser.tsx` -- Gallery image rendering

### Implementation Steps

1. Read `IterationCard.tsx` line 131: `<img src={iteration.imageUrl} ...>`. The `imageUrl` comes from the `/status` response where `handle_status()` calls `image_storage.get_cloudfront_url(iteration["imageKey"])`. After the storage refactor, the key ends in `.png`, so the CloudFront URL points to a real PNG file. The browser will render it correctly. **No changes needed.**

1. Read `ImageModal.tsx` to verify it also uses `imageUrl` as `src`. **No changes expected.**

1. Gallery preview URLs: `handle_gallery_list()` uses the first image's CloudFront URL as `previewUrl`. For new `.png` images, this is a direct image URL. For old `.json` images, the URL points to a JSON file -- browsers won't render it. This is acceptable during the 30-day transition. No code change needed.

1. If any component tries to fetch the image URL and parse it as JSON (rather than using it as an `<img src>`), that would break. Search the frontend for any `fetch(imageUrl)` or JSON parsing of image URLs. This should not exist based on the code read, but verify.

### Verification Checklist

- [x] `<img src>` tags work with CloudFront PNG URLs
- [x] No frontend code fetches and parses image URLs as JSON
- [x] ImageModal works with direct PNG URLs

### Testing Instructions

This is a verification task, not a code change. Run the existing frontend tests to confirm nothing broke:

```bash
cd frontend && npm test
```

If any test mocks image URLs with `.json` extensions, they may need updating to `.png` for consistency, but functionally the `<img>` tag doesn't care about the extension.

### Commit Message Template

No commit needed unless changes are required. If changes are found:

```text
fix(frontend): update image URL handling for PNG storage format
```

## Phase Verification

- [x] All tasks committed (3.1 through 3.6)
- [x] `cd frontend && npm run lint` passes
- [x] `cd frontend && npm run typecheck` passes
- [x] `cd frontend && npm test` passes
- [x] Download button works on completed iteration cards
- [x] Adapted prompt section appears when adaptation is active
- [x] Prompt history panel shows recent feed for all users
- [x] Prompt history panel shows user history when authenticated
- [x] Re-run from history populates prompt input
- [x] Comparison modal shows selected models side-by-side
- [x] Iteration picker changes displayed image in compare modal
- [x] `cd frontend && npm run build` succeeds (production build)
