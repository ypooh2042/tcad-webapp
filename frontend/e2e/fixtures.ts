/**
 * E2E 공용 도우미.
 *
 * 가입에는 초대 코드가 필요하다. 관리자를 거쳐 발급받는 것이 실제 경로지만
 * 매 테스트마다 하기엔 무겁다. 백엔드 서비스를 직접 불러 코드를 만든다 —
 * **가입 자체는 반드시 브라우저로** 한다. 그 경로가 검증 대상이다.
 */
import { spawnSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { expect, type Page } from '@playwright/test'

const BACKEND_ROOT = new URL('../../backend/', import.meta.url).pathname
const PYTHON = `${BACKEND_ROOT}.venv/bin/python`

/**
 * setup 이 만든 백엔드 환경변수.
 *
 * 이걸 넘기지 않으면 여기서 띄운 Python 이 **개발 DB** 에 붙는다. 초대 코드가
 * 엉뚱한 DB 에 생기고, 브라우저는 "초대 코드가 올바르지 않습니다"만 본다.
 */
function backendEnv(): NodeJS.ProcessEnv {
  const file = join(tmpdir(), 'tcad-e2e-env.json')
  return { ...process.env, ...JSON.parse(readFileSync(file, 'utf8')) }
}

export const PASSWORD = 'correct-horse-battery-staple'

/** 겹치지 않는 이메일. 테스트끼리 계정을 공유하면 세션 정원에 걸린다. */
export function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e4)}@example.com`
}

export function issueInviteCode(maxUses = 5): string {
  const script = [
    'import asyncio',
    'from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine',
    'from app.auth.invites import issue_invite',
    'from app.core.config import get_settings',
    'async def main():',
    '    engine = create_async_engine(get_settings().database_url)',
    '    maker = async_sessionmaker(engine, expire_on_commit=False)',
    '    async with maker() as session:',
            `        _, code = await issue_invite(session, created_by=None, max_uses=${maxUses})`,
    '    await engine.dispose()',
    '    print(code)',
    'asyncio.run(main())',
  ].join('\n')

  const result = spawnSync(PYTHON, ['-c', script], {
    cwd: BACKEND_ROOT,
    env: backendEnv(),
    encoding: 'utf8',
  })
  if (result.status !== 0) {
    throw new Error(`초대 코드 발급 실패\n${result.stdout}\n${result.stderr}`)
  }
  return result.stdout.trim()
}

/** 브라우저로 가입한다. 실제 사용자가 지나는 경로 그대로. */
export async function signUp(page: Page, email: string): Promise<void> {
  await page.goto('/')
  await page.getByRole('button', { name: /계정이 없으신가요/ }).click()

  await page.getByLabel('이메일').fill(email)
  await page.getByLabel('비밀번호').fill(PASSWORD)
  await page.getByLabel('초대 코드').fill(issueInviteCode())
  await page.getByRole('button', { name: '가입하고 시작' }).click()

  await expect(page.getByRole('button', { name: '실행' })).toBeVisible()
}

/**
 * 세션을 반납한다.
 *
 * 브라우저를 닫아도 서버 세션은 남는다(유휴 30분). 테스트마다 새 계정을 만들면
 * 세션이 쌓여 동시 접속 정원(10명)에 부딪힌다.
 */
export async function logOut(page: Page): Promise<void> {
  const button = page.getByRole('button', { name: '로그아웃' })
  if (await button.isVisible().catch(() => false)) {
    await button.click().catch(() => undefined)
  }
}

/** 프로젝트를 만든다. 이름은 window.prompt 로 받는다. */
export async function createProject(page: Page, name: string): Promise<void> {
  page.once('dialog', (dialog) => dialog.accept(name))
  await page.getByRole('button', { name: '+ 새 프로젝트' }).click()
  await expect(page.getByRole('button', { name, exact: true })).toBeVisible()
}

/** Monaco 에 소스를 넣는다. textarea 에 직접 쓰면 편집기 상태가 어긋난다. */
export async function setSource(page: Page, source: string): Promise<void> {
  const editor = page.locator('.monaco-editor').first()
  await expect(editor).toBeVisible()
  await editor.click()

  await page.keyboard.press('ControlOrMeta+A')
  await page.keyboard.press('Delete')
  // 자동 들여쓰기·자동 완성이 끼어들지 않도록 붙여넣기처럼 한 번에 넣는다.
  await page.evaluate((text) => navigator.clipboard.writeText(text), source)
  await page.keyboard.press('ControlOrMeta+V')
}

/** 메시가 제대로 잡히는 최소 1D 공정. `mode one.dim` 이 빠지면 2D 로 해석된다. */
export const ONE_DIMENSIONAL_SOURCE = `mode one.dim
line x loc = 0    spacing = 0.05 tag = top
line x loc = 1.0  spacing = 0.10 tag = bottom
region silicon xlo = top xhi = bottom
bound exposed xlo = top xhi = top
init boron conc = 1e15
structure outfile = result.str
`
