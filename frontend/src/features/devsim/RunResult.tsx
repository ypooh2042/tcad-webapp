/**
 * 돌고 있는 해석의 상태와, 끝난 뒤의 곡선.
 *
 * 진행률은 `.str` 이 아니라 바이어스 점을 센다 — 해석기가 한 점 풀 때마다
 * 흘려보내는 줄을 서버가 세어 준다. 로그는 끝나야 들어오므로 그것 없이는
 * 사용자가 몇 분 동안 "실행 중" 세 글자만 본다.
 */
import { useEffect, useMemo, useState } from 'react'
import { devsim } from '../../api/endpoints'
import type { IvDataset, IvFailure, JobDetail } from '../../api/types'
import { formatDuration } from '../jobs/duration'
import { useElapsed } from '../jobs/useElapsed'
import { dominantBias, figuresOf, seriesOf } from './figures'
import { FigureTable } from './FigureTable'
import { IvChart } from './IvChart'

// 상태 표시는 공정 쪽(`JobPanel`)과 같은 말과 같은 클래스를 쓴다. 같은 뜻인데
// 화면마다 다른 낱말이면 읽는 사람이 다른 것인 줄 안다.
/** 안 풀린 점이 어느 바이어스였는지. 예: `Vg=1V, Vd=1.5V` */
function describeBias(failure: IvFailure): string {
  const parts = Object.entries(failure.steps).map(
    ([name, value]) => `${name}=${Number(value.toPrecision(4))}V`,
  )
  if (failure.sweep !== null) {
    parts.push(`${Number(failure.sweep.toPrecision(4))}V`)
  }
  return parts.join(', ')
}

const STATUS_LABEL: Record<string, string> = {
  queued: '대기 중',
  running: '실행 중',
  succeeded: '성공',
  failed: '실패',
  timed_out: '시간 초과',
  cancelled: '중단됨',
}

export function RunResult({ job }: { job: JobDetail | null }) {
  const [dataset, setDataset] = useState<IvDataset | null>(null)
  const [bias, setBias] = useState<string | null>(null)
  const [logScale, setLogScale] = useState(false)
  const elapsed = useElapsed(
    job?.elapsed_seconds ?? null,
    job?.status === 'running',
  )

  const finished = job !== null && job.status === 'succeeded'

  useEffect(() => {
    if (!job || !finished) {
      if (!job) setDataset(null)
      return
    }
    let cancelled = false
    devsim
      .run(job.id)
      .then((detail) => {
        if (cancelled) return
        setDataset(detail.data)
        setBias(dominantBias(detail.data))
      })
      .catch(() => {
        // 결과가 아직 안 실렸을 수 있다. 로그와 상태는 그대로 보여준다.
      })
    return () => {
      cancelled = true
    }
  }, [job, finished])

  const series = useMemo(
    () => (dataset && bias ? seriesOf(dataset, bias) : []),
    [dataset, bias],
  )

  const failures = dataset?.failures ?? []

  if (!job) {
    return <p className="hint">해석을 실행하면 여기에 곡선이 나옵니다.</p>
  }

  return (
    <div className="run-result">
      <div className="run-status">
        <span className={`status status-${job.status}`}>
          {STATUS_LABEL[job.status] ?? job.status}
        </span>
        {elapsed !== null ? (
          <span className="elapsed">
            {job.status === 'running'
              ? `${formatDuration(elapsed)}…`
              : `총 ${formatDuration(elapsed)}`}
          </span>
        ) : null}
      </div>

      {job.progress ? (
        <div className="progress">
          {job.progress.latest
            ? `${job.progress.latest} 풀림 · `
            : '첫 점 푸는 중 · '}
          {job.progress.done}/{job.progress.total}
        </div>
      ) : null}

      {dataset?.error ? (
        <p className="warning">
          {dataset.error} ({dataset.completed}/{dataset.total}점)
        </p>
      ) : null}

      {/*
        안 풀린 점은 반드시 드러내야 한다. 조용히 빼면 사용자는 그 자리에 값이
        없다는 것도 모른 채 곡선을 읽는다.
      */}
      {failures.length > 0 ? (
        <details className="skipped" open={failures.length <= 4}>
          <summary>
            수렴하지 못해 건너뛴 점 {failures.length}개
            {dataset ? ` (전체 ${dataset.total}점 중)` : ''}
          </summary>
          <ul>
            {failures.map((failure, index) => (
              <li key={index}>
                <code>{describeBias(failure)}</code> — {failure.reason}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {series.length > 0 && bias ? (
        <>
          <div className="chart-controls">
            <select
              value={bias}
              aria-label="볼 전류"
              onChange={(event) => setBias(event.target.value)}
            >
              {(dataset?.biases ?? []).map((name) => (
                <option key={name} value={name}>
                  {name} 전류
                </option>
              ))}
            </select>
            <label>
              <input
                type="checkbox"
                checked={logScale}
                onChange={(event) => setLogScale(event.target.checked)}
              />
              로그 축
            </label>
          </div>
          <IvChart
            series={series}
            xLabel={`${dataset?.sweep ?? '스윕'} (V)`}
            yLabel={`I (${dataset?.current_unit ?? 'A/um'})`}
            logScale={logScale}
          />
          <ul className="legend">
            {series.map((one, index) => (
              <li key={one.label || index}>
                <span className={`swatch c${index % 8}`} aria-hidden="true" />
                {one.label || '곡선'}
              </li>
            ))}
          </ul>
          <FigureTable
            rows={series.map((one) => ({
              label: one.label || '곡선',
              figures: figuresOf(one),
            }))}
          />
        </>
      ) : null}

      {job.log && job.status !== 'succeeded' ? (
        <pre className="log">{job.log.slice(-4000)}</pre>
      ) : null}
    </div>
  )
}
