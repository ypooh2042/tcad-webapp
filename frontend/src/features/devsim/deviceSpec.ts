/**
 * 해석 조건을 만들고 검사한다.
 *
 * 검사는 서버에도 있다(`app/devsim/spec.py`). 여기 것은 **먼저** 알려 주기 위한
 * 것이다 — 제출해 봐야 422 를 받는 것과, 실행 버튼 옆에 무엇이 잘못됐는지 떠
 * 있는 것은 다르다. 규칙이 갈리면 서버 쪽이 맞다.
 */
import type { Bias, DeviceSpec, DevSimElectrode } from '../../api/types'

/** 서버의 `MAX_TOTAL_POINTS` 와 같아야 한다. */
export const MAX_TOTAL_POINTS = 300

/** 기본 게이트 단계. 문턱 아래부터 확실한 온 상태까지 걸친다. */
const DEFAULT_STEPS = [0, 1, 2]

const DEFAULT_SWEEP = { start: 0, stop: 2, step: 0.25 }

/**
 * 스윕이 훑는 전압. 서버의 `sweep_values` 와 같은 규칙이다.
 *
 * 간격이 구간을 딱 나누지 않아도 마지막 점은 `stop` 이다 — 목표 전압에 못 미치고
 * 끝나면 정작 보고 싶은 지점의 값을 못 얻는다.
 */
export function sweepValues(
  start: number,
  stop: number,
  step: number,
): number[] {
  if (!(step > 0)) return []
  if (start === stop) return [start]
  const direction = stop > start ? 1 : -1
  const span = Math.abs(stop - start)
  const count = Math.floor(span / step)
  const values: number[] = []
  for (let i = 0; i <= count; i++) values.push(start + direction * step * i)
  if (Math.abs(values[values.length - 1] - stop) > step * 1e-9) values.push(stop)
  else values[values.length - 1] = stop
  return values
}

function pointsOf(bias: Bias): number[] {
  if (bias.role === 'const') return [bias.value ?? 0]
  if (bias.role === 'step') return bias.values ?? []
  if (!bias.sweep) return []
  return sweepValues(bias.sweep.start, bias.sweep.stop, bias.sweep.step)
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
 * 자동으로 찾은 전극에서 쓸 만한 첫 조건을 만든다.
 *
 * 게이트는 곡선족을 만드는 단계로, 게이트가 아닌 것 중 가장 오른쪽을 스윕으로
 * 놓는다. 나머지는 접지에 함께 묶는다 — MOSFET 출력 특성이 늘 그 모양이다.
 */
export function defaultSpec(electrodes: DevSimElectrode[]): DeviceSpec {
  const spec: DeviceSpec = {
    label: '기본 조건',
    electrodes: electrodes.map((electrode) => ({
      origin: electrode.origin,
      key: electrode.origin === 'detected' ? electrode.key : undefined,
      label: electrode.key,
    })),
    biases: [],
    gate_model: 'semiconductor',
  }
  if (electrodes.length === 0) return spec

  const gates = electrodes.filter(
    (electrode) => electrode.key === 'gate' || electrode.kind === 'insulator',
  )
  const others = electrodes.filter((electrode) => !gates.includes(electrode))
  const ordered = [...others].sort(
    (a, b) => a.extent.x_min + a.extent.x_max - (b.extent.x_min + b.extent.x_max),
  )
  const swept = ordered.pop()
  const grounded = ordered

  const biases: Bias[] = []
  if (grounded.length) {
    biases.push({
      name: 'V0',
      electrodes: grounded.map((electrode) => electrode.key),
      role: 'const',
      value: 0,
    })
  }
  for (const gate of gates) {
    biases.push({
      name: `V${gate.key}`,
      electrodes: [gate.key],
      role: 'step',
      values: [...DEFAULT_STEPS],
    })
  }
  if (swept) {
    biases.push({
      name: `V${swept.key}`,
      electrodes: [swept.key],
      role: 'sweep',
      sweep: { ...DEFAULT_SWEEP },
    })
  }
  return { ...spec, biases }
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

  const claimed = new Map<string, string>()
  for (const bias of spec.biases) {
    if (bias.electrodes.length === 0) {
      problems.push(`${bias.name}: 연결된 전극이 없습니다.`)
    }
    for (const label of bias.electrodes) {
      const owner = claimed.get(label)
      if (owner) {
        problems.push(
          `전극 ${label} 이(가) 두 전압원(${owner}, ${bias.name})에 걸려 있습니다.`,
        )
      }
      claimed.set(label, bias.name)
    }
    if (bias.role === 'step' && !(bias.values ?? []).length) {
      problems.push(`${bias.name}: 단계 전압을 하나 이상 넣어 주세요.`)
    }
  }

  const loose = labels.filter((label) => !claimed.has(label))
  if (loose.length) {
    problems.push(`전압원에 안 걸린 전극이 있습니다: ${loose.join(', ')}`)
  }

  const total = pointCount(spec)
  if (total > MAX_TOTAL_POINTS) {
    problems.push(
      `바이어스 점이 ${total}개입니다. ${MAX_TOTAL_POINTS}개까지만 풀 수 있습니다.`,
    )
  }

  return problems
}
