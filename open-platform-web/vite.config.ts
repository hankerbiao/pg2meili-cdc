import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ command }) => ({
  base: command === 'serve' ? '/' : '/open-platform/',
  plugins: [react()],
  server: {
    host: true,
    port: 3100,
    proxy: {
      '/api': 'http://127.0.0.1:8080',
      '/openapi.json': 'http://127.0.0.1:8080',
      '/docs': 'http://127.0.0.1:8080',
    },
  },
}))
