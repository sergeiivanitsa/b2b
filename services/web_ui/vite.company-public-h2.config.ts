import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'

export default defineConfig({
  plugins: [react()],
  publicDir: false,
  build: {
    outDir: 'dist-company-public-h2', emptyOutDir: true, manifest: true,
    rollupOptions: { input: resolve(import.meta.dirname, 'src/companyPublicH2/main.tsx'), output: { entryFileNames: 'assets/company-public-h2.[hash].js', chunkFileNames: 'assets/company-public-h2.[hash].js', assetFileNames: 'assets/company-public-h2.[hash][extname]' } },
  },
})
