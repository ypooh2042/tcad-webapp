import { describe, expect, it } from 'vitest'
import { distanceToSegment, nearestInterface } from './hitTest'

describe('distanceToSegment', () => {
  it('선분 위의 점은 거리 0', () => {
    expect(distanceToSegment(5, 0, 0, 0, 10, 0)).toBe(0)
  })

  it('수직 거리를 잰다', () => {
    expect(distanceToSegment(5, 3, 0, 0, 10, 0)).toBeCloseTo(3)
  })

  it('선분을 무한히 늘리지 않는다', () => {
    // 늘린 직선까지 재면 0 이 나온다. 멀리 있는 계면이 커서 옆에 있는 것처럼
    // 잡히면 화면이 엉뚱한 곳을 밝힌다.
    expect(distanceToSegment(50, 0, 0, 0, 10, 0)).toBeCloseTo(40)
  })

  it('길이 0 인 선분은 점까지의 거리', () => {
    expect(distanceToSegment(3, 4, 0, 0, 0, 0)).toBeCloseTo(5)
  })
})

describe('nearestInterface', () => {
  const candidates = [
    { key: 'source', segments: [[0, 0, 10, 0]] },
    { key: 'drain', segments: [[0, 100, 10, 100]] },
  ]

  it('가까운 쪽을 고른다', () => {
    expect(nearestInterface(5, 3, candidates, 12)).toBe('source')
    expect(nearestInterface(5, 97, candidates, 12)).toBe('drain')
  })

  it('문턱 밖이면 아무것도 안 고른다', () => {
    // 늘 무언가 잡히면 커서를 어디에 둬도 화면이 어두워진다.
    expect(nearestInterface(5, 50, candidates, 12)).toBeNull()
  })

  it('꺾인 계면도 조각마다 잰다', () => {
    const bent = [
      { key: 'gate', segments: [[0, 0, 10, 0], [10, 0, 10, 40]] },
    ]
    expect(nearestInterface(12, 30, bent, 12)).toBe('gate')
  })

  it('후보가 없으면 null', () => {
    expect(nearestInterface(0, 0, [], 12)).toBeNull()
  })
})
