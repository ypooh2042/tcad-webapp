// vitest 설정을 같이 두려면 vite 가 아니라 vitest 쪽 defineConfig 를 써야 한다.
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // 개발 중에는 백엔드를 따로 띄운다. 프록시를 두면 프론트가 같은 출처로
    // 요청하게 되어 세션 쿠키가 그대로 실린다. CORS 설정을 열 필요가 없다.
    proxy: {
      '/api': {
        target: process.env.TCAD_API_URL ?? 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    // e2e 는 Playwright 가 돌린다. vitest 가 주워 가면 브라우저 API 를 못 찾아
    // 실패한다.
    exclude: ['node_modules/**', 'e2e/**', 'dist/**'],
    setupFiles: ['./src/test/setup.ts'],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/main.tsx',
        'src/test/**',
        'src/**/*.test.{ts,tsx}',
        'src/vite-env.d.ts',
      ],
    },
  },
})
