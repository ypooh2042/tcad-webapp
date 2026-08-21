/**
 * 소자 해석 화면.
 *
 * 공정 편집 창과 일부러 분리했다. 여기로 넘어오는 것은 `.str` 구조 하나뿐이고,
 * 사용자는 파이썬을 보지 않는다 — 구조를 고르고, 단면에서 계면을 눌러 전극에
 * 붙이고, 전극마다 전압을 정해 스윕을 돌린다.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError } from '../../api/client'
import { devsim, plot } from '../../api/endpoints'
import type {
  DeviceSpec,
  DevSimInterface,
  GateModel,
  StructureSource,
  SurfaceResponse,
} from '../../api/types'
import { Splitter } from '../../components/Splitter'
import { useJob } from '../jobs/useJob'
import { usePanelWidth } from '../workspace/usePanelWidth'
import { CompareView } from './CompareView'
import {
  addElectrode,
  assignInterface,
  defaultSpec,
  pointCount,
  problemsOf,
  removeElectrode,
  renameElectrode,
  unassignInterface,
} from './deviceSpec'
import { ElectrodeMap } from './ElectrodeMap'
import { RunResult } from './RunResult'
import { colorOfIndex, SourceEditor } from './SourceEditor'

export interface Handoff {
  jobId: number
  sequence: number
}

interface Props {
  /** 공정 결과에서 "소자 해석" 을 눌러 넘어온 구조. */
  handoff: Handoff | null
  onHandoffUsed: () => void
}

interface Selection {
  jobId: number
  sequence: number
}

function messageOf(error: unknown): string {
  // ApiError.message 는 detail 이 문자열이면 그걸 그대로 쓴다. 객체 detail 까지
  // 여기서 풀지 않는다 — client.ts 가 이미 사람이 읽을 문구를 만들어 둔다.
  if (error instanceof ApiError) return error.message
  return error instanceof Error ? error.message : '알 수 없는 오류'
}

export function DevSimPage({ handoff, onHandoffUsed }: Props) {
  const [sources, setSources] = useState<StructureSource[]>([])
  const [selection, setSelection] = useState<Selection | null>(null)
  const [gateModel, setGateModel] = useState<GateModel>('semiconductor')

  const [interfaces, setInterfaces] = useState<DevSimInterface[]>([])
  const [surface, setSurface] = useState<SurfaceResponse | null>(null)
  const [spec, setSpec] = useState<DeviceSpec | null>(null)

  const [jobId, setJobId] = useState<number | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [tab, setTab] = useState<'run' | 'compare'>('run')
  const [runWidth, setRunWidth] = usePanelWidth('tcad.width.devsim', 420)

  const { job } = useJob(jobId)

  useEffect(() => {
    let cancelled = false
    devsim
      .structures()
      .then((found) => {
        if (cancelled) return
        setSources(found)
        setSelection((current) => {
          if (current) return current
          const first = found[0]
          if (!first || first.artifacts.length === 0) return null
          const last = first.artifacts[first.artifacts.length - 1]
          return { jobId: first.job_id, sequence: last.sequence }
        })
      })
      .catch((error) => {
        if (!cancelled) setMessage(messageOf(error))
      })
    return () => {
      cancelled = true
    }
  }, [])

  // 공정 결과에서 넘어온 구조를 받는다. 목록 로딩과 경쟁하지 않도록 따로 둔다.
  useEffect(() => {
    if (!handoff) return
    setSelection({ jobId: handoff.jobId, sequence: handoff.sequence })
    setTab('run')
    onHandoffUsed()
  }, [handoff, onHandoffUsed])

  // 구조가 바뀌면 계면과 조건을 처음부터 다시 만든다. 예전 조건을 그대로 두면
  // 이름은 남아 있는데 가리키는 계면이 없는 상태가 된다.
  useEffect(() => {
    if (!selection) return
    let cancelled = false
    setMessage(null)
    setInterfaces([])
    setSpec(null)
    Promise.all([
      devsim.interfaces(selection.jobId, selection.sequence, gateModel),
      plot.surface(selection.jobId, selection.sequence, null),
    ])
      .then(([found, drawn]) => {
        if (cancelled) return
        setInterfaces(found.interfaces)
        setSurface(drawn)
        setSpec(defaultSpec(found.interfaces))
        // 뒷면 후보는 반도체만 있어도 늘 딸려 온다. 그것까지 세면 금속이
        // 하나도 없는 단계에서도 "계면을 찾았다"가 되어 버린다.
        if (found.interfaces.every((one) => one.origin === 'backside')) {
          setMessage(
            '이 구조에는 금속 전극이 없습니다. 금속 배선까지 끝난 단계를 골라 주세요.',
          )
        }
      })
      .catch((error) => {
        if (!cancelled) setMessage(messageOf(error))
      })
    return () => {
      cancelled = true
    }
  }, [selection, gateModel])

  const problems = useMemo(() => (spec ? problemsOf(spec) : []), [spec])
  const points = useMemo(() => (spec ? pointCount(spec) : 0), [spec])

  const owners = useMemo(() => {
    const map: Record<string, string> = {}
    for (const electrode of spec?.electrodes ?? []) {
      for (const key of electrode.interfaces) map[key] = electrode.label
    }
    return map
  }, [spec])

  const chips = useMemo(
    () =>
      (spec?.electrodes ?? []).map((electrode, index) => ({
        label: electrode.label,
        color: colorOfIndex(index),
      })),
    [spec],
  )

  const describeInterface = useCallback(
    (key: string) => {
      const found = interfaces.find((one) => one.key === key)
      if (!found) return key
      const where = found.origin === 'backside' ? '뒷면 경계' : '금속 접촉'
      return `${where} · ${found.materials.join(', ')} · 변 ${found.edge_count}개`
    },
    [interfaces],
  )

  const edit = useCallback(
    (change: (current: DeviceSpec) => DeviceSpec) =>
      setSpec((current) => (current ? change(current) : current)),
    [],
  )

  const createFor = useCallback(
    (key: string) =>
      edit((current) => {
        const grown = addElectrode(current)
        const added = grown.electrodes[grown.electrodes.length - 1]
        return assignInterface(grown, key, added.label)
      }),
    [edit],
  )

  async function run() {
    if (!selection || !spec) return
    setMessage(null)
    try {
      const started = await devsim.submit(
        selection.jobId,
        selection.sequence,
        spec,
      )
      setJobId(started.id)
    } catch (error) {
      setMessage(messageOf(error))
    }
  }

  const busy = job !== null && (job.status === 'queued' || job.status === 'running')

  return (
    <div className="devsim">
      <div className="devsim-bar">
        <label className="field">
          구조
          <select
            value={selection ? `${selection.jobId}:${selection.sequence}` : ''}
            onChange={(event) => {
              const [job, sequence] = event.target.value.split(':')
              setSelection({ jobId: Number(job), sequence: Number(sequence) })
            }}
          >
            {sources.length === 0 ? <option value="">실행 결과가 없습니다</option> : null}
            {sources.map((source) =>
              source.artifacts.map((artifact) => (
                <option
                  key={`${source.job_id}:${artifact.sequence}`}
                  value={`${source.job_id}:${artifact.sequence}`}
                >
                  {source.source_path ?? `잡 ${source.job_id}`} · {artifact.filename}
                </option>
              )),
            )}
          </select>
        </label>

        <label className="field">
          폴리 게이트
          <select
            value={gateModel}
            onChange={(event) => setGateModel(event.target.value as GateModel)}
          >
            <option value="semiconductor">반도체로 해석</option>
            <option value="conductor">이상 도체로</option>
          </select>
        </label>

        <div className="devsim-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'run'}
            onClick={() => setTab('run')}
          >
            해석
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'compare'}
            onClick={() => setTab('compare')}
          >
            비교
          </button>
        </div>
      </div>

      {tab === 'compare' ? (
        <CompareView />
      ) : (
        // 폭은 인라인 스타일로 준다. 드래그 중에는 값이 계속 바뀌므로 CSS
        // 클래스로는 표현할 수 없다.
        <div
          className="devsim-body"
          style={{ gridTemplateColumns: `minmax(0, 1fr) auto ${runWidth}px` }}
        >
          <section className="devsim-map">
            {surface && spec ? (
              <>
                <ElectrodeMap
                  surface={surface}
                  interfaces={interfaces}
                  owners={owners}
                  electrodes={chips}
                  onAssign={(key, label) =>
                    edit((current) => assignInterface(current, key, label))
                  }
                  onUnassign={(key) =>
                    edit((current) => unassignInterface(current, key))
                  }
                  onCreate={createFor}
                />
                <SourceEditor
                  spec={spec}
                  onChange={setSpec}
                  onAddElectrode={() => edit(addElectrode)}
                  onRemoveElectrode={(label) =>
                    edit((current) => removeElectrode(current, label))
                  }
                  onRenameElectrode={(from, to) =>
                    edit((current) => renameElectrode(current, from, to))
                  }
                  describeInterface={describeInterface}
                />
              </>
            ) : (
              <p className="hint">구조를 불러오는 중…</p>
            )}
          </section>

          <Splitter width={runWidth} onChange={setRunWidth} label="해석 패널 폭" />

          <aside className="devsim-run">
            <div className="devsim-actions">
              <button
                type="button"
                className="primary"
                onClick={run}
                disabled={!spec || problems.length > 0 || busy}
              >
                해석 실행
              </button>
              <span className="hint">바이어스 점 {points}개</span>
            </div>
            {problems.length ? (
              <ul className="problems">
                {problems.map((problem) => (
                  <li key={problem}>{problem}</li>
                ))}
              </ul>
            ) : null}
            {message ? <p className="error">{message}</p> : null}
            <RunResult job={job} />
          </aside>
        </div>
      )}
    </div>
  )
}
