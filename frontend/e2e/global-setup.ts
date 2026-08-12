/**
 * E2E 백엔드 기동.
 *
 * 임시 PostgreSQL 데이터베이스를 만들어 마이그레이션을 걸고, 그 위에서 API 를
 * 띄운다. 개발용 DB 를 그대로 쓰면 E2E 가 남긴 계정·잡이 쌓이고, 반대로 개발
 * 중이던 데이터가 테스트 결과를 흔든다.
 *
 * 워커도 함께 띄운다. 잡이 실제로 도는 것까지 봐야 E2E 다.
 */
import { spawn, spawnSync, type ChildProcess } from 'node:child_process'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'

const BACKEND_ROOT = new URL('../../backend/', import.meta.url).pathname

/** setup 이 만든 백엔드 환경변수를 워커 프로세스에 넘기는 통로. */
export const ENV_FILE = join(tmpdir(), 'tcad-e2e-env.json')
const PYTHON = join(BACKEND_ROOT, '.venv/bin/python')
const API_PORT = 8123
const ADMIN_URL =
  process.env.TCAD_TEST_DATABASE_URL ??
  'postgresql+asyncpg://tcad:tcad-dev-only@localhost:5433/tcad'

export interface E2EState {
  databaseName: string
  jobsRoot: string
  workspacesRoot: string
  api?: ChildProcess
  worker?: ChildProcess
}

// Playwright 는 setup 과 teardown 사이에 값을 넘겨주지 않는다. 모듈 전역에
// 둔다(같은 프로세스에서 둘 다 돈다).
export const state: E2EState = {
  databaseName: '',
  jobsRoot: '',
  workspacesRoot: '',
}

function run(command: string, args: string[], env: NodeJS.ProcessEnv = {}) {
  const result = spawnSync(command, args, {
    cwd: BACKEND_ROOT,
    env: { ...process.env, ...env },
    encoding: 'utf8',
  })
  if (result.status !== 0) {
    throw new Error(
      `${command} ${args.join(' ')} 실패\n${result.stdout}\n${result.stderr}`,
    )
  }
  return result.stdout
}

function databaseUrl(name: string): string {
  return `${ADMIN_URL.slice(0, ADMIN_URL.lastIndexOf('/'))}/${name}`
}

/** psql 대신 앱의 드라이버를 쓴다. 호스트에 psql 이 없어도 돌아간다. */
function sql(statement: string) {
  run(PYTHON, [
    '-c',
    [
      'import asyncio',
      'from sqlalchemy import text',
      'from sqlalchemy.ext.asyncio import create_async_engine',
      'async def main():',
      `    engine = create_async_engine(${JSON.stringify(ADMIN_URL)}, isolation_level="AUTOCOMMIT")`,
      '    async with engine.connect() as connection:',
      `        await connection.execute(text(${JSON.stringify(statement)}))`,
      '    await engine.dispose()',
      'asyncio.run(main())',
    ].join('\n'),
  ])
}

async function waitForHealth(url: string, attempts = 60): Promise<void> {
  for (let i = 0; i < attempts; i += 1) {
    try {
      const response = await fetch(url)
      if (response.ok) return
    } catch {
      // 아직 안 떴다
    }
    await sleep(500)
  }
  throw new Error(`백엔드가 뜨지 않았습니다: ${url}`)
}

export default async function globalSetup() {
  const suffix = Date.now().toString(36)
  state.databaseName = `tcad_e2e_${suffix}`
  state.jobsRoot = mkdtempSync(join(tmpdir(), 'tcad-e2e-jobs-'))
  // 작업공간도 실행마다 새로 잡는다. 고정 경로를 쓰면 실행마다 DB 가 새로
  // 만들어져 user id 가 1 부터 다시 시작하는 탓에, 이전 실행이 남긴
  // user-N 폴더를 그대로 물려받는다(실제로 테스트가 남의 파일을 봤다).
  state.workspacesRoot = mkdtempSync(join(tmpdir(), 'tcad-e2e-workspaces-'))

  sql(`create database "${state.databaseName}"`)

  const url = databaseUrl(state.databaseName)
  const env = {
    TCAD_DATABASE_URL: url,
    // 개발용 세션과 섞이지 않도록 별도 Redis DB 를 쓴다.
    TCAD_REDIS_URL: 'redis://localhost:6380/14',
    TCAD_JOBS_ROOT: state.jobsRoot,
    TCAD_WORKSPACES_ROOT: state.workspacesRoot,
    // 브라우저가 http:// 로 접속하므로 Secure 쿠키는 되돌아오지 않는다.
    TCAD_SESSION_COOKIE_SECURE: 'false',
    // E2E 잡은 작고 빨라야 한다.
    TCAD_JOB_TIMEOUT_SECONDS: '120',
  }

  run(PYTHON, ['-m', 'alembic', 'upgrade', 'head'], env)

  state.api = spawn(
    PYTHON,
    ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(API_PORT)],
    { cwd: BACKEND_ROOT, env: { ...process.env, ...env }, stdio: 'pipe' },
  )
  state.worker = spawn(PYTHON, ['-m', 'app.jobs.main'], {
    cwd: BACKEND_ROOT,
    env: { ...process.env, ...env },
    stdio: 'pipe',
  })

  // 테스트는 별도 워커 프로세스에서 돈다. globalSetup 의 env 를 그대로
  // 물려받는다고 가정할 수 없으므로 파일로 넘긴다.
  writeFileSync(ENV_FILE, JSON.stringify(env), 'utf8')

  await waitForHealth(`http://127.0.0.1:${API_PORT}/api/health`)
}

export { API_PORT, BACKEND_ROOT, PYTHON, databaseUrl, sql }
