/**
 * 엔드포인트 경로와 메서드.
 *
 * 경로를 잘못 적으면 404 가 나고, 화면에서는 "프로젝트를 찾을 수 없습니다"
 * 처럼 그럴듯한 메시지로 보인다. 여기서 한 번씩 눌러 두면 그 혼동이 없다.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { auth, jobs, projects } from './endpoints'

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({}),
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => vi.unstubAllGlobals())

function lastCall() {
  const [path, init] = fetchMock.mock.calls[0]
  return { path, method: init.method, body: init.body }
}

describe('인증', () => {
  it('가입은 초대 코드를 함께 보낸다', async () => {
    // 초대 없이는 가입할 수 없다. 코드를 빠뜨리면 서버가 422 로 거절한다.
    await auth.register('a@example.com', 'pw', 'invite-xyz')

    expect(lastCall()).toMatchObject({
      path: '/api/auth/register',
      method: 'POST',
    })
    expect(JSON.parse(lastCall().body)).toEqual({
      email: 'a@example.com',
      password: 'pw',
      invite_code: 'invite-xyz',
    })
  })

  it('로그인', async () => {
    await auth.login('a@example.com', 'pw')

    expect(lastCall().path).toBe('/api/auth/login')
  })

  it('로그아웃은 본문 없이 POST 한다', async () => {
    await auth.logout()

    expect(lastCall()).toMatchObject({ path: '/api/auth/logout', method: 'POST' })
  })

  it('현재 사용자', async () => {
    await auth.me()

    expect(lastCall().path).toBe('/api/auth/me')
  })
})

describe('프로젝트', () => {
  it('목록', async () => {
    await projects.list()

    expect(lastCall().path).toBe('/api/projects')
  })

  it('생성', async () => {
    await projects.create('cmos')

    expect(lastCall().body).toBe('{"name":"cmos"}')
  })

  it('소스 저장은 리비전을 만든다', async () => {
    await projects.saveSource(7, 'init boron\n')

    expect(lastCall().path).toBe('/api/projects/7/revisions')
  })

  it('실행 제출', async () => {
    await projects.submit(7)

    expect(lastCall()).toMatchObject({
      path: '/api/projects/7/jobs',
      method: 'POST',
    })
  })

  it('잡 목록은 같은 경로를 GET 한다', async () => {
    await projects.jobs(7)

    expect(lastCall()).toMatchObject({
      path: '/api/projects/7/jobs',
      method: 'GET',
    })
  })
})

describe('잡', () => {
  it('상세', async () => {
    await jobs.get(42)

    expect(lastCall().path).toBe('/api/jobs/42')
  })

  it('산출물은 순번으로 가져온다', async () => {
    // 이름순이 아니라 생성 순서여야 공정 흐름과 일치한다.
    await jobs.artifact(42, 3)

    expect(lastCall().path).toBe('/api/jobs/42/artifacts/3')
  })
})
