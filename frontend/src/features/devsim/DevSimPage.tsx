/**
 * 소자 해석 화면.
 *
 * 공정 편집 창과 일부러 분리했다. 여기로 넘어오는 것은 `.str` 구조 하나뿐이고,
 * 사용자는 파이썬을 보지 않는다 — 구조를 고르고, 단면에서 계면을 눌러 전극에
 * 붙이고, 전극마다 전압을 정해 스윕을 돌린다.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError } from '../../api/client'
import { devsim } from '../../api/endpoints'
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
  nameFromMap,
  removeElectrode,
  renameElectrode,
  renameInterface,
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
  /** 해석이 도는 중인지. 화면을 옮길 때 알려 주려고 바깥에서 본다. */
  onBusyChange?: (busy: boolean) => void
  /**
   * 지금 이 화면을 보고 있는지.
   *
   * 이 화면은 한 번 연 뒤에는 내려놓지 않는다(조건과 진행률을 잃지 않으려고).
   * 그래서 다시 열려도 마운트가 일어나지 않아, 그 사이에 공정을 돌려 새로
   * 생긴 구조가 목록에 안 나타났다. 다시 보일 때 목록을 새로 받는다.
   */
  active?: boolean
}

/** 지금 보고 있는 보관 구조의 id. */
type Selection = number

/** 조건을 맡기기 전에 기다리는 시간. 편집기 상태와 같은 값이다. */
const PERSIST_DEBOUNCE_MS = 1000

function messageOf(error: unknown): string {
  // ApiError.message 는 detail 이 문자열이면 그걸 그대로 쓴다. 객체 detail 까지
  // 여기서 풀지 않는다 — client.ts 가 이미 사람이 읽을 문구를 만들어 둔다.
  if (error instanceof ApiError) return error.message
  return error instanceof Error ? error.message : '알 수 없는 오류'
}

export function DevSimPage({
  handoff,
  onHandoffUsed,
  onBusyChange,
  active = true,
}: Props) {
  const [sources, setSources] = useState<StructureSource[]>([])
  const [selection, setSelection] = useState<Selection | null>(null)
  const [gateModel, setGateModel] = useState<GateModel>('semiconductor')

  const [interfaces, setInterfaces] = useState<DevSimInterface[]>([])
  const [surface, setSurface] = useState<SurfaceResponse | null>(null)
  const [spec, setSpec] = useState<DeviceSpec | null>(null)

  //: 조건을 서버에서 받아 오는 중인지. 받아 오기 전에 저장하면 기본값이
  //: 맡아 둔 조건을 덮어쓴다.
  const [restoring, setRestoring] = useState(false)
  const [jobId, setJobId] = useState<number | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [tab, setTab] = useState<'run' | 'compare'>('run')
  const [runWidth, setRunWidth] = usePanelWidth('tcad.width.devsim', 420)

  const { job } = useJob(jobId)

  useEffect(() => {
    if (!active) return
    let cancelled = false
    devsim
      .structures()
      .then((found) => {
        if (cancelled) return
        setSources(found)
        setSelection((current) => {
          // 고르고 있던 것이 아직 있으면 그대로 둔다. 목록을 다시 받을 때마다
          // 선택이 튀면 조건을 짜다 말고 처음으로 돌아간다.
          const alive = found.some((source) =>
            source.structures.some((one) => one.id === current),
          )
          if (current !== null && alive) return current
          const first = found[0]
          if (!first || first.structures.length === 0) return null
          // 마지막 단계부터 보여준다. 보통 그것이 완성된 소자다.
          return first.structures[first.structures.length - 1].id
        })
      })
      .catch((error) => {
        if (!cancelled) setMessage(messageOf(error))
      })
    return () => {
      cancelled = true
    }
  }, [active])

  // 공정 결과에서 넘어온 구조를 받는다.
  //
  // 결과 화면은 잡과 단계로 가리키므로 보관 구조에서 짝을 찾아야 한다. 목록이
  // 아직 안 왔을 수 있어 목록이 바뀔 때마다 다시 본다.
  useEffect(() => {
    if (!handoff) return
    for (const source of sources) {
      const match = source.structures.find(
        (one) =>
          one.job_id === handoff.jobId && one.sequence === handoff.sequence,
      )
      if (match) {
        setSelection(match.id)
        setTab('run')
        onHandoffUsed()
        return
      }
    }
    if (sources.length > 0) {
      // 목록은 왔는데 짝이 없다. 보관되지 않은 단계다.
      setMessage(
        '넘겨받은 단계에는 전극이 없어 해석할 수 없습니다. 금속 배선까지 끝난 단계를 골라 주세요.',
      )
      onHandoffUsed()
    }
  }, [handoff, sources, onHandoffUsed])

  // 구조가 바뀌면 계면과 조건을 처음부터 다시 만든다. 예전 조건을 그대로 두면
  // 이름은 남아 있는데 가리키는 계면이 없는 상태가 된다.
  useEffect(() => {
    if (selection === null) return
    let cancelled = false
    setMessage(null)
    setInterfaces([])
    setSpec(null)
    setRestoring(true)
    Promise.all([
      devsim.interfaces(selection, gateModel),
      devsim.surface(selection),
      // 맡아 둔 조건. 없거나 지금 구조에 안 맞으면 404 가 오고 기본값으로 간다.
      devsim.state(selection).catch(() => null),
    ])
      .then(([found, drawn, stored]) => {
        if (cancelled) return
        setInterfaces(found.interfaces)
        setSurface(drawn)
        setSpec(stored?.spec ?? defaultSpec(found.interfaces))
      })
      .catch((error) => {
        if (!cancelled) setMessage(messageOf(error))
      })
      .finally(() => {
        if (!cancelled) setRestoring(false)
      })
    return () => {
      cancelled = true
    }
  }, [selection, gateModel])

  /**
   * 짜 둔 조건을 맡긴다.
   *
   * 전극에 이름을 붙이고 계면을 붙이고 전압을 정하는 데는 손이 꽤 간다. 그런데
   * 새로고침 한 번에 전부 초기값으로 돌아갔다 — 편집기 탭을 맡아 두는 것과
   * 같은 이유다.
   *
   * 한 글자마다 보내지 않고 잠깐 기다린다. 그리고 **받아 오는 중에는 보내지
   * 않는다** — 기본값이 맡아 둔 조건을 덮어쓴다.
   */
  useEffect(() => {
    if (selection === null || spec === null || restoring) return
    const timer = window.setTimeout(() => {
      // 못 쓸 조건은 서버가 거절한다. 화면에서 이미 빨갛게 알려 주고 있으므로
      // 여기서 또 말하지 않는다.
      void devsim.saveState(selection, spec).catch(() => undefined)
    }, PERSIST_DEBOUNCE_MS)
    return () => window.clearTimeout(timer)
  }, [selection, spec, restoring])

  const problems = useMemo(() => (spec ? problemsOf(spec) : []), [spec])
  const points = useMemo(() => (spec ? pointCount(spec) : 0), [spec])

  // 아래 셋은 **`spec` 통째가 아니라 실제로 읽는 부분**에만 매단다.
  //
  // `spec` 에 걸면 전압을 한 글자 칠 때마다 새 참조가 되고, 그것이 그대로
  // 단면 그림의 다시 그리기로 번진다 — 내용은 하나도 안 바뀌었는데도. 조건을
  // 불변으로 갱신하므로(`{...spec, biases: ...}`) 전극을 안 건드린 갱신에서는
  // `spec.electrodes` 가 같은 배열 그대로다.
  const electrodes = spec?.electrodes
  const interfaceNames = spec?.interface_names

  const owners = useMemo(() => {
    const map: Record<string, string> = {}
    for (const electrode of electrodes ?? []) {
      for (const key of electrode.interfaces) map[key] = electrode.label
    }
    return map
  }, [electrodes])

  const chips = useMemo(
    () =>
      (electrodes ?? []).map((electrode, index) => ({
        label: electrode.label,
        color: colorOfIndex(index),
      })),
    [electrodes],
  )

  const describeInterface = useCallback(
    (key: string) => {
      const found = interfaces.find((one) => one.key === key)
      if (!found) return key
      const where = found.origin === 'backside' ? '뒷면 경계' : '금속 접촉'
      return `${key} · ${where} · ${found.materials.join(', ')} · 변 ${found.edge_count}개`
    },
    [interfaces],
  )

  const nameOf = useCallback(
    (key: string) => nameFromMap(interfaceNames, key),
    [interfaceNames],
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
    if (selection === null || !spec) return
    setMessage(null)
    try {
      const started = await devsim.submit(selection, spec)
      setJobId(started.id)
    } catch (error) {
      setMessage(messageOf(error))
    }
  }

  const busy = job !== null && (job.status === 'queued' || job.status === 'running')

  useEffect(() => {
    onBusyChange?.(busy)
  }, [busy, onBusyChange])

  return (
    <div className="devsim">
      <div className="devsim-bar">
        <label className="field">
          구조
          <select
            value={selection ?? ''}
            onChange={(event) => setSelection(Number(event.target.value))}
          >
            {sources.length === 0 ? (
              <option value="">전극이 있는 실행 결과가 없습니다</option>
            ) : null}
            {sources.map((source) => (
              <optgroup key={source.source_path} label={source.source_path}>
                {source.structures.map((one) => (
                  <option key={one.id} value={one.id}>
                    {one.filename}
                  </option>
                ))}
              </optgroup>
            ))}
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

        <p className="notice">
          <strong>알루미늄이 실리콘 또는 폴리실리콘에 닿은 계면</strong>만 전극으로
          인식합니다. 금속 배선까지 끝나 그런 계면이 생긴 단계만 위 목록에
          나옵니다.
        </p>

        {gateModel === 'conductor' ? (
          <p className="notice caution">
            polysilicon 층을 저항이 0인 완전 도체로 인식합니다. 결과가 크게 달라질
            수 있습니다.
          </p>
        ) : null}

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
                  nameOf={nameOf}
                  onRename={(key, name) =>
                    edit((current) => renameInterface(current, key, name))
                  }
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
                  nameOf={nameOf}
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
