# Phase 3: Feature Components

## Phase Goal

Migrate the core feature components: prompt input, image generation, image display, and gallery. This phase converts the main user-facing features to TypeScript with Tailwind while integrating with Zustand stores.

**Success Criteria:**
- Prompt input with enhancement working
- Image generation flow functional end-to-end
- Image grid displays results with modal preview
- Gallery browser functional in left column (desktop) / toggle (mobile)
- All state managed via Zustand stores
- Context providers removed

**Estimated Tokens:** ~45,000

---

## Prerequisites

- Phase 2 complete (core components migrated)
- Zustand stores created
- Layout system working
- Sound and animation systems functional

---

## Tasks

### Task 1: Migrate Prompt Input Component

**Goal:** Convert the prompt text input to TypeScript with Tailwind styling.

**Files to Modify/Create:**
- `frontend/src/components/generation/PromptInput.tsx` - Rename and convert
- Delete: `frontend/src/components/generation/PromptInput.jsx`
- Delete: `frontend/src/components/generation/PromptInput.module.css`

**Prerequisites:**
- useAppStore created with prompt state
- Sound hook available

**Implementation Steps:**
- Convert PromptInput.jsx to TypeScript
- Replace Context usage with useAppStore for prompt state
- Style textarea with Tailwind matching reference (thick accent border, rounded corners)
- Add character counter if applicable
- Add clear button with switch sound effect
- Make responsive (larger on desktop, full width on mobile)
- Style placeholder text appropriately

**Verification Checklist:**
- [x] Text input works and updates store
- [x] Styling matches reference aesthetic (accent border)
- [x] Clear button clears input and plays sound
- [x] Placeholder text visible and styled
- [x] Responsive sizing correct

**Testing Instructions:**
- Unit test input updates store state
- Test clear functionality
- Test character limit if implemented
- Manual test: verify visual appearance

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(components): migrate PromptInput to TypeScript

Convert to TSX with Zustand integration
Style with Tailwind accent border
Add clear button with sound effect
```

---

### Task 2: Migrate Prompt Enhancer Component

**Goal:** Convert the prompt enhancement feature to TypeScript.

**Files to Modify/Create:**
- `frontend/src/components/generation/PromptEnhancer.tsx` - Rename and convert
- Delete: `frontend/src/components/generation/PromptEnhancer.jsx`
- Delete: `frontend/src/components/generation/PromptEnhancer.module.css`

**Prerequisites:**
- PromptInput migrated
- API client typed

**Implementation Steps:**
- Convert PromptEnhancer to TypeScript with typed API response
- Integrate with useAppStore for prompt state
- Style enhance button with playful accent colors
- Add loading state during enhancement API call
- Show before/after comparison or just update input
- Add swoosh sound when enhancement completes
- Handle API errors gracefully with toast notification

**Verification Checklist:**
- [x] Enhance button triggers API call
- [x] Loading state visible during request
- [x] Enhanced prompt updates input field
- [x] Sound plays on completion
- [x] Errors show toast notification

**Testing Instructions:**
- Unit test with mocked API response
- Test loading state renders correctly
- Test error handling with failed API call
- Manual test: verify enhancement flow works

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(components): migrate PromptEnhancer to TypeScript

Convert to TSX with typed API integration
Add loading and error states
Integrate sound effect on completion
```

---

### Task 3: Migrate Random Prompt Button

**Goal:** Convert the random prompt generator to TypeScript.

**Files to Modify/Create:**
- `frontend/src/components/features/generation/RandomPromptButton.tsx` - Rename and convert (keep in features/)
- Delete: `frontend/src/components/features/generation/RandomPromptButton.jsx`
- Delete: `frontend/src/components/features/generation/RandomPromptButton.module.css`

**Note:** This component stays in `features/generation/` to maintain existing directory structure.

**Prerequisites:**
- Button component available
- Seed prompts data typed (Phase 1 Task 10)

**Implementation Steps:**
- Convert RandomPromptButton to TypeScript
- Type the seed prompts data file
- Use Button component with appropriate variant
- Play switch sound when selecting random prompt
- Update prompt in useAppStore
- Add fun animation or visual feedback on selection

**Verification Checklist:**
- [x] Random prompt selected on click
- [x] Different prompt each click (within reason)
- [x] Sound plays on selection
- [x] Prompt updates in input field
- [x] Button styled consistently

**Testing Instructions:**
- Unit test random selection logic
- Test sound plays on click
- Verify prompt updates store state

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(components): migrate RandomPromptButton to TypeScript

Convert to TSX with typed seed data
Add switch sound on random selection
Use consistent Button styling
```

---

### Task 4: Migrate Generation Panel Component

**Goal:** Convert the main generation control panel to TypeScript.

**Files to Modify/Create:**
- `frontend/src/components/generation/GenerationPanel.tsx` - Rename and convert
- Delete: `frontend/src/components/generation/GenerationPanel.jsx`
- Delete: `frontend/src/components/generation/GenerationPanel.module.css`

**Prerequisites:**
- PromptInput, PromptEnhancer, RandomPromptButton migrated
- GenerateButton (from Phase 2) available

**Implementation Steps:**
- Convert GenerationPanel to TypeScript
- Compose child components (PromptInput, enhancer, random, generate button)
- Integrate with useAppStore for generation state
- Style panel with Tailwind (card-like appearance with shadows)
- Ensure proper spacing between child components
- Make panel responsive (stacks vertically on mobile)

**Verification Checklist:**
- [x] Panel renders all child components
- [x] Layout is clean and well-spaced
- [x] Responsive stacking works on mobile
- [x] All child component interactions work
- [x] Styling matches playful aesthetic

**Testing Instructions:**
- Unit test panel renders children
- Test integration with store
- Manual test: verify complete input flow

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(components): migrate GenerationPanel to TypeScript

Convert to TSX composing input components
Style with card-like Tailwind appearance
Add responsive layout behavior
```

---

### Task 5: Migrate Job Polling Hook

**Goal:** Convert the job polling hook to TypeScript with proper types.

**Files to Modify/Create:**
- `frontend/src/hooks/useJobPolling.ts` - Rename and convert
- Delete: `frontend/src/hooks/useJobPolling.js`

**Prerequisites:**
- API types defined
- useAppStore available

**Implementation Steps:**
- Convert useJobPolling to TypeScript
- Type the job status response (pending, in_progress, completed, failed)
- Type the polling options (interval, timeout)
- Update store with job progress
- Handle completion and error states
- Clean up polling on unmount or completion
- Return typed status and error information

**Verification Checklist:**
- [x] Polling starts when job ID provided
- [x] Status updates flow to store
- [x] Polling stops on completion
- [x] Polling stops on component unmount
- [x] Error state handled correctly

**Testing Instructions:**
- Unit test with mocked timer and API
- Test polling starts and stops correctly
- Test status updates propagate to callback
- Test cleanup on unmount

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(hooks): migrate useJobPolling to TypeScript

Add typed job status responses
Handle polling lifecycle correctly
Integrate with Zustand store
```

---

### Task 6: Migrate Image Card Component

**Goal:** Convert the individual image card to TypeScript with Tailwind.

**Files to Modify/Create:**
- `frontend/src/components/generation/ImageCard.tsx` - Rename and convert
- Delete: `frontend/src/components/generation/ImageCard.jsx`
- Delete: `frontend/src/components/generation/ImageCard.module.css`

**Prerequisites:**
- Modal component available
- Sound hook available

**Implementation Steps:**
- Convert ImageCard to TypeScript with typed image prop
- Style card with Tailwind (rounded, shadow, hover effects)
- Add click handler to open modal (expand sound)
- Show loading skeleton while image loads
- Show error state if image fails
- Add model name/provider badge on card
- Make card responsive (size adjusts to grid)

**Verification Checklist:**
- [x] Image displays correctly in card
- [x] Loading skeleton shows before load
- [x] Click opens modal with expand sound
- [x] Model badge displays provider info
- [x] Hover effects applied
- [x] Error state shows placeholder

**Testing Instructions:**
- Unit test card renders image
- Test loading and error states
- Test click handler fires
- Test sound plays on click

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(components): migrate ImageCard to TypeScript

Convert to TSX with loading/error states
Add model badge and hover effects
Integrate expand sound on click
```

---

### Task 7: Migrate Image Modal Component

**Goal:** Convert the image preview modal to TypeScript.

**Files to Modify/Create:**
- `frontend/src/components/features/generation/ImageModal.tsx` - Rename and convert (keep in features/)
- Delete: `frontend/src/components/features/generation/ImageModal.jsx`
- Delete: `frontend/src/components/features/generation/ImageModal.module.css`

**Note:** This component stays in `features/generation/` to maintain existing directory structure.

**Prerequisites:**
- Modal base component available
- Image type defined

**Implementation Steps:**
- Convert ImageModal to TypeScript extending base Modal
- Display full-size image with zoom capability
- Show image metadata (model, prompt, timestamp)
- Add download button functionality
- Style with Tailwind for dark theme
- Ensure image is responsive and centered
- Add navigation if multiple images (prev/next)

**Verification Checklist:**
- [x] Modal displays full-size image
- [x] Metadata shows correctly
- [x] Download button works
- [x] Keyboard navigation works (arrows for prev/next)
- [x] Close on escape or click outside

**Testing Instructions:**
- Unit test modal renders image
- Test download functionality
- Test navigation between images
- Test keyboard handlers

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(components): migrate ImageModal to TypeScript

Convert to TSX with full image display
Add download and navigation features
Show image metadata
```

---

### Task 8: Migrate Image Grid Component

**Goal:** Convert the image results grid to TypeScript.

**Files to Modify/Create:**
- `frontend/src/components/generation/ImageGrid.tsx` - Rename and convert
- Delete: `frontend/src/components/generation/ImageGrid.jsx`
- Delete: `frontend/src/components/generation/ImageGrid.module.css`

**Prerequisites:**
- ImageCard component migrated
- useAppStore with images state

**Implementation Steps:**
- Convert ImageGrid to TypeScript
- Use Tailwind grid utilities for layout
- Make grid responsive (1 col mobile, 2 col tablet, 3+ col desktop)
- Show empty state when no images
- Show loading skeletons during generation
- Animate new images appearing
- Integrate with useAppStore for image data

**Verification Checklist:**
- [x] Grid displays images in responsive columns
- [x] Empty state shows when no images
- [x] Loading skeletons show during generation
- [x] New images animate in
- [x] Grid adapts to screen size

**Testing Instructions:**
- Unit test grid renders correct number of cards
- Test empty state rendering
- Test loading state with skeletons
- Manual test: verify responsive behavior

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(components): migrate ImageGrid to TypeScript

Convert to TSX with responsive grid layout
Add empty and loading states
Animate new image appearance
```

---

### Task 9: Migrate Gallery Browser Component

**Goal:** Convert the gallery browsing component to TypeScript.

**Files to Modify/Create:**
- `frontend/src/components/gallery/GalleryBrowser.tsx` - Rename and convert
- Delete: `frontend/src/components/gallery/GalleryBrowser.jsx`
- Delete: `frontend/src/components/gallery/GalleryBrowser.module.css`

**Prerequisites:**
- Gallery types defined
- useGallery hook available

**Implementation Steps:**
- Convert GalleryBrowser to TypeScript
- Integrate with useGallery hook (convert if needed)
- Display list of past generation sessions
- Each item shows thumbnail, prompt snippet, date
- Click loads session images into main view
- Style with Tailwind for scrollable list
- Add loading and empty states
- Play switch sound when selecting gallery item

**Verification Checklist:**
- [x] Gallery items display correctly
- [x] Click loads selected session
- [x] Loading state shows spinner
- [x] Empty state shows helpful message
- [x] Sound plays on selection
- [x] Scrollable when many items

**Testing Instructions:**
- Unit test with mocked gallery data
- Test click handler updates selection
- Test loading and empty states
- Test scroll behavior with many items

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(components): migrate GalleryBrowser to TypeScript

Convert to TSX with gallery list display
Add thumbnail, prompt preview, date
Integrate switch sound on selection
```

---

### Task 10: Migrate Gallery Preview Component

**Goal:** Convert the gallery preview widget to TypeScript.

**Files to Modify/Create:**
- `frontend/src/components/gallery/GalleryPreview.tsx` - Rename and convert
- Delete: `frontend/src/components/gallery/GalleryPreview.jsx`
- Delete: `frontend/src/components/gallery/GalleryPreview.module.css`

**Prerequisites:**
- GalleryBrowser migrated
- Layout system with gallery column

**Implementation Steps:**
- Convert GalleryPreview to TypeScript
- Show compact preview suitable for sidebar
- Display recent generations thumbnails
- Click to expand full gallery browser
- Style to fit left column of desktop layout
- On mobile, this becomes toggle button for gallery drawer/modal

**Verification Checklist:**
- [x] Preview shows recent items
- [x] Compact design fits sidebar
- [x] Click expands or navigates to full view
- [x] Mobile toggle behavior works
- [x] Styling consistent with overall design

**Testing Instructions:**
- Unit test preview renders items
- Test click behavior
- Test mobile toggle functionality
- Manual test: verify fits in layout

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(components): migrate GalleryPreview to TypeScript

Convert to TSX with compact sidebar display
Add mobile toggle behavior
Show recent generation thumbnails
```

---

### Task 11: Migrate Gallery Hook

**Goal:** Convert the useGallery hook to TypeScript.

**Files to Modify/Create:**
- `frontend/src/hooks/useGallery.ts` - Rename and convert
- Delete: `frontend/src/hooks/useGallery.js`

**Prerequisites:**
- API types defined
- Gallery type available

**Implementation Steps:**
- Convert useGallery to TypeScript
- Type the gallery list response
- Type the individual gallery item
- Handle loading and error states
- Cache gallery data to avoid refetching
- Provide refresh function
- Return typed data and status

**Verification Checklist:**
- [x] Hook fetches gallery data
- [x] Loading state exposed
- [x] Error handling works
- [x] Refresh function refetches
- [x] Return type is fully typed

**Testing Instructions:**
- Unit test with mocked API
- Test loading state
- Test error handling
- Test refresh functionality

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(hooks): migrate useGallery to TypeScript

Add typed gallery responses
Handle loading and error states
Add cache and refresh capability
```

---

### Task 12: Migrate API Client to TypeScript

**Goal:** Convert the API client to TypeScript with full type safety.

**Files to Modify/Create:**
- `frontend/src/api/client.ts` - Rename and convert
- `frontend/src/api/config.ts` - Rename and convert
- Delete: `frontend/src/api/client.js`
- Delete: `frontend/src/api/config.js`

**Prerequisites:**
- API types defined in types/api.ts

**Implementation Steps:**
- Convert client.js to TypeScript
- Type all API methods with request/response types
- Type configuration values
- Add proper error typing
- Use generics where appropriate for flexibility
- Ensure fetch calls have typed responses
- Add request/response interceptors if needed

**Verification Checklist:**
- [x] All API methods are typed
- [x] Errors are properly typed
- [x] Config values are typed
- [x] No `any` types in client
- [x] IDE autocomplete works for API calls

**Testing Instructions:**
- Type check passes on client file
- Existing API tests still pass
- Verify autocomplete in consuming components

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(api): migrate API client to TypeScript

Type all API methods and responses
Add error typing
Remove any types
```

---

### Task 13: Migrate Context to Zustand

**Goal:** Remove React Context providers and use Zustand stores exclusively.

**Files to Modify/Create:**
- `frontend/src/stores/useAppStore.ts` - Update with toast functionality
- `frontend/src/stores/useUIStore.ts` - Ensure complete
- `frontend/src/App.tsx` - Remove context providers
- Delete: `frontend/src/context/AppContext.jsx`
- Delete: `frontend/src/context/ToastContext.jsx`

**Prerequisites:**
- All components using stores instead of context
- Stores feature-complete

**Implementation Steps:**
- Audit all context usage and ensure store equivalents exist
- Move toast state and actions to useUIStore
- Update App.tsx to remove provider wrappers
- Update any remaining context consumers
- Delete context files
- Verify no context imports remain

**Verification Checklist:**
- [x] No context providers in App
- [x] All state accessed via stores
- [x] Toast system works via store
- [x] No context imports in codebase
- [x] App functionality unchanged

**Testing Instructions:**
- Run full app and verify all features work
- Check no context-related errors
- Verify toast notifications still work

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(stores): migrate Context to Zustand

Move toast state to useUIStore
Remove Context providers from App
Delete context files
```

---

### Task 14: Migrate useImageLoader Hook

**Goal:** Convert the image loading hook to TypeScript.

**Files to Modify/Create:**
- `frontend/src/hooks/useImageLoader.ts` - Rename and convert
- Delete: `frontend/src/hooks/useImageLoader.js`

**Prerequisites:**
- TypeScript configured

**Implementation Steps:**
- Convert useImageLoader to TypeScript
- Type the loading states (loading, loaded, error)
- Type the return value
- Handle image load events with proper typing
- Clean up event listeners on unmount

**Verification Checklist:**
- [x] Hook compiles without errors
- [x] Loading states properly typed
- [x] Image load/error handling works
- [x] Cleanup on unmount

**Testing Instructions:**
- Unit test with mocked Image object
- Test loading and error states

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(hooks): migrate useImageLoader to TypeScript

Add typed loading states
Handle image events with proper types
```

---

### Task 15: Migrate useMemoizedCallback Hook

**Goal:** Convert the memoized callback hook to TypeScript.

**Files to Modify/Create:**
- `frontend/src/hooks/useMemoizedCallback.ts` - Rename and convert
- Delete: `frontend/src/hooks/useMemoizedCallback.js`

**Prerequisites:**
- TypeScript configured

**Implementation Steps:**
- Convert useMemoizedCallback to TypeScript
- Use proper generic types for callback functions
- Ensure proper typing for dependencies
- Maintain useCallback semantics

**Verification Checklist:**
- [x] Hook compiles without errors
- [x] Generic types work correctly
- [x] Callback memoization works
- [x] Dependencies typed properly

**Testing Instructions:**
- Unit test callback memoization
- Test with different callback signatures

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(hooks): migrate useMemoizedCallback to TypeScript

Add generic callback typing
Maintain memoization semantics
```

---

### Task 16: Migrate Utility Functions

**Goal:** Convert remaining utility files to TypeScript.

**Files to Modify/Create:**
- `frontend/src/utils/correlation.ts` - Rename and convert
- `frontend/src/utils/errorMessages.ts` - Rename and convert
- `frontend/src/utils/imageHelpers.ts` - Rename and convert
- `frontend/src/utils/logger.ts` - Rename and convert
- Delete all corresponding .js files

**Prerequisites:**
- Types available for function parameters and returns

**Implementation Steps:**
- Convert each utility file to TypeScript
- Add proper parameter and return types
- Remove any implicit `any` types
- Export types if they might be useful elsewhere
- Ensure no breaking changes to function signatures

**Verification Checklist:**
- [x] All utility files are .ts
- [x] All functions have typed parameters
- [x] All functions have typed returns
- [x] No `any` types
- [x] Consuming code still works

**Testing Instructions:**
- Run existing utility tests
- Type check all files
- Verify utilities work in components

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(utils): migrate utility functions to TypeScript

Convert all utility files to TypeScript
Add complete type annotations
```

---

## Phase Verification

After completing all tasks in this phase:

1. **Full Feature Test:**
   - Enter a prompt → click enhance → generate images
   - View images in grid → click to open modal
   - Download an image
   - View gallery → select past session
   - Verify sounds play at appropriate times

2. **TypeScript Check:**
   ```bash
   npx tsc --noEmit
   # Should pass with no errors
   ```

3. **Store Check:**
   - Open React DevTools or Zustand debugger
   - Verify state updates flow correctly
   - No context providers visible in component tree

4. **Responsive Check:**
   - Desktop: Gallery in left column, generation in right
   - Mobile: Single column with gallery toggle
   - Smooth transition between layouts

5. **Test Check:**
   ```bash
   npm test
   # All tests should pass
   ```

### Integration Points

- Generation flow complete: prompt → enhance → generate → display
- Gallery integrated: view, select, load historical sessions
- Layouts populated: gallery left, generation right
- All state flows through Zustand stores

### Known Limitations

- Some animations may need polish (Phase 4)
- Accessibility may need review (Phase 4)
- Test coverage may need improvement (Phase 4)

### Technical Debt

- Consider adding React Query for API state management
- Gallery pagination for large datasets
- Image lazy loading optimization

---

## Review Feedback (Iteration 1) - RESOLVED ✓

Previous issues have been addressed:
- ✓ Context files deleted
- ✓ Toast migrated to Zustand (`useToastStore`)
- ✓ All 323 tests passing
- ✓ Context imports removed from codebase

---

## Review Feedback (Iteration 2)

### Minor Issues - Test File Quality

> **Consider:** Running `npx tsc --noEmit` shows 5 TypeScript errors in `tests/__tests__/stores/useAppStore.test.ts`. The test passes partial `Job` objects missing required fields (`prompt`, `createdAt`, `results`, `modelCount`).
>
> **Think about:** Should the test file use complete mock Job objects, or should the `Job` type allow partial objects for testing?

### Minor Issues - Unused Imports

> **Consider:** Running `npm run lint` shows 3 unused import errors in test files:
> - `ImageCard.test.jsx`: unused `act`
> - `ImageGrid.test.jsx`: unused `act`
> - `PromptInput.test.jsx`: unused `fireEvent`
>
> **Reflect:** These are minor cleanup items that don't affect functionality but should be addressed for code quality.

### Verification Status

```
Build:       ✓ Passes
Tests:       ✓ 323 passing (28 files)
TypeScript:  ⚠ 5 errors in test files only (source code clean)
Lint:        ⚠ 3 unused import warnings in test files
```

**Note:** These are minor test file issues. Source code is clean and functional.
