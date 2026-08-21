import { expect, test } from '@playwright/test'
import {
  CONTACT_SOURCE,
  TWO_GATE_SOURCE,
  createProject,
  logOut,
  setSource,
  signUp,
  uniqueEmail,
} from './fixtures'

// 세션은 브라우저를 닫아도 서버에 남는다(유휴 30분). 정리하지 않으면 테스트가
// 쌓일수록 동시 접속 정원에 부딪힌다.
test.afterEach(async ({ page }) => {
  await logOut(page)
})

/**
 * 단면에서 계면 하나를 눌러 쪽지를 띄운다.
 *
 * 좌표를 계산하지 않고 훑는다. `surfaceGeometry` 는 비율을 유지하며 가운데
 * 정렬하고 눈금 여백을 두므로, 시험이 그 수식을 복제하면 여백을 손볼 때마다
 * 같이 깨진다.
 */
async function clickInterface(
  page: import('@playwright/test').Page,
  name: RegExp,
) {
  const map = page.locator('.electrode-map')
  const box = (await map.boundingBox())!
  const popover = page.getByRole('dialog', { name })
  // 가로로도 훑는다. 같은 종류의 계면이 여럿이면(게이트 둘) 가운데만 눌러서는
  // 오른쪽 것에 닿을 수 없다.
  for (let x = 8; x < box.width; x += 12) {
    for (let y = box.height - 4; y > 0; y -= 6) {
      await map.click({ position: { x, y } })
      if (await popover.isVisible()) return popover
    }
  }
  return popover
}

/** 공정을 돌려 알루미늄 전극이 있는 구조를 하나 만든다. */
async function runProcess(page: import('@playwright/test').Page) {
  await createProject(page, 'contacts')
  await setSource(page, CONTACT_SOURCE)
  await page.getByRole('button', { name: /실행/ }).click()
  await expect(page.locator('.status-succeeded')).toBeVisible({
    timeout: 90_000,
  })
}

test('공정 결과를 소자 해석으로 넘겨 I-V 를 뽑는다', async ({
  page,
  context,
}) => {
  // 재메시와 솔버는 컨테이너 두 개를 거친다. 배관이 실제로 이어지는지는
  // 브라우저에서 한 번 돌려 봐야만 확인된다.
  test.setTimeout(240_000)
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await signUp(page, uniqueEmail('devsim'))

  await runProcess(page)

  // 결과에서 넘긴다. `.str` 은 파일 목록에 안 나오므로 이것이 주 경로다.
  await page.getByRole('button', { name: '소자 해석' }).click()

  // 계면마다 전극이 하나씩 자동으로 잡혀야 한다 — source / gate / drain / body.
  const editor = page.locator('.source-editor')
  await expect(editor.getByRole('textbox', { name: '전극 1 이름' })).toHaveValue(
    'source',
    { timeout: 30_000 },
  )
  await expect(editor.getByRole('textbox', { name: '전극 2 이름' })).toHaveValue(
    'gate',
  )
  await expect(editor.getByRole('textbox', { name: '전극 3 이름' })).toHaveValue(
    'drain',
  )
  await expect(editor.getByRole('textbox', { name: '전극 4 이름' })).toHaveValue(
    'body',
  )

  // 기본 조건은 바로 제출할 수 있어야 한다.
  await expect(page.locator('.problems')).toHaveCount(0)

  // 스윕을 세 점으로 줄인다. 곡선이 나오는지만 보면 된다.
  const sweep = page.locator('.bias[data-role="sweep"]')
  await sweep.getByLabel('끝 (V)').fill('1')
  await sweep.getByLabel('점 개수').fill('3')

  await page.getByRole('button', { name: '해석 실행' }).click()

  await expect(page.locator('.run-result .status-succeeded')).toBeVisible({
    timeout: 180_000,
  })
  await expect(page.getByRole('img', { name: /곡선/ })).toBeVisible()
  // 지표 표가 함께 나와야 한다. 곡선만으로는 얼마나 다른지 못 읽는다.
  await expect(page.locator('.figure-table')).toBeVisible()
})

test('전극마다 전압원이 하나씩 붙는다', async ({ page, context }) => {
  // 1전극-1전압원. 전압원이 전극을 여러 개 거느리면 "여러 계면을 한 전위로"
  // 라는 같은 일을 전극 쪽과 전압원 쪽 두 군데서 할 수 있게 된다.
  test.setTimeout(180_000)
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await signUp(page, uniqueEmail('bias'))

  await runProcess(page)
  await page.getByRole('button', { name: '소자 해석' }).click()

  await expect(page.locator('.bias')).toHaveCount(4, { timeout: 30_000 })
  // 기판도 자기 전압원을 갖는다.
  await expect(page.locator('.bias .drives')).toHaveText([
    '→ source',
    '→ gate',
    '→ drain',
    '→ body',
  ])
  // 전극을 고르는 체크박스는 없다.
  await expect(page.locator('.bias input[type="checkbox"]')).toHaveCount(0)
  await expect(page.locator('.bias[data-role="sweep"]')).toHaveCount(1)
})

test('계면을 다른 전극으로 옮기면 전극 옆 표시가 따라간다', async ({
  page,
  context,
}) => {
  // 전극 지정은 단면 위에서 한다. 이름만 보고 고르면 그게 구조의 어디인지
  // 알 수 없다.
  test.setTimeout(180_000)
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await signUp(page, uniqueEmail('assign'))

  await runProcess(page)
  await page.getByRole('button', { name: '소자 해석' }).click()

  const list = page.locator('.electrode-list li')
  await expect(list).toHaveCount(4, { timeout: 30_000 })
  await expect(list.nth(0).locator('.chip')).toHaveText(['source'])
  await expect(list.nth(3).locator('.chip')).toHaveText(['body'])

  // 뒷면 계면을 눌러 쪽지를 띄운다.
  //
  // 좌표를 미리 계산해 두지 않는다. 단면은 비율을 유지하며 가운데 정렬되고
  // 눈금 여백까지 있어서, 시험이 그 수식을 복제하면 여백을 고칠 때마다 같이
  // 깨진다. 아래에서부터 훑어 올라가며 찾는다.
  const popover = await clickInterface(page, /body/)
  await expect(popover).toBeVisible()

  // source 전극으로 옮긴다.
  await popover.getByRole('button', { name: /source/ }).click()

  await expect(list.nth(0).locator('.chip')).toHaveText(['source', 'body'])
  // 원래 있던 전극에는 계면이 없어져 실행이 막힌다.
  await expect(page.locator('.problems')).toBeVisible()
  await expect(page.getByRole('button', { name: '해석 실행' })).toBeDisabled()
})

test('전압을 소수로 칠 수 있다', async ({ page, context }) => {
  // 예전에는 값을 매번 다시 문자열로 만들어 넣어서, "0." 이 "0" 으로 되돌아가
  // 게이트 단계 전압을 정수로만 넣을 수 있었다. 한 글자씩 실제로 쳐 봐야
  // 드러나는 종류의 결함이라 fill() 이 아니라 type() 을 쓴다.
  test.setTimeout(180_000)
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await signUp(page, uniqueEmail('decimal'))

  await runProcess(page)
  await page.getByRole('button', { name: '소자 해석' }).click()

  const step = page.locator('.bias[data-role="step"]')
  const values = step.getByLabel('단계 전압 (쉼표로 구분, V)')
  await expect(values).toBeVisible({ timeout: 30_000 })

  await values.fill('')
  await values.pressSequentially('0.4, 0.8, 1.2')
  await expect(values).toHaveValue('0.4, 0.8, 1.2')

  // 스윕의 끝 전압도 같은 문제를 겪었다.
  const sweep = page.locator('.bias[data-role="sweep"]')
  const stop = sweep.getByLabel('끝 (V)')
  await stop.fill('')
  await stop.pressSequentially('1.25')
  await expect(stop).toHaveValue('1.25')

  // 간격은 점 개수에서 계산해 보여주기만 한다.
  await expect(sweep.getByText(/0\.25V 간격/)).toBeVisible()

  // 소수가 실제로 조건에 들어갔는지는 점 개수로 확인된다.
  // 스윕 6점 × 단계 3개 = 18점.
  await expect(page.getByText('바이어스 점 18개')).toBeVisible()
  await expect(page.locator('.problems')).toHaveCount(0)
})

test('해석 패널 폭을 끌어서 바꾼다', async ({ page, context }) => {
  test.setTimeout(180_000)
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await signUp(page, uniqueEmail('split'))

  await runProcess(page)
  await page.getByRole('button', { name: '소자 해석' }).click()

  const panel = page.locator('.devsim-run')
  await expect(panel).toBeVisible({ timeout: 30_000 })
  const before = (await panel.boundingBox())!.width

  const splitter = page.getByRole('separator', { name: '해석 패널 폭' })
  const grip = (await splitter.boundingBox())!
  await page.mouse.move(grip.x + grip.width / 2, grip.y + grip.height / 2)
  await page.mouse.down()
  await page.mouse.move(grip.x - 120, grip.y + grip.height / 2, { steps: 8 })
  await page.mouse.up()

  const after = (await panel.boundingBox())!.width
  expect(after).toBeGreaterThan(before + 80)
})

test('금속이 없는 단계는 소자 해석으로 넘길 수 없다', async ({
  page,
  context,
}) => {
  // 전극은 알루미늄이 실리콘이나 폴리실리콘에 닿아야 생긴다. 넘길 수 있게
  // 두면 사용자는 넘어간 뒤에야 "전극이 없습니다"를 보고, 25단계짜리 흐름에서
  // 어느 단계부터 되는지 하나씩 눌러 보게 된다.
  test.setTimeout(180_000)
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await signUp(page, uniqueEmail('nometal'))

  await createProject(page, 'bare')
  await setSource(
    page,
    [
      'line x loc=0 spacing=0.5 tag=left',
      'line x loc=1 spacing=0.5 tag=right',
      'line y loc=0 spacing=0.2 tag=top',
      'line y loc=1 spacing=0.5 tag=bottom',
      'region silicon xlo=left xhi=right ylo=top yhi=bottom',
      'bound exposed xlo=left xhi=right ylo=top yhi=top',
      'bound backside xlo=left xhi=right ylo=bottom yhi=bottom',
      'initialize boron conc=1.0e15 ori=100',
      'structure out=bare.str',
      '',
    ].join('\n'),
  )
  await page.getByRole('button', { name: /실행/ }).click()
  await expect(page.locator('.status-succeeded')).toBeVisible({
    timeout: 90_000,
  })
  // 결과가 그려질 때까지 기다린다. 편집기 본문에도 같은 글자가 있으므로
  // 결과 창 안으로 좁힌다.
  await expect(page.locator('.stage-name')).toHaveText('bare.str')

  // 결과 창에 넘기기 버튼이 아예 없어야 한다. 머리말의 화면 전환 탭은 같은
  // 글자를 쓰므로 버튼 쪽만 센다.
  await expect(page.locator('button.analyse')).toHaveCount(0)

  // 소자 해석 탭의 구조 목록에도 올라오지 않는다.
  //
  // 가입할 때 들어가는 예제(`nmos.str`)만 남아 있어야 한다.
  await page.getByRole('tab', { name: /소자 해석/ }).click()
  const picker = page.locator('.devsim-bar select').first()
  await expect(picker.locator('option')).toHaveCount(1, { timeout: 30_000 })
  await expect(picker).toContainText('nmos.str')
  await expect(picker).not.toContainText('bare.str')
})

test('같은 .in 을 다시 돌리면 그 구조가 갈아 끼워진다', async ({
  page,
  context,
}) => {
  // 공정 코드를 고쳐 다시 돌렸는데 옛 구조가 목록에 남아 있으면, 어느 것이
  // 지금 코드의 결과인지 구분할 수 없다.
  test.setTimeout(240_000)
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await signUp(page, uniqueEmail('rerun'))

  await runProcess(page)
  await page.getByRole('tab', { name: /소자 해석/ }).click()
  const picker = page.locator('.devsim-bar select').first()
  // 가입할 때 들어간 예제와 방금 돌린 것, 둘이다.
  await expect(picker.locator('option')).toHaveCount(2, { timeout: 30_000 })
  await expect(picker).toContainText('contacts.str')

  // 같은 파일에서 금속을 빼고 다시 돌린다.
  await page.getByRole('tab', { name: '공정' }).click()
  await setSource(
    page,
    [
      'line x loc=0 spacing=0.5 tag=left',
      'line x loc=1 spacing=0.5 tag=right',
      'line y loc=0 spacing=0.2 tag=top',
      'line y loc=1 spacing=0.5 tag=bottom',
      'region silicon xlo=left xhi=right ylo=top yhi=bottom',
      'bound exposed xlo=left xhi=right ylo=top yhi=top',
      'bound backside xlo=left xhi=right ylo=bottom yhi=bottom',
      'initialize boron conc=1.0e15 ori=100',
      'structure out=nometal.str',
      '',
    ].join('\n'),
  )
  await page.getByRole('button', { name: /실행/ }).click()
  await expect(page.locator('.stage-name')).toHaveText('nometal.str', {
    timeout: 120_000,
  })

  // 옛 구조가 사라지고 예제만 남아야 한다.
  await page.getByRole('tab', { name: /소자 해석/ }).click()
  await expect(picker.locator('option')).toHaveCount(1, { timeout: 30_000 })
  await expect(picker).not.toContainText('contacts.str')
})

test('계면 이름을 바꾸면 전극 옆 표시도 따라간다', async ({ page, context }) => {
  test.setTimeout(180_000)
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await signUp(page, uniqueEmail('rename'))

  await runProcess(page)
  await page.getByRole('button', { name: '소자 해석' }).click()

  const list = page.locator('.electrode-list li')
  await expect(list).toHaveCount(4, { timeout: 30_000 })

  const popover = await clickInterface(page, /body/)
  await expect(popover).toBeVisible()
  const name = popover.getByLabel('계면 이름')
  await name.fill('')
  await name.pressSequentially('기판 뒷면')

  await expect(name).toHaveValue('기판 뒷면')
  // 전극 목록의 칩에도 그대로 나와야 한다.
  await expect(list.nth(3).locator('.chip')).toHaveText(['기판 뒷면'])
})

test('게이트가 둘이어도 각각 따로 다룬다', async ({ page, context }) => {
  // CMOS 처럼 트랜지스터가 둘이면 게이트도 둘이다. 예전에는 서버가 둘 다
  // `gate` 로 이름 붙였고, 그러면 화면만 헷갈리는 것으로 끝나지 않는다 —
  // 해석기가 뒤엣것으로 앞엣것을 덮어써 한쪽이 엉뚱한 자리에 걸린다.
  test.setTimeout(240_000)
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await signUp(page, uniqueEmail('twogate'))

  await createProject(page, 'twogate')
  await setSource(page, TWO_GATE_SOURCE)
  await page.getByRole('button', { name: /실행/ }).click()
  await expect(page.locator('.status-succeeded')).toBeVisible({
    timeout: 120_000,
  })

  await page.getByRole('button', { name: '소자 해석' }).click()
  const list = page.locator('.electrode-list li')
  await expect(list).toHaveCount(7, { timeout: 30_000 })

  // 게이트가 서로 다른 이름으로 잡혀야 한다.
  const chips = page.locator('.electrode-list .chip')
  await expect(chips.filter({ hasText: /^gate1$/ })).toHaveCount(1)
  await expect(chips.filter({ hasText: /^gate2$/ })).toHaveCount(1)

  // 오른쪽 게이트를 눌러도 오른쪽 것이 떠야 한다.
  const second = await clickInterface(page, /gate2/)
  await expect(second).toBeVisible()
  await expect(second.getByLabel('계면 이름')).toHaveValue('gate2')
  await second.getByRole('button', { name: '닫기' }).click()

  // 한쪽 게이트를 빼도 다른 쪽은 남는다.
  await page.getByRole('button', { name: 'gate1 전극 빼기' }).click()
  await expect(list).toHaveCount(6)
  await expect(chips.filter({ hasText: /^gate2$/ })).toHaveCount(1)
})

test('저장을 눌러야 비교 목록에 올라간다', async ({ page, context }) => {
  // 조건을 조금씩 바꿔 가며 여남은 번 돌리는 것이 보통이다. 그것이 다 쌓이면
  // 정작 비교하고 싶은 둘을 그 안에서 찾아야 한다.
  test.setTimeout(300_000)
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await signUp(page, uniqueEmail('save'))

  await runProcess(page)
  await page.getByRole('button', { name: '소자 해석' }).click()

  const sweep = page.locator('.bias[data-role="sweep"]')
  await expect(sweep).toBeVisible({ timeout: 30_000 })
  await sweep.getByLabel('끝 (V)').fill('1')
  await sweep.getByLabel('점 개수').fill('2')
  const step = page.locator('.bias[data-role="step"]')
  await step.getByLabel('단계 전압 (쉼표로 구분, V)').fill('2')

  await page.getByRole('button', { name: '해석 실행' }).click()
  await expect(page.locator('.run-result .status-succeeded')).toBeVisible({
    timeout: 240_000,
  })

  // 아직 아무것도 저장되지 않았다.
  await page.locator('.devsim-tabs').getByRole('tab', { name: '비교' }).click()
  await expect(page.getByText('저장된 해석이 아직 없습니다')).toBeVisible()

  // 이름을 붙여 저장한다.
  await page.locator('.devsim-tabs').getByRole('tab', { name: '해석' }).click()
  await page.getByLabel('해석 이름').fill('두꺼운 산화막')
  await page.getByRole('button', { name: '저장' }).click()
  await expect(page.getByText(/저장했습니다/)).toBeVisible()

  // 비교 목록에 뜨고, 어느 코드에서 나왔는지 보인다.
  await page.locator('.devsim-tabs').getByRole('tab', { name: '비교' }).click()
  const entry = page.locator('.compare-picker li').first()
  await expect(entry).toContainText('두꺼운 산화막')
  await entry.getByRole('checkbox').check()
  await expect(page.locator('.origins')).toContainText('contacts.in')

  // 이름을 고칠 수 있다.
  await page.locator('.origins .link').click()
  const rename = page.locator('.origins input')
  await rename.fill('얇은 산화막')
  await rename.press('Enter')
  await expect(page.locator('.compare-picker li').first()).toContainText(
    '얇은 산화막',
  )
})

test('전류 단위가 µA/µm 로 나온다', async ({ page, context }) => {
  test.setTimeout(300_000)
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await signUp(page, uniqueEmail('unit'))

  await page.getByRole('tab', { name: /소자 해석/ }).click()
  const sweep = page.locator('.bias[data-role="sweep"]')
  await expect(sweep).toBeVisible({ timeout: 30_000 })

  // 기본 조건: 게이트 1, 2, 4 V / 드레인 0~2.5 V 6점.
  await expect(
    page.locator('.bias[data-role="step"]').getByLabel(/단계 전압/),
  ).toHaveValue('1, 2, 4')
  await expect(sweep.getByLabel('끝 (V)')).toHaveValue('2.5')
  await expect(sweep.getByLabel('점 개수')).toHaveValue('6')
  await expect(sweep.getByText(/0\.5V 간격/)).toBeVisible()

  // 빠르게 끝나도록 줄인다.
  await sweep.getByLabel('끝 (V)').fill('1')
  await sweep.getByLabel('점 개수').fill('2')
  await page
    .locator('.bias[data-role="step"]')
    .getByLabel(/단계 전압/)
    .fill('2')

  await page.getByRole('button', { name: '해석 실행' }).click()
  await expect(page.locator('.run-result .status-succeeded')).toBeVisible({
    timeout: 240_000,
  })
  await expect(page.getByRole('img', { name: /uA\/um/ })).toBeVisible()
  await expect(page.locator('.figure-table')).toContainText('µA/µm')
})

test('폴리를 이상 도체로 놓으면 경고가 뜬다', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await signUp(page, uniqueEmail('caution'))

  await page.getByRole('tab', { name: /소자 해석/ }).click()
  await expect(page.locator('.devsim-bar .notice.caution')).toHaveCount(0)

  await page
    .locator('.devsim-bar select')
    .nth(1)
    .selectOption('conductor')

  const caution = page.locator('.devsim-bar .notice.caution')
  await expect(caution).toBeVisible()
  await expect(caution).toContainText('저항이 0인 완전 도체')
})

test('가입하면 소자 해석에 예제 구조가 들어 있다', async ({ page, context }) => {
  // 소자 해석은 실행 결과를 입력으로 받으므로, 예제를 한 번 돌리기 전에는
  // 탭이 비어 있었다.
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await signUp(page, uniqueEmail('seeded'))

  await page.getByRole('tab', { name: /소자 해석/ }).click()
  const picker = page.locator('.devsim-bar select').first()
  await expect(picker).toContainText('nmos.str', { timeout: 30_000 })
  await expect(page.locator('.electrode-list li')).toHaveCount(4)
})

test('로그인 화면이 DevSim 도 함께 알린다', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText(/DevSim/)).toBeVisible()
})

test('무엇을 전극으로 보는지 탭에 적혀 있다', async ({ page, context }) => {
  // 목록에 왜 일부 단계만 나오는지 알려주지 않으면, 사용자는 앱이 결과를
  // 잃어버린 줄 안다.
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await signUp(page, uniqueEmail('notice'))

  await page.getByRole('tab', { name: /소자 해석/ }).click()
  const notice = page.locator('.devsim-bar .notice')
  await expect(notice).toBeVisible()
  await expect(notice).toContainText('알루미늄')
  await expect(notice).toContainText('폴리실리콘')
})
