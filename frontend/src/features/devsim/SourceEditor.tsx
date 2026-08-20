/**
 * 전극과 전압원을 손보는 패널.
 *
 * 두 계층을 일부러 나눠 두었다.
 *
 *   전극은 **구조에서 나온다.** 같은 금속 덩어리는 같은 전위라는 규칙이
 *   등전위를 이미 보장하므로, 사용자가 묶어 줄 것이 없다.
 *   전압원은 **사용자가 만든다.** 서로 다른 전극을 하나로 묶고 싶을 때
 *   (기판을 소스에 단다) 쓰는 자리가 여기다.
 */
import type { Bias, BiasRole, DeviceSpec } from '../../api/types'
import { CURVE_COLORS } from './IvChart'

interface Props {
  spec: DeviceSpec
  onChange: (spec: DeviceSpec) => void
  /** 화면에서 경계를 찍는 중인지. 켜면 지도에서 끌어 범위를 그린다. */
  picking: boolean
  onPickingChange: (picking: boolean) => void
}

function replaceBias(spec: DeviceSpec, index: number, bias: Bias): DeviceSpec {
  return {
    ...spec,
    biases: spec.biases.map((one, at) => (at === index ? bias : one)),
  }
}

/** 쉼표로 나눈 숫자 목록. 편집 중의 빈칸은 버린다. */
function parseValues(text: string): number[] {
  return text
    .split(',')
    .map((part) => Number(part.trim()))
    .filter((value) => Number.isFinite(value))
}

const ROLE_LABEL: Record<BiasRole, string> = {
  sweep: '스윕 (가로축)',
  step: '단계 (곡선족)',
  const: '고정',
}

export function SourceEditor({
  spec,
  onChange,
  picking,
  onPickingChange,
}: Props) {
  const used = new Map<string, string>()
  for (const bias of spec.biases) {
    for (const label of bias.electrodes) used.set(label, bias.name)
  }

  function renameElectrode(index: number, label: string) {
    const before = spec.electrodes[index].label
    onChange({
      ...spec,
      electrodes: spec.electrodes.map((electrode, at) =>
        at === index ? { ...electrode, label } : electrode,
      ),
      // 전압원이 이름으로 전극을 가리킨다. 같이 안 바꾸면 연결이 끊긴다.
      biases: spec.biases.map((bias) => ({
        ...bias,
        electrodes: bias.electrodes.map((one) => (one === before ? label : one)),
      })),
    })
  }

  function removeElectrode(index: number) {
    const label = spec.electrodes[index].label
    onChange({
      ...spec,
      electrodes: spec.electrodes.filter((_, at) => at !== index),
      biases: spec.biases.map((bias) => ({
        ...bias,
        electrodes: bias.electrodes.filter((one) => one !== label),
      })),
    })
  }

  function toggleConnection(index: number, label: string) {
    const bias = spec.biases[index]
    const connected = bias.electrodes.includes(label)
    // 다른 전압원에 걸려 있던 것은 떼어 온다. 한 전극이 두 전위를 가질 수는 없다.
    const cleaned = connected
      ? spec.biases
      : spec.biases.map((one) => ({
          ...one,
          electrodes: one.electrodes.filter((each) => each !== label),
        }))
    const next = connected
      ? bias.electrodes.filter((one) => one !== label)
      : [...cleaned[index].electrodes, label]
    onChange({
      ...spec,
      biases: cleaned.map((one, at) =>
        at === index ? { ...one, electrodes: next } : one,
      ),
    })
  }

  function changeRole(index: number, role: BiasRole) {
    const bias = spec.biases[index]
    onChange(
      replaceBias(spec, index, {
        ...bias,
        role,
        value: role === 'const' ? (bias.value ?? 0) : undefined,
        values: role === 'step' ? (bias.values ?? [0, 1, 2]) : undefined,
        sweep:
          role === 'sweep'
            ? (bias.sweep ?? { start: 0, stop: 2, step: 0.25 })
            : undefined,
      }),
    )
  }

  function addBias() {
    const name = `V${spec.biases.length + 1}`
    onChange({
      ...spec,
      biases: [...spec.biases, { name, electrodes: [], role: 'const', value: 0 }],
    })
  }

  return (
    <div className="source-editor">
      <section>
        <h3>전극</h3>
        <p className="hint">
          같은 금속 덩어리에 닿은 계면은 하나의 전극입니다. 이름은 바꿔도 됩니다.
        </p>
        <ul className="electrode-list">
          {spec.electrodes.map((electrode, index) => (
            <li key={`${electrode.origin}-${index}`}>
              <span
                className="swatch"
                style={{
                  background: CURVE_COLORS[index % CURVE_COLORS.length],
                }}
                aria-hidden="true"
              />
              <input
                value={electrode.label}
                aria-label={`전극 ${index + 1} 이름`}
                onChange={(event) => renameElectrode(index, event.target.value)}
              />
              <span className="origin">
                {electrode.origin === 'detected'
                  ? electrode.key
                  : electrode.origin === 'backside'
                    ? '뒷면'
                    : '직접 지정'}
              </span>
              <button
                type="button"
                className="ghost"
                onClick={() => removeElectrode(index)}
                aria-label={`${electrode.label} 전극 빼기`}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
        <button
          type="button"
          className={picking ? 'primary' : ''}
          onClick={() => onPickingChange(!picking)}
        >
          {picking ? '지도에서 범위를 끌어 주세요' : '화면에서 경계 찍기'}
        </button>
      </section>

      <section>
        <h3>전압원</h3>
        <p className="hint">
          전극을 하나의 전압원에 묶으면 같은 전위가 걸립니다. 스윕은 하나만 둘 수
          있고, 그것이 곡선의 가로축이 됩니다.
        </p>
        {spec.biases.map((bias, index) => (
          // data-role 을 둔다. 역할 <select> 안에는 세 선택지의 글자가 모두
          // 들어 있어, 글자로 고르면 어느 전압원이든 다 걸린다.
          <div className="bias" data-role={bias.role} key={index}>
            <div className="bias-head">
              <input
                className="bias-name"
                value={bias.name}
                aria-label={`전압원 ${index + 1} 이름`}
                onChange={(event) =>
                  onChange(
                    replaceBias(spec, index, { ...bias, name: event.target.value }),
                  )
                }
              />
              <select
                value={bias.role}
                aria-label={`${bias.name} 역할`}
                onChange={(event) =>
                  changeRole(index, event.target.value as BiasRole)
                }
              >
                {(['sweep', 'step', 'const'] as BiasRole[]).map((role) => (
                  <option key={role} value={role}>
                    {ROLE_LABEL[role]}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="ghost"
                aria-label={`${bias.name} 빼기`}
                onClick={() =>
                  onChange({
                    ...spec,
                    biases: spec.biases.filter((_, at) => at !== index),
                  })
                }
              >
                ×
              </button>
            </div>

            <div className="bias-electrodes">
              {spec.electrodes.map((electrode) => {
                const owner = used.get(electrode.label)
                const mine = owner === bias.name
                return (
                  <label key={electrode.label} className={mine ? 'on' : ''}>
                    <input
                      type="checkbox"
                      checked={mine}
                      onChange={() => toggleConnection(index, electrode.label)}
                    />
                    {electrode.label}
                    {owner && !mine ? <em> ({owner})</em> : null}
                  </label>
                )
              })}
            </div>

            {bias.role === 'const' ? (
              <label className="field">
                전압 (V)
                <input
                  type="number"
                  step="0.1"
                  value={bias.value ?? 0}
                  onChange={(event) =>
                    onChange(
                      replaceBias(spec, index, {
                        ...bias,
                        value: Number(event.target.value),
                      }),
                    )
                  }
                />
              </label>
            ) : null}

            {bias.role === 'step' ? (
              <label className="field">
                단계 전압 (쉼표로 구분, V)
                <input
                  value={(bias.values ?? []).join(', ')}
                  onChange={(event) =>
                    onChange(
                      replaceBias(spec, index, {
                        ...bias,
                        values: parseValues(event.target.value),
                      }),
                    )
                  }
                />
              </label>
            ) : null}

            {bias.role === 'sweep' ? (
              <div className="sweep-fields">
                {(['start', 'stop', 'step'] as const).map((field) => (
                  <label className="field" key={field}>
                    {field === 'start' ? '시작' : field === 'stop' ? '끝' : '간격'}
                    <input
                      type="number"
                      step="0.05"
                      value={bias.sweep?.[field] ?? 0}
                      onChange={(event) =>
                        onChange(
                          replaceBias(spec, index, {
                            ...bias,
                            sweep: {
                              ...(bias.sweep ?? { start: 0, stop: 2, step: 0.25 }),
                              [field]: Number(event.target.value),
                            },
                          }),
                        )
                      }
                    />
                  </label>
                ))}
              </div>
            ) : null}
          </div>
        ))}
        <button type="button" onClick={addBias}>
          전압원 추가
        </button>
      </section>
    </div>
  )
}
