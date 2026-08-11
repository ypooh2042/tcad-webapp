/**
 * 깊이 프로파일 차트.
 *
 * 세로축이 로그다. 도핑 농도는 1e14~1e21 로 7제곱을 오가므로 선형 축이면 가장
 * 큰 값 하나만 보인다.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ProfileChart } from './ProfileChart'

const point = (depth: number, value: number, material = 'silicon') => ({
  depth,
  value,
  material,
})

function polylines(container: HTMLElement) {
  return [...container.querySelectorAll('polyline')]
}

function pointsOf(polyline: SVGPolylineElement) {
  return (polyline.getAttribute('points') ?? '')
    .split(' ')
    .filter(Boolean)
    .map((pair) => pair.split(',').map(Number) as [number, number])
}

describe('빈 데이터', () => {
  it('그릴 것이 없다고 말한다', () => {
    render(<ProfileChart points={[]} quantity="chem_boron" />)

    expect(screen.getByText(/데이터가 없습니다/)).toBeInTheDocument()
  })
})

describe('축', () => {
  it('물리량 이름을 접근성 레이블에 담는다', () => {
    render(
      <ProfileChart points={[point(0, 1e18), point(1, 1e15)]} quantity="chem_boron" />,
    )

    expect(screen.getByRole('img', { name: /chem_boron/ })).toBeInTheDocument()
  })

  it('값이 클수록 위에 놓는다', () => {
    // SVG 의 y 는 아래로 갈수록 커진다. 뒤집으면 농도가 거꾸로 그려진다.
    const { container } = render(
      <ProfileChart points={[point(0, 1e18), point(1, 1e15)]} quantity="q" />,
    )
    const [high, low] = pointsOf(polylines(container)[0]!)

    expect(high![1]).toBeLessThan(low![1])
  })

  it('깊이가 클수록 오른쪽에 놓는다', () => {
    const { container } = render(
      <ProfileChart points={[point(0, 1e18), point(1, 1e15)]} quantity="q" />,
    )
    const [shallow, deep] = pointsOf(polylines(container)[0]!)

    expect(shallow![0]).toBeLessThan(deep![0])
  })

  it('10의 거듭제곱 눈금을 붙인다', () => {
    render(
      <ProfileChart points={[point(0, 1e15), point(1, 1e18)]} quantity="q" />,
    )

    expect(screen.getByText('1e15')).toBeInTheDocument()
    expect(screen.getByText('1e18')).toBeInTheDocument()
  })
})

describe('물질 구간', () => {
  it('물질마다 선을 따로 그린다', () => {
    // 이어 그리면 계면에서 수직으로 뚝 떨어지는 가짜 선이 생긴다.
    const { container } = render(
      <ProfileChart
        points={[
          point(-0.075, 2.45e15, 'oxide'),
          point(0, 1.14e19, 'oxide'),
          point(0, 5.86e18, 'silicon'),
          point(0.02, 5.82e18, 'silicon'),
        ]}
        quantity="chem_boron"
      />,
    )

    expect(polylines(container)).toHaveLength(2)
  })

  it('범례에 물질을 적는다', () => {
    render(
      <ProfileChart
        points={[point(0, 1e18, 'oxide'), point(1, 1e15, 'silicon')]}
        quantity="q"
      />,
    )

    expect(screen.getByText('oxide')).toBeInTheDocument()
    expect(screen.getByText('silicon')).toBeInTheDocument()
  })

  it('물질마다 다른 색을 쓴다', () => {
    const { container } = render(
      <ProfileChart
        points={[point(0, 1e18, 'oxide'), point(1, 1e15, 'silicon')]}
        quantity="q"
      />,
    )
    const strokes = polylines(container).map((line) => line.getAttribute('stroke'))

    expect(new Set(strokes).size).toBe(2)
  })
})

describe('증착층', () => {
  it('표면선을 그어 음수 깊이를 구분한다', () => {
    // 증착된 산화막은 깊이가 음수다. 표면이 어디인지 표시하지 않으면
    // 기판 안에 있는 것처럼 보인다.
    const { container } = render(
      <ProfileChart
        points={[point(-0.075, 2e15, 'oxide'), point(1, 1e15)]}
        quantity="q"
      />,
    )

    expect(container.querySelector('.surface-line')).toBeInTheDocument()
  })

  it('증착층이 없으면 표면선도 없다', () => {
    const { container } = render(
      <ProfileChart points={[point(0, 1e18), point(1, 1e15)]} quantity="q" />,
    )

    expect(container.querySelector('.surface-line')).not.toBeInTheDocument()
  })
})

describe('부호 있는 값', () => {
  it('전부 음수여도 그린다', () => {
    // 보론만 주입한 구조의 net_doping 은 44점 전부 음수다(실측). 음수를
    // 버리면 p 형 기판에서 그래프가 통째로 비어 버린다.
    const { container } = render(
      <ProfileChart
        points={[point(0, -1e18), point(1, -1e15)]}
        quantity="net_doping"
      />,
    )
    const coordinates = pointsOf(polylines(container)[0]!)

    expect(coordinates).toHaveLength(2)
    expect(coordinates.every(([x, y]) => Number.isFinite(x) && Number.isFinite(y))).toBe(
      true,
    )
  })

  it('절댓값이 클수록 위에 놓는다', () => {
    const { container } = render(
      <ProfileChart points={[point(0, -1e18), point(1, -1e15)]} quantity="q" />,
    )
    const [big, small] = pointsOf(polylines(container)[0]!)

    expect(big![1]).toBeLessThan(small![1])
  })

  it('음수 구간을 점선으로 구분한다', () => {
    // 부호가 바뀌는 자리가 곧 접합이다. 같은 선으로 이으면 그 위치가 사라진다.
    const { container } = render(
      <ProfileChart
        points={[point(0, 1e18), point(1, -1e16)]}
        quantity="net_doping"
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
        points={[point(0, 1e18), point(1, -1e16)]}
        quantity="net_doping"
      />,
    )

    expect(screen.getByText(/점선 = 음수/)).toBeInTheDocument()
  })

  it('전부 양수면 알리지 않는다', () => {
    render(
      <ProfileChart points={[point(0, 1e18), point(1, 1e15)]} quantity="q" />,
    )

    expect(screen.queryByText(/점선 = 음수/)).not.toBeInTheDocument()
  })
})

describe('균일 도핑', () => {
  it('값이 모두 같아도 그린다', () => {
    // 정의역이 한 점이면 축 계산이 0 으로 나눠질 수 있다.
    const { container } = render(
      <ProfileChart
        points={[point(0, 1e15), point(1, 1e15), point(2, 1e15)]}
        quantity="q"
      />,
    )
    const coordinates = pointsOf(polylines(container)[0]!)

    expect(coordinates).toHaveLength(3)
    expect(coordinates.every(([x, y]) => Number.isFinite(x) && Number.isFinite(y))).toBe(
      true,
    )
  })
})
