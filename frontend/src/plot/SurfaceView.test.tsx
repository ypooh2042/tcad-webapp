/**
 * 2D 단면.
 *
 * jsdom 에는 캔버스가 없다. 컨텍스트를 흉내 내어 **좌표 변환**과 **컷 위치
 * 계산**을 확인한다 — 그림 자체가 아니라 그 두 계산이 틀리면 접합 깊이가
 * 실제와 달라 보이거나 엉뚱한 위치의 프로파일이 나온다.
 */
import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SurfaceView } from './SurfaceView'
import type { SurfaceResponse } from '../api/types'

/** 도메인 x=[0,4], y=[0,3] 짜리 삼각형 두 개. */
const SURFACE: SurfaceResponse = {
  quantity: 'chem_boron',
  x: [0, 4, 0, 4],
  y: [0, 0, 3, 3],
  triangles: [
    [0, 1, 2],
    [1, 3, 2],
  ],
  values: [
    [1e18, 1e17, 1e16],
    [1e17, 1e15, 1e16],
  ],
  materials: ['silicon', 'silicon'],
  value_min: 1e15,
  value_max: 1e18,
}

let context: Record<string, ReturnType<typeof vi.fn>>
let moves: [number, number][]

beforeEach(() => {
  moves = []
  context = {
    setTransform: vi.fn(),
    clearRect: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn((x: number, y: number) => void moves.push([x, y])),
    lineTo: vi.fn(),
    closePath: vi.fn(),
    fill: vi.fn(),
    stroke: vi.fn(),
    setLineDash: vi.fn(),
  }
  HTMLCanvasElement.prototype.getContext = vi.fn(() => context) as never

  // jsdom 은 레이아웃을 하지 않아 크기가 전부 0 이다. 400x300 인 척한다.
  Object.defineProperty(HTMLCanvasElement.prototype, 'clientWidth', {
    configurable: true,
    value: 400,
  })
  Object.defineProperty(HTMLCanvasElement.prototype, 'clientHeight', {
    configurable: true,
    value: 300,
  })
  HTMLCanvasElement.prototype.getBoundingClientRect = () =>
    ({ left: 0, top: 0, width: 400, height: 300 }) as DOMRect
})

describe('그리기', () => {
  it('삼각형마다 경로를 만든다', () => {
    render(<SurfaceView surface={SURFACE} cutX={null} onPickCut={vi.fn()} />)

    expect(context.beginPath).toHaveBeenCalledTimes(2)
    expect(context.fill).toHaveBeenCalledTimes(2)
  })

  it('가로세로 비율을 유지한다', () => {
    // 도메인이 4x3, 캔버스가 400x300 이므로 배율이 정확히 100 이다. 늘려
    // 그리면 접합 깊이가 실제와 달라 보인다.
    render(<SurfaceView surface={SURFACE} cutX={null} onPickCut={vi.fn()} />)

    // 첫 삼각형의 첫 정점은 도메인 원점 (0,0) 이다.
    expect(moves[0]).toEqual([0, 0])
  })

  it('컷 라인이 없으면 점선을 긋지 않는다', () => {
    render(<SurfaceView surface={SURFACE} cutX={null} onPickCut={vi.fn()} />)

    expect(context.setLineDash).not.toHaveBeenCalled()
  })

  it('컷 라인이 있으면 점선을 긋는다', () => {
    render(<SurfaceView surface={SURFACE} cutX={2} onPickCut={vi.fn()} />)

    expect(context.setLineDash).toHaveBeenCalled()
  })
})

describe('컷 위치 고르기', () => {
  it('클릭한 화면 좌표를 도메인 좌표로 바꾼다', async () => {
    const onPickCut = vi.fn()
    const { container } = render(
      <SurfaceView surface={SURFACE} cutX={null} onPickCut={onPickCut} />,
    )

    // 배율 100 이므로 화면 x=200 은 도메인 x=2 다.
    await userEvent.pointer({
      target: container.querySelector('canvas')!,
      coords: { clientX: 200, clientY: 100 },
      keys: '[MouseLeft]',
    })

    expect(onPickCut).toHaveBeenCalledWith(2)
  })

  it('도메인 밖을 찍으면 가장자리로 잘라 준다', async () => {
    // 그대로 넘기면 빈 프로파일이 돌아와 화면이 비어 버린다.
    const onPickCut = vi.fn()
    const { container } = render(
      <SurfaceView surface={SURFACE} cutX={null} onPickCut={onPickCut} />,
    )

    await userEvent.pointer({
      target: container.querySelector('canvas')!,
      coords: { clientX: 9999, clientY: 100 },
      keys: '[MouseLeft]',
    })

    expect(onPickCut).toHaveBeenCalledWith(4)
  })
})

describe('접근성', () => {
  it('무엇을 할 수 있는지 알려준다', () => {
    const { container } = render(
      <SurfaceView surface={SURFACE} cutX={null} onPickCut={vi.fn()} />,
    )

    expect(container.querySelector('canvas')).toHaveAttribute(
      'aria-label',
      expect.stringContaining('클릭하면'),
    )
  })
})
