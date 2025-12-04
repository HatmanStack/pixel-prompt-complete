# Phase 1: Infrastructure Setup

## Phase Goal

Establish the TypeScript and Tailwind CSS infrastructure that all subsequent phases will build upon. This phase sets up the build system, design tokens, and core type definitions without modifying existing component functionality.

**Success Criteria:**
- TypeScript compiles without errors in strict mode
- Tailwind CSS builds and applies custom theme
- Sigmar font loads correctly
- Sound assets copied from reference and loadable
- Existing tests still pass (may need minor adjustments)

**Estimated Tokens:** ~35,000

---

## Prerequisites

- Node.js v18+ installed
- Access to reference project for assets
- Working AWS deployment (from existing setup)

---

## Tasks

### Task 1: Install TypeScript and Configure Build

**Goal:** Add TypeScript to the Vite build pipeline with strict configuration.

**Files to Modify/Create:**
- `frontend/package.json` - Add TypeScript dependencies
- `frontend/tsconfig.json` - TypeScript configuration
- `frontend/tsconfig.node.json` - Node-specific TS config for Vite
- `frontend/vite.config.ts` - Rename and update Vite config

**Prerequisites:**
- None (first task)

**Implementation Steps:**
- Install TypeScript, @types/react, @types/react-dom as dev dependencies
- Create tsconfig.json with strict mode, path aliases matching existing @ alias
- Configure jsx to "react-jsx" for React 19 compatibility
- Rename vite.config.js to vite.config.ts and add type annotations
- Ensure vite-env.d.ts exists for Vite client types
- Update package.json scripts to use tsc for type checking

**Verification Checklist:**
- [ ] `npx tsc --noEmit` runs without errors (may have component errors initially)
- [ ] `npm run dev` still starts the development server
- [ ] Path alias `@/` resolves correctly in TypeScript
- [ ] No regressions in existing functionality

**Testing Instructions:**
- Run `npx tsc --noEmit` to verify TypeScript configuration
- Run `npm run dev` to verify Vite still works
- Check browser console for any new errors

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

feat(config): add TypeScript configuration

Install TypeScript and type definitions
Configure strict mode with path aliases
Migrate vite.config to TypeScript
```

---

### Task 2: Install and Configure Tailwind CSS

**Goal:** Set up Tailwind CSS with PostCSS, replacing the need for CSS Modules.

**Files to Modify/Create:**
- `frontend/package.json` - Add Tailwind dependencies
- `frontend/tailwind.config.ts` - Tailwind configuration with custom theme
- `frontend/postcss.config.js` - PostCSS configuration
- `frontend/src/index.css` - Add Tailwind directives

**Prerequisites:**
- Task 1 complete (TypeScript configured)

**Implementation Steps:**
- Install tailwindcss, postcss, autoprefixer as dev dependencies
- Create tailwind.config.ts with TypeScript (use `satisfies Config`)
- Configure content paths to scan tsx files
- Add Tailwind directives (@tailwind base, components, utilities) to index.css
- Temporarily keep existing CSS for backward compatibility during migration
- Configure PostCSS with tailwindcss and autoprefixer plugins

**Verification Checklist:**
- [ ] Tailwind utility classes apply in browser (test with temp element)
- [ ] PostCSS processes CSS without errors
- [ ] Existing CSS Modules still work (no breaking changes yet)
- [ ] Build completes successfully with `npm run build`

**Testing Instructions:**
- Add a temporary element with Tailwind classes to App.tsx
- Verify classes apply correctly in browser dev tools
- Remove temporary element after verification
- Run `npm run build` to verify production build works

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

feat(config): add Tailwind CSS configuration

Install Tailwind and PostCSS
Configure content paths for TSX files
Add Tailwind directives to index.css
```

---

### Task 3: Configure Custom Design Tokens

**Goal:** Extend Tailwind with the project's design system colors, typography, and spacing.

**Files to Modify/Create:**
- `frontend/tailwind.config.ts` - Add theme extensions
- `frontend/src/styles/tokens.ts` - Export design tokens for JS usage (optional)

**Prerequisites:**
- Task 2 complete (Tailwind installed)

**Implementation Steps:**
- Define color palette based on Phase-0 specification (primary, secondary, accent, etc.)
- Add Sigmar font to fontFamily configuration
- Define custom spacing values (container, section, element)
- Add custom border radius values
- Define custom animations for breathing effect and loading states
- Consider dark mode support (project is dark-theme first)

**Verification Checklist:**
- [ ] Custom colors available as `bg-primary`, `text-accent`, etc.
- [ ] `font-display` class applies Sigmar font
- [ ] Custom animations defined and can be applied
- [ ] IntelliSense shows custom classes in VS Code

**Testing Instructions:**
- Create temporary test elements using custom theme values
- Verify colors match specification in browser
- Check font loading in Network tab
- Remove temporary elements after verification

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

feat(ui): add custom design tokens to Tailwind

Configure color palette (primary, accent, semantic)
Add Sigmar font family
Define custom animations for UI effects
```

---

### Task 4: Add Sigmar Font

**Goal:** Load the Sigmar display font used for headers and branding.

**Files to Modify/Create:**
- `frontend/src/index.css` or `frontend/index.html` - Font import
- `frontend/public/fonts/` (optional) - Self-hosted font files
- `frontend/tailwind.config.ts` - Ensure font-display configured

**Prerequisites:**
- Task 3 complete (Tailwind theme configured)

**Implementation Steps:**
- Option A: Use Google Fonts CDN link in index.html
- Option B: Self-host font from reference project's Sigmar folder
- Add font-display: swap for performance
- Ensure fallback fonts defined (cursive, sans-serif)
- Test font loading on slow connections

**Verification Checklist:**
- [ ] Sigmar font loads and renders correctly
- [ ] `font-display` Tailwind class applies Sigmar
- [ ] Fallback font displays if Sigmar fails to load
- [ ] No FOUT (Flash of Unstyled Text) or handled gracefully

**Testing Instructions:**
- Apply `font-display` class to a heading element
- Verify font renders as expected
- Throttle network to slow 3G and verify fallback behavior
- Check Lighthouse for font performance warnings

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

feat(ui): add Sigmar display font

Load Sigmar font for headers and branding
Configure font-display swap for performance
Add fallback font stack
```

---

### Task 5: Copy Sound Assets from Reference

**Goal:** Migrate sound effect files from the reference project to this project.

**Files to Modify/Create:**
- `frontend/public/sounds/click.wav` - Copy from reference
- `frontend/public/sounds/swoosh.mp3` - Copy from reference
- `frontend/public/sounds/switch.wav` - Copy from reference
- `frontend/public/sounds/expand.wav` - Copy from reference

**Prerequisites:**
- Access to `/home/christophergalliart/war/pixel-prompt-js/assets/`

**Implementation Steps:**
- Create `frontend/public/sounds/` directory
- Copy sound files from reference project's assets folder
- Verify file formats are web-compatible (wav, mp3)
- Test that files are accessible via `/sounds/filename.ext`
- Update any existing sound references to use correct paths

**Verification Checklist:**
- [ ] All 4 sound files exist in public/sounds/
- [ ] Files accessible at runtime via /sounds/ path
- [ ] No 404 or 416 errors when loading sounds
- [ ] File sizes reasonable (under 100KB each)

**Testing Instructions:**
- Start dev server and navigate to /sounds/click.wav directly
- Verify file downloads/plays correctly
- Check Network tab for any errors loading sound files

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

feat(assets): add sound effect files

Copy sound assets from reference project
Add click, swoosh, switch, expand sounds
Place in public/sounds for static serving
```

---

### Task 6: Define Core TypeScript Types

**Goal:** Create type definitions for API responses, state, and shared interfaces.

**Files to Modify/Create:**
- `frontend/src/types/` - **Create this directory first**
- `frontend/src/types/api.ts` - API response types
- `frontend/src/types/store.ts` - State/store types
- `frontend/src/types/components.ts` - Shared component prop types
- `frontend/src/types/index.ts` - Re-export all types

**Prerequisites:**
- Task 1 complete (TypeScript configured)

**Implementation Steps:**
- Analyze existing API client to define response types
- Define Job, Image, Gallery types based on API shape
- Create store state types for Zustand migration
- Define common component prop types (BaseProps, WithChildren, etc.)
- Use strict types (avoid `any`, prefer `unknown` when needed)
- Export all types from index.ts for clean imports

**Verification Checklist:**
- [ ] All API response shapes have corresponding types
- [ ] Types compile without errors
- [ ] Types are importable via `@/types`
- [ ] No `any` types in definitions (except intentional)

**Testing Instructions:**
- Import types in a component file
- Verify IDE autocomplete works with types
- Run `npx tsc --noEmit` to verify no type errors

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

feat(types): add core TypeScript type definitions

Define API response types (Job, Image, Gallery)
Add store state types for Zustand
Create shared component prop types
```

---

### Task 7: Install and Configure Zustand

**Goal:** Set up Zustand state management as replacement for React Context.

**Files to Modify/Create:**
- `frontend/package.json` - Add zustand dependency
- `frontend/src/stores/` - **Create this directory first**
- `frontend/src/stores/useAppStore.ts` - Main application store
- `frontend/src/stores/useUIStore.ts` - UI state store
- `frontend/src/stores/index.ts` - Re-export stores

**Prerequisites:**
- Task 6 complete (types defined)

**Implementation Steps:**
- Install zustand as production dependency
- Create useAppStore with typed state (prompt, images, jobId, etc.)
- Create useUIStore for UI-specific state (modals, toasts, sound muted)
- Define actions within stores for state mutations
- Use immer middleware if needed for complex state updates
- Keep Context providers for now (remove in Phase 3)

**Verification Checklist:**
- [ ] Zustand stores export correctly
- [ ] State can be read and updated
- [ ] TypeScript types work with store selectors
- [ ] No runtime errors when importing stores

**Testing Instructions:**
- Create a simple test component that uses the store
- Verify state reads and updates work
- Check that TypeScript autocomplete works with store state

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

feat(stores): add Zustand state management

Create useAppStore for application state
Create useUIStore for UI state
Type stores with TypeScript interfaces
```

---

### Task 8: Update Test Configuration for TypeScript

**Goal:** Configure Vitest to work with TypeScript test files.

**Files to Modify/Create:**
- `frontend/vite.config.ts` - Update test configuration
- `frontend/tests/setupTests.ts` - Rename and type setup file
- `frontend/tsconfig.json` - Include test files

**Prerequisites:**
- Task 1 complete (TypeScript configured)

**Implementation Steps:**
- Rename setupTests.js to setupTests.ts
- Add type annotations to setup file
- Configure Vitest to handle .tsx test files
- Update test include patterns for TypeScript
- Ensure @testing-library types are available
- Mock Audio API in setup file for sound tests

**Verification Checklist:**
- [ ] `npm test` runs without configuration errors
- [ ] TypeScript test files (.test.tsx) are recognized
- [ ] Existing tests still pass (or fail for expected reasons)
- [ ] Test coverage reports still generate

**Testing Instructions:**
- Run `npm test` and verify tests execute
- Check that TypeScript errors in tests are reported
- Verify coverage report generates correctly

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(test): update test configuration for TypeScript

Rename setup file to TypeScript
Configure Vitest for TSX test files
Add Audio API mock for sound tests
```

---

### Task 9: Create Migration Helper Script

**Goal:** Create a utility script to assist with JSX to TSX file conversion.

**Files to Modify/Create:**
- `frontend/scripts/migrate-to-tsx.ts` - Migration helper script
- `frontend/package.json` - Add migrate script

**Prerequisites:**
- Task 1 complete (TypeScript configured)

**Implementation Steps:**
- Create script that renames .jsx to .tsx files
- Script should update import statements if needed
- Include dry-run mode to preview changes
- Generate report of files needing manual type additions
- Script is a helper, not fully automated conversion

**Verification Checklist:**
- [ ] Script can list all .jsx files to migrate
- [ ] Dry-run mode shows expected changes
- [ ] Script handles nested directories
- [ ] No files corrupted during rename

**Testing Instructions:**
- Run script in dry-run mode
- Verify output matches expected files
- Test on a single file to verify rename works

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

chore(scripts): add JSX to TSX migration helper

Create script to rename jsx files to tsx
Add dry-run mode for preview
Generate migration report
```

---

### Task 10: Migrate Seed Prompts Data

**Goal:** Convert the seed prompts data file to TypeScript.

**Files to Modify/Create:**
- `frontend/src/data/seedPrompts.ts` - Rename and add types
- Delete: `frontend/src/data/seedPrompts.js`

**Prerequisites:**
- Task 1 complete (TypeScript configured)

**Implementation Steps:**
- Rename seedPrompts.js to seedPrompts.ts
- Define type for seed prompt structure
- Add type annotations to exported array
- Ensure consumers can import with type safety

**Verification Checklist:**
- [ ] File renamed to .ts
- [ ] Type defined for prompt structure
- [ ] Export is properly typed
- [ ] No TypeScript errors

**Testing Instructions:**
- Import seedPrompts in a test file
- Verify type inference works correctly

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(data): migrate seedPrompts to TypeScript

Add type definitions for seed prompts
Convert to TypeScript module
```

---

### Task 11: Migrate Test Fixtures

**Goal:** Convert test fixture files to TypeScript for type safety in tests.

**Files to Modify/Create:**
- `frontend/tests/__tests__/fixtures/apiResponses.ts` - Rename and type
- Delete: `frontend/tests/__tests__/fixtures/apiResponses.js`

**Prerequisites:**
- Task 6 complete (API types defined)

**Implementation Steps:**
- Rename apiResponses.js to apiResponses.ts
- Import API types from src/types
- Type all fixture data to match API response types
- Ensure fixtures are valid according to types

**Verification Checklist:**
- [ ] File renamed to .ts
- [ ] Fixtures typed with API types
- [ ] Tests still pass using fixtures
- [ ] No TypeScript errors

**Testing Instructions:**
- Run tests that use fixtures
- Verify type checking catches invalid fixture data

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(test): migrate test fixtures to TypeScript

Type API response fixtures
Ensure type safety in tests
```

---

## Phase Verification

After completing all tasks in this phase:

1. **TypeScript Check:**
   ```bash
   npx tsc --noEmit
   # Should complete without errors (components not yet migrated will be skipped)
   ```

2. **Build Check:**
   ```bash
   npm run build
   # Should complete successfully
   ```

3. **Dev Server Check:**
   ```bash
   npm run dev
   # Should start without errors, existing UI should work
   ```

4. **Tailwind Check:**
   - Temporarily add a `<div className="bg-primary text-accent">Test</div>` to App
   - Verify custom colors apply correctly
   - Remove test div

5. **Sound Check:**
   - Navigate to `http://localhost:3000/sounds/click.wav`
   - Should play or download the sound file

6. **Test Check:**
   ```bash
   npm test
   # Existing tests should pass (or have known failures)
   ```

### Known Limitations

- Existing JSX components are not yet typed (Phase 2-3)
- CSS Modules still in use (migrated in component phases)
- Context still used (migrated in Phase 3)
- Some tests may fail due to type mismatches (expected)

### Technical Debt

- Migration script is helper only, manual work still required
- Parallel CSS Modules and Tailwind may cause specificity issues
- Some `@ts-ignore` or `any` types may be temporarily needed
