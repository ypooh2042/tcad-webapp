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
  TWO_DIMENSIONAL_SOURCE,
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
  // 타이핑만으로 띄운다. Ctrl+Space 는 헤드리스에서 편집기까지 닿지 않는
  // 경우가 있어 판정이 흔들린다 — 3회 중 1회 깨졌다.
  await page.keyboard.type('initialize co', { delay: 60 })

  // conc 는 initialize 의 파라미터다. deposit 에는 없다.
  await expect(page.locator('.suggest-widget')).toContainText('conc')
})

test('소스를 저장하면 파일에 쓰인다', async ({ page }) => {
  await createProject(page, 'save')

  await setSource(page, ONE_DIMENSIONAL_SOURCE)
  await page.getByRole('button', { name: /저장/ }).click()

  await expect(page.getByText(/저장됨/)).toBeVisible()
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

test('물리량을 추가하면 함께 그려진다', async ({ page }) => {
  test.slow()

  await createProject(page, 'quantity')
  await setSource(page, ONE_DIMENSIONAL_SOURCE)
  await page.getByRole('button', { name: '실행' }).click()
  await expect(page.getByText('성공')).toBeVisible({ timeout: 120_000 })

  // net_doping 은 저장 컬럼이 아니라 계산값이다. 보론만 있으므로 전부 음수라,
  // 절댓값으로 그리지 않으면 그래프가 통째로 빈다.
  await page.getByLabel('net_doping').check()

  await expect(page.getByText(/점선 = 음수/)).toBeVisible()
})

test('작업공간은 사용자마다 따로다', async ({ page, browser }) => {
  // 남의 파일이 보이면 코드가 그대로 새는 것이다.
  await createProject(page, 'mine-only')

  const other = await browser.newContext()
  const otherPage = await other.newPage()
  await signUp(otherPage, uniqueEmail('stranger'))

  await otherPage.getByRole('button', { name: '파일 열기' }).click()
  const browserPanel = otherPage.getByRole('dialog', { name: '내 파일' })
  await expect(browserPanel).toBeVisible()

  await expect(
    browserPanel.getByRole('button', { name: 'mine-only.in', exact: true }),
  ).toHaveCount(0)
  await expect(browserPanel.getByText(/파일이 없습니다/)).toBeVisible()

  await otherPage.getByRole('button', { name: '로그아웃' }).click()
  await other.close()
})

test('커맨드 목록에서 골라 문서를 읽는다', async ({ page }) => {
  // 검색은 찾을 낱말을 알아야 쓴다. 처음 쓰는 사람은 그 낱말을 모르므로,
  // 무리별 목록을 훑어 고르는 길이 실제로 열려 있어야 한다.
  await page.getByRole('button', { name: '매뉴얼' }).click()
  await page.getByRole('tab', { name: '목록' }).click()

  // 분류는 매뉴얼 p.51 이 나눈 것이다. 서버 reference.json 을 탔다는 뜻이 된다.
  await expect(page.getByText('공정 시뮬레이션')).toBeVisible()

  await page.getByLabel('커맨드 거르기').fill('implant')
  await page.getByRole('button', { name: 'implant', exact: true }).click()

  // 목록 → 본문. 매뉴얼 PDF 에서 뽑은 산문이 떠야 한다.
  await expect(page.locator('.docs article')).toContainText('implantation')
})

test('매뉴얼에 없는 커맨드는 파라미터를 보여준다', async ({ page }) => {
  // suprem.key 에만 있는 커맨드다. 목록에서 빼면 존재조차 모르고, 매뉴얼 탭으로
  // 보내면 빈 화면만 뜬다.
  await page.getByRole('button', { name: '매뉴얼' }).click()
  await page.getByRole('tab', { name: '목록' }).click()

  await page.getByLabel('커맨드 거르기').fill('device')
  await page.getByRole('button', { name: 'device', exact: true }).click()

  await expect(page.getByRole('tab', { name: '파라미터' })).toHaveAttribute(
    'aria-selected',
    'true',
  )
  await expect(page.locator('.docs')).toContainText('매뉴얼에 설명이 없습니다')
})

test('파일 브라우저에서 이름을 바꾸고 지운다', async ({ page }) => {
  // 이름 바꾸기와 삭제는 파일 브라우저로 옮겼다. 위쪽 탭은 열어 둔 파일일 뿐이다.
  await createProject(page, 'rename-me')

  await page.getByRole('button', { name: '파일 열기' }).click()
  const files = page.getByRole('dialog', { name: '내 파일' })
  const row = files.locator('li', { hasText: 'rename-me.in' })

  page.once('dialog', (dialog) => dialog.accept('renamed.in'))
  await row.getByRole('button', { name: '이름 바꾸기' }).click()
  await expect(
    files.getByRole('button', { name: 'renamed.in', exact: true }),
  ).toBeVisible()

  page.once('dialog', (dialog) => dialog.accept())
  await files
    .locator('li', { hasText: 'renamed.in' })
    .getByRole('button', { name: '삭제' })
    .click()
  await expect(files.getByText(/파일이 없습니다/)).toBeVisible()
})

test('삭제를 취소하면 남아 있는다', async ({ page }) => {
  await createProject(page, 'keep-me')

  await page.getByRole('button', { name: '파일 열기' }).click()
  const files = page.getByRole('dialog', { name: '내 파일' })

  page.once('dialog', (dialog) => dialog.dismiss())
  await files
    .locator('li', { hasText: 'keep-me.in' })
    .getByRole('button', { name: '삭제' })
    .click()

  await expect(
    files.getByRole('button', { name: 'keep-me.in', exact: true }),
  ).toBeVisible()
})

test('탭을 닫아도 파일은 남는다', async ({ page }) => {
  await createProject(page, 'keep-tab')

  await page.getByRole('button', { name: 'keep-tab.in 탭 닫기' }).click()
  await expect(page.getByRole('tab')).toHaveCount(0)

  await page.getByRole('button', { name: '파일 열기' }).click()
  await expect(
    page.getByRole('dialog', { name: '내 파일' })
      .getByRole('button', { name: 'keep-tab.in', exact: true }),
  ).toBeVisible()
})

test('2D 단면에 x/깊이 눈금이 그려진다', async ({ page }) => {
  // 캔버스는 jsdom 에서 그려지지 않는다. 눈금이 실제로 화면에 찍히는지는
  // 진짜 브라우저에서만 확인할 수 있다.
  await createProject(page, 'two-dim')
  await setSource(page, TWO_DIMENSIONAL_SOURCE)
  await page.getByRole('button', { name: '실행' }).click()

  const canvas = page.locator('canvas.surface')
  await expect(canvas).toBeVisible({ timeout: 120_000 })

  // 눈금 라벨은 그림 영역 왼쪽 여백에 찍힌다. 그 띠에 배경이 아닌 픽셀이
  // 있어야 무언가 그려진 것이다.
  const drawn = await canvas.evaluate((node: HTMLCanvasElement) => {
    const ratio = window.devicePixelRatio || 1
    const context = node.getContext('2d')!
    // 왼쪽 여백(38px) 안쪽을 훑는다.
    const strip = context.getImageData(0, 0, Math.round(36 * ratio), node.height)
    let painted = 0
    for (let i = 3; i < strip.data.length; i += 4) {
      if (strip.data[i]! > 0) painted += 1
    }
    return painted
  })

  expect(drawn).toBeGreaterThan(0)
})

test('단면을 재질로 볼 수 있다', async ({ page }) => {
  await createProject(page, 'materials')
  await setSource(page, TWO_DIMENSIONAL_SOURCE)
  await page.getByRole('button', { name: '실행' }).click()

  const canvas = page.locator('canvas.surface')
  await expect(canvas).toBeVisible({ timeout: 120_000 })

  // 기본이 재질이다. 구조가 어떻게 생겼는지부터 보는 것이 자연스럽다.
  const picker = page.getByLabel('구조 단면')
  await expect(picker).toHaveValue('재질')

  // 층이 여럿인 단계로 옮긴다. 첫 단계(substrate)는 silicon 하나뿐이라
  // 재질 구분을 확인할 수 없다. 마지막까지 눌러 간다 — 다 가면 비활성이 된다.
  const next = page.getByRole('button', { name: /다음/ })
  while (await next.isEnabled()) await next.click()
  await expect(page.getByText(/15\/15/)).toBeVisible()

  // 물리량으로 갔다가 재질로 돌아오며 요청을 확인한다. 이미 재질인 상태에서
  // 다시 고르면 change 이벤트가 뜨지 않아 응답을 기다릴 수 없다.
  await picker.selectOption('chem_boron')
  const request = page.waitForResponse(
    (response) =>
      response.url().includes('/surface') && !response.url().includes('quantity='),
  )
  await picker.selectOption('재질')

  // 물리량 없이 불러야 서버가 요소를 버리지 않아 층이 다 나온다.
  const body = await (await request).json()
  expect(body.quantity).toBe('')
  expect(new Set(body.materials).size).toBeGreaterThan(1)
})

test('그래프 가로축을 확대·축소한다', async ({ page }) => {
  // jsdom 은 레이아웃이 없어 화면 좌표 → 깊이 변환이 검증되지 않는다.
  // 실제 크기를 가진 브라우저에서만 확인할 수 있다.
  await createProject(page, 'zoom')
  await setSource(page, ONE_DIMENSIONAL_SOURCE)
  await page.getByRole('button', { name: '실행' }).click()

  const chart = page.locator('.chart svg')
  await expect(chart).toBeVisible({ timeout: 120_000 })

  const depths = async () =>
    (await chart.locator('.tick').allTextContents())
      .filter((text) => !text.startsWith('1e'))
      .map(Number)

  const full = Math.max(...(await depths()))

  await chart.hover()
  await page.mouse.wheel(0, -300)

  await expect
    .poll(async () => Math.max(...(await depths())))
    .toBeLessThan(full)

  // 되돌리면 전체가 다시 보인다.
  await page.getByRole('button', { name: '전체 보기' }).click()
  await expect.poll(async () => Math.max(...(await depths()))).toBe(full)
})

test('그래프 위에서 굴리면 바깥 패널이 스크롤되지 않는다', async ({ page }) => {
  // 확대와 바깥 스크롤이 겹치면 그래프를 키우려다 화면이 함께 밀린다.
  // jsdom 에는 스크롤이 없어 여기서만 확인된다.
  await createProject(page, 'noscroll')
  await setSource(page, ONE_DIMENSIONAL_SOURCE)
  await page.getByRole('button', { name: '실행' }).click()

  const chart = page.locator('.chart svg')
  await expect(chart).toBeVisible({ timeout: 120_000 })

  const panel = page.locator('.workspace aside').last()
  const scrollTop = async () => panel.evaluate((node) => node.scrollTop)
  const before = await scrollTop()

  const depths = async () =>
    (await chart.locator('.tick').allTextContents())
      .filter((text) => !text.startsWith('1e'))
      .map(Number)
  const fullDepth = Math.max(...(await depths()))

  await chart.hover()
  await page.mouse.wheel(0, 300)   // 아래로: 보통은 페이지가 내려간다
  await page.mouse.wheel(0, -300)

  // 확대는 일어나되 패널은 제자리여야 한다.
  await expect.poll(async () => Math.max(...(await depths()))).toBeLessThan(fullDepth)
  expect(await scrollTop()).toBe(before)
})

test('그래프를 끌어도 글자가 선택되지 않는다', async ({ page }) => {
  // 눈금·범례 글자가 파랗게 잡히면 그래프를 옮길 때마다 지저분해진다.
  await createProject(page, 'noselect')
  await setSource(page, ONE_DIMENSIONAL_SOURCE)
  await page.getByRole('button', { name: '실행' }).click()

  const chart = page.locator('.chart svg')
  await expect(chart).toBeVisible({ timeout: 120_000 })

  // 확대해야 끌 수 있다.
  await chart.hover()
  await page.mouse.wheel(0, -300)
  await expect(page.getByRole('button', { name: '전체 보기' })).toBeVisible()

  const box = (await chart.boundingBox())!
  await page.mouse.move(box.x + box.width * 0.3, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width * 0.7, box.y + box.height / 2, { steps: 12 })
  await page.mouse.up()

  const selected = await page.evaluate(() =>
    (window.getSelection()?.toString() ?? '').trim(),
  )
  expect(selected).toBe('')
})

test('확대한 채 컷을 옮겨도 확대가 유지된다', async ({ page }) => {
  // 컷을 옮길 때마다 확대가 풀리면 매번 다시 확대해야 한다.
  await createProject(page, 'keepzoom')
  await setSource(page, TWO_DIMENSIONAL_SOURCE)
  await page.getByRole('button', { name: '실행' }).click()

  const surface = page.locator('canvas.surface')
  await expect(surface).toBeVisible({ timeout: 120_000 })
  const chart = page.locator('.chart svg')
  await expect(chart).toBeVisible()

  const depths = async () =>
    (await chart.locator('.tick').allTextContents())
      .filter((text) => !text.startsWith('1e'))
      .map(Number)
  const full = Math.max(...(await depths()))

  await chart.hover()
  await page.mouse.wheel(0, -300)
  await expect.poll(async () => Math.max(...(await depths()))).toBeLessThan(full)
  const zoomed = Math.max(...(await depths()))

  // 단면의 다른 위치를 눌러 컷을 옮긴다.
  const box = (await surface.boundingBox())!
  await page.mouse.click(box.x + box.width * 0.7, box.y + box.height / 2)

  // 컷 위치는 바뀌되 확대는 그대로여야 한다.
  await expect(page.getByRole('button', { name: '전체 보기' })).toBeVisible()
  expect(Math.max(...(await depths()))).toBeCloseTo(zoomed, 5)
})

test('물리량 체크박스가 그래프 바로 위에 있다', async ({ page }) => {
  // 2D 단면이 사이에 끼면 체크박스를 누를 때마다 스크롤을 오르내려야 한다.
  await createProject(page, 'boxpos')
  await setSource(page, TWO_DIMENSIONAL_SOURCE)
  await page.getByRole('button', { name: '실행' }).click()

  const chart = page.locator('.chart')
  await expect(chart).toBeVisible({ timeout: 120_000 })

  const boxes = (await page.locator('.quantities').boundingBox())!
  const graph = (await chart.boundingBox())!
  const canvas = (await page.locator('canvas.surface').boundingBox())!

  expect(boxes.y).toBeGreaterThan(canvas.y)
  expect(boxes.y).toBeLessThan(graph.y)
  // 사이에 다른 것이 끼면 안 된다.
  expect(graph.y - (boxes.y + boxes.height)).toBeLessThan(40)
})

test('격자 보기를 켜면 단면에 격자가 얹힌다', async ({ page }) => {
  // 캔버스에 그리는 기능이라 단위 테스트로는 "그리라고 시켰는지"까지만 볼 수
  // 있다. 실제로 픽셀이 바뀌는지는 브라우저에서만 확인된다.
  await createProject(page, 'meshview')
  await setSource(page, TWO_DIMENSIONAL_SOURCE)
  await page.getByRole('button', { name: '실행' }).click()

  const canvas = page.locator('canvas.surface')
  await expect(canvas).toBeVisible({ timeout: 120_000 })

  const toggle = page.getByLabel('격자 보기')
  await expect(toggle).not.toBeChecked()
  const before = await canvas.screenshot()

  await toggle.check()
  await expect(toggle).toBeChecked()
  const withMesh = await canvas.screenshot()
  expect(Buffer.compare(before, withMesh)).not.toBe(0)

  // 끄면 원래대로 돌아와야 한다. 남아 있으면 끌 방법이 없다.
  await toggle.uncheck()
  const after = await canvas.screenshot()
  expect(Buffer.compare(before, after)).toBe(0)
})

test('오래 도는 잡을 중단할 수 있다', async ({ page }) => {
  // 시뮬레이터는 인식하지 못한 첫 단어를 셸로 넘긴다. 타임아웃(600초)까지
  // 도는 잡을 만들어, 사용자가 직접 멈출 수 있는지 확인한다.
  await createProject(page, 'cancelme')
  await setSource(page, 'sleep 300\n')
  await page.getByRole('button', { name: '실행' }).click()

  // **실행 중까지 기다린다.** 대기 중에 눌러 버리면 컨테이너를 죽이는 경로를
  // 타지 않아, 정작 확인하려던 부분이 검증되지 않는다.
  await expect(page.getByText('실행 중')).toBeVisible({ timeout: 60_000 })

  const stop = page.getByRole('button', { name: '중단' })
  await stop.click()

  await expect(page.getByText('중단됨')).toBeVisible({ timeout: 30_000 })
  // 멈춘 잡에는 다시 누를 버튼이 없어야 한다.
  await expect(stop).toBeHidden()
})
