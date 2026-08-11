/**
 * 카탈로그 캐시.
 *
 * 자동완성은 키를 누를 때마다 부른다. 그때마다 서버에 물으면 목록이 커서를
 * 따라오지 못하고, 홈서버에 초당 수십 건이 꽂힌다. 카탈로그는 배포 중에 바뀌지
 * 않으므로 한 번 받아 두고 걸러 쓴다.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CatalogCache } from './catalog'

const COMMAND_LIST = {
  commands: [
    { name: 'structure', description: '구조 저장', parameter_count: 20 },
    { name: 'stress', description: null, parameter_count: 3 },
    { name: 'select', description: null, parameter_count: 5 },
  ],
  keywords: [{ name: 'source', description: '파일을 읽어 실행' }],
}

const STRUCTURE = {
  name: 'structure',
  source_name: 'structure',
  description: '구조 저장',
  parameters: [
    { name: 'outfile', type: 'string', units: '저장할 파일 이름', unreachable: false },
    { name: 'backside', type: 'boolean', units: null, unreachable: true },
    { name: 'backside.y', type: 'float', units: null, unreachable: false },
  ],
}

let fetchMock: ReturnType<typeof vi.fn>
let cache: CatalogCache

beforeEach(() => {
  fetchMock = vi.fn(async (path: string) => {
    const body = path.includes('/commands/') ? STRUCTURE : COMMAND_LIST
    return { ok: true, status: 200, json: async () => body } as Response
  })
  vi.stubGlobal('fetch', fetchMock)
  cache = new CatalogCache()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('커맨드 목록', () => {
  it('커맨드와 키워드를 함께 돌려준다', async () => {
    const names = (await cache.words()).map((w) => w.name)

    expect(names).toContain('structure')
    expect(names).toContain('source')
  })

  it('키워드를 구분해 표시한다', async () => {
    const source = (await cache.words()).find((w) => w.name === 'source')

    expect(source?.kind).toBe('keyword')
  })

  it('두 번 불러도 한 번만 가져온다', async () => {
    await cache.words()
    await cache.words()

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('동시에 불러도 한 번만 가져온다', async () => {
    // 타이핑 중에는 요청이 겹친다. 진행 중인 요청을 공유하지 않으면
    // 첫 글자마다 목록을 새로 받는다.
    await Promise.all([cache.words(), cache.words(), cache.words()])

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})

describe('파라미터', () => {
  it('커맨드별로 한 번만 가져온다', async () => {
    await cache.parameters('structure')
    await cache.parameters('structure')

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('도달 불가 파라미터는 빼고 준다', async () => {
    // 골라 봐야 시뮬레이터가 ambiguous 로 거절한다.
    const names = (await cache.parameters('structure')).map((p) => p.name)

    expect(names).not.toContain('backside')
    expect(names).toContain('backside.y')
  })

  it('사용자가 친 접두사 그대로 서버에 묻는다', async () => {
    await cache.parameters('stru')

    expect(fetchMock.mock.calls[0][0]).toContain('/commands/stru')
  })

  it('접두사와 정식 이름을 같은 항목으로 캐시한다', async () => {
    // stru 로 받아 온 결과는 structure 의 것이다. 다시 물을 이유가 없다.
    await cache.parameters('stru')
    await cache.parameters('structure')

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('찾을 수 없는 커맨드는 빈 목록으로 넘긴다', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: '없음' }),
    } as Response)

    // 오타를 치는 중에도 404 가 난다. 자동완성이 예외로 죽으면 안 된다.
    await expect(cache.parameters('zzz')).resolves.toEqual([])
  })

  it('모호한 커맨드도 빈 목록으로 넘긴다', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ detail: { message: '모호', candidates: [] } }),
    } as Response)

    await expect(cache.parameters('str')).resolves.toEqual([])
  })
})
