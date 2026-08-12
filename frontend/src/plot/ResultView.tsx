/**
 * 결과 보기.
 *
 * 산출물 하나가 공정 한 단계다. `structure out=` 이 나온 순서대로 저장되어
 * 있으므로, 순번을 훑으면 공정이 진행되는 모습을 그대로 볼 수 있다. 이름순으로
 * 정렬하면 그 순서가 깨진다 — 그래서 서버가 준 sequence 를 그대로 쓴다.
 *
 * **물리량 고르기가 두 군데로 나뉜다.** 보는 대상이 다르기 때문이다:
 *
 *     구조 단면(2D)  = 콤보박스 하나. 값을 색으로 칠하는 그림이라 한 번에
 *                      하나만 의미가 있다. "재질" 을 고르면 값 대신 층을
 *                      칠한다 — 이때는 물리량을 보내지 않아야 서버가 요소를
 *                      버리지 않고 층이 다 나온다.
 *     수직선 프로파일 = 체크박스 여럿. chem 과 active 를 나란히 봐야 얼마나
 *                      활성화됐는지 알고, net_doping 을 겹쳐야 접합이 보인다.
 *
 * 둘을 한 상태로 묶으면 단면 색을 바꾸려다 그래프가 통째로 바뀐다.
 */
import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { plot } from '../api/endpoints'
import type {
  Artifact,
  ProfilePoint,
  StructureSummary,
  SurfaceResponse,
} from '../api/types'
import { ProfileChart, type Series } from './ProfileChart'
import { SurfaceView } from './SurfaceView'

/** 물리량별 선 색. 재질은 배경 띠가 맡으므로 선 색은 전부 물리량 몫이다. */
const SERIES_COLORS = [
  '#4a9eff',
  '#a55eea',
  '#4ade80',
  '#ffd93d',
  '#ff6b6b',
  '#22d3ee',
]

/** 값 대신 재질로 칠하는 보기. 물리량 이름과 겹치지 않는다. */
const MATERIAL_VIEW = '재질'

interface Props {
  jobId: number
  artifacts: Artifact[]
}

export function ResultView({ jobId, artifacts }: Props) {
  const [step, setStep] = useState(0)
  const [summary, setSummary] = useState<StructureSummary | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  //: 구조 단면에 무엇을 칠할지. 수직선 프로파일과 따로 둔다 — 묶으면 단면 색을
  //  바꾸려다 그래프가 통째로 바뀐다. MATERIAL_VIEW 면 재질로 칠한다.
  const [surfaceView, setSurfaceView] = useState<string>(MATERIAL_VIEW)
  const [series, setSeries] = useState<Series[]>([])
  const [surface, setSurface] = useState<SurfaceResponse | null>(null)
  const [cutX, setCutX] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const current = artifacts[Math.min(step, artifacts.length - 1)]
  const sequence = current?.sequence ?? null

  const report = useCallback((caught: unknown) => {
    setError(caught instanceof ApiError ? caught.message : '결과를 읽지 못했습니다')
  }, [])

  // 단계가 바뀌면 무엇을 그릴 수 있는지부터 다시 묻는다. 단계마다 존재하는
  // 물리량이 다르다 — 주입 전 구조에는 arsenic 컬럼이 아예 없다.
  useEffect(() => {
    if (sequence === null) return
    let cancelled = false

    setError(null)
    plot
      .summary(jobId, sequence)
      .then((next) => {
        if (cancelled) return
        setSummary(next)
        setSelected((previous) => {
          // 이 단계에 없는 물리량은 떨어뜨린다. 하나도 안 남으면 첫 번째를
          // 골라 준다 — 빈 차트로 시작하면 무엇을 해야 할지 알기 어렵다.
          const kept = previous.filter((name) => next.quantities.includes(name))
          return kept.length ? kept : next.quantities.slice(0, 1)
        })
        setSurfaceView((previous) => {
          // **기본은 재질이다.** 구조가 어떻게 생겼는지부터 보는 것이 자연스럽고,
          // 값 분포는 그다음이다. 물리량이 없는 구조에서도 언제나 볼 수 있다.
          if (previous === MATERIAL_VIEW) return previous
          // 이 단계에 없는 물리량을 보고 있었으면 재질로 돌아간다.
          if (previous && next.quantities.includes(previous)) return previous
          return MATERIAL_VIEW
        })
        // 2D 는 가로 한가운데를 기본 컷으로 잡는다.
        setCutX((previous) =>
          next.dimension === 2
            ? (previous ?? (next.bounds.x_min + next.bounds.x_max) / 2)
            : null,
        )
      })
      .catch(report)

    return () => {
      cancelled = true
    }
  }, [jobId, sequence, report])

  // 고른 물리량을 모두 읽는다. 같은 단계·같은 컷이어야 비교가 의미를 가진다.
  useEffect(() => {
    if (sequence === null || !summary || selected.length === 0) {
      setSeries([])
      return
    }
    if (summary.dimension === 2 && cutX === null) return
    let cancelled = false

    Promise.all(
      selected.map((name) =>
        plot
          .profile(
            jobId,
            sequence,
            name,
            summary.dimension === 2 ? cutX! : undefined,
          )
          .then((next) => ({ name, points: next.points }))
          .catch(() => null),
      ),
    ).then((results) => {
      if (cancelled) return
      setSeries(
        results
          .filter((r): r is { name: string; points: ProfilePoint[] } => Boolean(r))
          .map((r, index) => ({
            label: r.name,
            points: r.points,
            color: SERIES_COLORS[index % SERIES_COLORS.length]!,
          })),
      )
    })

    return () => {
      cancelled = true
    }
  }, [jobId, sequence, summary, selected, cutX])

  // 단면은 컷 위치와 무관하다. cutX 를 의존성에 넣으면 컷을 옮길 때마다
  // 수천 개 삼각형을 다시 받는다.
  useEffect(() => {
    if (sequence === null || !summary) return
    if (summary.dimension !== 2) {
      setSurface(null)
      return
    }
    let cancelled = false

    plot
      .surface(
        jobId,
        sequence,
        surfaceView === MATERIAL_VIEW ? null : surfaceView,
      )
      .then((next) => !cancelled && setSurface(next))
      .catch(report)

    return () => {
      cancelled = true
    }
  }, [jobId, sequence, summary, surfaceView, report])

  if (artifacts.length === 0) {
    return <p className="muted">저장된 구조가 없습니다. `structure out=` 을 넣어 보세요.</p>
  }

  function toggle(name: string, on: boolean) {
    setSelected((current) =>
      on ? [...current, name] : current.filter((item) => item !== name),
    )
  }

  return (
    <div className="result">
      <div className="scrubber">
        {/* 슬라이더는 단계가 둘 이상일 때만 의미가 있다. 다만 파일 이름은
            언제나 보여야 한다 — 지금 무엇을 보고 있는지 알 수 있는 유일한
            단서다. */}
        {artifacts.length > 1 && (
          <>
            <label htmlFor="step">공정 단계</label>
            <input
              id="step"
              type="range"
              min={0}
              max={artifacts.length - 1}
              value={step}
              onChange={(event) => setStep(Number(event.target.value))}
            />
          </>
        )}
        <span className="muted">
          {artifacts.length > 1 && `${step + 1}/${artifacts.length} · `}
          {current?.filename}
        </span>
      </div>

      <div className="controls">
        {/* 구조 단면은 값을 색으로 칠하는 그림이라 한 번에 하나만 의미가 있다.
            아래 체크박스(수직선 프로파일)와 일부러 따로 둔다. */}
        {summary?.dimension === 2 && (
          <>
            <label htmlFor="surface-quantity">구조 단면</label>
            <select
              id="surface-quantity"
              value={surfaceView}
              onChange={(event) => setSurfaceView(event.target.value)}
            >
              {/* 재질은 값이 없어도 볼 수 있으므로 언제나 맨 위에 둔다. */}
              <option value={MATERIAL_VIEW}>{MATERIAL_VIEW}</option>
              {summary.quantities.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </>
        )}
        {summary && (
          <span className="muted">
            {summary.dimension}D · 노드 {summary.node_count}
          </span>
        )}
      </div>

      {error && <p role="alert" className="error">{error}</p>}

      {summary?.warnings.map((warning) => (
        // 파서 경고를 삼키면 이상한 그림의 원인을 알 수 없다.
        <p key={warning} className="muted">⚠ {warning}</p>
      ))}

      {surface && (
        <SurfaceView surface={surface} cutX={cutX} onPickCut={setCutX} />
      )}

      {summary?.dimension === 2 && cutX !== null && (
        <p className="muted">
          단면을 클릭하면 그 위치의 깊이 프로파일을 봅니다 (x = {cutX.toFixed(3)} µm)
        </p>
      )}

      {/* 그래프 **바로 위**에 둔다. 2D 단면이 사이에 끼면 체크박스를 누를
          때마다 스크롤을 오르내려야 한다. */}
      <fieldset className="quantities">
        <legend>수직선 물리량</legend>
        {summary?.quantities.map((name) => (
          <label key={name}>
            <input
              type="checkbox"
              checked={selected.includes(name)}
              onChange={(event) => toggle(name, event.target.checked)}
            />
            {name}
          </label>
        ))}
      </fieldset>

      {selected.length === 0 ? (
        <p className="muted">물리량을 하나 이상 골라 주세요.</p>
      ) : (
        <ProfileChart series={series} />
      )}
    </div>
  )
}
