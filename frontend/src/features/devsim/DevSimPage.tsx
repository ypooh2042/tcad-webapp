/**
 * 소자 해석 화면.
 *
 * 공정 편집 창과 일부러 분리했다. 여기로 넘어오는 것은 `.str` 구조 하나뿐이고,
 * 사용자는 파이썬을 보지 않는다 — 구조를 고르고, 전극에 전압원을 붙이고,
 * 스윕을 돌린다.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError } from '../../api/client'
import { devsim, plot } from '../../api/endpoints'
import type {
  DeviceSpec,
  DevSimElectrode,
  GateModel,
  StructureSource,
  SurfaceResponse,
} from '../../api/types'
import { useJob } from '../jobs/useJob'
import { CompareView } from './CompareView'
import { defaultSpec, pointCount, problemsOf } from './deviceSpec'
import { ElectrodeMap, type PickedBox } from './ElectrodeMap'
import { RunResult } from './RunResult'
import { SourceEditor } from './SourceEditor'

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

  const [electrodes, setElectrodes] = useState<DevSimElectrode[]>([])
  const [surface, setSurface] = useState<SurfaceResponse | null>(null)
  const [spec, setSpec] = useState<DeviceSpec | null>(null)
  const [picking, setPicking] = useState(false)

  const [jobId, setJobId] = useState<number | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [tab, setTab] = useState<'run' | 'compare'>('run')

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

  // 구조가 바뀌면 전극과 조건을 처음부터 다시 만든다. 예전 조건을 그대로 두면
  // 이름은 남아 있는데 가리키는 전극이 없는 상태가 된다.
  useEffect(() => {
    if (!selection) return
    let cancelled = false
    setMessage(null)
    setElectrodes([])
    setSpec(null)
    Promise.all([
      devsim.electrodes(selection.jobId, selection.sequence, gateModel),
      plot.surface(selection.jobId, selection.sequence, null),
    ])
      .then(([found, drawn]) => {
        if (cancelled) return
        setElectrodes(found.electrodes)
        setSurface(drawn)
        setSpec(defaultSpec(found.electrodes))
        // 뒷면 후보는 반도체만 있어도 늘 딸려 온다. 그것까지 세면 금속이
        // 하나도 없는 단계에서도 "전극을 찾았다"가 되어 버린다.
        const metal = found.electrodes.filter(
          (electrode) => electrode.origin === 'detected',
        )
        if (metal.length === 0) {
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

  const mapped = useMemo(() => {
    if (!spec) return []
    const byKey = new Map(electrodes.map((one) => [one.key, one]))
    return spec.electrodes.map((choice) => ({
      label: choice.label,
      segments:
        choice.origin === 'picked'
          ? boxOutline(choice.box)
          : (byKey.get(choice.key ?? choice.label)?.segments ??
            byKey.get(choice.origin === 'backside' ? 'body' : '')?.segments ??
            []),
      active: true,
    }))
  }, [spec, electrodes])

  const addPicked = useCallback(
    (box: PickedBox) => {
      setPicking(false)
      setSpec((current) => {
        if (!current) return current
        let index = current.electrodes.length + 1
        while (current.electrodes.some((one) => one.label === `E${index}`)) index++
        return {
          ...current,
          electrodes: [
            ...current.electrodes,
            { origin: 'picked', label: `E${index}`, box },
          ],
        }
      })
    },
    [],
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
        <div className="devsim-body">
          <section className="devsim-map">
            {surface ? (
              <ElectrodeMap
                surface={surface}
                electrodes={mapped}
                picking={picking}
                onPick={addPicked}
              />
            ) : (
              <p className="hint">구조를 불러오는 중…</p>
            )}
            {spec ? (
              <SourceEditor
                spec={spec}
                onChange={setSpec}
                picking={picking}
                onPickingChange={setPicking}
              />
            ) : null}
          </section>

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

/** 직접 찍은 전극은 서버가 그 안의 경계를 골라낸다. 화면에는 상자를 그린다. */
function boxOutline(box?: {
  x_min: number
  x_max: number
  y_min: number
  y_max: number
}): number[][] {
  if (!box) return []
  const { x_min, x_max, y_min, y_max } = box
  return [
    [x_min, y_min, x_max, y_min],
    [x_max, y_min, x_max, y_max],
    [x_max, y_max, x_min, y_max],
    [x_min, y_max, x_min, y_min],
  ]
}
