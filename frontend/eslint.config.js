import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';
import { defineConfig, globalIgnores } from 'eslint/config';

// Vitest runs with `globals: true` (vite.config.ts), so the test tree uses
// describe/it/expect/vi without importing them.
const vitestGlobals = {
  afterAll: 'readonly',
  afterEach: 'readonly',
  beforeAll: 'readonly',
  beforeEach: 'readonly',
  describe: 'readonly',
  expect: 'readonly',
  it: 'readonly',
  suite: 'readonly',
  test: 'readonly',
  vi: 'readonly',
};

export default defineConfig([
  globalIgnores(['dist', 'coverage', 'node_modules']),
  {
    // The application is entirely .ts/.tsx. This glob used to read
    // '**/*.{js,jsx}', which matched no source file at all: `eslint .`
    // inspected one file and reported success, so the react-hooks rules below
    // were configured and applied to nothing. It now inspects 149 files.
    //
    // `tests` is in scope deliberately rather than by accident. A lint config
    // that silently skips the test tree is the same defect one directory over.
    files: ['**/*.{js,jsx,ts,tsx}'],
    extends: [
      js.configs.recommended,
      // Non-type-checked `recommended`, not `recommendedTypeChecked`: the
      // latter needs a projectService and is materially slower, and this gate
      // runs in lint-staged on every commit.
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: { ...globals.browser, ...vitestGlobals },
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    rules: {
      // tsc already enforces this via noUnusedLocals/noUnusedParameters
      // (tsconfig.json). Two tools enforcing the same thing with different
      // defaults is how the base rule acquired a varsIgnorePattern of
      // '^[A-Z_]' that nobody can explain. Keep one enforcer, and it is the
      // one that understands types.
      'no-unused-vars': 'off',
      '@typescript-eslint/no-unused-vars': 'off',

      // Downgraded, not deleted. Counts measured 2026-07-27 when this config
      // first saw the TypeScript tree; both are React Compiler-era advisories
      // rather than defects, and both want an effect restructured.
      //
      // set-state-in-effect: 12 findings across 8 files (CompareModal,
      // GenerationPanel, ImageCard, ImageModal x2, PromptHistory x3,
      // useGallery, useSessionPolling, Admin, AuthCallback). Every one is a
      // guard clause setting error/loading state on an early return. Fixing
      // them means reshaping the effects, which is a behaviour change and not
      // what a lint-config commit should carry.
      //
      // immutability: 1 finding, useSessionPolling.ts:84, where `poll`
      // schedules itself via setTimeout. The rule's stated concern -- an
      // earlier access not updating as the value changes -- does not bite
      // here: `poll` is re-created each render and each closure reads its own
      // render's binding, and staleness is already handled by the
      // activeSessionIdRef guard on the line above.
      //
      // Raise these to 'error' when the counts reach zero; do not raise the
      // counts to keep them here.
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/immutability': 'warn',
    },
  },
  {
    // ban-ts-comment stays an error in src/ (zero findings there, so it is a
    // ratchet) and is a warning in the test tree, where six files open with
    // `// @ts-nocheck`: GalleryBrowser, GalleryPreview, ImageCard, ImageGrid,
    // and PromptEnhancer component tests plus the galleryFlow integration
    // test. Measured 2026-07-27: deleting those six comments surfaces 43 tsc
    // errors. That is a typing project, not a lint-config change.
    files: ['tests/**/*.{ts,tsx}'],
    rules: {
      '@typescript-eslint/ban-ts-comment': 'warn',
    },
  },
]);
