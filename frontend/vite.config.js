import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/webhook':  'http://localhost:8000',
      '/upload':   'http://localhost:8000',
      '/health':   'http://localhost:8000',
      '/claims':   'http://localhost:8000',   // dashboard pending claims + images
      '/decision': 'http://localhost:8000',   // agent approve / reject
      '/uploads':  'http://localhost:8000',   // serve stored claim photos
      '/qr':       'http://localhost:8000',   // T-018 — QR code generation
      '/events': {                            // SSE real-time notifications (A5)
        target: 'http://localhost:8000',
        changeOrigin: true,
        // SSE requires these headers to be stripped so the browser receives
        // the raw chunked stream rather than a buffered response.
        headers: {
          'Accept': 'text/event-stream',
        },
      },
    },
  },
})