/**
 * 인증 흐름.
 *
 * 단위 테스트는 API 를 목으로 가려 놓는다. 세션 쿠키가 **브라우저에** 실리고
 * 새로고침 뒤에도 살아 있는지는 여기서만 확인된다.
 */
import { expect, test } from '@playwright/test'
import { PASSWORD, issueInviteCode, logOut, signUp, uniqueEmail } from './fixtures'

// 세션은 브라우저를 닫아도 서버에 남는다(유휴 30분). 정리하지 않으면 테스트가
// 쌓일수록 동시 접속 정원에 부딪힌다.
test.afterEach(async ({ page }) => {
  await logOut(page)
})

test('초대 코드 없이는 가입할 수 없다', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /계정이 없으신가요/ }).click()

  await page.getByLabel('이메일').fill(uniqueEmail('no-invite'))
  await page.getByLabel('비밀번호').fill(PASSWORD)
  await page.getByRole('button', { name: '가입하고 시작' }).click()

  // 브라우저가 required 로 막는다. 작업 화면으로 넘어가면 안 된다.
  await expect(page.getByRole('button', { name: '실행' })).toBeHidden()
})

test('잘못된 초대 코드는 이유를 알려준다', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /계정이 없으신가요/ }).click()

  await page.getByLabel('이메일').fill(uniqueEmail('bad-invite'))
  await page.getByLabel('비밀번호').fill(PASSWORD)
  await page.getByLabel('초대 코드').fill('완전히-틀린-코드')
  await page.getByRole('button', { name: '가입하고 시작' }).click()

  await expect(page.getByRole('alert')).toContainText('초대 코드')
})

test('가입하면 곧바로 작업 화면으로 들어간다', async ({ page }) => {
  const email = uniqueEmail('signup')

  await signUp(page, email)

  await expect(page.getByText(email)).toBeVisible()
})

test('세션이 새로고침을 견딘다', async ({ page }) => {
  // 세션 쿠키는 httponly 다. JS 가 볼 수 없으므로 새로고침 뒤 /auth/me 로
  // 복구되어야 한다 — 그러지 못하면 사용자는 매번 다시 로그인해야 한다.
  const email = uniqueEmail('refresh')
  await signUp(page, email)

  await page.reload()

  await expect(page.getByText(email)).toBeVisible()
})

test('로그아웃하면 로그인 화면으로 돌아간다', async ({ page }) => {
  await signUp(page, uniqueEmail('logout'))

  await page.getByRole('button', { name: '로그아웃' }).click()

  await expect(page.getByLabel('비밀번호')).toBeVisible()
})

test('로그아웃 뒤 새로고침해도 로그인 상태로 돌아오지 않는다', async ({ page }) => {
  await signUp(page, uniqueEmail('logout-refresh'))
  await page.getByRole('button', { name: '로그아웃' }).click()
  await expect(page.getByLabel('비밀번호')).toBeVisible()

  await page.reload()

  // 쿠키가 실제로 지워졌는지 본다. 화면만 바꾸고 세션이 살아 있으면
  // 사용자는 로그아웃했다고 믿는데 아니다.
  await expect(page.getByLabel('비밀번호')).toBeVisible()
})

test('다시 로그인할 수 있다', async ({ page }) => {
  const email = uniqueEmail('relogin')
  await signUp(page, email)
  await page.getByRole('button', { name: '로그아웃' }).click()

  await page.getByLabel('이메일').fill(email)
  await page.getByLabel('비밀번호').fill(PASSWORD)
  await page.getByRole('button', { name: '로그인' }).click()

  await expect(page.getByText(email)).toBeVisible()
})

test('사용 횟수를 다 쓴 초대 코드는 거절된다', async ({ page, browser }) => {
  // max_uses=1 짜리 코드를 하나 만들어 한 번 쓰고, 두 번째를 시도한다.
  const code = issueInviteCode(1)

  // **컨텍스트를 새로 판다.** 같은 컨텍스트에서는 첫 가입의 세션 쿠키가 남아
  // 두 번째 페이지가 이미 로그인 상태로 열린다.
  const first = await browser.newContext()
  const firstPage = await first.newPage()
  await firstPage.goto('/')
  await firstPage.getByRole('button', { name: /계정이 없으신가요/ }).click()
  await firstPage.getByLabel('이메일').fill(uniqueEmail('reuse-first'))
  await firstPage.getByLabel('비밀번호').fill(PASSWORD)
  await firstPage.getByLabel('초대 코드').fill(code)
  await firstPage.getByRole('button', { name: '가입하고 시작' }).click()
  await expect(firstPage.getByRole('button', { name: '실행' })).toBeVisible()
  // 세션을 반납한다. 동시 접속 정원은 브라우저를 닫아도 풀리지 않는다.
  await firstPage.getByRole('button', { name: '로그아웃' }).click()
  await first.close()

  await page.goto('/')
  await page.getByRole('button', { name: /계정이 없으신가요/ }).click()
  await page.getByLabel('이메일').fill(uniqueEmail('reuse-second'))
  await page.getByLabel('비밀번호').fill(PASSWORD)
  await page.getByLabel('초대 코드').fill(code)
  await page.getByRole('button', { name: '가입하고 시작' }).click()

  await expect(page.getByRole('alert')).toContainText('사용된')
})

test('머리말에 접속 현황이 보인다', async ({ page }) => {
  // 정원이 차면 다음 사람이 못 들어온다. 들어와 있는 사람이 자리를 비워
  // 줄지 판단하려면 지금 몇 명인지 보여야 한다.
  await signUp(page, uniqueEmail('occupancy'))

  await expect(page.locator('.occupancy')).toHaveText(/^접속 \d+\/\d+$/)
})
