import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  base: '/',
  build: {
    outDir: fileURLToPath(new URL('../tg_signer/webui/static', import.meta.url)),
    emptyOutDir: true,
  },
})

