/**
 * 전극과 전압원 패널.
 *
 * 세 계층이 있고 사용자가 손대는 자리가 각각 다르다.
 *
 *   계면  **구조에서 나온다.** 금속 접촉 하나, 뒷면 하나. 목록에 없는 경계를
 *         전극으로 만들 수는 없다 — 반도체 표면 아무 데나 접촉을 걸면 소자가
 *         아니라 수치 실험이 된다.
 *   전극  여기 목록에서 만들고·지우고·이름을 붙인다. **어느 계면이 붙느냐는
 *         단면 그림에서 정한다** — 이름만 보고 고르면 그게 구조의 어디인지
 *         알 수 없다.
 *   전압원 전극마다 정확히 하나. 어느 전극을 모는지는 못 바꾼다.
 */
import type { Bias, BiasRole, DeviceSpec } from '../../api/types'
import { CURVE_COLORS } from './IvChart'
import { sweepGap } from './deviceSpec'
import { NameField } from './NameField'
import { NumberField, NumberListField } from './NumberField'

interface Props {
  spec: DeviceSpec
  onChange: (spec: DeviceSpec) => void
  onAddElectrode: () => void
  onRemoveElectrode: (label: string) => void
  onRenameElectrode: (from: string, to: string) => void
  /** 계면 열쇠 → 사람이 읽을 설명. 전극 옆에 붙여 보여준다. */
  describeInterface: (key: string) => string
  /** 계면에 붙은 이름. 단면에서 바꾼 것이 여기에도 보여야 한다. */
  nameOf: (key: string) => string
}

function replaceBias(spec: DeviceSpec, index: number, bias: Bias): DeviceSpec {
  return {
    ...spec,
    biases: spec.biases.map((one, at) => (at === index ? bias : one)),
  }
}

const ROLE_LABEL: Record<BiasRole, string> = {
  sweep: '스윕 (가로축)',
  step: '단계 (곡선족)',
  const: '고정',
  float: '부유 (풀어서 얻음)',
}

const DEFAULT_SWEEP = { start: 0, stop: 2.5, points: 6 }

function sweepOf(bias: Bias) {
  return bias.sweep ?? DEFAULT_SWEEP
}

function formatGap(sweep: { start: number; stop: number; points: number }): string {
  const gap = sweepGap(sweep.start, sweep.stop, sweep.points)
  if (gap === 0) return '한 점뿐이라'
  return `${Number(Math.abs(gap).toPrecision(4))}V`
}

export function colorOfIndex(index: number): string {
  return CURVE_COLORS[index % CURVE_COLORS.length]
}

export function SourceEditor({
  spec,
  onChange,
  onAddElectrode,
  onRemoveElectrode,
  onRenameElectrode,
  describeInterface,
  nameOf,
}: Props) {
  const colorOf = new Map(
    spec.electrodes.map((electrode, index) => [
      electrode.label,
      colorOfIndex(index),
    ]),
  )

  return (
    <div className="source-editor">
      <section>
        <h3>전극</h3>
        <p className="hint">
          단면에서 계면을 눌러 전극에 붙입니다. 한 계면은 한 전극에만 속하고, 한
          전극에 여러 계면을 붙이면 그 계면들이 같은 전위가 됩니다.
        </p>
        <ul className="electrode-list">
          {spec.electrodes.map((electrode, index) => (
            // 키를 이름으로 삼지 않는다. 이름은 사용자가 고치는 값이라, 키로
            // 쓰면 한 글자 칠 때마다 항목이 새로 만들어져 입력칸이 포커스를
            // 잃는다(실제로 한 글자밖에 못 쳐졌다). 전극은 순서가 바뀌지
            // 않으므로 자리 번호로 충분하다.
            <li key={index}>
              <span
                className="swatch"
                style={{ background: colorOfIndex(index) }}
                aria-hidden="true"
              />
              <NameField
                label={`전극 ${index + 1} 이름`}
                value={electrode.label}
                onCommit={(name) => onRenameElectrode(electrode.label, name)}
              />
              <span className="attached">
                {electrode.interfaces.length === 0 ? (
                  <em className="empty">계면 없음</em>
                ) : (
                  electrode.interfaces.map((key) => (
                    <span className="chip" key={key} title={describeInterface(key)}>
                      {nameOf(key)}
                    </span>
                  ))
                )}
              </span>
              <button
                type="button"
                className="ghost"
                onClick={() => onRemoveElectrode(electrode.label)}
                aria-label={`${electrode.label} 전극 빼기`}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
        <button type="button" onClick={onAddElectrode}>
          전극 추가
        </button>
      </section>

      <section>
        <h3>전압원</h3>
        <p className="hint">
          전극마다 전압원이 하나씩 있습니다. 스윕은 하나만 둘 수 있고 그것이
          곡선의 가로축이 됩니다.
        </p>
        {spec.biases.map((bias, index) => (
          // data-role 을 둔다. 역할 <select> 안에는 세 선택지의 글자가 모두
          // 들어 있어, 글자로 고르면 어느 전압원이든 다 걸린다.
          <div className="bias" data-role={bias.role} key={index}>
            <div className="bias-head">
              <span
                className="swatch"
                style={{ background: colorOf.get(bias.electrode) ?? '#888' }}
                aria-hidden="true"
              />
              <NameField
                className="bias-name"
                label={`전압원 ${index + 1} 이름`}
                value={bias.name}
                onCommit={(name) =>
                  onChange(replaceBias(spec, index, { ...bias, name }))
                }
              />
              <span className="drives" title="이 전압원이 모는 전극">
                → {bias.electrode}
              </span>
              <select
                value={bias.role}
                aria-label={`${bias.name} 역할`}
                onChange={(event) => {
                  const role = event.target.value as BiasRole
                  onChange(
                    replaceBias(spec, index, {
                      ...bias,
                      role,
                      value: role === 'const' ? (bias.value ?? 0) : undefined,
                      values: role === 'step' ? (bias.values ?? [1, 2, 4]) : undefined,
                      sweep: role === 'sweep' ? (bias.sweep ?? DEFAULT_SWEEP) : undefined,
                    }),
                  )
                }}
              >
                {(['sweep', 'step', 'const', 'float'] as BiasRole[]).map((role) => (
                  <option key={role} value={role}>
                    {ROLE_LABEL[role]}
                  </option>
                ))}
              </select>
            </div>

            {bias.role === 'const' ? (
              <NumberField
                label="전압 (V)"
                value={bias.value ?? 0}
                onChange={(value) =>
                  onChange(replaceBias(spec, index, { ...bias, value }))
                }
              />
            ) : null}

            {bias.role === 'step' ? (
              <NumberListField
                label="단계 전압 (쉼표로 구분, V)"
                values={bias.values ?? []}
                onChange={(values) =>
                  onChange(replaceBias(spec, index, { ...bias, values }))
                }
              />
            ) : null}

            {bias.role === 'float' ? (
              /* 부유는 넣을 값이 없다. 대신 무엇을 하는 것인지 적어 준다 —
                 값 칸이 사라지기만 하면 고장으로 보인다. */
              <p className="hint">
                전압을 주지 않고 <strong>풀어서 얻습니다.</strong> 인버터의 출력처럼
                회로가 스스로 정하는 전위에 씁니다. 이 전극에 전류 경로가 둘 이상
                있어야 합니다.
              </p>
            ) : null}

            {bias.role === 'sweep' ? (
              <>
                <div className="sweep-fields">
                  {(['start', 'stop'] as const).map((field) => (
                    <NumberField
                      key={field}
                      label={field === 'start' ? '시작 (V)' : '끝 (V)'}
                      value={bias.sweep?.[field] ?? 0}
                      onChange={(value) =>
                        onChange(
                          replaceBias(spec, index, {
                            ...bias,
                            sweep: { ...sweepOf(bias), [field]: value },
                          }),
                        )
                      }
                    />
                  ))}
                  <NumberField
                    label="점 개수"
                    value={sweepOf(bias).points}
                    onChange={(value) =>
                      onChange(
                        replaceBias(spec, index, {
                          ...bias,
                          sweep: {
                            ...sweepOf(bias),
                            points: Math.max(1, Math.round(value)),
                          },
                        }),
                      )
                    }
                  />
                </div>
                {/* 점 개수만 보면 얼마나 촘촘한지 감이 안 온다. 간격은 계산해
                    보여주기만 하고 고치게 하지 않는다 — 둘 다 고칠 수 있으면
                    어느 쪽이 기준인지 알 수 없다. */}
                <p className="hint">
                  {formatGap(sweepOf(bias))} 간격 · {sweepOf(bias).points}점
                </p>
              </>
            ) : null}
          </div>
        ))}
      </section>
    </div>
  )
}
