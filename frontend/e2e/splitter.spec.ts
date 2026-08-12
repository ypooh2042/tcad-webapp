/**
 * 패널 크기 조절.
 *
 * 이건 단위 테스트로 잡히지 않는다. 폭 계산이 맞아도 그리드가 넘치면 편집기
 * 칸이 소리 없이 0 으로 접히고, 그 결과는 배치를 실제로 해 봐야 보인다 —
 * 매뉴얼 손잡이가 매뉴얼을 왼쪽 끝에 붙여 놓던 버그가 그랬다.
 */
import { expect, test, type Page } from '@playwright/test'
import { createProject, signUp, uniqueEmail } from './fixtures'

async function widthOf(page: Page, selector: string): Promise<number> {
  const box = await page.locator(selector).boundingBox()
  if (!box) throw new Error(`${selector} 이(가) 화면에 없습니다`)
  return box.width
}

/** 손잡이를 가로로 끈다. */
async function dragSplitter(page: Page, label: string, by: number) {
  const handle = page.getByRole('separator', { name: label })
  const box = await handle.boundingBox()
  if (!box) throw new Error(`${label} 손잡이가 없습니다`)

  const y = box.y + box.height / 2
  await page.mouse.move(box.x + box.width / 2, y)
  await page.mouse.down()
  // 한 번에 옮기면 드래그로 인식하지 않는 브라우저가 있다.
  await page.mouse.move(box.x + box.width / 2 + by / 2, y)
  await page.mouse.move(box.x + box.width / 2 + by, y)
  await page.mouse.up()
}

test('매뉴얼 손잡이가 편집기를 밀어내지 않는다', async ({ page }) => {
  await signUp(page, uniqueEmail('split'))
  await createProject(page, 'layout')

  await page.getByRole('button', { name: '매뉴얼', exact: true }).click()
  await expect(page.getByRole('separator', { name: '매뉴얼 패널 크기' })).toBeVisible()

  const before = await widthOf(page, '.editor')

  // 왼쪽으로 끌면 매뉴얼이 그만큼 넓어지고 편집기가 그만큼 좁아진다.
  await dragSplitter(page, '매뉴얼 패널 크기', -120)

  const after = await widthOf(page, '.editor')
  expect(after).toBeGreaterThan(0)
  // 창 끝을 기준으로 재던 시절에는 여기서 편집기가 0 이 됐다.
  expect(after).toBeLessThan(before)
  expect(before - after).toBeLessThan(240)
})

test('끈 만큼만 넓어진다', async ({ page }) => {
  await signUp(page, uniqueEmail('split'))
  await createProject(page, 'layout')

  await page.getByRole('button', { name: '매뉴얼', exact: true }).click()
  const docs = page.locator('aside.docs')
  const before = await widthOf(page, 'aside.docs')

  await dragSplitter(page, '매뉴얼 패널 크기', -100)

  // 몇 픽셀은 반올림과 커서 보정에서 생긴다. 100 언저리면 맞는 것이다.
  const after = await widthOf(page, 'aside.docs')
  expect(after - before).toBeGreaterThan(90)
  expect(after - before).toBeLessThan(110)
  await expect(docs).toBeVisible()
})
