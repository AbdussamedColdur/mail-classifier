import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The OAuth callback comes back through this proxy, so the dev server must keep the
// browser's Host header (no changeOrigin) and listen on 127.0.0.1 like the backend.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
