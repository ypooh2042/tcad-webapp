import type { DeviceSpec } from '../../api/types'
import { describe, expect, it } from 'vitest'
import type { DevSimInterface } from '../../api/types'
import {
  addElectrode,
  assignInterface,
  defaultSpec,
  nameOfInterface,
  ownerOf,
  pointCount,
  problemsOf,
  removeElectrode,
  renameElectrode,
  renameInterface,
  sweepGap,
  sweepValues,
  unassignInterface,
} from './deviceSpec'

function detected(
  key: string,
  origin: DevSimInterface['origin'] = 'metal',
  x = 0,
): DevSimInterface {
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
  detected('source', 'metal', 1.2),
  detected('gate', 'metal', 1.85),
  detected('drain', 'metal', 2.5),
  detected('body', 'backside', 0),
]

describe('defaultSpec', () => {
  it('계면마다 전극을 하나씩 만든다', () => {
    const spec = defaultSpec(MOSFET)
    expect(spec.electrodes.map((e) => e.label)).toEqual([
      'source',
      'gate',
      'drain',
      'body',
    ])
    expect(spec.electrodes.map((e) => e.interfaces)).toEqual([
      ['source'],
      ['gate'],
      ['drain'],
      ['body'],
    ])
  })

  it('전극마다 전압원을 정확히 하나씩 붙인다', () => {
    // 1전극-1전압원. 기판도 자기 전압원을 갖는다.
    const spec = defaultSpec(MOSFET)
    expect(spec.biases).toHaveLength(4)
    expect(spec.biases.map((b) => b.electrode).sort()).toEqual([
      'body',
      'drain',
      'gate',
      'source',
    ])
  })

  it('게이트를 단계 전압원으로 놓는다', () => {
    const gate = defaultSpec(MOSFET).biases.find((b) => b.electrode === 'gate')
    expect(gate?.role).toBe('step')
    expect(gate?.values?.length).toBeGreaterThan(1)
  })

  it('가장 오른쪽 금속을 스윕으로 놓는다', () => {
    const sweep = defaultSpec(MOSFET).biases.find((b) => b.role === 'sweep')
    expect(sweep?.electrode).toBe('drain')
  })

  it('나머지는 0V 고정이다', () => {
    const spec = defaultSpec(MOSFET)
    for (const label of ['source', 'body']) {
      const bias = spec.biases.find((b) => b.electrode === label)
      expect(bias?.role).toBe('const')
      expect(bias?.value).toBe(0)
    }
  })

  it('만들자마자 제출할 수 있어야 한다', () => {
    expect(problemsOf(defaultSpec(MOSFET))).toEqual([])
  })

  it('계면이 둘뿐이어도 스윕 하나는 만든다', () => {
    const spec = defaultSpec([
      detected('source', 'metal', 0),
      detected('drain', 'metal', 1),
    ])
    expect(spec.biases.filter((b) => b.role === 'sweep')).toHaveLength(1)
    expect(problemsOf(spec)).toEqual([])
  })

  it('계면이 없으면 전극도 전압원도 없다', () => {
    const spec = defaultSpec([])
    expect(spec.electrodes).toEqual([])
    expect(spec.biases).toEqual([])
  })
})

describe('ownerOf', () => {
  it('계면을 물고 있는 전극을 알려 준다', () => {
    expect(ownerOf(defaultSpec(MOSFET), 'gate')).toBe('gate')
  })

  it('아무도 안 물었으면 null', () => {
    const spec = unassignInterface(defaultSpec(MOSFET), 'gate')
    expect(ownerOf(spec, 'gate')).toBeNull()
  })
})

describe('assignInterface', () => {
  it('계면을 다른 전극으로 옮긴다', () => {
    // 한 계면이 두 전극에 걸리면 같은 변에 두 전위를 걸겠다는 뜻이 된다.
    const spec = assignInterface(defaultSpec(MOSFET), 'body', 'source')
    expect(ownerOf(spec, 'body')).toBe('source')
    expect(spec.electrodes.find((e) => e.label === 'source')?.interfaces).toEqual(
      ['source', 'body'],
    )
    expect(spec.electrodes.find((e) => e.label === 'body')?.interfaces).toEqual([])
  })

  it('이미 그 전극에 있으면 그대로 둔다', () => {
    const spec = defaultSpec(MOSFET)
    expect(assignInterface(spec, 'gate', 'gate')).toEqual(spec)
  })

  it('없는 전극으로는 옮기지 않는다', () => {
    const spec = defaultSpec(MOSFET)
    expect(assignInterface(spec, 'gate', '없는전극')).toEqual(spec)
  })

  it('원본을 바꾸지 않는다', () => {
    const spec = defaultSpec(MOSFET)
    const before = JSON.stringify(spec)
    assignInterface(spec, 'body', 'source')
    expect(JSON.stringify(spec)).toBe(before)
  })
})

describe('addElectrode / removeElectrode / renameElectrode', () => {
  it('전극을 더하면 전압원도 같이 생긴다', () => {
    const spec = addElectrode(defaultSpec(MOSFET))
    expect(spec.electrodes).toHaveLength(5)
    expect(spec.biases).toHaveLength(5)
    const added = spec.electrodes[4]
    expect(spec.biases.some((b) => b.electrode === added.label)).toBe(true)
  })

  it('새 전극은 이름이 겹치지 않는다', () => {
    const spec = addElectrode(addElectrode(defaultSpec(MOSFET)))
    const labels = spec.electrodes.map((e) => e.label)
    expect(new Set(labels).size).toBe(labels.length)
  })

  it('새로 만든 전극은 계면이 없어 아직 제출할 수 없다', () => {
    const spec = addElectrode(defaultSpec(MOSFET))
    expect(problemsOf(spec).join(' ')).toContain('계면')
  })

  it('전극을 빼면 전압원도 같이 빠진다', () => {
    const spec = removeElectrode(defaultSpec(MOSFET), 'body')
    expect(spec.electrodes.map((e) => e.label)).not.toContain('body')
    expect(spec.biases.some((b) => b.electrode === 'body')).toBe(false)
    expect(problemsOf(spec)).toEqual([])
  })

  it('이름을 바꾸면 전압원이 가리키는 곳도 따라간다', () => {
    const spec = renameElectrode(defaultSpec(MOSFET), 'drain', '출력')
    expect(ownerOf(spec, 'drain')).toBe('출력')
    expect(spec.biases.find((b) => b.role === 'sweep')?.electrode).toBe('출력')
    expect(problemsOf(spec)).toEqual([])
  })

  it('이미 있는 이름으로는 바꾸지 않는다', () => {
    const spec = defaultSpec(MOSFET)
    expect(renameElectrode(spec, 'drain', 'source')).toEqual(spec)
  })
})

describe('pointCount', () => {
  it('스윕 점 × 단계 조합', () => {
    const spec = defaultSpec(MOSFET)
    const sweep = spec.biases.find((b) => b.role === 'sweep')!
    const step = spec.biases.find((b) => b.role === 'step')!
    expect(pointCount(spec)).toBe(sweep.sweep!.points * step.values!.length)
  })

  it('스윕이 없으면 0', () => {
    expect(pointCount({ label: 'x', electrodes: [], biases: [] })).toBe(0)
  })

  it('스윕 점 개수를 그대로 센다', () => {
    // 서버의 sweep_values 와 같은 규칙이다. 안 맞으면 진행률 분모가 어긋난다.
    expect(
      pointCount({
        label: 'x',
        electrodes: [{ label: 'a', interfaces: ['a'] }],
        biases: [
          {
            name: 'V',
            electrode: 'a',
            role: 'sweep',
            sweep: { start: 0, stop: 1, points: 4 },
          },
        ],
      }),
    ).toBe(4)
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
          ? { ...b, role: 'sweep' as const, sweep: { start: 0, stop: 1, points: 3 } }
          : b,
      ),
    }
    expect(problemsOf(spec).join(' ')).toContain('스윕')
  })

  it('계면이 하나도 안 붙은 전극을 짚는다', () => {
    const spec = unassignInterface(base, 'body')
    expect(problemsOf(spec).join(' ')).toContain('body')
  })

  it('전압원 없는 전극을 짚는다', () => {
    const spec = { ...base, biases: base.biases.filter((b) => b.electrode !== 'body') }
    expect(problemsOf(spec).join(' ')).toContain('body')
  })

  it('점이 너무 많으면 짚는다', () => {
    const spec = {
      ...base,
      biases: base.biases.map((b) =>
        b.role === 'sweep'
          ? { ...b, sweep: { start: 0, stop: 90, points: 901 } }
          : b,
      ),
    }
    expect(problemsOf(spec).join(' ')).toContain('점')
  })

  it('단계 전압이 비면 짚는다', () => {
    const spec = {
      ...base,
      biases: base.biases.map((b) =>
        b.role === 'step' ? { ...b, values: [] } : b,
      ),
    }
    expect(problemsOf(spec).length).toBeGreaterThan(0)
  })
})

describe('계면 이름', () => {
  const base = defaultSpec(MOSFET)

  it('붙인 이름이 없으면 열쇠를 그대로 쓴다', () => {
    expect(nameOfInterface(base, 'gate')).toBe('gate')
  })

  it('이름을 붙이면 그것을 쓴다', () => {
    const spec = renameInterface(base, 'gate', '게이트 접촉')
    expect(nameOfInterface(spec, 'gate')).toBe('게이트 접촉')
  })

  it('열쇠는 그대로 둔다', () => {
    // 열쇠는 구조에서 나온 신원이다. 바꾸면 다음 실행에서 못 찾는다.
    const spec = renameInterface(base, 'gate', '게이트 접촉')
    expect(spec.electrodes.find((e) => e.label === 'gate')?.interfaces).toEqual([
      'gate',
    ])
  })

  it('치는 도중의 공백을 잘라내지 않는다', () => {
    // 즉시 다듬으면 "기판 " 이 "기판" 이 되어 공백을 칠 수 없다. 두 단어짜리
    // 이름을 아예 못 쓰게 된다.
    const spec = renameInterface(base, 'body', '기판 ')
    expect(nameOfInterface(spec, 'body')).toBe('기판 ')
  })

  it('빈 이름은 저장하지 않는다', () => {
    const named = renameInterface(base, 'gate', '게이트')
    const cleared = renameInterface(named, 'gate', '  ')
    expect(cleared.interface_names).toEqual({})
    expect(nameOfInterface(cleared, 'gate')).toBe('gate')
  })

  it('열쇠와 같은 이름도 저장하지 않는다', () => {
    expect(renameInterface(base, 'gate', 'gate').interface_names).toEqual({})
  })

  it('원본을 바꾸지 않는다', () => {
    const before = JSON.stringify(base)
    renameInterface(base, 'gate', '게이트')
    expect(JSON.stringify(base)).toBe(before)
  })
})

describe('게이트가 둘일 때', () => {
  // CMOS 처럼 트랜지스터가 둘이면 게이트도 둘이다. 예전에는 서버가 둘 다
  // `gate` 로 이름 붙여서, 하나를 지우면 다른 하나까지 사라졌다.
  const TWO_GATES = [
    detected('source', 'metal', 0.2),
    detected('gate1', 'metal', 0.85),
    detected('drain', 'metal', 1.5),
    detected('gate2', 'metal', 2.85),
    detected('body', 'backside', 0),
  ]

  it('전극이 계면 수만큼 생긴다', () => {
    expect(defaultSpec(TWO_GATES).electrodes).toHaveLength(5)
  })

  it('한쪽 게이트를 빼도 다른 쪽은 남는다', () => {
    const spec = removeElectrode(defaultSpec(TWO_GATES), 'gate1')
    expect(spec.electrodes.map((e) => e.label)).toContain('gate2')
    expect(spec.electrodes.map((e) => e.label)).not.toContain('gate1')
    expect(spec.biases.some((b) => b.electrode === 'gate2')).toBe(true)
  })

  it('한쪽 게이트 이름을 바꿔도 다른 쪽은 그대로다', () => {
    const spec = renameElectrode(defaultSpec(TWO_GATES), 'gate1', 'pmos 게이트')
    expect(ownerOf(spec, 'gate1')).toBe('pmos 게이트')
    expect(ownerOf(spec, 'gate2')).toBe('gate2')
  })

  it('계면 이름도 따로 붙는다', () => {
    const spec = renameInterface(defaultSpec(TWO_GATES), 'gate2', 'nmos 게이트')
    expect(nameOfInterface(spec, 'gate1')).toBe('gate1')
    expect(nameOfInterface(spec, 'gate2')).toBe('nmos 게이트')
  })
})

describe('sweepValues / sweepGap', () => {
  it('구간을 고르게 나눈다', () => {
    expect(sweepValues(0, 2, 5)).toEqual([0, 0.5, 1, 1.5, 2])
  })

  it('양 끝을 반드시 포함한다', () => {
    const values = sweepValues(0, 1, 4)
    expect(values[0]).toBe(0)
    expect(values[values.length - 1]).toBe(1)
  })

  it('점이 하나면 시작점만', () => {
    expect(sweepValues(0.5, 2, 1)).toEqual([0.5])
  })

  it('점이 없으면 아무것도 없다', () => {
    expect(sweepValues(0, 1, 0)).toEqual([])
  })

  it('간격을 알려 준다', () => {
    // 화면이 "0.5V 간격" 을 곁들여 보여준다. 점 개수만 보면 얼마나 촘촘한지
    // 감이 안 온다.
    expect(sweepGap(0, 2.5, 6)).toBeCloseTo(0.5)
  })

  it('점이 하나면 간격이 없다', () => {
    expect(sweepGap(0, 2, 1)).toBe(0)
  })
})

describe('기본 조건', () => {
  it('게이트 단계는 1, 2, 4 V', () => {
    const gate = defaultSpec(MOSFET).biases.find((b) => b.electrode === 'gate')
    expect(gate?.values).toEqual([1, 2, 4])
  })

  it('드레인 스윕은 0~2.5 V 를 6 점으로', () => {
    const sweep = defaultSpec(MOSFET).biases.find((b) => b.role === 'sweep')
    expect(sweep?.sweep).toEqual({ start: 0, stop: 2.5, points: 6 })
    expect(sweepGap(0, 2.5, 6)).toBeCloseTo(0.5)
  })
})

describe('부유 전압원', () => {
  // 출력 노드의 전위는 **미지수**다. 회로가 스스로 정한다. 전압으로 강제하면
  // 자연 동작점에서 멀어질수록 큰 전류가 흘러(실측 −440 µA/µm) 물리적으로도
  // 수치적으로도 어려운 문제가 된다.
  //
  // 부유를 전극이 아니라 **역할**로 둔 덕에 "전극마다 전압원 하나" 전제가
  // 그대로 산다 — 전압원은 붙어 있고 값만 없다.
  function withFloat(): DeviceSpec {
    const spec = defaultSpec(MOSFET)
    return {
      ...spec,
      biases: spec.biases.map((bias, index) =>
        index === 0
          ? { name: bias.name, electrode: bias.electrode, role: 'float' as const }
          : bias,
      ),
    }
  }

  it('부유는 전압을 갖지 않아도 된다', () => {
    expect(problemsOf(withFloat())).toEqual([])
  })

  it('전압을 함께 주면 짚어준다', () => {
    const spec = withFloat()
    spec.biases[0] = { ...spec.biases[0], value: 1.5 }

    expect(problemsOf(spec).join()).toMatch(/부유/)
  })

  it('전극은 여전히 전압원을 갖는다', () => {
    // 이 규칙이 안 깨지는 것이 역할 방식을 고른 이유다.
    expect(problemsOf(withFloat()).join()).not.toMatch(/전압원이 없는/)
  })

  it('부유는 점 수를 늘리지 않는다', () => {
    expect(pointCount(withFloat())).toBe(pointCount(defaultSpec(MOSFET)))
  })

  it('전부 부유면 스윕이 없다고 짚는다', () => {
    const spec = defaultSpec(MOSFET)
    const all = {
      ...spec,
      biases: spec.biases.map((bias) => ({
        name: bias.name,
        electrode: bias.electrode,
        role: 'float' as const,
      })),
    }

    expect(problemsOf(all).join()).toMatch(/스윕/)
  })
})

describe('스윕을 목록으로 적기', () => {
  // 등간격만 되면 어려운 구간에 점을 몰아줄 수 없다. 인버터 전달특성이 딱
  // 그런 경우로, 실측에서 0.5 V 간격이 전환 구간을 못 넘어 3 점을 잃었다.
  function listed(values: number[]): DeviceSpec {
    const spec = defaultSpec(MOSFET)
    return {
      ...spec,
      biases: spec.biases.map((bias) =>
        bias.role === 'sweep'
          ? { name: bias.name, electrode: bias.electrode, role: 'sweep' as const, values }
          : bias,
      ),
    }
  }

  it('목록으로 적어도 통과한다', () => {
    expect(problemsOf(listed([0, 1, 1.5, 1.75, 2, 5]))).toEqual([])
  })

  it('점 수를 목록 길이로 센다', () => {
    const spec = listed([0, 1, 2])
    const steps = spec.biases.filter((b) => b.role === 'step')
    const families = steps.reduce((n, b) => n * Math.max(1, (b.values ?? []).length), 1)

    expect(pointCount(spec)).toBe(3 * families)
  })

  it('둘 다 주면 짚어준다', () => {
    const spec = listed([0, 1])
    spec.biases = spec.biases.map((b) =>
      b.role === 'sweep' ? { ...b, sweep: { start: 0, stop: 1, points: 2 } } : b,
    )

    expect(problemsOf(spec).join()).toMatch(/둘 중 하나/)
  })

  it('둘 다 없으면 짚어준다', () => {
    const spec = listed([])
    spec.biases = spec.biases.map((b) =>
      b.role === 'sweep' ? { name: b.name, electrode: b.electrode, role: 'sweep' } : b,
    )

    expect(problemsOf(spec).join()).toMatch(/스윕/)
  })
})
