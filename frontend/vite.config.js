import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// En développement, le front (http://localhost:5173) proxifie /api vers
// FastAPI (http://localhost:8000). En production, FastAPI sert le dossier
// dist/ directement : le code front utilise donc toujours des URL relatives.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
