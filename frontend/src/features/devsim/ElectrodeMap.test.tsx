/**
 * 단면은 **구조가 바뀔 때만** 다시 칠한다.
 *
 * 삼각형이 nmos 8,813개, cmos 16,248개다. 커서를 계면 위로 옮길 때마다,
 * 전압을 한 글자 칠 때마다 그걸 다시 칠하면 손에 걸린다. 삼각형은 미리 그려
 * 두고 얹기만 하고, 전극 선과 어둡게 덮는 것만 매번 그린다.
 *
 * jsdom 은 캔버스를 그리지 않으므로 컨텍스트를 가로채 호출 횟수로 본다.
 */
import { render } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { DevSimInterface, SurfaceResponse } from '../../api/types'
import { ElectrodeMap } from './ElectrodeMap'

const SURFACE: SurfaceResponse = {
  quantity: '',
  x: [0, 1, 1, 0],
  y: [0, 0, 1, 1],
  triangles: [
    [0, 1, 2],
    [0, 2, 3],
  ],
  values: [],
  materials: ['silicon', 'silicon'],
  value_min: 0,
  value_max: 0,
}

const INTERFACES: DevSimInterface[] = [
  {
    key: 'source',
    origin: 'metal',
    kind: 'semiconductor',
    materials: ['silicon'],
    extent: { x_min: 0, x_max: 0.3, y_min: 0, y_max: 0 },
    edge_count: 1,
    segments: [[0, 0, 0.3, 0]],
  },
  {
    key: 'body',
    origin: 'backside',
    kind: 'semiconductor',
    materials: ['silicon'],
    extent: { x_min: 0, x_max: 1, y_min: 1, y_max: 1 },
    edge_count: 1,
    segments: [[0, 1, 1, 1]],
  },
]

let fills: number
let drawImages: number
let strokes: number

function stubCanvas() {
  fills = 0
  drawImages = 0
  strokes = 0
  const context = {
    clearRect: vi.fn(),
    setTransform: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    closePath: vi.fn(),
    fill: vi.fn(() => void fills++),
    stroke: vi.fn(() => void strokes++),
    fillRect: vi.fn(),
    fillText: vi.fn(),
    measureText: vi.fn((text: string) => ({ width: text.length * 6 })),
    drawImage: vi.fn(() => void drawImages++),
    setLineDash: vi.fn(),
  }
  Object.defineProperty(context, 'fillStyle', {
    configurable: true,
    set: () => undefined,
    get: () => '',
  })
  Object.defineProperty(context, 'strokeStyle', {
    configurable: true,
    set: () => undefined,
    get: () => '',
  })
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
}

function view(overrides: Partial<React.ComponentProps<typeof ElectrodeMap>> = {}) {
  return (
    <ElectrodeMap
      surface={SURFACE}
      interfaces={INTERFACES}
      owners={{ source: 'S' }}
      electrodes={[{ label: 'S', color: '#fff' }]}
      onAssign={vi.fn()}
      onUnassign={vi.fn()}
      onCreate={vi.fn()}
      nameOf={(key) => key}
      onRename={vi.fn()}
      {...overrides}
    />
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  stubCanvas()
})

describe('단면 다시 그리기', () => {
  it('처음에는 삼각형을 칠한다', () => {
    render(view())
    expect(fills).toBeGreaterThanOrEqual(SURFACE.triangles.length)
  })

  it('전극 배치가 바뀌어도 삼각형을 다시 칠하지 않는다', () => {
    // 계면을 다른 전극에 붙이면 선 색만 바뀐다. 구조는 그대로다.
    const { rerender } = render(view())
    const painted = fills

    rerender(view({ owners: { source: 'S', body: 'S' } }))

    expect(fills).toBe(painted)
    // 대신 미리 그려 둔 층을 얹는다.
    expect(drawImages).toBeGreaterThan(0)
  })

  it('이름이 바뀌어도 삼각형을 다시 칠하지 않는다', () => {
    const { rerender } = render(view())
    const painted = fills
    rerender(view({ nameOf: (key) => `${key} 접촉` }))
    expect(fills).toBe(painted)
  })

  it('전극 선은 매번 다시 긋는다', () => {
    // 색과 굵기가 바뀌므로 이건 다시 그려야 한다.
    const { rerender } = render(view())
    const before = strokes
    rerender(view({ owners: {} }))
    expect(strokes).toBeGreaterThan(before)
  })

  it('구조가 바뀌면 다시 칠한다', () => {
    const { rerender } = render(view())
    const painted = fills
    rerender(view({ surface: { ...SURFACE } }))
    expect(fills).toBeGreaterThan(painted)
  })

  it('크기가 0 이면 아무것도 하지 않는다', () => {
    // 화면이 숨겨져 있을 때 그렇게 된다.
    Object.defineProperty(HTMLCanvasElement.prototype, 'clientWidth', {
      configurable: true,
      value: 0,
    })
    render(view())
    expect(fills).toBe(0)
    expect(drawImages).toBe(0)
  })
})
