import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  build: {
    outDir: '../frontend/static/dist',
    emptyDir: true,
    rollupOptions: {
      output: {
        entryFileNames: 'books.js',
        chunkFileNames: '[name].js',
        assetFileNames: 'books.[ext]',
      },
    },
  },
})