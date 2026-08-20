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
 * 세션이 쌓여 동시 접속 정원에 부딪힌다.
 */
export async function logOut(page: Page): Promise<void> {
  const button = page.getByRole('button', { name: '로그아웃' })
  if (await button.isVisible().catch(() => false)) {
    await button.click().catch(() => undefined)
  }
}

/** 프로젝트를 만든다. 이름은 window.prompt 로 받는다. */
/**
 * 새 `.in` 파일을 만들어 탭으로 연다.
 *
 * 프로젝트 개념은 없어졌다. 작업 단위는 작업공간의 파일 하나다.
 */
export async function createProject(page: Page, name: string): Promise<void> {
  const filename = name.endsWith('.in') ? name : `${name}.in`

  await page.getByRole('button', { name: '파일 열기' }).click()
  const browser = page.getByRole('dialog', { name: '내 파일' })
  await expect(browser).toBeVisible()

  page.once('dialog', (dialog) => dialog.accept(filename))
  await browser.getByRole('button', { name: '새 파일' }).click()

  // 만든 파일을 눌러 탭에 붙인다.
  await browser.getByRole('button', { name: filename, exact: true }).click()
  await expect(page.getByRole('tab', { name: filename })).toBeVisible()
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


/**
 * 검증된 2D 예제(SUPREM4GS/examples/mosfet/CMOS.in 그대로).
 *
 * 2D 는 손으로 쓰기 어렵다 — 경계 조건을 조금만 잘못 써도 시뮬레이터가
 * SIGSEGV 로 죽는다(실측). 레포에 든 예제를 그대로 쓴다. 3초쯤 걸린다.
 */
export const TWO_DIMENSIONAL_SOURCE = String.raw`#some set stuff

set echo


##1. substrate

#the x dimension definition

line x loc=0 spacing=0.2 tag=left

line x loc=2 spacing=0.06

line x loc=4 spacing=0.2 tag=right

#the y dimension definition

line y loc=0 spacing=0.01 tag=top

line y loc=0.1 spacing=0.01

line y loc=0.8 spacing=0.1

line y loc=1.5 spacing=0.2

line y loc=3 spacing=1 tag=bottom

#the silicon wafer

region silicon xlo=left xhi=right ylo=top yhi=bottom

#set up the exposed surfaces

bound exposed  xlo=left xhi=right ylo=top  yhi=top

bound backside xlo=left xhi=right ylo=bottom yhi=bottom

#Initialize the Si substrate

initialize boron conc=1.0e15 ori=100

structure out=substrate.str


##2. oxidation

diffuse time=30 temp=1050 dry

structure out=oxidation.str


##3. nitride deposition

deposit nitride thick=0.2

structure out=nitride.str


##4. nitride etch

etch nitride left p1.x=0.5

etch nitride right p1.x=3.5

structure out=nitride_etch.str


##5. field oxide

diffuse time=400 temp=1000 dry pressure=5

structure out=field_oxide.str


##6. nitride remove

etch nitride all

structure out=nitride_remove.str


##7. Vth adjust implant

implant boron energy=30 dose=6e12

#insitu oxidation and activation

diffuse time=500 temp=1100 dry pressure=0.02

structure out=vth_implant.str


##8. oxide etch

etch dry oxide thick=0.05

structure out=oxide_etch.str


##9. gate oxide

diffuse time=30 temp=1000 dry

structure out=gate_oxide.str


##10. poly gate deposition

deposit poly thick=0.4

#poly phosphor implant

implant phosphorus energy=120 dose=5e15

structure out=poly_gate.str


##11. poly gate etch

etch poly left p1.x=1.75

etch poly right p1.x=2.25

structure out=poly_etch.str


##12. LDD implant

implant phosphorus energy=50 dose=4e13

structure out=ldd.str


##13. sidewall

deposit oxide thick=0.2

etch dry oxide thick=0.195

structure out=sidewall.str


##14. source and drain implant

implant arsenic energy=80 dose=6e15

#activation and drive-in

diffuse time=15 temp=950

structure out=source.str


##15. ILD deposition

deposit oxide thick=0.6

structure out=ild.str


`
