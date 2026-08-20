import { expect, test } from '@playwright/test'
import {
  CONTACT_SOURCE,
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

  // 전극이 자동으로 잡혀야 한다 — source / gate / drain / body.
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
  await sweep.getByLabel('끝').fill('1')
  await sweep.getByLabel('간격').fill('0.5')

  await page.getByRole('button', { name: '해석 실행' }).click()

  await expect(page.locator('.run-result .status-succeeded')).toBeVisible({
    timeout: 180_000,
  })
  await expect(page.getByRole('img', { name: /곡선/ })).toBeVisible()
  // 지표 표가 함께 나와야 한다. 곡선만으로는 얼마나 다른지 못 읽는다.
  await expect(page.locator('.figure-table')).toBeVisible()
})

test('전압원을 묶으면 전극이 한쪽에만 걸린다', async ({ page, context }) => {
  // 한 전극이 두 전위를 가질 수는 없다. 화면에서 그 상태를 만들 수 있으면
  // 사용자는 서버가 거절할 때까지 이유를 모른다.
  test.setTimeout(180_000)
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await signUp(page, uniqueEmail('bias'))

  await runProcess(page)
  await page.getByRole('button', { name: '소자 해석' }).click()

  const ground = page.locator('.bias[data-role="const"]')
  await expect(ground.getByText('source')).toBeVisible({ timeout: 30_000 })

  // drain 은 스윕 전압원에 걸려 있다. 접지에 체크하면 저쪽에서 떨어져야 한다.
  const sweep = page.locator('.bias[data-role="sweep"]')
  await ground.getByRole('checkbox').nth(2).check()

  await expect(sweep.getByRole('checkbox').nth(2)).not.toBeChecked()
  // 스윕 전압원에 남은 전극이 없으므로 실행을 막아야 한다.
  await expect(page.locator('.problems')).toBeVisible()
  await expect(page.getByRole('button', { name: '해석 실행' })).toBeDisabled()
})

test('금속이 없는 단계에는 전극이 없다고 알려 준다', async ({
  page,
  context,
}) => {
  // 조용히 빈 화면을 보여 주면 사용자는 앱이 고장 난 줄 안다.
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

  await page.getByRole('button', { name: '소자 해석' }).click()
  await expect(page.getByText(/금속 전극이 없습니다/)).toBeVisible({
    timeout: 30_000,
  })
})
