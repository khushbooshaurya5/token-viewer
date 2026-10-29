import { defineConfig } from 'vite'

// The development server serves the page on http://localhost:5173 and passes
// every request under /api on to the FastAPI back end. Page and API then share
// one origin, so the page can use relative URLs and needs no CORS.
export default defineConfig({
  server: {
    port: 5173,
    // Stop instead of moving to another port: the browser debug
    // configuration opens exactly this one.
    strictPort: true,
    proxy: {
      // uvicorn listens on IPv4 only; localhost could resolve to IPv6 (::1).
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
