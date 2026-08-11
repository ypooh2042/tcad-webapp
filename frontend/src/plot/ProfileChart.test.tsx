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
import { render, screen } from '@testing-library/react'
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
  return [...container.querySelectorAll('svg rect')]
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
