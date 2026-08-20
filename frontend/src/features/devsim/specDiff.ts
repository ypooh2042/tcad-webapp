/**
 * 고른 해석들의 조건에서 **다른 것만** 뽑는다.
 *
 * 비교 화면의 핵심이 여기다. 곡선 두 개를 겹쳐 놓고 "왜 다르지" 를 사용자가
 * 되짚게 하면, 조건을 하나씩 열어 눈으로 대조하게 된다. 같은 항목은 지우고
 * 다른 항목만 남기면 원인 후보가 바로 좁혀진다.
 */
import type { Bias, DeviceSpec } from '../../api/types'

export interface DiffRow {
  field: string
  /** 런 순서대로의 값. 사람이 읽을 문자열이다. */
  values: string[]
}

function formatSweep(bias: Bias): string {
  if (bias.role === 'const') return `${bias.value ?? 0} V 고정`
  if (bias.role === 'step') return `${(bias.values ?? []).join(', ')} V 단계`
  if (!bias.sweep) return '스윕'
  const { start, stop, step } = bias.sweep
  return `${start} → ${stop} V, ${step} V 간격`
}

function describe(spec: DeviceSpec): Map<string, string> {
  const fields = new Map<string, string>()
  fields.set(
    '폴리 게이트',
    spec.gate_model === 'conductor' ? '이상 도체' : '반도체',
  )
  fields.set('온도', `${spec.temperature_k ?? 300} K`)
  fields.set(
    '전극',
    spec.electrodes
      .map((electrode) => electrode.label)
      .sort()
      .join(', '),
  )
  for (const bias of spec.biases) {
    fields.set(
      `전압원 ${bias.name}`,
      `${[...bias.electrodes].sort().join('+') || '연결 없음'} · ${formatSweep(bias)}`,
    )
  }
  return fields
}

export interface Compared {
  label: string
  structure: string
  spec: DeviceSpec
}

/**
 * 다른 항목만. 한쪽에만 있는 항목도 다른 것으로 친다 — 전압원 하나가 빠진 것이
 * 곡선이 달라진 이유일 수 있다.
 */
export function diffOf(runs: Compared[]): DiffRow[] {
  if (runs.length < 2) return []
  const described = runs.map((run) => describe(run.spec))
  const fields = new Set<string>()
  for (const one of described) for (const key of one.keys()) fields.add(key)

  const rows: DiffRow[] = []
  for (const field of fields) {
    const values = described.map((one) => one.get(field) ?? '—')
    if (new Set(values).size === 1) continue
    rows.push({ field, values })
  }

  // 구조가 다른 것은 거의 늘 가장 중요한 차이다. 맨 위에 둔다.
  const structures = runs.map((run) => run.structure)
  if (new Set(structures).size > 1) {
    rows.unshift({ field: '구조', values: structures })
  }
  return rows
}
