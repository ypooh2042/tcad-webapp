/**
 * 결과 보기.
 *
 * 산출물 하나가 공정 한 단계다. `structure out=` 이 나온 순서대로 저장되어
 * 있으므로, 순번을 훑으면 공정이 진행되는 모습을 그대로 볼 수 있다. 이름순으로
 * 정렬하면 그 순서가 깨진다 — 그래서 서버가 준 sequence 를 그대로 쓴다.
 */
import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { plot } from '../api/endpoints'
import type {
  Artifact,
  ProfilePoint,
  ProfileResponse,
  StructureSummary,
  SurfaceResponse,
} from '../api/types'
import { ProfileChart, type Series } from './ProfileChart'
import { SurfaceView } from './SurfaceView'

//: 겹쳐 그릴 선의 색. 기준선(파랑)과 단계 비교(주황)와 겹치지 않게 고른다.
const EXTRA_COLORS = ['#a55eea', '#4ade80', '#ffd93d', '#ff6b6b']

interface Props {
  jobId: number
  artifacts: Artifact[]
}

export function ResultView({ jobId, artifacts }: Props) {
  const [step, setStep] = useState(0)
  const [summary, setSummary] = useState<StructureSummary | null>(null)
  const [quantity, setQuantity] = useState<string | null>(null)
  const [profile, setProfile] = useState<ProfileResponse | null>(null)
  const [surface, setSurface] = useState<SurfaceResponse | null>(null)
  const [cutX, setCutX] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  //: 겹쳐 볼 다른 공정 단계. 확산이 프로파일을 얼마나 넓혔는지 같은 것은
  //: 두 그림을 번갈아 봐서는 알 수 없다.
  const [compareTo, setCompareTo] = useState<number | null>(null)
  const [stepOverlay, setStepOverlay] = useState<Series[]>([])
  //: 함께 볼 다른 물리량. chem 과 active 를 겹치면 얼마나 활성화됐는지,
  //: net_doping 을 겹치면 접합이 어디인지 한눈에 보인다.
  const [extraQuantities, setExtraQuantities] = useState<string[]>([])
  const [quantityOverlay, setQuantityOverlay] = useState<Series[]>([])

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
        setQuantity((previous) =>
          previous && next.quantities.includes(previous)
            ? previous
            : (next.quantities[0] ?? null),
        )
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

  useEffect(() => {
    if (sequence === null || !summary || !quantity) return
    if (summary.dimension === 2 && cutX === null) return
    let cancelled = false

    plot
      .profile(
        jobId,
        sequence,
        quantity,
        summary.dimension === 2 ? cutX! : undefined,
      )
      .then((next) => !cancelled && setProfile(next))
      .catch(report)

    return () => {
      cancelled = true
    }
  }, [jobId, sequence, summary, quantity, cutX, report])

  useEffect(() => {
    if (sequence === null || !summary || !quantity) return
    if (summary.dimension !== 2) {
      setSurface(null)
      return
    }
    let cancelled = false

    // 단면은 컷 위치와 무관하다. cutX 를 의존성에 넣으면 컷을 옮길 때마다
    // 수천 개 삼각형을 다시 받는다.
    plot
      .surface(jobId, sequence, quantity)
      .then((next) => !cancelled && setSurface(next))
      .catch(report)

    return () => {
      cancelled = true
    }
  }, [jobId, sequence, summary, quantity, report])

  // 비교 대상 단계의 프로파일을 따로 읽는다. 같은 물리량·같은 컷 위치여야
  // 비교가 의미를 가진다.
  useEffect(() => {
    if (compareTo === null || !summary || !quantity) {
      setStepOverlay([])
      return
    }
    let cancelled = false

    plot
      .profile(
        jobId,
        compareTo,
        quantity,
        summary.dimension === 2 ? (cutX ?? undefined) : undefined,
      )
      .then((next) => {
        if (cancelled) return
        const name =
          artifacts.find((a) => a.sequence === compareTo)?.filename ??
          `#${compareTo}`
        setStepOverlay([{ label: name, points: next.points, color: '#ff9f43' }])
      })
      .catch(() => !cancelled && setStepOverlay([]))

    return () => {
      cancelled = true
    }
  }, [jobId, compareTo, quantity, summary, cutX, artifacts])

  // 함께 고른 물리량들을 같은 단계·같은 컷에서 읽는다.
  useEffect(() => {
    if (sequence === null || !summary || extraQuantities.length === 0) {
      setQuantityOverlay([])
      return
    }
    let cancelled = false

    Promise.all(
      extraQuantities.map((name) =>
        plot
          .profile(
            jobId,
            sequence,
            name,
            summary.dimension === 2 ? (cutX ?? undefined) : undefined,
          )
          .then((next) => ({ name, points: next.points }))
          .catch(() => null),
      ),
    ).then((results) => {
      if (cancelled) return
      setQuantityOverlay(
        results
          .filter((r): r is { name: string; points: ProfilePoint[] } =>
            Boolean(r),
          )
          .map((r, index) => ({
            label: r.name,
            points: r.points,
            color: EXTRA_COLORS[index % EXTRA_COLORS.length]!,
          })),
      )
    })

    return () => {
      cancelled = true
    }
  }, [jobId, sequence, summary, extraQuantities, cutX])

  if (artifacts.length === 0) {
    return <p className="muted">저장된 구조가 없습니다. `structure out=` 을 넣어 보세요.</p>
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
        <label htmlFor="quantity">물리량</label>
        <select
          id="quantity"
          value={quantity ?? ''}
          onChange={(event) => setQuantity(event.target.value)}
        >
          {summary?.quantities.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        {(summary?.quantities.length ?? 0) > 1 && (
          <details className="extra-quantities">
            <summary>함께 보기{extraQuantities.length ? ` (${extraQuantities.length})` : ''}</summary>
            <div>
              {summary?.quantities
                .filter((name) => name !== quantity)
                .map((name) => (
                  <label key={name}>
                    <input
                      type="checkbox"
                      checked={extraQuantities.includes(name)}
                      onChange={(event) =>
                        setExtraQuantities((current) =>
                          event.target.checked
                            ? [...current, name]
                            : current.filter((item) => item !== name),
                        )
                      }
                    />
                    {name}
                  </label>
                ))}
            </div>
          </details>
        )}
        {artifacts.length > 1 && (
          <>
            <label htmlFor="compare">비교</label>
            <select
              id="compare"
              value={compareTo ?? ''}
              onChange={(event) =>
                setCompareTo(
                  event.target.value ? Number(event.target.value) : null,
                )
              }
            >
              <option value="">없음</option>
              {artifacts
                .filter((a) => a.sequence !== sequence)
                .map((a) => (
                  <option key={a.sequence} value={a.sequence}>
                    {a.filename}
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
        <p className="muted">단면을 클릭하면 그 위치의 깊이 프로파일을 봅니다 (x = {cutX.toFixed(3)} µm)</p>
      )}

      {profile && quantity && (
        <ProfileChart
          points={profile.points}
          quantity={quantity}
          overlays={[...quantityOverlay, ...stepOverlay]}
        />
      )}
    </div>
  )
}
