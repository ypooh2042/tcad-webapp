/**
 * 해석 조건을 만들고 검사한다.
 *
 * 검사는 서버에도 있다(`app/devsim/spec.py`). 여기 것은 **먼저** 알려 주기 위한
 * 것이다 — 제출해 봐야 422 를 받는 것과, 실행 버튼 옆에 무엇이 잘못됐는지 떠
 * 있는 것은 다르다. 규칙이 갈리면 서버 쪽이 맞다.
 */
import type { Bias, DeviceSpec, DevSimInterface } from '../../api/types'

/** 서버의 `MAX_TOTAL_POINTS` 와 같아야 한다. */
export const MAX_TOTAL_POINTS = 300

/** 기본 게이트 단계. 문턱 아래부터 확실한 온 상태까지 걸친다. */
const DEFAULT_STEPS = [1, 2, 4]

const DEFAULT_SWEEP = { start: 0, stop: 2.5, points: 6 }

/**
 * 스윕이 훑는 전압. 서버의 `sweep_values` 와 같은 규칙이다.
 *
 * 간격이 아니라 **점 개수**로 정한다. 간격으로 정하면 `0 → 1` 을 `0.3` 씩
 * 훑을 때 몇 점이 나오는지 손으로 세야 하고 끝점이 걸리는지도 눈에 안 보인다.
 * 실행 시간은 점 개수에 비례하므로 숫자가 사용자의 의도와 일치한다.
 */
export function sweepValues(
  start: number,
  stop: number,
  points: number,
): number[] {
  if (points <= 0) return []
  if (points === 1 || start === stop) return [start]
  const span = stop - start
  return Array.from(
    { length: points },
    (_unused, index) => start + (span * index) / (points - 1),
  )
}

/** 점 사이 간격. 화면이 "0.5V 간격" 을 곁들여 보여줄 때 쓴다. */
export function sweepGap(start: number, stop: number, points: number): number {
  if (points <= 1) return 0
  return (stop - start) / (points - 1)
}

function pointsOf(bias: Bias): number[] {
  if (bias.role === 'const') return [bias.value ?? 0]
  if (bias.role === 'step') return bias.values ?? []
  if (!bias.sweep) return []
  return sweepValues(bias.sweep.start, bias.sweep.stop, bias.sweep.points)
}

/** 풀어야 할 바이어스 점의 총수. 실행 시간이 여기에 비례한다. */
export function pointCount(spec: DeviceSpec): number {
  const sweep = spec.biases.find((bias) => bias.role === 'sweep')
  if (!sweep) return 0
  const steps = spec.biases.filter((bias) => bias.role === 'step')
  const combinations = steps.reduce(
    (total, bias) => total * Math.max(1, pointsOf(bias).length),
    1,
  )
  return pointsOf(sweep).length * combinations
}

/**
 * 자동으로 찾은 계면에서 쓸 만한 첫 조건을 만든다.
 *
 * 계면마다 전극 하나, 전극마다 전압원 하나. 게이트는 곡선족을 만드는 단계로,
 * 게이트가 아닌 금속 중 가장 오른쪽을 스윕으로 놓는다. 나머지는 0V 고정이다 —
 * MOSFET 출력 특성이 늘 그 모양이다.
 */
export function defaultSpec(interfaces: DevSimInterface[]): DeviceSpec {
  if (interfaces.length === 0) {
    return { label: '기본 조건', electrodes: [], biases: [], gate_model: 'semiconductor' }
  }

  const gates = interfaces.filter(
    (one) => one.key === 'gate' || one.kind === 'insulator',
  )
  const others = interfaces.filter((one) => !gates.includes(one))
  const ordered = [...others].sort(
    (a, b) => a.extent.x_min + a.extent.x_max - (b.extent.x_min + b.extent.x_max),
  )
  // 뒷면은 스윕으로 삼지 않는다. 기판을 흔드는 것은 특수한 실험이고, 첫 조건이
  // 그것이면 사용자는 자기가 무엇을 보고 있는지 알기 어렵다.
  const sweepable = ordered.filter((one) => one.origin !== 'backside')
  const swept = sweepable[sweepable.length - 1] ?? ordered[ordered.length - 1]

  return {
    label: '기본 조건',
    electrodes: interfaces.map((one) => ({
      label: one.key,
      interfaces: [one.key],
    })),
    biases: interfaces.map((one) => {
      if (gates.includes(one)) {
        return {
          name: `V${one.key}`,
          electrode: one.key,
          role: 'step' as const,
          values: [...DEFAULT_STEPS],
        }
      }
      if (one === swept) {
        return {
          name: `V${one.key}`,
          electrode: one.key,
          role: 'sweep' as const,
          sweep: { ...DEFAULT_SWEEP },
        }
      }
      return {
        name: `V${one.key}`,
        electrode: one.key,
        role: 'const' as const,
        value: 0,
      }
    }),
    gate_model: 'semiconductor',
  }
}

/** 이 계면을 물고 있는 전극. 아무도 안 물었으면 null. */
export function ownerOf(spec: DeviceSpec, key: string): string | null {
  const found = spec.electrodes.find((electrode) =>
    electrode.interfaces.includes(key),
  )
  return found ? found.label : null
}

/**
 * 계면을 전극에 붙인다. 다른 전극에 있었으면 떼어 온다.
 *
 * 한 계면이 두 전극에 걸리면 같은 변에 서로 다른 전위를 걸겠다는 뜻이 되고,
 * 솔버가 무엇을 골랐는지 알 수 없다. 그래서 "추가"가 아니라 "이동"이다.
 */
export function assignInterface(
  spec: DeviceSpec,
  key: string,
  label: string,
): DeviceSpec {
  if (!spec.electrodes.some((electrode) => electrode.label === label)) return spec
  if (ownerOf(spec, key) === label) return spec
  return {
    ...spec,
    electrodes: spec.electrodes.map((electrode) => {
      if (electrode.label === label) {
        return { ...electrode, interfaces: [...electrode.interfaces, key] }
      }
      if (!electrode.interfaces.includes(key)) return electrode
      return {
        ...electrode,
        interfaces: electrode.interfaces.filter((one) => one !== key),
      }
    }),
  }
}

export function unassignInterface(spec: DeviceSpec, key: string): DeviceSpec {
  return {
    ...spec,
    electrodes: spec.electrodes.map((electrode) =>
      electrode.interfaces.includes(key)
        ? {
            ...electrode,
            interfaces: electrode.interfaces.filter((one) => one !== key),
          }
        : electrode,
    ),
  }
}

/** 빈 전극을 하나 더한다. 전압원도 같이 생긴다 — 둘은 1:1 이다. */
export function addElectrode(spec: DeviceSpec, label?: string): DeviceSpec {
  const taken = new Set(spec.electrodes.map((electrode) => electrode.label))
  let name = label ?? `전극${spec.electrodes.length + 1}`
  let counter = spec.electrodes.length + 1
  while (taken.has(name)) {
    counter += 1
    name = `전극${counter}`
  }
  return {
    ...spec,
    electrodes: [...spec.electrodes, { label: name, interfaces: [] }],
    biases: [
      ...spec.biases,
      { name: `V${name}`, electrode: name, role: 'const', value: 0 },
    ],
  }
}

export function removeElectrode(spec: DeviceSpec, label: string): DeviceSpec {
  return {
    ...spec,
    electrodes: spec.electrodes.filter((electrode) => electrode.label !== label),
    biases: spec.biases.filter((bias) => bias.electrode !== label),
  }
}

export function renameElectrode(
  spec: DeviceSpec,
  from: string,
  to: string,
): DeviceSpec {
  if (!to || spec.electrodes.some((electrode) => electrode.label === to)) {
    return spec
  }
  return {
    ...spec,
    electrodes: spec.electrodes.map((electrode) =>
      electrode.label === from ? { ...electrode, label: to } : electrode,
    ),
    // 전압원이 이름으로 전극을 가리킨다. 같이 안 바꾸면 연결이 끊긴다.
    biases: spec.biases.map((bias) =>
      bias.electrode === from ? { ...bias, electrode: to } : bias,
    ),
  }
}

/**
 * 계면에 보여줄 이름. 사용자가 붙인 것이 있으면 그것, 없으면 구조에서 나온 열쇠.
 *
 * 열쇠 자체는 절대 바꾸지 않는다. 그것이 구조에서 나온 신원이라, 바꾸면 다음
 * 실행에서 같은 계면을 못 찾는다.
 */
export function nameOfInterface(spec: DeviceSpec, key: string): string {
  return nameFromMap(spec.interface_names, key)
}

/**
 * 이름표만 들고 찾는다.
 *
 * 화면은 `spec` 통째가 아니라 `spec.interface_names` 에만 매달려야 한다 —
 * 조건 전체에 매달면 전압을 한 글자 칠 때마다 새 참조가 되고, 그것이 단면
 * 그림의 다시 그리기로 번진다.
 */
export function nameFromMap(
  names: Record<string, string> | undefined,
  key: string,
): string {
  return names?.[key] ?? key
}

export function renameInterface(
  spec: DeviceSpec,
  key: string,
  name: string,
): DeviceSpec {
  const names = { ...(spec.interface_names ?? {}) }
  // 빈 이름이나 열쇠와 같은 이름은 저장하지 않는다. 그대로 두면 스펙에
  // 아무 뜻도 없는 항목이 쌓이고 비교 화면에 "다름" 으로 뜬다.
  //
  // **여기서 다듬지 않는다.** 치는 도중의 `"기판 "` 을 즉시 `"기판"` 으로
  // 만들면 공백을 칠 수 없어 두 단어 이름을 못 쓴다. 다듬는 것은 다 치고 난
  // 뒤(입력칸에서 벗어날 때) 한 번이다.
  if (!name.trim() || name === key) delete names[key]
  else names[key] = name.slice(0, 32)
  return { ...spec, interface_names: names }
}

/** 제출을 막을 이유들. 비어 있으면 보낼 수 있다. */
export function problemsOf(spec: DeviceSpec): string[] {
  const problems: string[] = []

  const sweeps = spec.biases.filter((bias) => bias.role === 'sweep')
  if (sweeps.length !== 1) {
    problems.push('스윕 전압원은 정확히 하나여야 합니다.')
  }

  const labels = spec.electrodes.map((electrode) => electrode.label)
  if (new Set(labels).size !== labels.length) {
    problems.push('전극 이름이 겹칩니다.')
  }

  const bare = spec.electrodes
    .filter((electrode) => electrode.interfaces.length === 0)
    .map((electrode) => electrode.label)
  if (bare.length) {
    problems.push(
      `계면이 안 붙은 전극이 있습니다: ${bare.join(', ')}. 단면에서 계면을 눌러 붙여 주세요.`,
    )
  }

  const claimed = new Map<string, string>()
  for (const electrode of spec.electrodes) {
    for (const key of electrode.interfaces) {
      const owner = claimed.get(key)
      if (owner) {
        problems.push(
          `계면 ${key} 이(가) 두 전극(${owner}, ${electrode.label})에 걸려 있습니다.`,
        )
      }
      claimed.set(key, electrode.label)
    }
  }

  const driven = new Map<string, string>()
  for (const bias of spec.biases) {
    const owner = driven.get(bias.electrode)
    if (owner) {
      problems.push(
        `전극 ${bias.electrode} 에 전압원이 둘(${owner}, ${bias.name}) 붙어 있습니다.`,
      )
    }
    driven.set(bias.electrode, bias.name)
    if (bias.role === 'step' && !(bias.values ?? []).length) {
      problems.push(`${bias.name}: 단계 전압을 하나 이상 넣어 주세요.`)
    }
  }

  const undriven = labels.filter((label) => !driven.has(label))
  if (undriven.length) {
    problems.push(`전압원이 없는 전극이 있습니다: ${undriven.join(', ')}`)
  }

  const total = pointCount(spec)
  if (total > MAX_TOTAL_POINTS) {
    problems.push(
      `바이어스 점이 ${total}개입니다. ${MAX_TOTAL_POINTS}개까지만 풀 수 있습니다.`,
    )
  }

  return problems
}
