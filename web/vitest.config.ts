import { defineConfig } from 'vitest/config';

/**
 * Vitest runs alongside the app's Vite pipeline. Kept in its own file so
 * `vite build` is untouched by test-only configuration.
 *
 * Tests live under `src/` so the project's `tsc` step type-checks them too —
 * a test that does not compile fails `npm run build`.
 */
export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: false,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
});
