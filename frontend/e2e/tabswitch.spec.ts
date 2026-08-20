import { expect, test } from '@playwright/test'
import { createProject, logOut, setSource, signUp, uniqueEmail } from './fixtures'

// 세션은 브라우저를 닫아도 서버에 남는다(유휴 30분). 정리하지 않으면 테스트가
// 쌓일수록 동시 접속 정원에 부딪힌다.
test.afterEach(async ({ page }) => {
  await logOut(page)
})

test('탭을 눌러 파일을 전환한다', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await signUp(page, uniqueEmail('tabsw'))

  await createProject(page, 'first')
  await setSource(page, 'FIRST FILE\n')
  await page.getByRole('button', { name: /저장/ }).click()
  await expect(page.getByText(/저장됨/)).toBeVisible()

  await createProject(page, 'second')
  await setSource(page, 'SECOND FILE\n')
  await page.getByRole('button', { name: /저장/ }).click()
  await expect(page.getByText(/저장됨/)).toBeVisible()

  // 지금은 second 가 활성. first 탭을 눌러 돌아간다.
  // 파일 탭 목록으로 좁힌다. 헤더에는 화면 전환 탭(공정/소자 해석)도 있다.
  await expect(
    page.getByRole('tablist', { name: '열어 둔 파일' }).getByRole('tab'),
  ).toHaveCount(2)
  await page.getByRole('tab', { name: 'first.in' }).click()

  await expect(page.getByRole('tab', { name: 'first.in' })).toHaveAttribute(
    'aria-selected',
    'true',
  )
  await expect(page.locator('.monaco-editor').first()).toContainText('FIRST FILE')
})

test('탭을 오가도 고치던 내용이 남는다', async ({ page, context }) => {
  // 예전에는 전환할 때마다 "버리고 이동할까요?" 를 물었다. 잠깐 다른 파일을
  // 들춰 보는 것조차 저장을 요구하면 안 된다.
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await signUp(page, uniqueEmail('keepdraft'))

  await createProject(page, 'first')
  await setSource(page, 'FIRST 원본\n')
  await page.getByRole('button', { name: /저장/ }).click()
  await expect(page.getByText(/저장됨/)).toBeVisible()

  await createProject(page, 'second')
  await setSource(page, 'SECOND 원본\n')
  await page.getByRole('button', { name: /저장/ }).click()
  await expect(page.getByText(/저장됨/)).toBeVisible()

  // 저장하지 않은 채로 고친다.
  await setSource(page, 'SECOND 고치던 중\n')

  // 아무것도 묻지 않고 오간다.
  await page.getByRole('tab', { name: 'first.in' }).click()
  await expect(page.locator('.monaco-editor')).toContainText('FIRST 원본')
  await page.getByRole('tab', { name: /second.in/ }).click()

  await expect(page.locator('.monaco-editor')).toContainText('SECOND 고치던 중')
})

test('새로고침해도 열어 둔 탭과 고치던 내용이 돌아온다', async ({
  page,
  context,
}) => {
  // 세션이 끊겼다 돌아오는 경우와 같은 경로다. 서버가 상태를 들고 있는지는
  // 실제로 페이지를 다시 띄워 봐야 확인된다.
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await signUp(page, uniqueEmail('restore'))

  await createProject(page, 'work')
  await setSource(page, '저장하지 않은 편집\n')

  // 상태를 서버에 남기는 것은 마지막 변경 뒤 1초다.
  await page.waitForTimeout(2000)
  await page.reload()

  await expect(page.getByRole('tab', { name: /work.in/ })).toBeVisible()
  await expect(page.locator('.monaco-editor')).toContainText(
    '저장하지 않은 편집',
  )
  // 저장하지 않았다는 표시도 함께 돌아와야 한다.
  await expect(
    page.getByRole('tab', { name: /work.in/ }).getByLabel('저장되지 않음'),
  ).toBeVisible()
})

test('새로 만든 파일은 비어 있다', async ({ page, context }) => {
  // 뼈대를 넣어 두면 새 파일을 만들 때마다 쓰지도 않을 줄을 먼저 지워야 한다.
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await signUp(page, uniqueEmail('blank'))

  await createProject(page, 'blank')

  await expect(page.locator('.monaco-editor .view-lines')).toHaveText('')
})

test('탭을 오가도 보던 줄로 돌아온다', async ({ page, context }) => {
  // 300줄짜리 공정 흐름에서 탭을 옮길 때마다 맨 위로 돌아가면 보던 자리를
  // 매번 다시 찾아야 한다.
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await signUp(page, uniqueEmail('cursor'))

  const long = Array.from({ length: 60 }, (_, i) => `# 줄 ${i + 1}`).join('\n')
  await createProject(page, 'long')
  await setSource(page, `${long}\n`)
  await createProject(page, 'other')
  await setSource(page, 'OTHER\n')

  // 긴 파일의 아래쪽으로 커서를 옮긴다.
  await page.getByRole('tab', { name: /long.in/ }).click()
  await page.locator('.monaco-editor').first().click()
  await page.keyboard.press('Control+End')
  const before = await page.locator('.monaco-editor .cursor').boundingBox()

  await page.getByRole('tab', { name: /other.in/ }).click()
  await expect(page.locator('.monaco-editor')).toContainText('OTHER')
  await page.getByRole('tab', { name: /long.in/ }).click()

  await expect(page.locator('.monaco-editor')).toContainText('줄 60')
  const after = await page.locator('.monaco-editor .cursor').boundingBox()
  expect(Math.abs(after!.y - before!.y)).toBeLessThan(3)
})

test('되돌리기가 파일마다 따로 남는다', async ({ page, context }) => {
  // 모델이 하나면 탭을 옮긴 뒤 Ctrl+Z 가 남의 파일 편집을 되돌린다.
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await signUp(page, uniqueEmail('undo'))

  await createProject(page, 'one')
  await setSource(page, 'ONE 원본\n')
  await createProject(page, 'two')
  await setSource(page, 'TWO 원본\n')

  // 한글은 IME 를 타서 한 글자씩 치면 글자가 새는 경우가 있다. 여기서 보려는
  // 것은 되돌리기 범위라 ASCII 로 친다.
  await page.getByRole('tab', { name: /one.in/ }).click()
  await page.locator('.monaco-editor').first().click()
  await page.keyboard.type('ADDED')
  await expect(page.locator('.monaco-editor')).toContainText('ADDED')

  // two.in 으로 옮겨 되돌리기를 여러 번 누른다. 이 파일 자신의 편집만
  // 되돌아가야 한다.
  await page.getByRole('tab', { name: /two.in/ }).click()
  await page.locator('.monaco-editor').first().click()
  for (let i = 0; i < 5; i++) await page.keyboard.press('Control+z')

  // one.in 의 편집은 그대로 남아 있어야 한다. 모델이 하나면 여기서 사라진다.
  await page.getByRole('tab', { name: /one.in/ }).click()
  await expect(page.locator('.monaco-editor')).toContainText('ADDED')
})
