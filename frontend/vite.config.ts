/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

// In development the Vite server proxies /api and /metrics to the FastAPI backend, so the
// frontend always calls same-origin paths. In Docker, nginx does the same job.
const backendUrl = process.env.VITE_DEV_BACKEND_URL ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': backendUrl,
      '/metrics': backendUrl,
    },
  },
  preview: {
    port: 4173,
    proxy: {
      '/api': backendUrl,
      '/metrics': backendUrl,
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    restoreMocks: true,
  },
});
