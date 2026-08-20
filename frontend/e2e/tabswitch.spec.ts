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
  await expect(page.getByRole('tab')).toHaveCount(2)
  await page.getByRole('tab', { name: 'first.in' }).click()

  await expect(page.getByRole('tab', { name: 'first.in' })).toHaveAttribute(
    'aria-selected',
    'true',
  )
  await expect(page.locator('.monaco-editor').first()).toContainText('FIRST FILE')
})
