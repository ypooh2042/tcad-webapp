/** E2E 뒷정리. 임시 DB 와 잡 디렉토리를 지운다. */
import { rmSync } from 'node:fs'
import { ENV_FILE, sql, state } from './global-setup'

export default async function globalTeardown() {
  for (const child of [state.api, state.worker]) {
    child?.kill('SIGTERM')
  }

  if (state.databaseName) {
    // 연결이 남아 있어도 지워야 한다. 안 그러면 임시 DB 가 계속 쌓인다.
    sql(`drop database if exists "${state.databaseName}" with (force)`)
  }
  if (state.jobsRoot) {
    rmSync(state.jobsRoot, { recursive: true, force: true })
  }
  rmSync(ENV_FILE, { force: true })
}
