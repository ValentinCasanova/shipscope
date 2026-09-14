import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // The app calls the API on its own origin under /api/, as it will behind
      // CloudFront, so the browser never makes a cross-origin request. The dev
      // server forwards those requests to Django. API_PROXY_TARGET overrides the
      // address, for example when the dev server runs in a container.
      '/api/': {
        target: process.env.API_PROXY_TARGET || 'http://localhost:8000',
        // Pass the browser's Host header (localhost:5173) through unchanged.
        // Django builds absolute URLs from it and compares it with the Origin
        // header in CSRF checks, so it has to match the address in the browser.
        changeOrigin: false,
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    // Undo vi.stubGlobal calls, such as a stubbed fetch, after each test.
    unstubGlobals: true,
  },
});
