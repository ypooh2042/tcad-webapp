/**
 * Monaco 자동완성·호버 제공자.
 *
 * Monaco 자체는 띄우지 않는다. 검증할 것은 "어떤 상황에 어떤 후보를 내놓는가"
 * 이고, 그건 제공자 함수만 떼어 부르면 확인할 수 있다.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { registerSupremProviders } from './providers'

const WORDS = {
  commands: [
    { name: 'structure', description: '구조 저장', parameter_count: 20 },
    { name: 'stress', description: null, parameter_count: 3 },
  ],
  keywords: [{ name: 'source', description: '파일을 읽어 실행' }],
}

const INITIALIZE = {
  name: 'initialize',
  source_name: 'initialize',
  description: '메시와 배경 농도 초기화',
  parameters: [
    {
      name: 'conc',
      type: 'float',
      source_name: 'conc',
      truncated: false,
      default: null,
      units: '배경 농도',
      description: null,
      error: null,
      message: null,
      group: null,
      group_message: null,
      unreachable: false,
    },
    {
      name: 'boron',
      type: 'boolean',
      source_name: 'boron',
      truncated: false,
      default: null,
      units: null,
      description: null,
      error: null,
      message: null,
      group: 'impurity',
      group_message: '불순물은 하나만',
      unreachable: false,
    },
  ],
}

/** 필요한 부분만 흉내 낸 monaco. */
function fakeMonaco() {
  const registered: { completion?: any; hover?: any } = {}
  return {
    monaco: {
      languages: {
        CompletionItemKind: {
          Function: 1,
          Keyword: 2,
          Property: 3,
          EnumMember: 4,
        },
        registerCompletionItemProvider: (_id: string, provider: unknown) => {
          registered.completion = provider
          return { dispose: () => undefined }
        },
        registerHoverProvider: (_id: string, provider: unknown) => {
          registered.hover = provider
          return { dispose: () => undefined }
        },
      },
    },
    registered,
  }
}

/** `|` 로 커서 위치를 표시한 한 줄짜리 모델. */
function modelFor(marked: string) {
  const column = marked.indexOf('|') + 1
  const line = marked.replace('|', '')
  const before = line.slice(0, column - 1)
  const word = /[\w./]*$/.exec(before)?.[0] ?? ''
  const after = /^[\w./]*/.exec(line.slice(column - 1))?.[0] ?? ''
  return {
    model: {
      getLineContent: () => line,
      getWordUntilPosition: () => ({
        word,
        startColumn: column - word.length,
        endColumn: column,
      }),
      getWordAtPosition: () =>
        word + after ? { word: word + after } : null,
    },
    position: { lineNumber: 1, column },
  }
}

let providers: ReturnType<typeof fakeMonaco>['registered']

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string) => ({
      ok: true,
      status: 200,
      json: async () => (path.includes('/commands/') ? INITIALIZE : WORDS),
    })),
  )
  const { monaco, registered } = fakeMonaco()
  registerSupremProviders(monaco as never)
  providers = registered
})

async function complete(marked: string) {
  const { model, position } = modelFor(marked)
  const result = await providers.completion.provideCompletionItems(
    model,
    position,
  )
  return result.suggestions as { label: string; insertText: string }[]
}

async function hover(marked: string) {
  const { model, position } = modelFor(marked)
  return providers.hover.provideHover(model, position)
}

describe('커맨드 자동완성', () => {
  it('접두사에 맞는 커맨드를 내놓는다', async () => {
    const labels = (await complete('stru|')).map((s) => s.label)

    expect(labels).toEqual(['structure'])
  })

  it('키워드도 함께 내놓는다', async () => {
    const labels = (await complete('sou|')).map((s) => s.label)

    expect(labels).toContain('source')
  })

  it('빈 줄에서는 전부 내놓는다', async () => {
    expect(await complete('|')).toHaveLength(3)
  })
})

describe('파라미터 자동완성', () => {
  it('커맨드의 파라미터를 내놓는다', async () => {
    const labels = (await complete('initialize c|')).map((s) => s.label)

    expect(labels).toEqual(['conc'])
  })

  it('값을 받는 파라미터에는 = 를 붙여 넣는다', async () => {
    const conc = (await complete('initialize c|'))[0]

    expect(conc.insertText).toBe('conc=')
  })

  it('boolean 에는 = 를 붙이지 않는다', async () => {
    // boolean 은 값을 받지 않는다. `boron=` 은 틀린 줄이 된다.
    const boron = (await complete('initialize b|'))[0]

    expect(boron.insertText).toBe('boron')
  })
})

describe('완성하지 않는 자리', () => {
  it('주석 안에서는 후보를 내놓지 않는다', async () => {
    expect(await complete('# 여기는 주석 stru|')).toEqual([])
  })

  it('값 자리에서는 후보를 내놓지 않는다', async () => {
    // 값은 파일 이름·수식·사용자 변수라 카탈로그가 모른다.
    expect(await complete('initialize conc=1e1|')).toEqual([])
  })
})

describe('호버', () => {
  it('커맨드 설명을 보여준다', async () => {
    const result = await hover('structure| outfile=a.str')

    expect(JSON.stringify(result?.contents)).toContain('구조 저장')
  })

  it('파라미터 설명을 보여준다', async () => {
    const result = await hover('initialize conc|=1e14')

    expect(JSON.stringify(result?.contents)).toContain('배경 농도')
  })

  it('상호배타 묶음을 경고한다', async () => {
    const result = await hover('initialize boron|')

    expect(JSON.stringify(result?.contents)).toContain('불순물은 하나만')
  })

  it('모르는 낱말에는 아무것도 띄우지 않는다', async () => {
    expect(await hover('initialize zzz|')).toBeNull()
  })
})
