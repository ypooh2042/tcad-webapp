/**
 * 재질 색 팔레트.
 *
 * 색이 구분되는지는 눈으로 판단하면 안 된다. 명암비는 밝기만 보므로 색이 달라도
 * 통과하고, 눈대중은 화면과 사람마다 다르다. 여기서는 지각 색차 ΔE(CIE Lab)로
 * 잰다 — 감지 한계가 약 2.3 이고, 좁은 띠에서 확실히 구분되려면 그보다 훨씬
 * 넉넉해야 한다.
 */
import { describe, expect, it } from 'vitest'
import { MATERIALS, fillOf, solidOf } from './materials'

/** 시뮬레이터가 증착할 수 있는 재질 전부. `.str` 의 material_id 순. */
const DEPOSITABLE = [
  'oxide',
  'nitride',
  'silicon',
  'poly',
  'oxynitride',
  'aluminum',
  'photoresist',
  'gaas',
]

function toLab(hex: string): [number, number, number] {
  const channel = (offset: number) => parseInt(hex.slice(offset, offset + 2), 16) / 255
  const linear = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  const [r, g, b] = [linear(channel(1)), linear(channel(3)), linear(channel(5))]

  const x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
  const y = r * 0.2126 + g * 0.7152 + b * 0.0722
  const z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883
  const f = (c: number) => (c > 0.008856 ? Math.cbrt(c) : 7.787 * c + 16 / 116)

  return [116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))]
}

function deltaE(a: string, b: string): number {
  const [la, aa, ba] = toLab(a)
  const [lb, ab, bb] = toLab(b)
  return Math.hypot(la - lb, aa - ab, ba - bb)
}

/** 팔레트 안에서 가장 가까운 두 색의 거리. 여기가 무너지면 전부 무의미하다. */
function closestPair(colors: string[]): number {
  let worst = Infinity
  for (let i = 0; i < colors.length; i += 1) {
    for (let j = i + 1; j < colors.length; j += 1) {
      worst = Math.min(worst, deltaE(colors[i], colors[j]))
    }
  }
  return worst
}

describe('재질 색', () => {
  it('증착 가능한 재질을 모두 안다', () => {
    // 이름이 빠지면 회색 "모르는 재질" 로 떨어진다. 알루미늄을 올린 구조가
    // 통째로 그렇게 보였다.
    for (const material of DEPOSITABLE) {
      expect(MATERIALS).toContain(material)
    }
  })

  it('어두운 띠끼리 확실히 구분된다', () => {
    expect(closestPair(DEPOSITABLE.map(fillOf))).toBeGreaterThan(15)
  })

  it('밝은 판끼리 확실히 구분된다', () => {
    expect(closestPair(DEPOSITABLE.map(solidOf))).toBeGreaterThan(20)
  })

  it('같은 재질은 두 화면에서 같은 색상 계열이다', () => {
    // 1D 띠와 2D 단면을 오갈 때 색상이 바뀌면 같은 층인지 알아보지 못한다.
    // 명도는 달라도 되지만(띠는 곡선을 얹으므로 어두워야 한다) 색상은 같아야
    // 한다. Lab 의 a·b 부호가 색상 방향이다.
    for (const material of DEPOSITABLE) {
      const [, fillA, fillB] = toLab(fillOf(material))
      const [, solidA, solidB] = toLab(solidOf(material))
      // 무채색(알루미늄)은 방향이 없으므로 건너뛴다.
      if (Math.hypot(fillA, fillB) < 6) continue
      expect(Math.sign(fillA)).toBe(Math.sign(solidA))
      expect(Math.sign(fillB)).toBe(Math.sign(solidB))
    }
  })

  it('모르는 재질은 실제 재질처럼 보이지 않는다', () => {
    expect(fillOf('unobtainium')).toBe(fillOf('알 수 없음'))
    expect(solidOf('unobtainium')).toBe(solidOf('알 수 없음'))
  })
})
