import { expect, test } from '@playwright/test'
import { createProject, logOut, signUp, uniqueEmail } from './fixtures'

// 세션은 브라우저를 닫아도 서버에 남는다(유휴 30분). 정리하지 않으면 테스트가
// 쌓일수록 동시 접속 정원에 부딪힌다.
test.afterEach(async ({ page }) => {
  await logOut(page)
})

test('파일을 끌어서 폴더에 넣는다', async ({ page, context }) => {
  // jsdom 은 실제 드래그를 하지 않는다. HTML5 드래그가 진짜로 붙는지는
  // 브라우저에서만 확인된다.
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await signUp(page, uniqueEmail('dnd'))
  await createProject(page, 'movable')

  await page.getByRole('button', { name: '파일 열기' }).click()
  const files = page.getByRole('dialog', { name: '내 파일' })

  page.once('dialog', (dialog) => dialog.accept('semi'))
  await files.getByRole('button', { name: '새 폴더' }).click()
  await expect(files.getByRole('button', { name: 'semi' })).toBeVisible()

  const source = files.locator('li', { hasText: 'movable.in' })
  const target = files.locator('li', { hasText: 'semi' }).first()
  await source.dragTo(target)

  // 폴더를 펼치면 안에 들어와 있어야 한다.
  await files.getByRole('button', { name: 'semi' }).click()
  const nested = files.locator('li').filter({ hasText: 'movable.in' })
  await expect(nested).toHaveCount(1)
  await expect(nested).toHaveAttribute('style', /--depth: 1/)
})
