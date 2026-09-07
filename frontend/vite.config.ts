import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The frontend is its own Vite project inside frontend/, but it shares the
// repo-root public/ directory with the Python pipeline, which writes
// public/data/dashboard_data.json there directly.
//
// publicDir points at that shared folder so Vite serves it verbatim at
// http://localhost:5173/... in dev AND copies it into the build output —
// the same fetch path in useDashboardData() works in both modes.
//
// emptyOutDir is explicitly false: outDir lives outside this project's
// root (a directory Vite would otherwise refuse to auto-empty and warn
// about), and the default "empty on build" behavior would delete
// dashboard_data.json the moment someone runs `npm run build`.
const REPO_PUBLIC_DIR = path.resolve(__dirname, '../public')

export default defineConfig({
  plugins: [react(), tailwindcss()],
  publicDir: REPO_PUBLIC_DIR,
  build: {
    outDir: REPO_PUBLIC_DIR,
    emptyOutDir: false,
  },
})