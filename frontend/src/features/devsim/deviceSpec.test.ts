import { describe, expect, it } from 'vitest'
import type { DevSimElectrode } from '../../api/types'
import { defaultSpec, pointCount, problemsOf } from './deviceSpec'

function electrode(
  key: string,
  origin: DevSimElectrode['origin'] = 'detected',
  x = 0,
): DevSimElectrode {
  return {
    key,
    origin,
    kind: 'semiconductor',
    materials: ['silicon'],
    extent: { x_min: x, x_max: x + 0.3, y_min: 0, y_max: 0.05 },
    edge_count: 4,
    segments: [[x, 0, x + 0.3, 0]],
  }
}

const MOSFET = [
  electrode('source', 'detected', 1.2),
  electrode('gate', 'detected', 1.85),
  electrode('drain', 'detected', 2.5),
  electrode('body', 'backside', 0),
]

describe('defaultSpec', () => {
  it('전극을 전부 데려온다', () => {
    const spec = defaultSpec(MOSFET)
    expect(spec.electrodes.map((e) => e.label)).toEqual([
      'source',
      'gate',
      'drain',
      'body',
    ])
  })

  it('게이트를 단계 전압원으로 놓는다', () => {
    const spec = defaultSpec(MOSFET)
    const gate = spec.biases.find((b) => b.electrodes.includes('gate'))
    expect(gate?.role).toBe('step')
    expect(gate?.values?.length).toBeGreaterThan(1)
  })

  it('드레인을 스윕 전압원으로 놓는다', () => {
    const spec = defaultSpec(MOSFET)
    const sweep = spec.biases.find((b) => b.role === 'sweep')
    expect(sweep?.electrodes).toEqual(['drain'])
  })

  it('소스와 기판을 한 전압원에 묶어 0V 로 둔다', () => {
    // 서로 다른 전극을 하나로 묶는 것이 전압원 계층의 존재 이유다.
    const spec = defaultSpec(MOSFET)
    const ground = spec.biases.find((b) => b.role === 'const')
    expect(ground?.electrodes.sort()).toEqual(['body', 'source'])
    expect(ground?.value).toBe(0)
  })

  it('만들자마자 제출할 수 있어야 한다', () => {
    expect(problemsOf(defaultSpec(MOSFET))).toEqual([])
  })

  it('전극이 둘뿐이어도 스윕 하나는 만든다', () => {
    const spec = defaultSpec([
      electrode('source', 'detected', 0),
      electrode('drain', 'detected', 1),
    ])
    expect(spec.biases.filter((b) => b.role === 'sweep')).toHaveLength(1)
    expect(problemsOf(spec)).toEqual([])
  })

  it('전극이 없으면 전압원도 없다', () => {
    const spec = defaultSpec([])
    expect(spec.electrodes).toEqual([])
    expect(spec.biases).toEqual([])
  })
})

describe('pointCount', () => {
  it('스윕 점 × 단계 조합', () => {
    const spec = defaultSpec(MOSFET)
    const sweep = spec.biases.find((b) => b.role === 'sweep')!
    const step = spec.biases.find((b) => b.role === 'step')!
    const sweepPoints =
      Math.floor((sweep.sweep!.stop - sweep.sweep!.start) / sweep.sweep!.step) + 1
    expect(pointCount(spec)).toBe(sweepPoints * step.values!.length)
  })

  it('스윕이 없으면 0', () => {
    expect(pointCount({ label: 'x', electrodes: [], biases: [] })).toBe(0)
  })

  it('간격이 구간을 딱 나누지 않으면 끝점을 더 센다', () => {
    // 서버의 sweep_values 와 같은 규칙이다. 안 맞으면 진행률 분모가 어긋난다.
    expect(
      pointCount({
        label: 'x',
        electrodes: [{ origin: 'detected', key: 'a', label: 'a' }],
        biases: [
          {
            name: 'V',
            electrodes: ['a'],
            role: 'sweep',
            sweep: { start: 0, stop: 1, step: 0.3 },
          },
        ],
      }),
    ).toBe(5)
  })
})

describe('problemsOf', () => {
  const base = defaultSpec(MOSFET)

  it('스윕이 없으면 알려 준다', () => {
    const spec = {
      ...base,
      biases: base.biases.map((b) =>
        b.role === 'sweep' ? { ...b, role: 'const' as const, value: 0 } : b,
      ),
    }
    expect(problemsOf(spec).join(' ')).toContain('스윕')
  })

  it('스윕이 둘이면 알려 준다', () => {
    const spec = {
      ...base,
      biases: base.biases.map((b) =>
        b.role === 'step'
          ? { ...b, role: 'sweep' as const, sweep: { start: 0, stop: 1, step: 0.5 } }
          : b,
      ),
    }
    expect(problemsOf(spec).join(' ')).toContain('스윕')
  })

  it('전압원에 안 걸린 전극을 짚는다', () => {
    const spec = {
      ...base,
      biases: base.biases.filter((b) => b.role !== 'const'),
    }
    expect(problemsOf(spec).join(' ')).toContain('source')
  })

  it('한 전극이 두 전압원에 걸리면 짚는다', () => {
    const spec = {
      ...base,
      biases: base.biases.map((b) =>
        b.role === 'sweep' ? { ...b, electrodes: ['drain', 'source'] } : b,
      ),
    }
    expect(problemsOf(spec).join(' ')).toContain('source')
  })

  it('점이 너무 많으면 짚는다', () => {
    const spec = {
      ...base,
      biases: base.biases.map((b) =>
        b.role === 'sweep'
          ? { ...b, sweep: { start: 0, stop: 90, step: 0.1 } }
          : b,
      ),
    }
    expect(problemsOf(spec).join(' ')).toContain('점')
  })

  it('전압원에 전극이 하나도 없으면 짚는다', () => {
    const spec = {
      ...base,
      biases: base.biases.map((b) =>
        b.role === 'step' ? { ...b, electrodes: [] } : b,
      ),
    }
    expect(problemsOf(spec).length).toBeGreaterThan(0)
  })
})
