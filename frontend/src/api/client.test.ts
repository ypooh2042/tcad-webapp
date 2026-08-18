/**
 * API 클라이언트.
 *
 * 백엔드는 오류를 FastAPI 관례대로 `detail` 에 담아 보낸다. 문자열일 때도
 * 있고(대부분) 객체일 때도 있다(모호한 커맨드는 후보 목록을 함께 준다).
 * 이걸 한 곳에서 풀지 않으면 화면마다 `[object Object]` 가 뜬다.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, request } from './client'

function mockFetch(response: Partial<Response> & { json?: () => unknown }) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({}),
    ...response,
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

/** 실패를 기대하는 호출. `.catch` 로 받으면 타입이 unknown 으로 뭉개진다. */
async function failure(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise
  } catch (error) {
    return error as ApiError
  }
  throw new Error('오류가 났어야 합니다')
}


describe('요청', () => {
  it('상대 경로로 보내 세션 쿠키가 실리게 한다', async () => {
    const fetchMock = mockFetch({})

    await request('/api/projects')

    expect(fetchMock.mock.calls[0][0]).toBe('/api/projects')
  })

  it('본문이 있으면 JSON 으로 보낸다', async () => {
    const fetchMock = mockFetch({})

    await request('/api/projects', { method: 'POST', body: { name: 'p' } })

    const init = fetchMock.mock.calls[0][1]
    expect(init.method).toBe('POST')
    expect(init.body).toBe('{"name":"p"}')
    expect(init.headers['Content-Type']).toBe('application/json')
  })

  it('본문이 없으면 Content-Type 을 붙이지 않는다', async () => {
    const fetchMock = mockFetch({})

    await request('/api/auth/me')

    expect(fetchMock.mock.calls[0][1].headers['Content-Type']).toBeUndefined()
  })

  it('204 에는 본문이 없다', async () => {
    mockFetch({
      status: 204,
      json: async () => {
        throw new Error('본문 없음')
      },
    })

    await expect(request('/api/auth/logout', { method: 'POST' })).resolves
      .toBeNull()
  })
})

describe('오류', () => {
  it('문자열 detail 을 메시지로 쓴다', async () => {
    mockFetch({
      ok: false,
      status: 404,
      json: async () => ({ detail: '프로젝트를 찾을 수 없습니다' }),
    })

    await expect(request('/api/projects/1')).rejects.toThrow(
      '프로젝트를 찾을 수 없습니다',
    )
  })

  it('객체 detail 에서 message 를 꺼낸다', async () => {
    mockFetch({
      ok: false,
      status: 409,
      json: async () => ({
        detail: { message: "'str' 은(는) 여러 커맨드에 걸립니다", candidates: ['stress'] },
      }),
    })

    await expect(request('/api/catalog/commands/str')).rejects.toThrow(
      '여러 커맨드에 걸립니다',
    )
  })

  it('구조화된 detail 을 그대로 남긴다', async () => {
    mockFetch({
      ok: false,
      status: 409,
      json: async () => ({
        detail: { message: '모호', candidates: ['stress', 'structure'] },
      }),
    })

    // 후보 목록을 화면에 보여줘야 하므로 메시지로 뭉개면 안 된다.
    const error = await failure(request('/api/x'))
    expect((error.detail as { candidates: string[] }).candidates).toEqual([
      'stress',
      'structure',
    ])
  })

  it('상태 코드를 남긴다', async () => {
    mockFetch({ ok: false, status: 401, json: async () => ({}) })

    const error = await failure(request('/api/auth/me'))
    expect(error.status).toBe(401)
  })

  it('본문이 JSON 이 아니어도 던진다', async () => {
    // nginx 가 502 를 HTML 로 돌려주는 경우가 있다.
    mockFetch({
      ok: false,
      status: 502,
      json: async () => {
        throw new Error('not json')
      },
    })

    const error = await failure(request('/api/projects'))
    expect(error.status).toBe(502)
    // 상태 번호는 사람에게 쓸모가 없다. 무엇을 하면 되는지 알려준다.
    expect(error.message).toMatch(/연결하지 못했습니다/)
  })

  it('네트워크가 끊기면 상태 0 으로 알린다', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('failed')))

    const error = await failure(request('/api/projects'))
    expect(error.status).toBe(0)
  })
})

describe('속도 제한', () => {
  it('429 는 잠시 기다리라고 알려준다', async () => {
    // 프록시가 막은 것이라 본문이 JSON 이 아니다. 기본 문구는 "요청이
    // 실패했습니다 (HTTP 429)" 뿐이라 고장인지 자기 탓인지 알 수 없다.
    mockFetch({
      ok: false,
      status: 429,
      json: async () => {
        throw new Error('본문이 JSON 이 아니다')
      },
    })

    const error = await failure(request('/api/plot/summary'))

    expect(error.message).toMatch(/잠시/)
  })

  it('503 은 서버 쪽 문제로 알린다', async () => {
    mockFetch({
      ok: false,
      status: 503,
      json: async () => {
        throw new Error('본문이 JSON 이 아니다')
      },
    })

    const error = await failure(request('/api/plot/summary'))

    expect(error.message).toMatch(/서버/)
  })
})
