/**
 * 깊이 프로파일 차트.
 *
 * 세로축이 로그다. 도핑 농도는 1e14~1e21 로 7제곱을 오가므로 선형 축이면 가장
 * 큰 값 하나만 보인다.
 *
 * 시각 채널을 둘로 나눈 것이 이 차트의 핵심이다:
 *     선 색   = 물리량
 *     배경 띠 = 재질
 * 재질을 선 색으로 쓰면 물리량에 쓸 색이 남지 않는다.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ProfileChart, type Series } from './ProfileChart'

const point = (depth: number, value: number, material = 'silicon') => ({
  depth,
  value,
  material,
})

const LAYERED = [
  point(-0.075, 2.45e15, 'oxide'),
  point(0, 1.14e19, 'oxide'),
  point(0, 5.86e18, 'silicon'),
  point(2, 1e15, 'silicon'),
]

function series(overrides: Partial<Series> = {}): Series {
  return {
    label: 'chem_boron',
    color: '#4a9eff',
    points: [point(0, 1e18), point(1, 1e15)],
    ...overrides,
  }
}

function polylines(container: HTMLElement) {
  return [...container.querySelectorAll('polyline')]
}

function bands(container: HTMLElement) {
  // clipPath 안에도 rect 가 있다. 재질 띠만 골라야 한다.
  return [...container.querySelectorAll('svg rect.band-fill')]
}

function pointsOf(polyline: SVGPolylineElement) {
  return (polyline.getAttribute('points') ?? '')
    .split(' ')
    .filter(Boolean)
    .map((pair) => pair.split(',').map(Number) as [number, number])
}

describe('빈 데이터', () => {
  it('그릴 것이 없다고 말한다', () => {
    render(<ProfileChart series={[series({ points: [] })]} />)

    expect(screen.getByText(/데이터가 없습니다/)).toBeInTheDocument()
  })
})

describe('축', () => {
  it('물리량 이름을 접근성 레이블에 담는다', () => {
    render(<ProfileChart series={[series()]} />)

    expect(screen.getByRole('img', { name: /chem_boron/ })).toBeInTheDocument()
  })

  it('값이 클수록 위에 놓는다', () => {
    // SVG 의 y 는 아래로 갈수록 커진다. 뒤집으면 농도가 거꾸로 그려진다.
    const { container } = render(<ProfileChart series={[series()]} />)
    const [high, low] = pointsOf(polylines(container)[0]!)

    expect(high![1]).toBeLessThan(low![1])
  })

  it('깊이가 클수록 오른쪽에 놓는다', () => {
    const { container } = render(<ProfileChart series={[series()]} />)
    const [shallow, deep] = pointsOf(polylines(container)[0]!)

    expect(shallow![0]).toBeLessThan(deep![0])
  })

  it('깊이 눈금 숫자를 붙인다', () => {
    // 이게 없으면 접합 깊이를 읽을 수 없다 — 가장 먼저 보는 숫자다.
    render(
      <ProfileChart
        series={[series({ points: [point(0, 1e18), point(2, 1e15)] })]}
      />,
    )

    expect(screen.getByText('0.0')).toBeInTheDocument()
    expect(screen.getByText('2.0')).toBeInTheDocument()
  })

  it('10의 거듭제곱 눈금을 붙인다', () => {
    render(
      <ProfileChart
        series={[series({ points: [point(0, 1e15), point(1, 1e18)] })]}
      />,
    )

    expect(screen.getByText('1e15')).toBeInTheDocument()
    expect(screen.getByText('1e18')).toBeInTheDocument()
  })
})

describe('재질 배경 띠', () => {
  it('재질마다 띠를 그린다', () => {
    const { container } = render(
      <ProfileChart series={[series({ points: LAYERED })]} />,
    )

    expect(bands(container)).toHaveLength(2)
  })

  it('띠마다 재질 이름을 붙인다', () => {
    const { container } = render(
      <ProfileChart series={[series({ points: LAYERED })]} />,
    )
    const titles = bands(container).map(
      (rect) => rect.querySelector('title')?.textContent,
    )

    expect(titles).toEqual(['oxide', 'silicon'])
  })

  it('범례에도 재질을 적는다', () => {
    // 띠의 <title> 에도 같은 이름이 있으므로 범례 안에서만 찾는다.
    const { container } = render(
      <ProfileChart series={[series({ points: LAYERED })]} />,
    )
    const legend = container.querySelector('.legend.materials')

    expect(legend).toHaveTextContent('oxide')
    expect(legend).toHaveTextContent('silicon')
  })
})

describe('재질 경계', () => {
  it('경계마다 구분선을 긋는다', () => {
    // 색만으로는 어두운 배경에서 아슬아슬하다(현재 팔레트 최소 ΔE 3.8, 감지
    // 한계 수준). 선을 그으면 색과 무관하게 경계가 보인다.
    const { container } = render(
      <ProfileChart series={[series({ points: LAYERED })]} />,
    )

    expect(container.querySelectorAll('.material-edge')).toHaveLength(1)
  })

  it('재질이 하나면 구분선이 없다', () => {
    const { container } = render(<ProfileChart series={[series()]} />)

    expect(container.querySelectorAll('.material-edge')).toHaveLength(0)
  })

  it('띠 위에 재질 이름을 적는다', () => {
    // 범례를 오가며 색을 맞춰 보지 않아도 되게. 색맹이어도 읽힌다.
    const { container } = render(
      <ProfileChart series={[series({ points: LAYERED })]} />,
    )
    const labels = [...container.querySelectorAll('.band-label')].map(
      (node) => node.textContent,
    )

    expect(labels).toEqual(['oxide', 'silicon'])
  })
})

describe('선 색은 물리량', () => {
  it('물리량마다 자기 색을 쓴다', () => {
    const { container } = render(
      <ProfileChart
        series={[
          series({ label: 'chem_boron', color: '#4a9eff' }),
          series({ label: 'active_boron', color: '#a55eea' }),
        ]}
      />,
    )
    const strokes = new Set(
      polylines(container).map((line) => line.getAttribute('stroke')),
    )

    expect(strokes).toEqual(new Set(['#4a9eff', '#a55eea']))
  })

  it('재질이 달라도 한 물리량은 한 색이다', () => {
    // 재질은 배경이 맡는다. 선 색까지 나누면 물리량 구분이 무너진다.
    const { container } = render(
      <ProfileChart series={[series({ points: LAYERED })]} />,
    )
    const strokes = new Set(
      polylines(container).map((line) => line.getAttribute('stroke')),
    )

    expect(polylines(container).length).toBeGreaterThan(1) // 계면에서 끊긴다
    expect(strokes.size).toBe(1) // 그래도 색은 하나
  })

  it('범례에 물리량 이름을 적는다', () => {
    render(
      <ProfileChart
        series={[series({ label: 'chem_boron' }), series({ label: 'net_doping' })]}
      />,
    )

    expect(screen.getByText('chem_boron')).toBeInTheDocument()
    expect(screen.getByText('net_doping')).toBeInTheDocument()
  })

  it('축이 모든 선을 담는다', () => {
    // 하나만 보고 축을 잡으면 나머지가 화면 밖으로 나간다.
    render(
      <ProfileChart
        series={[
          series({ points: [point(0, 1e15), point(1, 1e16)] }),
          series({ label: 'other', points: [point(0, 1e19), point(1, 1e20)] }),
        ]}
      />,
    )

    expect(screen.getByText('1e19')).toBeInTheDocument()
  })
})

describe('계면에서 선 끊기', () => {
  it('재질이 바뀌면 선을 끊는다', () => {
    // 이어 그리면 계면에서 수직으로 뚝 떨어지는 가짜 선이 생긴다.
    const { container } = render(
      <ProfileChart series={[series({ points: LAYERED })]} />,
    )

    expect(polylines(container)).toHaveLength(2)
  })
})

describe('증착층', () => {
  it('표면선을 그어 음수 깊이를 구분한다', () => {
    const { container } = render(
      <ProfileChart series={[series({ points: LAYERED })]} />,
    )

    expect(container.querySelector('.surface-line')).toBeInTheDocument()
  })

  it('증착층이 없으면 표면선도 없다', () => {
    const { container } = render(<ProfileChart series={[series()]} />)

    expect(container.querySelector('.surface-line')).not.toBeInTheDocument()
  })
})

describe('부호 있는 값', () => {
  it('전부 음수여도 그린다', () => {
    // 보론만 주입한 구조의 net_doping 은 전부 음수다(실측).
    const { container } = render(
      <ProfileChart
        series={[
          series({
            label: 'net_doping',
            points: [point(0, -1e18), point(1, -1e15)],
          }),
        ]}
      />,
    )
    const coordinates = pointsOf(polylines(container)[0]!)

    expect(coordinates).toHaveLength(2)
    expect(
      coordinates.every(([x, y]) => Number.isFinite(x) && Number.isFinite(y)),
    ).toBe(true)
  })

  it('음수 구간을 점선으로 구분한다', () => {
    // 부호가 바뀌는 자리가 곧 접합이다.
    const { container } = render(
      <ProfileChart
        series={[
          series({
            label: 'net_doping',
            points: [point(0, 1e18), point(1, -1e16)],
          }),
        ]}
      />,
    )
    const dashes = polylines(container).map((line) =>
      line.getAttribute('stroke-dasharray'),
    )

    expect(dashes.filter(Boolean)).toHaveLength(1)
  })

  it('음수가 있으면 읽는 법을 알린다', () => {
    render(
      <ProfileChart
        series={[
          series({
            label: 'net_doping',
            points: [point(0, 1e18), point(1, -1e16)],
          }),
        ]}
      />,
    )

    expect(screen.getByText(/점선 = 음수/)).toBeInTheDocument()
  })

  it('전부 양수면 알리지 않는다', () => {
    render(<ProfileChart series={[series()]} />)

    expect(screen.queryByText(/점선 = 음수/)).not.toBeInTheDocument()
  })
})

describe('단계 비교선', () => {
  it('흐리게 그려 기준선과 구분한다', () => {
    const { container } = render(
      <ProfileChart
        series={[
          series(),
          series({ label: 'before', color: '#ff9f43', muted: true }),
        ]}
      />,
    )
    const muted = polylines(container).find(
      (line) => line.getAttribute('stroke') === '#ff9f43',
    )

    expect(Number(muted?.getAttribute('stroke-opacity'))).toBeLessThan(1)
  })
})

describe('균일 도핑', () => {
  it('값이 모두 같아도 그린다', () => {
    // 정의역이 한 점이면 축 계산이 0 으로 나눠질 수 있다.
    const { container } = render(
      <ProfileChart
        series={[
          series({ points: [point(0, 1e15), point(1, 1e15), point(2, 1e15)] }),
        ]}
      />,
    )
    const coordinates = pointsOf(polylines(container)[0]!)

    expect(coordinates).toHaveLength(3)
    expect(
      coordinates.every(([x, y]) => Number.isFinite(x) && Number.isFinite(y)),
    ).toBe(true)
  })
})

describe('가로축 확대·축소', () => {
  const WIDE = [
    point(0, 1e20),
    point(0.05, 1e19),
    point(0.1, 1e18),
    point(5, 1e15),
  ]

  function svgOf(container: HTMLElement) {
    const svg = container.querySelector('svg')!
    // jsdom 은 레이아웃을 하지 않아 크기가 0 이다. 640x380 인 척한다.
    svg.getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: 640, height: 380 }) as DOMRect
    return svg
  }

  function depthLabels(container: HTMLElement) {
    return [...container.querySelectorAll('.tick')]
      .map((node) => node.textContent!)
      .filter((text) => !text.startsWith('1e'))
  }

  it('처음에는 전체를 보여준다', () => {
    const { container } = render(<ProfileChart series={[series({ points: WIDE })]} />)

    expect(depthLabels(container).map(Number)).toContain(5)
  })

  it('휠을 굴리면 범위가 좁아진다', () => {
    const { container } = render(<ProfileChart series={[series({ points: WIDE })]} />)
    const before = Math.max(...depthLabels(container).map(Number))

    fireEvent.wheel(svgOf(container), { deltaY: -100, clientX: 100 })

    expect(Math.max(...depthLabels(container).map(Number))).toBeLessThan(before)
  })

  it('반대로 굴리면 다시 넓어진다', () => {
    const { container } = render(<ProfileChart series={[series({ points: WIDE })]} />)
    const svg = svgOf(container)
    fireEvent.wheel(svg, { deltaY: -100, clientX: 100 })
    const zoomed = Math.max(...depthLabels(container).map(Number))

    fireEvent.wheel(svg, { deltaY: 100, clientX: 100 })

    expect(Math.max(...depthLabels(container).map(Number))).toBeGreaterThan(zoomed)
  })

  it('확대하면 되돌리기 버튼이 나온다', () => {
    const { container } = render(<ProfileChart series={[series({ points: WIDE })]} />)

    fireEvent.wheel(svgOf(container), { deltaY: -100, clientX: 100 })

    expect(screen.getByRole('button', { name: /전체 보기/ })).toBeInTheDocument()
  })

  it('전체를 보고 있으면 되돌리기 버튼이 없다', () => {
    render(<ProfileChart series={[series({ points: WIDE })]} />)

    expect(screen.queryByRole('button', { name: /전체 보기/ })).not.toBeInTheDocument()
  })

  it('되돌리면 전체가 다시 보인다', () => {
    const { container } = render(<ProfileChart series={[series({ points: WIDE })]} />)
    fireEvent.wheel(svgOf(container), { deltaY: -100, clientX: 100 })

    fireEvent.click(screen.getByRole('button', { name: /전체 보기/ }))

    expect(depthLabels(container).map(Number)).toContain(5)
  })

  it('확대해도 세로 눈금은 그대로다', () => {
    // 단계를 오갈 때 높이를 비교할 수 없게 된다.
    const { container } = render(<ProfileChart series={[series({ points: WIDE })]} />)
    const before = [...container.querySelectorAll('.tick')]
      .map((n) => n.textContent!)
      .filter((t) => t.startsWith('1e'))

    fireEvent.wheel(svgOf(container), { deltaY: -100, clientX: 100 })

    const after = [...container.querySelectorAll('.tick')]
      .map((n) => n.textContent!)
      .filter((t) => t.startsWith('1e'))
    expect(after).toEqual(before)
  })

  it('그림이 축 밖으로 넘치지 않는다', () => {
    // 확대하면 범위 밖 점들이 좌우로 밀려난다. 잘라내지 않으면 눈금과 범례
    // 위에까지 선이 그려진다.
    const { container } = render(<ProfileChart series={[series({ points: WIDE })]} />)

    fireEvent.wheel(svgOf(container), { deltaY: -100, clientX: 100 })

    expect(container.querySelector('clipPath')).toBeInTheDocument()
  })

  it('그래프 위에서는 페이지가 스크롤되지 않는다', () => {
    // 확대와 바깥 스크롤이 겹치면 그래프를 키우려다 화면이 같이 밀린다.
    // React 의 onWheel 은 루트에 passive 로 붙어 preventDefault 가 먹지
    // 않는다 — 네이티브 리스너를 passive:false 로 달아야 한다.
    const { container } = render(<ProfileChart series={[series({ points: WIDE })]} />)
    const svg = svgOf(container)

    const event = new WheelEvent('wheel', {
      deltaY: -100,
      clientX: 100,
      bubbles: true,
      cancelable: true,
    })
    svg.dispatchEvent(event)

    expect(event.defaultPrevented).toBe(true)
  })

  it('빈 상태로 떴다가 데이터가 와도 휠이 걸린다', () => {
    // 결과를 받기 전에는 그릴 것이 없어 일찍 반환한다. 그 시점에 리스너를
    // 달려고 하면 노드가 없어 영영 안 붙는다 — 실제로 그렇게 깨졌고 단위
    // 테스트가 처음부터 데이터를 주는 바람에 E2E 에서야 드러났다.
    const { container, rerender } = render(
      <ProfileChart series={[series({ points: [] })]} />,
    )

    rerender(<ProfileChart series={[series({ points: WIDE })]} />)

    const svg = svgOf(container)
    const event = new WheelEvent('wheel', {
      deltaY: -100,
      clientX: 100,
      bubbles: true,
      cancelable: true,
    })
    svg.dispatchEvent(event)

    expect(event.defaultPrevented).toBe(true)

    // 축이 실제로 좁아지는지는 fireEvent 로 본다. raw dispatchEvent 는
    // act() 로 감싸이지 않아 상태 갱신이 반영되기 전에 읽게 된다.
    fireEvent.wheel(svg, { deltaY: -100, clientX: 100 })
    expect(Math.max(...depthLabels(container).map(Number))).toBeLessThan(5)
  })

  it('확대 한계에 닿아도 페이지로 새어 나가지 않는다', () => {
    // 더 확대할 수 없다고 스크롤이 뚫리면 화면이 튄다.
    const { container } = render(<ProfileChart series={[series({ points: WIDE })]} />)
    const svg = svgOf(container)
    for (let i = 0; i < 60; i += 1) {
      fireEvent.wheel(svg, { deltaY: -100, clientX: 100 })
    }

    const event = new WheelEvent('wheel', {
      deltaY: -100,
      clientX: 100,
      bubbles: true,
      cancelable: true,
    })
    svg.dispatchEvent(event)

    expect(event.defaultPrevented).toBe(true)
  })

  it('값만 바뀌면 확대를 유지한다', () => {
    // 2D 에서 컷 위치를 옮기면 같은 깊이 범위의 새 값이 온다. 확대가 풀리면
    // 컷을 옮길 때마다 다시 확대해야 한다.
    const { container, rerender } = render(
      <ProfileChart series={[series({ points: WIDE })]} />,
    )
    fireEvent.wheel(svgOf(container), { deltaY: -100, clientX: 100 })
    const zoomed = Math.max(...depthLabels(container).map(Number))

    rerender(
      <ProfileChart
        series={[
          series({
            points: WIDE.map((p) => ({ ...p, value: p.value * 2 })),
          }),
        ]}
      />,
    )

    expect(Math.max(...depthLabels(container).map(Number))).toBeCloseTo(zoomed, 6)
    expect(screen.getByRole('button', { name: /전체 보기/ })).toBeInTheDocument()
  })

  it('깊이 범위가 좁아지면 그 안으로 밀어 넣는다', () => {
    // 확대 구간이 새 데이터 밖에 있으면 빈 화면이 뜬다.
    const { container, rerender } = render(
      <ProfileChart series={[series({ points: WIDE })]} />,
    )
    // 오른쪽 끝(깊은 쪽)으로 확대해 둔다.
    const svg = svgOf(container)
    for (let i = 0; i < 6; i += 1) {
      fireEvent.wheel(svg, { deltaY: -100, clientX: 600 })
    }

    rerender(
      <ProfileChart
        series={[series({ points: [point(0, 1e18), point(0.2, 1e15)] })]}
      />,
    )

    const labels = depthLabels(container).map(Number)
    expect(Math.max(...labels)).toBeLessThanOrEqual(0.2)
    expect(labels.length).toBeGreaterThan(1)
  })
})
