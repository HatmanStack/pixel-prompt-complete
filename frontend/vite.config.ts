/// <reference types="vitest/config" />
// The reference is what makes the `test` block below type-check: it
// augments vite's UserConfig with vitest's options. Without it tsc
// reports "'test' does not exist in type 'UserConfigExport'" -- which
// nothing saw, because tsconfig.json included only src and tests.
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { visualizer } from 'rollup-plugin-visualizer';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    // Opt-in only: `npm run analyze` sets ANALYZE=true. Unconditionally it
    // wrote a 432 KB dist/stats.html -- a module graph carrying absolute
    // source paths -- into the directory that gets deployed. The report
    // belongs to whoever asked for it, not to the CDN.
    ...(process.env.ANALYZE === 'true'
      ? [
          visualizer({
            filename: './dist/stats.html',
            open: false,
            gzipSize: true,
            brotliSize: true,
          }),
        ]
      : []),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 3000,
    host: true,
    strictPort: true,
  },
  build: {
    // false, not 'hidden'. Hidden maps are still written to dist/, and there
    // is no frontend deploy target yet (H40) -- whatever ships will be an
    // `aws s3 sync dist/`, which would upload them, and a .map next to a
    // content-hashed .js is guessable without the sourceMappingURL comment.
    // Nothing consumes them either: the only error reporting is
    // ErrorBoundary -> POST /log, and it sends React's componentStack
    // (a component-name tree) rather than minified stack frames, so a map
    // would not decode anything it sends. Set this to 'hidden' the day an
    // error tracker with a map-upload step exists.
    sourcemap: false,
    outDir: 'dist',
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          // React core + state management libraries
          if (id.includes('node_modules')) {
            if (id.includes('react') || id.includes('react-dom') || id.includes('zustand')) {
              return 'vendor';
            }
            if (id.includes('uuid')) {
              return 'api';
            }
          }

          // Split gallery components into separate chunk (lazy loaded)
          if (id.includes('/components/gallery/')) {
            return 'gallery';
          }
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './tests/setupTests.ts',
    include: ['tests/**/*.test.{js,jsx,ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      include: ['src/**/*.{js,jsx,ts,tsx}'],
      exclude: ['src/main.jsx', 'src/main.tsx'],
      // Ratcheted to just under the current numbers so the coverage added
      // for the generation surface and pages cannot silently regress. Raise
      // these when coverage rises; never lower them to make a build pass.
      //
      // Re-measured 2026-07-27 (Phase 6): statements 72.36, branches 65.26,
      // functions 75.40, lines 73.08. Each floor below is the measured value
      // rounded DOWN to the whole percent -- rounding up is a build that is
      // red on arrival.
      //
      // No perFile floor, and that is a decision rather than an omission.
      // Nine files are at 0%: api/billing.ts, api/me.ts, data/seedPrompts.ts,
      // utils/imageHelpers.ts, and the generation controls IterationInput,
      // RegenerateInput, OutpaintControls and RandomPromptButton -- plus
      // admin/AdminNotifications at 4%. Any per-file threshold above zero
      // fails immediately, so the aggregate is the only honest gate today and
      // those nine files are where to aim. The two the audit named have both
      // moved: hooks/useIteration.ts 30.76 -> 44.44 and hooks/useGallery.ts
      // 0 -> 57.44.
      thresholds: {
        statements: 72,
        lines: 73,
        branches: 65,
        functions: 75,
      },
    },
  },
});
