import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

export default defineConfig(({ mode }) => {
  const root = fileURLToPath(new URL('..', import.meta.url))
  const env = loadEnv(mode, root, 'VITE_')
  return {
    plugins: [react()],
    envDir: root,
    server: { proxy: { '/api': env.VITE_API_URL || 'http://127.0.0.1:8000', '/health': env.VITE_API_URL || 'http://127.0.0.1:8000' } },
  }
})
