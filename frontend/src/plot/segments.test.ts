/**
 * 프로파일을 물질 구간으로 끊기.
 *
 * 계면에서는 같은 깊이에 물질별 값이 따로 있다. 예를 들어 1d_boron.str 의
 * 표면(깊이 0)에서 chem_boron 은 oxide 쪽 1.14e19, silicon 쪽 5.86e18 이다.
 * 이걸 한 줄로 이으면 수직으로 뚝 떨어지는 가짜 선이 생기고, 실제로는 물질이
 * 바뀌는 지점인데 농도가 급락한 것처럼 보인다.
 */
import { describe, expect, it } from 'vitest'
import { splitByMaterial } from './segments'

const point = (depth: number, value: number, material: string) => ({
  depth,
  value,
  material,
})

describe('구간 나누기', () => {
  it('물질이 하나면 구간도 하나다', () => {
    const segments = splitByMaterial([
      point(0, 1e18, 'silicon'),
      point(1, 1e17, 'silicon'),
    ])

    expect(segments).toHaveLength(1)
    expect(segments[0]!.material).toBe('silicon')
  })

  it('물질이 바뀌면 구간을 끊는다', () => {
    const segments = splitByMaterial([
      point(-0.075, 2.45e15, 'oxide'),
      point(0, 1.14e19, 'oxide'),
      point(0, 5.86e18, 'silicon'),
      point(0.02, 5.82e18, 'silicon'),
    ])

    expect(segments.map((s) => s.material)).toEqual(['oxide', 'silicon'])
  })

  it('계면의 두 값을 각자 구간에 남긴다', () => {
    // 어느 한쪽을 버리면 그 물질의 계면 값이 그림에서 사라진다.
    const segments = splitByMaterial([
      point(0, 1.14e19, 'oxide'),
      point(0, 5.86e18, 'silicon'),
    ])

    expect(segments[0]!.points).toHaveLength(1)
    expect(segments[1]!.points).toHaveLength(1)
  })

  it('같은 물질이 다시 나오면 새 구간이 된다', () => {
    // oxide / silicon / oxide 처럼 층이 반복될 수 있다. 하나로 합치면
    // 떨어져 있는 두 층이 선으로 이어진다.
    const segments = splitByMaterial([
      point(0, 1, 'oxide'),
      point(1, 2, 'silicon'),
      point(2, 3, 'oxide'),
    ])

    expect(segments).toHaveLength(3)
  })

  it('빈 입력은 빈 결과다', () => {
    expect(splitByMaterial([])).toEqual([])
  })
})

describe('부호', () => {
  it('부호가 바뀌면 구간을 끊는다', () => {
    // net_doping 의 부호가 바뀌는 지점이 접합이다. 한 선으로 이으면 접합이
    // 골짜기처럼 보여 소자에서 가장 중요한 위치가 사라진다.
    const segments = splitByMaterial([
      point(0, 1e18, 'silicon'),
      point(1, -1e17, 'silicon'),
    ])

    expect(segments).toHaveLength(2)
    expect(segments.map((s) => s.negative)).toEqual([false, true])
  })

  it('부호가 같으면 이어 간다', () => {
    const segments = splitByMaterial([
      point(0, -1e18, 'silicon'),
      point(1, -1e17, 'silicon'),
    ])

    expect(segments).toHaveLength(1)
    expect(segments[0]!.negative).toBe(true)
  })
})
