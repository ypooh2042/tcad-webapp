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
import { useHoldRepeat } from '../components/useHoldRepeat'
import { useSettled } from '../components/useSettled'

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
//: 단계가 멎었다고 보는 시간. 꾹 누르기 반복 주기(150ms)보다 넉넉히 길어야
//: 중간 단계를 걸러낸다. 사람이 손을 뗀 뒤 이만큼은 기다려도 느껴지지 않는다.
const LOAD_SETTLE_MS = 250

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
  //: 격자 오버레이. 기본은 꺼짐 — 촘촘한 메시를 항상 얹으면 값이 묻힌다.
  const [showMesh, setShowMesh] = useState(false)

  const back = useHoldRepeat(() =>
    setStep((current) => Math.max(0, current - 1)),
  )
  const forward = useHoldRepeat(() =>
    setStep((current) => Math.min(artifacts.length - 1, current + 1)),
  )
  const [error, setError] = useState<string | null>(null)

  const current = artifacts[Math.min(step, artifacts.length - 1)]

  //: 화면에 보이는 단계와 **불러오는 단계를 분리한다.** 번호와 파일 이름은
  //: 곧바로 바뀌어야 누른 것이 느껴지고, 데이터는 멎은 뒤에 한 번만 받으면
  //: 된다. 지나치는 단계까지 받으면 단계당 요청 4개(요약·물리량·단면)가
  //: 그대로 곱해져 nginx 레이트 리밋(20 req/s)에 걸려 503 이 난다.
  const sequence = useSettled(current?.sequence ?? null, LOAD_SETTLE_MS)

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
        {/* 단계 이동은 버튼이다. 슬라이더는 한 칸씩 옮기기가 어렵고, 끝에
            닿았는지도 잡아 봐야 안다. 버튼은 끝에서 비활성으로 알려 준다.
            단계가 하나면 누를 데가 없으므로 아예 두지 않는다. 파일 이름은
            언제나 보여야 한다 — 지금 무엇을 보고 있는지 아는 유일한 단서다. */}
        {artifacts.length > 1 && (
          <>
            <span className="muted">공정 단계</span>
            {/* 꾹 누르면 연달아 넘어간다. 15단계짜리 공정을 한 칸씩 누르는
                것은 번거롭다. 범위를 넘지 않도록 clamp 는 여기서 한다 —
                반복 중에도 없는 단계를 서버에 묻지 않는다. */}
            <button {...back} disabled={step === 0}>
              « 이전
            </button>
            <button {...forward} disabled={step === artifacts.length - 1}>
              다음 »
            </button>
          </>
        )}
        <span className="muted">
          {artifacts.length > 1 && `${step + 1}/${artifacts.length} · `}
          {current?.filename}
        </span>
        {/* 번호는 곧바로 바뀌지만 데이터는 멎은 뒤에 온다. 그 사이를 알리지
            않으면 옛 단계의 그림을 새 단계의 것으로 읽게 된다. */}
        {current && sequence !== current.sequence && (
          <span className="muted">불러오는 중…</span>
        )}
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
            {/* 격자는 값과 무관한 별개의 보기라 콤보박스가 아니라 체크박스다.
                구조가 얼마나 촘촘한지 확인할 때만 잠깐 켜는 용도다. */}
            <label className="toggle">
              <input
                type="checkbox"
                checked={showMesh}
                onChange={(event) => setShowMesh(event.target.checked)}
              />
              격자 보기
            </label>
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
        <SurfaceView
          surface={surface}
          cutX={cutX}
          onPickCut={setCutX}
          showMesh={showMesh}
        />
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
