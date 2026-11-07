import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// In development (`npm run dev`) the React app runs on http://localhost:5173.
// Any request starting with /api is forwarded to your FastAPI server on port 8000,
// so the frontend can call fetch('/api/...') with no CORS setup.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
});
