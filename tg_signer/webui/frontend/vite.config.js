import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  // Avoid esbuild's >1 MB temporary-file deletion race on Windows.
  esbuild: false,
  base: '/',
  build: {
    outDir: fileURLToPath(new URL('../static', import.meta.url)),
    emptyOutDir: true,
  },
})
