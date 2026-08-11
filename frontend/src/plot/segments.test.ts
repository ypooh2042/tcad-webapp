/**
 * 프로파일을 물질 구간으로 끊기.
 *
 * 계면에서는 같은 깊이에 물질별 값이 따로 있다. 예를 들어 1d_boron.str 의
 * 표면(깊이 0)에서 chem_boron 은 oxide 쪽 1.14e19, silicon 쪽 5.86e18 이다.
 * 이걸 한 줄로 이으면 수직으로 뚝 떨어지는 가짜 선이 생기고, 실제로는 물질이
 * 바뀌는 지점인데 농도가 급락한 것처럼 보인다.
 */
import { describe, expect, it } from 'vitest'
import { materialBands, splitByMaterial } from './segments'

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

describe('재질 배경 띠', () => {
  it('재질별 깊이 구간을 만든다', () => {
    const bands = materialBands([
      point(-0.075, 1, 'oxide'),
      point(0, 2, 'oxide'),
      point(0, 3, 'silicon'),
      point(2, 4, 'silicon'),
    ])

    expect(bands).toEqual([
      { material: 'oxide', from: -0.075, to: 0 },
      { material: 'silicon', from: 0, to: 2 },
    ])
  })

  it('띠 사이에 빈틈을 남기지 않는다', () => {
    // 계면에서 끊기면 배경에 흰 줄이 생겨 층이 떨어져 보인다.
    const bands = materialBands([
      point(0, 1, 'oxide'),
      point(1, 2, 'oxide'),
      point(1, 3, 'silicon'),
      point(3, 4, 'silicon'),
    ])

    expect(bands[0]!.to).toBe(bands[1]!.from)
  })

  it('같은 재질이 떨어져 나오면 따로 만든다', () => {
    // CMOS 게이트 적층: oxide / poly / oxide / silicon.
    // 구간마다 점이 둘 이상 있어야 폭이 생긴다 — 실제 데이터가 그렇다.
    const bands = materialBands([
      point(-0.41, 1, 'oxide'),
      point(-0.40, 2, 'oxide'),
      point(-0.40, 3, 'poly'),
      point(-0.001, 4, 'poly'),
      point(-0.001, 5, 'oxide'),
      point(0.042, 6, 'oxide'),
      point(0.042, 7, 'silicon'),
      point(3, 8, 'silicon'),
    ])

    expect(bands.map((b) => b.material)).toEqual([
      'oxide',
      'poly',
      'oxide',
      'silicon',
    ])
  })

  it('폭이 0 인 띠는 버린다', () => {
    // 계면 점 하나만 있는 재질에서 나온다. 그려 봐야 보이지 않는다.
    const bands = materialBands([
      point(0, 1, 'oxide'),
      point(0, 2, 'poly'),
      point(2, 3, 'silicon'),
    ])

    expect(bands.every((b) => b.to > b.from)).toBe(true)
  })

  it('빈 입력은 빈 결과다', () => {
    expect(materialBands([])).toEqual([])
  })
})
