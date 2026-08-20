/**
 * E2E 설정.
 *
 * 진짜 브라우저로 진짜 백엔드를 친다. 단위·컴포넌트 테스트가 목으로 가려 놓은
 * 것들 — Monaco 가 실제로 뜨는지, 세션 쿠키가 브라우저에 실리는지, 자동완성이
 * 카탈로그 API 를 타고 오는지 — 은 여기서만 확인된다.
 *
 * 백엔드는 `e2e/global-setup.ts` 가 띄운다. 그쪽에서 임시 DB 를 만들고
 * 마이그레이션을 걸기 때문에 개발용 데이터에 손대지 않는다.
 */
import { defineConfig, devices } from '@playwright/test'

const PORT = 5273

export default defineConfig({
  testDir: './e2e',
  // 브라우저를 띄우는 테스트라 단위 테스트보다 넉넉히 준다.
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  // 동시 접속 정원과 잡 큐를 공유하므로 병렬로 돌리면 서로를 방해한다.
  workers: 1,
  reporter: process.env.CI ? 'github' : 'list',
  globalSetup: './e2e/global-setup.ts',
  globalTeardown: './e2e/global-teardown.ts',

  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    // 실패했을 때 원인을 볼 수 있어야 한다. 통과한 실행에는 남기지 않는다.
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },

  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],

  webServer: {
    // 개발 서버를 쓴다. 빌드 산출물로 돌리면 프록시를 따로 세워야 하고,
    // 검증하려는 것은 번들 최적화가 아니라 동작이다.
    command: `npx vite --port ${PORT} --strictPort`,
    env: { TCAD_API_URL: 'http://127.0.0.1:8123' },
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
})
