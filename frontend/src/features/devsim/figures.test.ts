import { describe, expect, it } from 'vitest'
import type { IvDataset, IvRow } from '../../api/types'
import { dominantBias, figuresOf, seriesOf, toMicroAmps } from './figures'

/**
 * 문턱전압 1V, 선형영역 이득 1e-4 인 교과서 nMOS 의 전달 특성.
 *
 * 조각을 이어 붙이지 않고 softplus 하나로 만든다. 이어 붙이면 이음매에서
 * log 기울기가 실제보다 가팔라져, 문턱 아래 기울기를 재는 시험이 곡선이 아니라
 * 이음매를 재게 된다(처음에 그렇게 만들었다가 49.9mV/dec 가 나왔다).
 *
 *   I = A·Vt·ln(1 + exp((Vg − Vth)/Vt))
 *
 * 큰 Vg 에서는 A·(Vg − Vth) 인 직선, 작은 Vg 에서는 지수 — 기울기가 정확히
 * Vt·ln10 = 59.6 mV/dec 다.
 */
const THERMAL_VOLT = 0.02585

function transfer(vth = 1.0): IvDataset {
  const rows: IvRow[] = []
  for (let i = 0; i <= 30; i++) {
    const vg = i * 0.1
    // log1p 를 쓴다. 1 + 1.7e-17 은 배정밀도에서 그냥 1 이라, Math.log 로 하면
    // 문턱 한참 아래가 통째로 0 이 되어 off 전류가 사라진다.
    const id = 1e-4 * THERMAL_VOLT * Math.log1p(Math.exp((vg - vth) / THERMAL_VOLT))
    rows.push({ sweep: vg, steps: { Vd: 0.1 }, currents: { Vg: 1e-16, Vd: id } })
  }
  return {
    sweep: 'Vg',
    biases: ['Vd', 'Vg'],
    current_unit: 'uA/um',
    rows,
    total: rows.length,
    completed: rows.length,
    error: null,
  }
}

/** Vgs 두 단계짜리 출력 특성. */
function output(): IvDataset {
  const rows: IvRow[] = []
  for (const vg of [1.0, 2.0]) {
    for (let i = 0; i <= 8; i++) {
      const vd = i * 0.25
      const over = vg - 1.0
      const id =
        vd < over ? 1e-4 * (over * vd - vd * vd / 2) : 1e-4 * (over * over) / 2
      rows.push({ sweep: vd, steps: { Vg: vg }, currents: { Vd: id, Vg: 0 } })
    }
  }
  return {
    sweep: 'Vd',
    biases: ['Vd', 'Vg'],
    current_unit: 'uA/um',
    rows,
    total: rows.length,
    completed: rows.length,
    error: null,
  }
}

describe('dominantBias', () => {
  it('전류가 가장 많이 움직인 전압원을 고른다', () => {
    // 게이트 전류는 절연막 너머라 늘 0 이다. 그걸 그리면 빈 그래프가 나온다.
    expect(dominantBias(transfer())).toBe('Vd')
  })

  it('데이터가 없으면 아무것도 못 고른다', () => {
    const empty = { ...transfer(), rows: [] }
    expect(dominantBias(empty)).toBeNull()
  })
})

describe('seriesOf', () => {
  it('단계 조합마다 곡선을 하나씩 만든다', () => {
    const series = seriesOf(output(), 'Vd')
    expect(series).toHaveLength(2)
    expect(series.map((s) => s.label)).toEqual(['Vg=1V', 'Vg=2V'])
  })

  it('각 곡선은 스윕 순서를 지킨다', () => {
    const [first] = seriesOf(output(), 'Vd')
    const xs = first.points.map((p) => p.x)
    expect(xs).toEqual([...xs].sort((a, b) => a - b))
  })

  it('단계가 없으면 곡선 하나에 이름이 비어 있다', () => {
    const series = seriesOf(
      { ...transfer(), rows: transfer().rows.map((r) => ({ ...r, steps: {} })) },
      'Vd',
    )
    expect(series).toHaveLength(1)
    expect(series[0].label).toBe('')
  })
})

describe('figuresOf — 전달 특성', () => {
  const [curve] = seriesOf(transfer(), 'Vd')

  it('최대 전류와 최소 전류를 잡는다', () => {
    const found = figuresOf(curve)
    expect(found.iOn).toBeCloseTo(2e-4, 5)
    expect(found.iOff).toBeGreaterThan(0)
  })

  it('on/off 비가 크게 나온다', () => {
    expect(figuresOf(curve).onOff).toBeGreaterThan(1e6)
  })

  it('최대 gm 접선 외삽으로 문턱전압을 되찾는다', () => {
    // 선형 영역의 기울기가 1e-4 이므로 외삽은 정확히 1V 를 가리킨다.
    expect(figuresOf(curve).vth).toBeCloseTo(1.0, 1)
  })

  it('문턱 아래 기울기를 60mV/dec 근처로 잡는다', () => {
    // Vt·ln10 = 59.6 mV/dec.
    expect(figuresOf(curve).ss).toBeCloseTo(59.6, 0)
  })

  it('최대 상호컨덕턴스를 잡는다', () => {
    expect(figuresOf(curve).gmMax).toBeCloseTo(1e-4, 6)
  })
})

describe('figuresOf — 출력 특성', () => {
  it('선형 영역 기울기에서 온저항을 뽑는다', () => {
    const [curve] = seriesOf(output(), 'Vd')
    // Vg=1, Vov=0 이면 전류가 0 이라 온저항이 없다. 두 번째 곡선을 본다.
    const [, second] = seriesOf(output(), 'Vd')
    expect(figuresOf(second).ron).toBeGreaterThan(0)
    expect(figuresOf(curve).ron).toBeNull()
  })
})

describe('figuresOf — 데이터가 모자랄 때', () => {
  it('점이 둘뿐이면 기울기 지표를 내지 않는다', () => {
    const found = figuresOf({
      label: '',
      steps: {},
      points: [
        { x: 0, y: 0 },
        { x: 1, y: 1e-5 },
      ],
    })
    expect(found.vth).toBeNull()
    expect(found.ss).toBeNull()
  })

  it('전류가 전부 0 이면 on/off 비를 내지 않는다', () => {
    const found = figuresOf({
      label: '',
      steps: {},
      points: [0, 1, 2].map((x) => ({ x, y: 0 })),
    })
    expect(found.onOff).toBeNull()
    expect(found.iOn).toBe(0)
  })

  it('점이 없으면 전부 비어 있다', () => {
    const found = figuresOf({ label: '', steps: {}, points: [] })
    expect(found.iOn).toBe(0)
    expect(found.vth).toBeNull()
    expect(found.gmMax).toBeNull()
  })
})

describe('단위 맞추기', () => {
  it('µA/µm 은 그대로 둔다', () => {
    expect(toMicroAmps(3.24, 'uA/um')).toBeCloseTo(3.24)
  })

  it('A/µm 은 µA/µm 로 올린다', () => {
    // 예전에 저장한 결과가 A/µm 로 남아 있다. 그대로 겹쳐 그리면 한쪽 곡선이
    // 바닥에 눌려 붙어 비교가 되지 않는다.
    expect(toMicroAmps(3.24e-5, 'A/um')).toBeCloseTo(32.4)
  })

  it('모르는 단위는 건드리지 않는다', () => {
    // 조용히 배수를 곱하면 틀린 값을 맞는 것처럼 보여준다.
    expect(toMicroAmps(5, 'mA/mm')).toBe(5)
    expect(toMicroAmps(5, undefined)).toBe(5)
  })
})

describe('seriesOf — 단위', () => {
  it('A/µm 로 저장된 곡선을 µA/µm 로 올려 준다', () => {
    const old = { ...transfer(), current_unit: 'A/um' }
    const [curve] = seriesOf(old, 'Vd')
    const peak = Math.max(...curve.points.map((p) => Math.abs(p.y)))
    expect(peak).toBeCloseTo(2e-4 * 1e6, 1)
  })

  it('µA/µm 로 저장된 곡선은 그대로 쓴다', () => {
    const [curve] = seriesOf(transfer(), 'Vd')
    const peak = Math.max(...curve.points.map((p) => Math.abs(p.y)))
    expect(peak).toBeCloseTo(2e-4, 6)
  })
})
