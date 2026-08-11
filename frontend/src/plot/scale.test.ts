/**
 * 축 스케일과 색 매핑.
 *
 * 도핑 농도는 1e14 에서 1e21 까지 7제곱을 오간다. 선형 축으로 그리면 가장 큰
 * 값 하나만 보이고 나머지는 전부 바닥에 붙는다. 로그 축이 기본이어야 한다.
 *
 * 문제는 0 과 음수다. net_doping 은 p 형 영역에서 음수가 되고, 로그를 취할 수
 * 없다. 그렇다고 버리면 접합 위치가 그림에서 사라진다.
 */
import { describe, expect, it } from 'vitest'
import { colorFor, logTicks, toLogDomain } from './scale'

describe('로그 축 정의역', () => {
  it('양수만 있으면 최소·최대를 그대로 쓴다', () => {
    const domain = toLogDomain([1e14, 1e18, 1e21])

    expect(domain.min).toBeCloseTo(1e14)
    expect(domain.max).toBeCloseTo(1e21)
  })

  it('0 과 음수는 정의역에서 뺀다', () => {
    // log(0) 은 -무한, log(음수)는 NaN 이라 축이 통째로 깨진다.
    const domain = toLogDomain([0, -1e16, 1e15, 1e19])

    expect(domain.min).toBeCloseTo(1e15)
    expect(domain.max).toBeCloseTo(1e19)
  })

  it('음수가 있었다는 사실을 알린다', () => {
    // 화면이 "음수 구간은 표시되지 않음"을 알려줄 수 있어야 한다.
    expect(toLogDomain([-1, 1e15]).hasNonPositive).toBe(true)
    expect(toLogDomain([1e15]).hasNonPositive).toBe(false)
  })

  it('쓸 수 있는 값이 없으면 비어 있다고 알린다', () => {
    expect(toLogDomain([0, -5]).empty).toBe(true)
  })

  it('값이 하나뿐이면 위아래로 한 자릿수씩 벌린다', () => {
    // 균일 도핑 기판이 이렇다. 정의역이 한 점이면 축이 그려지지 않는다.
    const domain = toLogDomain([1e15, 1e15])

    expect(domain.min).toBeLessThan(1e15)
    expect(domain.max).toBeGreaterThan(1e15)
  })
})

describe('로그 눈금', () => {
  it('10의 거듭제곱마다 눈금을 놓는다', () => {
    expect(logTicks(1e14, 1e17)).toEqual([1e14, 1e15, 1e16, 1e17])
  })

  it('정의역 안쪽으로만 놓는다', () => {
    const ticks = logTicks(3e14, 7e16)

    expect(Math.min(...ticks)).toBeGreaterThanOrEqual(3e14)
    expect(Math.max(...ticks)).toBeLessThanOrEqual(7e16)
  })

  it('범위가 아주 넓어도 눈금이 폭주하지 않는다', () => {
    // 눈금이 수십 개면 축 글자가 서로 겹쳐 읽을 수 없다.
    expect(logTicks(1e-30, 1e30).length).toBeLessThanOrEqual(12)
  })

  it('한 자릿수 안이면 빈 배열이 아니다', () => {
    expect(logTicks(2e15, 8e15).length).toBeGreaterThan(0)
  })
})

describe('색 매핑', () => {
  it('정의역 양끝이 서로 다른 색이다', () => {
    expect(colorFor(1e14, 1e14, 1e20)).not.toBe(colorFor(1e20, 1e14, 1e20))
  })

  it('로그 기준으로 중간을 잡는다', () => {
    // 1e14~1e20 의 가운데는 1e17 이다. 선형으로 잡으면 5e19 가 되어
    // 색이 위쪽에 몰린다.
    const middle = colorFor(1e17, 1e14, 1e20)
    const linearMiddle = colorFor(5e19, 1e14, 1e20)

    expect(middle).not.toBe(linearMiddle)
  })

  it('정의역을 벗어난 값은 양끝 색으로 잘라 쓴다', () => {
    expect(colorFor(1e10, 1e14, 1e20)).toBe(colorFor(1e14, 1e14, 1e20))
    expect(colorFor(1e30, 1e14, 1e20)).toBe(colorFor(1e20, 1e14, 1e20))
  })

  it('0 과 음수도 색을 준다', () => {
    // 그리지 못하는 값이라고 투명하게 두면 메시에 구멍이 뚫린 것처럼 보인다.
    expect(colorFor(0, 1e14, 1e20)).toMatch(/^#|rgb/)
    expect(colorFor(-1e16, 1e14, 1e20)).toMatch(/^#|rgb/)
  })

  it('정의역이 한 점이어도 색이 나온다', () => {
    expect(colorFor(1e15, 1e15, 1e15)).toMatch(/^#|rgb/)
  })
})
