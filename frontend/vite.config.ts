import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: {
        sidepanel: path.resolve(import.meta.dirname, 'sidepanel.html')
      },
      output: {
        entryFileNames: '[name].js'
      }
    }
  }
});