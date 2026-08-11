/**
 * 코드 작성 → 실행 → 결과 확인.
 *
 * 이 파일이 E2E 의 본론이다. 단위 테스트는 Monaco 를 통째로 목으로 바꾸고
 * 백엔드를 가려 놓기 때문에, 다음은 여기서만 확인된다:
 *
 *   - Monaco 가 브라우저에서 실제로 뜨는가 (jsdom 에서는 뜨지 않는다)
 *   - 자동완성이 카탈로그 API 를 타고 오는가
 *   - 제출한 잡이 워커를 거쳐 진짜 컨테이너에서 돌아 결과가 돌아오는가
 */
import { expect, test } from '@playwright/test'
import {
  ONE_DIMENSIONAL_SOURCE,
  createProject,
  logOut,
  setSource,
  signUp,
  uniqueEmail,
} from './fixtures'

test.afterEach(async ({ page }) => {
  await logOut(page)
})

test.beforeEach(async ({ page, context }) => {
  // setSource 가 클립보드를 쓴다. Monaco 에 한 글자씩 타이핑하면 자동 들여쓰기와
  // 자동완성이 끼어들어 소스가 뒤틀린다.
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await signUp(page, uniqueEmail('flow'))
})

test('편집기가 뜨고 문법 강조가 걸린다', async ({ page }) => {
  const editor = page.locator('.monaco-editor').first()

  await expect(editor).toBeVisible()
  // 커맨드가 키워드로 칠해져야 한다. 언어 등록이 안 되면 전부 기본색이다.
  await expect(editor.locator('.mtk1, .mtk4, .mtk5').first()).toBeVisible()
})

test('커맨드 자동완성이 카탈로그에서 온다', async ({ page }) => {
  await createProject(page, 'autocomplete')
  await setSource(page, '')

  const editor = page.locator('.monaco-editor').first()
  await editor.click()
  // 타이핑만으로 뜨게 둔다. Ctrl+Space 는 헤드리스 환경에서 편집기까지
  // 닿지 않는 경우가 있어 판정이 흔들린다.
  await page.keyboard.type('stru', { delay: 60 })

  // structure 는 suprem.key 에서 온 이름이다. 프론트에 박아 둔 목록이 아니라
  // 서버 카탈로그를 탔다는 뜻이 된다.
  await expect(page.locator('.suggest-widget')).toContainText('structure')
})

test('파라미터 자동완성은 커맨드에 따라 달라진다', async ({ page }) => {
  await createProject(page, 'params')
  await setSource(page, '')

  const editor = page.locator('.monaco-editor').first()
  await editor.click()
  await page.keyboard.type('initialize ')
  await page.keyboard.press('Control+Space')

  await expect(page.locator('.suggest-widget')).toContainText('conc')
})

test('소스를 저장하면 리비전 번호가 올라간다', async ({ page }) => {
  await createProject(page, 'save')

  await setSource(page, ONE_DIMENSIONAL_SOURCE)
  await page.getByRole('button', { name: /저장/ }).click()

  await expect(page.getByText(/리비전 1 저장됨/)).toBeVisible()
})

test('시뮬레이션이 실제로 돌고 결과가 그려진다', async ({ page }) => {
  test.slow() // 컨테이너를 띄우고 시뮬레이터를 돌린다

  await createProject(page, 'run')
  await setSource(page, ONE_DIMENSIONAL_SOURCE)

  await page.getByRole('button', { name: '실행' }).click()

  // 워커가 집어가 컨테이너에서 돌 때까지 기다린다.
  await expect(page.getByText('성공')).toBeVisible({ timeout: 120_000 })
  // 편집기 안에도 `structure outfile = result.str` 이 보이므로 결과 패널로
  // 범위를 좁힌다.
  await expect(page.locator('.panel').getByText('result.str')).toBeVisible()

  // 깊이 프로파일이 그려져야 한다. 서버가 .str 을 풀어 보낸 것이다.
  const chart = page.getByRole('img', { name: /깊이 프로파일/ })
  await expect(chart).toBeVisible()

  // 축에 숫자가 있어야 읽을 수 있다. 처음 배포했을 때 가로축에 제목만 있고
  // 눈금 값이 없어서 접합 깊이를 읽을 방법이 없었다.
  const ticks = await chart.locator('text.tick').allTextContents()
  expect(ticks.some((t) => /^\d/.test(t))).toBe(true)   // 깊이 (0.0, 0.5 …)
  expect(ticks.some((t) => /^1e/.test(t))).toBe(true)    // 농도 (1e15 …)
})

test('기본 예제가 손대지 않고 그대로 돌아간다', async ({ page }) => {
  test.slow()

  // **편집기를 건드리지 않는다.** 처음 들어온 사람이 가장 먼저 누르는 것이
  // 실행 버튼이다. 그때 실패하면 이 도구를 쓸 수 있다는 믿음이 먼저 깨진다.
  //
  // 다른 테스트는 fixtures 의 소스를 붙여 넣기 때문에 앱의 기본값이 깨져도
  // 통과한다. 실제로 그렇게 배포됐다 — `mode one.dim` 이 빠져 있어
  // "No mesh defined!" 가 났다.
  await createProject(page, 'starter')

  await page.getByRole('button', { name: '실행' }).click()

  await expect(page.getByText('성공')).toBeVisible({ timeout: 120_000 })
  await expect(page.getByRole('img', { name: /깊이 프로파일/ })).toBeVisible()
})

test('메시가 없는 소스는 실패로 보고된다', async ({ page }) => {
  test.slow()

  // `mode one.dim` 과 line/region 이 없으면 "No mesh defined!" 가 난다.
  // 예전에는 이런 실행이 "성공"으로 기록되어 사용자가 빈 그래프만 봤다.
  await createProject(page, 'nomesh')
  await setSource(page, 'init boron conc=1e15\nstructure outfile=out.str\n')

  await page.getByRole('button', { name: '실행' }).click()

  await expect(page.getByText('실패')).toBeVisible({ timeout: 120_000 })
})

test('물리량을 바꾸면 다른 프로파일이 나온다', async ({ page }) => {
  test.slow()

  await createProject(page, 'quantity')
  await setSource(page, ONE_DIMENSIONAL_SOURCE)
  await page.getByRole('button', { name: '실행' }).click()
  await expect(page.getByText('성공')).toBeVisible({ timeout: 120_000 })

  // net_doping 은 저장 컬럼이 아니라 계산값이다. 보론만 있으므로 전부 음수라,
  // 절댓값으로 그리지 않으면 그래프가 통째로 빈다.
  await page.getByLabel('물리량').selectOption('net_doping')

  await expect(page.getByText(/점선 = 음수/)).toBeVisible()
})

test('프로젝트는 사용자마다 따로다', async ({ page, browser }) => {
  await createProject(page, 'mine-only')

  const other = await browser.newContext()
  const otherPage = await other.newPage()
  await signUp(otherPage, uniqueEmail('stranger'))

  await expect(
    otherPage.getByRole('button', { name: 'mine-only', exact: true }),
  ).toBeHidden()

  await otherPage.getByRole('button', { name: '로그아웃' }).click()
  await other.close()
})
