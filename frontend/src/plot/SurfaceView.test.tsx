/**
 * 2D 단면.
 *
 * jsdom 에는 캔버스가 없다. 컨텍스트를 흉내 내어 **무엇을 그리라고 시켰는지**를
 * 확인한다. 정확한 좌표 계산은 surfaceGeometry.test.ts 가 따로 검증하므로
 * 여기서는 배선(삼각형·눈금·컷 선)과 클릭 전달만 본다.
 */
import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SurfaceView } from './SurfaceView'
import type { SurfaceResponse } from '../api/types'
import { solidOf } from './materials'
import { MESH_COLOR } from './SurfaceView'
import { subdivisionDepth } from './shading'
import { colorFor } from './scale'

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
let texts: string[]
let fills: string[]
let strokes: string[]

beforeEach(() => {
  texts = []
  fills = []
  strokes = []
  context = {
    setTransform: vi.fn(),
    clearRect: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    closePath: vi.fn(),
    fill: vi.fn(),
    stroke: vi.fn(),
    setLineDash: vi.fn(),
    fillText: vi.fn((text: string) => void texts.push(text)),
    save: vi.fn(),
    restore: vi.fn(),
    translate: vi.fn(),
    rotate: vi.fn(),
    fillRect: vi.fn(),
    // 범례 판 크기를 글자 폭으로 정한다.
    measureText: vi.fn((text: string) => ({ width: text.length * 5 })),
  }
  // fillStyle 은 메서드가 아니라 속성이다. 대입을 가로채야 어떤 색으로
  // 칠했는지 볼 수 있다.
  Object.defineProperty(context, 'fillStyle', {
    configurable: true,
    set: (value: string) => void fills.push(value),
    get: () => '',
  })
  Object.defineProperty(context, 'strokeStyle', {
    configurable: true,
    set: (value: string) => void strokes.push(value),
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
  HTMLCanvasElement.prototype.getBoundingClientRect = () =>
    ({ left: 0, top: 0, width: 400, height: 300 }) as DOMRect
})

describe('그리기', () => {
  it('삼각형을 잘게 나눠 칠한다', () => {
    // 단색으로 칠하면 격자가 성긴 곳에서 삼각형 무늬가 그대로 드러나,
    // 데이터에 없는 조각남을 만들어 낸다. 나눈 만큼 fill 이 늘어난다.
    render(<SurfaceView surface={SURFACE} cutX={null} onPickCut={vi.fn()} />)

    const shards = 4 ** subdivisionDepth(SURFACE.triangles.length)
    expect(context.fill).toHaveBeenCalledTimes(2 * shards)
    expect(shards).toBeGreaterThan(1)
  })

  it('도핑된 정점 하나로 삼각형 전체를 물들이지 않는다', () => {
    // 산술평균이면 (1e5+1e5+1e20)/3 = 3.3e19 로 사실상 최댓값이 된다.
    // 실측: 그 탓에 증착 산화막의 저농도 영역이 통째로 메워져 사라졌다.
    const spike: SurfaceResponse = {
      ...SURFACE,
      x: [0, 4, 0],
      y: [0, 0, 3],
      triangles: [[0, 1, 2]],
      values: [[1e5, 1e5, 1e20]],
      materials: ['oxide'],
      value_min: 1e5,
      value_max: 1e20,
    }

    render(<SurfaceView surface={spike} cutX={null} onPickCut={vi.fn()} />)

    const hottest = colorFor(1e20, 1e5, 1e20)
    const painted = fills.filter((c) => c === hottest).length
    const shards = 4 ** subdivisionDepth(1)
    // 최고 농도 색은 그 꼭짓점 근처 몇 조각에만 나와야 한다.
    expect(painted).toBeLessThan(shards / 2)
  })

  it('가로 눈금 숫자를 찍는다', () => {
    // 이게 없으면 소자 폭이 몇 µm 인지 그림에서 읽을 수 없다.
    render(<SurfaceView surface={SURFACE} cutX={null} onPickCut={vi.fn()} />)

    // 1µm 간격이라 소수점이 붙지 않는다. 간격이 좁아지면 자릿수가 늘어난다.
    expect(texts).toContain('0')
    expect(texts).toContain('4')
  })

  it('세로 눈금 숫자를 찍는다', () => {
    render(<SurfaceView surface={SURFACE} cutX={null} onPickCut={vi.fn()} />)

    expect(texts).toContain('3')
  })

  it('어느 축이 무엇인지 적는다', () => {
    // 둘 다 µm 라 숫자만 보면 가로가 폭인지 깊이인지 알 수 없다.
    render(<SurfaceView surface={SURFACE} cutX={null} onPickCut={vi.fn()} />)

    expect(texts).toContain('x (µm)')
    expect(texts).toContain('깊이 (µm)')
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

    await userEvent.pointer({
      target: container.querySelector('canvas')!,
      coords: { clientX: 200, clientY: 100 },
      keys: '[MouseLeft]',
    })

    // 정확한 값은 여백에 달렸다(surfaceGeometry 가 검증한다). 여기서 볼 것은
    // 화면 가운데쯤을 찍으면 도메인 안쪽 값이 넘어간다는 배선이다.
    const [picked] = onPickCut.mock.calls[0]!
    expect(picked).toBeGreaterThan(0)
    expect(picked).toBeLessThan(4)
  })

  it('왼쪽 끝을 찍으면 도메인 시작이다', async () => {
    const onPickCut = vi.fn()
    const { container } = render(
      <SurfaceView surface={SURFACE} cutX={null} onPickCut={onPickCut} />,
    )

    await userEvent.pointer({
      target: container.querySelector('canvas')!,
      coords: { clientX: 0, clientY: 100 },
      keys: '[MouseLeft]',
    })

    expect(onPickCut).toHaveBeenCalledWith(0)
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

describe('재질 보기', () => {
  /** quantity 가 빈 문자열이고 values 가 없으면 재질만 온 것이다. */
  const BY_MATERIAL: SurfaceResponse = {
    ...SURFACE,
    quantity: '',
    values: [],
    materials: ['oxide', 'silicon'],
  }

  it('값이 없어도 삼각형을 그린다', () => {
    // 값 기준으로 색을 고르려 들면 여기서 터지거나 아무것도 안 그린다.
    render(<SurfaceView surface={BY_MATERIAL} cutX={null} onPickCut={vi.fn()} />)

    // 재질 보기는 삼각형 안에서 색이 변하지 않으므로 나눌 이유가 없다.
    expect(context.fill).toHaveBeenCalledTimes(2)
  })

  it('재질마다 자기 색을 쓴다', () => {
    // fills 에는 축 라벨 색도 섞인다. 재질 색이 들어 있는지를 직접 본다.
    render(<SurfaceView surface={BY_MATERIAL} cutX={null} onPickCut={vi.fn()} />)

    expect(solidOf('oxide')).not.toBe(solidOf('silicon'))
    expect(fills).toContain(solidOf('oxide'))
    expect(fills).toContain(solidOf('silicon'))
  })

  it('1D 배경 띠와 같은 재질 체계를 쓴다', () => {
    // 두 화면에서 oxide 색이 다르면 같은 층인지 알아보지 못한다.
    expect(solidOf('oxide')).toBeTruthy()
    expect(solidOf('알수없는재질')).toBe(solidOf('또다른미지재질'))
  })

  it('오른쪽 위에 범례를 넣는다', () => {
    // 색만 칠하면 무엇이 무엇인지 알 수 없다.
    render(<SurfaceView surface={BY_MATERIAL} cutX={null} onPickCut={vi.fn()} />)

    expect(texts).toContain('oxide')
    expect(texts).toContain('silicon')
  })

  it('범례 뒤에 판을 깐다', () => {
    // 배경 없이 얹으면 구조 위에 겹친 글자가 묻힌다 — 회색 글씨가 amber
    // 산화막 위에 놓여 첫 글자가 사라졌다(실측).
    render(<SurfaceView surface={BY_MATERIAL} cutX={null} onPickCut={vi.fn()} />)

    // 색 견본 2개 + 판 1개.
    expect(context.fillRect).toHaveBeenCalledTimes(3)
  })

  it('범례에 재질을 한 번씩만 적는다', () => {
    // 삼각형마다 적으면 수천 줄이 겹쳐 찍힌다.
    render(<SurfaceView surface={BY_MATERIAL} cutX={null} onPickCut={vi.fn()} />)

    expect(texts.filter((t) => t === 'silicon')).toHaveLength(1)
  })

  it('물리량 보기에는 범례를 넣지 않는다', () => {
    // 그쪽은 색이 값을 뜻한다. 재질 범례를 붙이면 거짓말이 된다.
    render(<SurfaceView surface={SURFACE} cutX={null} onPickCut={vi.fn()} />)

    expect(texts).not.toContain('silicon')
  })

  it('축 눈금은 그대로 나온다', () => {
    render(<SurfaceView surface={BY_MATERIAL} cutX={null} onPickCut={vi.fn()} />)

    expect(texts).toContain('x (µm)')
    expect(texts).toContain('깊이 (µm)')
  })
})


describe('격자 보기', () => {
  it('꺼 두면 격자선을 그리지 않는다', () => {
    // 기본은 꺼짐이다. 촘촘한 메시를 항상 얹으면 정작 값이 안 보인다.
    render(<SurfaceView surface={SURFACE} cutX={null} onPickCut={vi.fn()} />)

    expect(strokes).not.toContain(MESH_COLOR)
  })

  it('켜면 격자선을 그린다', () => {
    render(
      <SurfaceView surface={SURFACE} cutX={null} onPickCut={vi.fn()} showMesh />,
    )

    expect(strokes).toContain(MESH_COLOR)
  })

  it('체크만 바꿔도 다시 그린다', () => {
    // 매번 새로 렌더하는 테스트는 이걸 못 잡는다. 실제 화면에서는 컴포넌트가
    // 살아 있는 채로 prop 만 바뀌므로, 그리기 effect 가 showMesh 를 의존성에
    // 넣지 않으면 체크박스를 눌러도 아무 일도 일어나지 않는다(E2E 가 잡았다).
    const view = render(
      <SurfaceView surface={SURFACE} cutX={null} onPickCut={vi.fn()} />,
    )
    expect(strokes).not.toContain(MESH_COLOR)

    view.rerender(
      <SurfaceView surface={SURFACE} cutX={null} onPickCut={vi.fn()} showMesh />,
    )

    expect(strokes).toContain(MESH_COLOR)
  })

  it('삼각형을 다 칠한 뒤에 얹는다', () => {
    // 먼저 그리면 삼각형 색에 덮여 아무것도 안 보인다.
    const order: string[] = []
    context.fill = vi.fn(() => void order.push('fill'))
    context.stroke = vi.fn(() => void order.push('stroke'))
    Object.defineProperty(context, 'strokeStyle', {
      configurable: true,
      set: (value: string) => {
        strokes.push(value)
        if (value === MESH_COLOR) order.push('mesh')
      },
      get: () => '',
    })

    render(
      <SurfaceView surface={SURFACE} cutX={null} onPickCut={vi.fn()} showMesh />,
    )

    // 마지막 삼각형 칠하기가 격자선보다 앞에 있어야 한다.
    expect(order.lastIndexOf('fill')).toBeLessThan(order.indexOf('mesh'))
  })

  it('격자선을 한 번에 그린다', () => {
    // 삼각형마다 stroke 를 부르면 겹친 변이 두 번 칠해져 얼룩덜룩해지고,
    // 수천 개에서는 느려진다. 경로 하나로 모아 한 번만 그린다.
    const plain = render(
      <SurfaceView surface={SURFACE} cutX={null} onPickCut={vi.fn()} />,
    )
    const without = context.stroke.mock.calls.length
    plain.unmount()
    context.stroke.mockClear()

    render(
      <SurfaceView surface={SURFACE} cutX={null} onPickCut={vi.fn()} showMesh />,
    )

    expect(context.stroke.mock.calls.length).toBe(without + 1)
  })
})
