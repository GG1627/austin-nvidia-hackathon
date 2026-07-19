import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // scripts/serve_dashboard.py — the Python agent system's API shim
      "/api": "http://127.0.0.1:8787",
    },
  },
})
