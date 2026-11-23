import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// base './': the built page is opened from the app folder by pywebview, so every asset path must be relative.
export default defineConfig({
  base: './',
  plugins: [react()],
  build: { outDir: 'dist', emptyOutDir: true, target: 'chrome110', chunkSizeWarningLimit: 1200 },
});
