/**
 * 삼각형 음영.
 *
 * 두 가지를 고친다.
 *
 * 1. **평균을 로그 공간에서 낸다.** 도핑은 자릿수를 오간다. 산술평균
 *    (1e5 + 1e5 + 1e20)/3 은 3.3e19 로 사실상 최댓값이라, 도핑된 정점 하나에
 *    닿기만 해도 삼각형 전체가 최고 농도로 칠해진다. 실측한 사례에서는 그 탓에
 *    증착 산화막 안의 저농도 영역이 통째로 메워져 사라졌다.
 *
 * 2. **정점 값을 삼각형 안에서 보간한다.** 단색으로 칠하면 격자가 성긴 곳에서
 *    삼각형 무늬가 그대로 드러나, 데이터에 없는 조각남을 만들어 낸다.
 */
import { describe, expect, it } from 'vitest'
import { logOf, shadeTriangle, subdivisionDepth } from './shading'

const TRI = { ax: 0, ay: 0, bx: 12, by: 0, cx: 0, cy: 12 }

describe('logOf', () => {
  it('로그를 취한다', () => {
    expect(logOf(1e18)).toBeCloseTo(18)
  })

  it('0 과 음수는 바닥으로 보낸다', () => {
    // 로그를 못 취한다고 버리면 그 자리에 구멍이 뚫린다.
    expect(Number.isFinite(logOf(0))).toBe(true)
    expect(Number.isFinite(logOf(-1e17))).toBe(true)
    expect(logOf(0)).toBeLessThan(logOf(1))
  })
})

describe('subdivisionDepth', () => {
  it('삼각형이 적으면 깊게 나눈다', () => {
    expect(subdivisionDepth(500)).toBeGreaterThanOrEqual(2)
  })

  it('삼각형이 많으면 얕게 나눈다', () => {
    // 세분화 비용은 4^depth 로 는다. 큰 구조에서 브라우저가 멈추면 안 된다.
    expect(subdivisionDepth(200_000)).toBe(0)
    expect(subdivisionDepth(200_000)).toBeLessThan(subdivisionDepth(500))
  })

  it('단조 감소한다', () => {
    const depths = [100, 5_000, 40_000, 200_000].map(subdivisionDepth)
    for (let i = 1; i < depths.length; i += 1) {
      expect(depths[i]!).toBeLessThanOrEqual(depths[i - 1]!)
    }
  })
})

describe('shadeTriangle', () => {
  it('나누지 않으면 조각 하나', () => {
    const shards = shadeTriangle(TRI, [18, 18, 18], 0)

    expect(shards).toHaveLength(1)
    expect(shards[0]!.logValue).toBeCloseTo(18)
  })

  it('한 단계 나누면 네 조각', () => {
    expect(shadeTriangle(TRI, [18, 16, 14], 1)).toHaveLength(4)
  })

  it('두 단계 나누면 열여섯 조각', () => {
    expect(shadeTriangle(TRI, [18, 16, 14], 2)).toHaveLength(16)
  })

  it('넓이를 보존한다', () => {
    const area = (s: { ax: number; ay: number; bx: number; by: number; cx: number; cy: number }) =>
      Math.abs((s.bx - s.ax) * (s.cy - s.ay) - (s.cx - s.ax) * (s.by - s.ay)) / 2

    const whole = area(TRI)
    const sum = shadeTriangle(TRI, [18, 16, 14], 2).reduce((t, s) => t + area(s), 0)

    expect(sum).toBeCloseTo(whole, 6)
  })

  it('로그 공간에서 평균 낸다', () => {
    // 산술평균이면 1e20 에 가까워진다. 그 동작이 이 버그의 정체였다.
    const [shard] = shadeTriangle(TRI, [logOf(1e5), logOf(1e5), logOf(1e20)], 0)

    expect(shard!.logValue).toBeCloseTo(10)
    expect(shard!.logValue).toBeLessThan(logOf(1e15))
  })

  it('꼭짓점 쪽 조각이 그 꼭짓점 값에 가깝다', () => {
    const shards = shadeTriangle(TRI, [20, 10, 10], 1)
    const near = shards.reduce((best, s) => {
      const d = (x: number, y: number) => Math.hypot(x - TRI.ax, y - TRI.ay)
      const c = (s2: typeof s) => d((s2.ax + s2.bx + s2.cx) / 3, (s2.ay + s2.by + s2.cy) / 3)
      return c(s) < c(best) ? s : best
    }, shards[0]!)

    expect(near.logValue).toBeGreaterThan(15)
  })

  it('값이 같으면 색도 그 값', () => {
    const shards = shadeTriangle(TRI, [17, 17, 17], 2)

    for (const s of shards) expect(s.logValue).toBeCloseTo(17)
  })
})

describe('값이 고른 삼각형은 나누지 않는다', () => {
  // 나누는 비용은 4^depth 로 는다. 색이 눈에 띄게 변하지 않는 삼각형까지
  // 나누면, 구조 대부분이 균일한 실제 구조에서 헛일만 수천 배로 는다.
  it('허용오차 안이면 조각 하나', () => {
    expect(shadeTriangle(TRI, [17, 17.01, 16.99], 3, 0.1)).toHaveLength(1)
  })

  it('허용오차를 넘으면 나눈다', () => {
    expect(shadeTriangle(TRI, [17, 20, 14], 2, 0.1).length).toBeGreaterThan(1)
  })

  it('허용오차가 클수록 조각이 준다', () => {
    // 값의 폭은 나눌 때마다 절반이 되므로, 허용오차를 올리면 더 얕은 깊이에서
    // 멈춘다.
    const counts = [0.1, 2, 8, 40].map(
      (tol) => shadeTriangle(TRI, [25, 10, 10], 3, tol).length,
    )

    for (let i = 1; i < counts.length; i += 1) {
      expect(counts[i]!).toBeLessThanOrEqual(counts[i - 1]!)
    }
    expect(counts[0]).toBeGreaterThan(counts[counts.length - 1]!)
    expect(counts[counts.length - 1]).toBe(1)
  })

  it('완전히 균일하면 허용오차 없이도 나누지 않는다', () => {
    // 색이 한 가지뿐인 삼각형을 16 조각으로 칠할 이유가 없다.
    expect(shadeTriangle(TRI, [17, 17, 17], 2)).toHaveLength(1)
  })
})
