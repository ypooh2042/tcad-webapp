/**
 * 2D 단면의 좌표 변환.
 *
 * 그리기와 클릭 처리가 **같은 계산을 써야 한다.** 따로 두면 여백을 넣는 순간
 * 한쪽만 고쳐서, 클릭한 자리와 컷 선이 어긋난다. 캔버스는 jsdom 에서 그릴 수
 * 없으므로 수식만 따로 떼어 여기서 검증한다.
 */
import { describe, expect, it } from 'vitest'
import { surfaceGeometry } from './surfaceGeometry'

const BOUNDS = { xMin: 0, xMax: 4, yMin: 0, yMax: 2 }

function geometry(width = 400, height = 300) {
  return surfaceGeometry(BOUNDS, width, height)
}

describe('그리는 영역', () => {
  it('눈금 라벨 자리를 남긴다', () => {
    // 여백이 없으면 라벨이 캔버스 밖으로 나가 잘린다.
    const g = geometry()

    expect(g.left).toBeGreaterThan(0)
    expect(g.top + g.plotHeight).toBeLessThan(300)
  })

  it('가로세로 비율을 유지한다', () => {
    // 늘려 그리면 접합 깊이가 실제와 달라 보인다.
    const g = geometry()
    const drawnWidth = g.px(BOUNDS.xMax) - g.px(BOUNDS.xMin)
    const drawnHeight = g.py(BOUNDS.yMax) - g.py(BOUNDS.yMin)

    expect(drawnWidth / drawnHeight).toBeCloseTo(2, 5)
  })

  it('그린 그림이 영역 안에 들어간다', () => {
    const g = geometry()

    expect(g.px(BOUNDS.xMin)).toBeGreaterThanOrEqual(g.left - 0.001)
    expect(g.px(BOUNDS.xMax)).toBeLessThanOrEqual(g.left + g.plotWidth + 0.001)
    expect(g.py(BOUNDS.yMax)).toBeLessThanOrEqual(g.top + g.plotHeight + 0.001)
  })

  it('깊이는 아래로 갈수록 커진다', () => {
    const g = geometry()

    expect(g.py(BOUNDS.yMin)).toBeLessThan(g.py(BOUNDS.yMax))
  })
})

describe('클릭 되돌리기', () => {
  it('그린 자리를 찍으면 그 좌표가 나온다', () => {
    // px 와 unpx 가 어긋나면 클릭한 곳과 컷 선이 다른 자리에 놓인다.
    const g = geometry()

    for (const x of [0, 1.5, 4]) {
      expect(g.unpx(g.px(x))).toBeCloseTo(x, 6)
    }
  })

  it('영역 밖은 가장자리로 자른다', () => {
    // 도메인 밖을 찍으면 빈 프로파일이 나온다.
    const g = geometry()

    expect(g.clampX(g.unpx(-500))).toBe(BOUNDS.xMin)
    expect(g.clampX(g.unpx(9999))).toBe(BOUNDS.xMax)
  })
})

describe('눈금', () => {
  it('가로 눈금을 낸다', () => {
    const g = geometry()

    expect(g.xTicks.length).toBeGreaterThan(1)
    expect(Math.min(...g.xTicks)).toBeGreaterThanOrEqual(BOUNDS.xMin)
    expect(Math.max(...g.xTicks)).toBeLessThanOrEqual(BOUNDS.xMax)
  })

  it('세로 눈금을 낸다', () => {
    const g = geometry()

    expect(g.yTicks.length).toBeGreaterThan(1)
    expect(Math.max(...g.yTicks)).toBeLessThanOrEqual(BOUNDS.yMax)
  })

  it('간격에 맞춰 자릿수를 정한다', () => {
    // 0.02um 간격에 "0.0" 이면 눈금이 전부 같은 값으로 보인다.
    const fine = surfaceGeometry(
      { xMin: 0, xMax: 0.1, yMin: 0, yMax: 0.1 },
      400,
      300,
    )

    expect(fine.formatX(0.02)).not.toBe('0.0')
  })

  it('크기가 0 이어도 터지지 않는다', () => {
    // 아직 레이아웃이 잡히기 전에 한 번 그려진다.
    const g = surfaceGeometry(BOUNDS, 0, 0)

    expect(Number.isFinite(g.px(1))).toBe(true)
  })

  it('한 점짜리 구조에서도 터지지 않는다', () => {
    const g = surfaceGeometry({ xMin: 1, xMax: 1, yMin: 1, yMax: 1 }, 400, 300)

    expect(Number.isFinite(g.px(1))).toBe(true)
    expect(Number.isFinite(g.py(1))).toBe(true)
  })
})

describe('unpy', () => {
  // 전극을 화면에서 찍으려면 세로도 되돌려야 한다. 예전에는 컷 선만 그으면
  // 됐으므로 x 만 있었다.
  const bounds = { xMin: 0, xMax: 4, yMin: 0, yMax: 2 }

  it('py 의 역함수다', () => {
    const g = surfaceGeometry(bounds, 400, 300)
    for (const y of [0, 0.5, 1.25, 2]) {
      expect(g.unpy(g.py(y))).toBeCloseTo(y, 9)
    }
  })

  it('가로와 같은 배율을 쓴다', () => {
    // 비율을 유지하므로 같은 픽셀 거리는 같은 µm 거리여야 한다.
    const g = surfaceGeometry(bounds, 400, 300)
    const dx = g.unpx(100) - g.unpx(0)
    const dy = g.unpy(100) - g.unpy(0)
    expect(dy).toBeCloseTo(dx, 9)
  })

  it('세로 범위를 벗어난 값을 잘라 준다', () => {
    const g = surfaceGeometry(bounds, 400, 300)
    expect(g.clampY(-5)).toBe(0)
    expect(g.clampY(99)).toBe(2)
  })
})
