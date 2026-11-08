import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// 개발 중에는 Vite가 /api와 /ws를 로컬 백엔드(uvicorn 또는 도커 :8000)로 넘긴다
const backend = 'http://localhost:8000'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': backend,
      '/ws': { target: backend.replace(/^http/, 'ws'), ws: true },
    },
  },
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.ts'],
  },
})
