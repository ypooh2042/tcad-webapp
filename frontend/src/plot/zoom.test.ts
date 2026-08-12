/**
 * 가로축 확대·축소.
 *
 * 도핑 프로파일은 표면 0.1µm 안에서 대부분이 일어나는데 꼬리는 몇 µm 까지
 * 끌린다. 전체를 한 화면에 넣으면 정작 봐야 할 접합부가 몇 픽셀로 뭉개진다.
 *
 * 계산만 떼어 여기서 검증한다. 화면 좌표와 섞으면 눈으로 확인할 수밖에 없다.
 */
import { describe, expect, it } from 'vitest'
import { clampView, panBy, resetView, zoomAround, type View } from './zoom'

const FULL: View = { from: 0, to: 10 }

describe('확대', () => {
  it('폭이 줄어든다', () => {
    const zoomed = zoomAround(FULL, FULL, 0.5, 5)

    expect(zoomed.to - zoomed.from).toBeCloseTo(5, 6)
  })

  it('가리킨 지점이 제자리에 남는다', () => {
    // 커서 아래가 움직이면 확대할수록 보려던 곳에서 멀어진다.
    const at = 2
    const before = (at - FULL.from) / (FULL.to - FULL.from)

    const zoomed = zoomAround(FULL, FULL, 0.5, at)

    const after = (at - zoomed.from) / (zoomed.to - zoomed.from)
    expect(after).toBeCloseTo(before, 6)
  })

  it('가장자리를 가리켜도 제자리에 남는다', () => {
    const zoomed = zoomAround(FULL, FULL, 0.5, 0)

    expect(zoomed.from).toBeCloseTo(0, 6)
  })

  it('축소하면 폭이 늘어난다', () => {
    const half = { from: 2.5, to: 7.5 }

    const wider = zoomAround(half, FULL, 2, 5)

    expect(wider.to - wider.from).toBeGreaterThan(5)
  })
})

describe('경계', () => {
  it('데이터 범위를 넘지 않는다', () => {
    // 넘어가면 빈 공간을 확대하게 된다.
    const wider = zoomAround(FULL, FULL, 4, 5)

    expect(wider.from).toBeGreaterThanOrEqual(FULL.from)
    expect(wider.to).toBeLessThanOrEqual(FULL.to)
  })

  it('축소하다 전체에 닿으면 전체가 된다', () => {
    const wider = zoomAround({ from: 4, to: 6 }, FULL, 100, 5)

    expect(wider).toEqual(FULL)
  })

  it('끝에서 확대해도 범위를 벗어나지 않는다', () => {
    const zoomed = zoomAround({ from: 9, to: 10 }, FULL, 0.5, 10)

    expect(zoomed.to).toBeLessThanOrEqual(FULL.to)
    expect(zoomed.from).toBeGreaterThanOrEqual(FULL.from)
  })

  it('무한정 확대되지 않는다', () => {
    // 폭이 0 이 되면 좌표 변환이 0 으로 나뉜다.
    let view = FULL
    for (let i = 0; i < 200; i += 1) view = zoomAround(view, FULL, 0.5, 5)

    expect(view.to - view.from).toBeGreaterThan(0)
  })

  it('한 점짜리 데이터에서도 터지지 않는다', () => {
    const degenerate = { from: 3, to: 3 }

    const zoomed = zoomAround(degenerate, degenerate, 0.5, 3)

    expect(Number.isFinite(zoomed.from)).toBe(true)
    expect(Number.isFinite(zoomed.to)).toBe(true)
  })
})

describe('이동', () => {
  it('폭을 유지한 채 옮긴다', () => {
    const view = { from: 2, to: 4 }

    const moved = panBy(view, FULL, 1)

    expect(moved).toEqual({ from: 3, to: 5 })
  })

  it('왼쪽 끝에서 더 못 간다', () => {
    const view = { from: 0, to: 2 }

    const moved = panBy(view, FULL, -5)

    expect(moved).toEqual({ from: 0, to: 2 })
  })

  it('오른쪽 끝에서 더 못 간다', () => {
    const view = { from: 8, to: 10 }

    const moved = panBy(view, FULL, 5)

    expect(moved).toEqual({ from: 8, to: 10 })
  })

  it('폭은 어떤 경우에도 그대로다', () => {
    const view = { from: 8, to: 10 }

    expect(panBy(view, FULL, 99).to - panBy(view, FULL, 99).from).toBeCloseTo(2, 6)
  })
})

describe('되돌리기', () => {
  it('전체 범위로 돌아간다', () => {
    expect(resetView(FULL)).toEqual(FULL)
  })
})

describe('데이터 범위가 바뀔 때', () => {
  it('그대로 들어가면 확대를 유지한다', () => {
    // 컷 위치만 옮겼을 뿐인데 확대가 풀리면 매번 다시 확대해야 한다.
    const view = { from: 2, to: 4 }

    expect(clampView(view, FULL)).toEqual(view)
  })

  it('범위 밖으로 나가면 안으로 밀어 넣는다', () => {
    // 다른 단계는 깊이 범위가 다르다. 그대로 두면 빈 화면이 뜬다.
    const view = { from: 8, to: 10 }

    const moved = clampView(view, { from: 0, to: 5 })

    expect(moved.from).toBeGreaterThanOrEqual(0)
    expect(moved.to).toBeLessThanOrEqual(5)
  })

  it('새 범위가 더 좁으면 폭을 줄인다', () => {
    const view = { from: 0, to: 10 }

    expect(clampView(view, { from: 0, to: 3 })).toEqual({ from: 0, to: 3 })
  })

  it('폭을 지킬 수 있으면 지킨다', () => {
    const view = { from: 4, to: 6 }

    const moved = clampView(view, { from: 0, to: 5 })

    expect(moved.to - moved.from).toBeCloseTo(2, 6)
  })
})
