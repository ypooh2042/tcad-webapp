/**
 * 호버에 띄울 문서 조립.
 *
 * 여기서 사용자가 실제로 알아야 하는 것은 두 가지다: 값의 제약(잘못 쓰면
 * 시뮬레이터가 거절한다)과 상호배타 묶음(같이 쓰면 안 된다). 둘 다 카탈로그에
 * 들어 있는데 보여 주지 않으면 사용자는 오류 메시지를 보고 나서야 알게 된다.
 */
import { describe, expect, it } from 'vitest'
import { parameterDocs } from './docs'
import type { CatalogParameter } from '../api/catalog'

function param(overrides: Partial<CatalogParameter> = {}): CatalogParameter {
  return {
    name: 'conc',
    type: 'float',
    source_name: 'conc',
    truncated: false,
    default: null,
    units: null,
    description: null,
    error: null,
    message: null,
    group: null,
    group_message: null,
    unreachable: false,
    ...overrides,
  }
}

describe('기본 정보', () => {
  it('이름과 타입을 보여준다', () => {
    expect(parameterDocs('init', param())).toContain('conc')
    expect(parameterDocs('init', param())).toContain('float')
  })

  it('기본값이 있으면 보여준다', () => {
    expect(parameterDocs('init', param({ default: '1.0e10' }))).toContain('1.0e10')
  })

  it('단위를 설명으로 쓴다', () => {
    const text = parameterDocs('init', param({ units: '배경 농도' }))

    expect(text).toContain('배경 농도')
  })

  it('설명이 단위와 같으면 한 번만 쓴다', () => {
    const text = parameterDocs('init', param({ units: '농도', description: '농도' }))

    expect(text.match(/농도/g)).toHaveLength(1)
  })
})

describe('제약', () => {
  it('오류 조건을 보여준다', () => {
    const text = parameterDocs('init', param({ error: 'conc < 0.0' }))

    expect(text).toContain('conc < 0.0')
  })

  it('오류 메시지를 함께 보여준다', () => {
    const text = parameterDocs(
      'init',
      param({ error: 'conc < 0.0', message: '농도는 양수여야 합니다' }),
    )

    expect(text).toContain('농도는 양수여야 합니다')
  })
})

describe('상호배타 묶음', () => {
  it('묶음에 속하면 경고한다', () => {
    const text = parameterDocs(
      'init',
      param({ name: 'boron', group: 'impurity', group_message: '불순물은 하나만' }),
    )

    expect(text).toContain('불순물은 하나만')
  })

  it('묶음 메시지가 없어도 배타라는 사실은 알린다', () => {
    const text = parameterDocs('init', param({ name: 'boron', group: 'impurity' }))

    expect(text).toContain('impurity')
  })
})

describe('잘린 이름', () => {
  it('원래 이름이 다르면 그 사실을 알린다', () => {
    // 문서에는 concentration 으로 적혀 있는데 시뮬레이터는 concentrati 만
    // 받는다. 이걸 말해 주지 않으면 사용자는 오타로 오해한다.
    const text = parameterDocs(
      'deposit',
      param({
        name: 'concentrati',
        source_name: 'concentration',
        truncated: true,
      }),
    )

    expect(text).toContain('concentration')
    expect(text).toContain('11')
  })

  it('잘리지 않았으면 언급하지 않는다', () => {
    expect(parameterDocs('init', param())).not.toContain('11자')
  })
})
