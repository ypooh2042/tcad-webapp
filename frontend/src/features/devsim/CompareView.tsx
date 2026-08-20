/**
 * 여러 해석을 겹쳐 보는 화면.
 *
 * 세 가지를 같이 놓는다. 곡선만 겹쳐 놓으면 "다르다"는 것 말고는 아무것도
 * 알 수 없기 때문이다.
 *
 *   1. 겹쳐 그리기 — 런마다 색, 곡선족은 선 스타일.
 *   2. 지표 표    — 숫자로 비교되지 않으면 비교가 아니다.
 *   3. 차이 패널  — 조건에서 **다른 항목만**. 원인 후보를 좁혀 준다.
 */
import { useEffect, useMemo, useState } from 'react'
import { devsim } from '../../api/endpoints'
import type { DevSimRunDetail, DevSimRunSummary } from '../../api/types'
import { dominantBias, figuresOf, seriesOf } from './figures'
import { FigureTable } from './FigureTable'
import { CURVE_COLORS, IvChart, type ChartSeries } from './IvChart'
import { diffOf } from './specDiff'

export function CompareView() {
  const [runs, setRuns] = useState<DevSimRunSummary[]>([])
  const [chosen, setChosen] = useState<number[]>([])
  const [loaded, setLoaded] = useState<Map<number, DevSimRunDetail>>(new Map())
  const [logScale, setLogScale] = useState(false)

  useEffect(() => {
    devsim
      .runs()
      .then(setRuns)
      .catch(() => setRuns([]))
  }, [])

  useEffect(() => {
    const missing = chosen.filter((id) => !loaded.has(id))
    if (missing.length === 0) return
    let cancelled = false
    Promise.all(missing.map((id) => devsim.run(id).catch(() => null))).then(
      (details) => {
        if (cancelled) return
        setLoaded((current) => {
          const next = new Map(current)
          for (const detail of details) {
            if (detail) next.set(detail.job_id, detail)
          }
          return next
        })
      },
    )
    return () => {
      cancelled = true
    }
  }, [chosen, loaded])

  const picked = useMemo(
    () =>
      chosen
        .map((id) => loaded.get(id))
        .filter((detail): detail is DevSimRunDetail => detail !== undefined),
    [chosen, loaded],
  )

  const series = useMemo<ChartSeries[]>(() => {
    const out: ChartSeries[] = []
    picked.forEach((run, index) => {
      const bias = dominantBias(run.data)
      if (!bias) return
      // 런은 색으로, 그 안의 곡선족은 선 스타일로 나눈다. 둘 다 색으로 하면
      // 어느 곡선이 어느 런의 것인지 못 읽는다.
      seriesOf(run.data, bias).forEach((one, at) => {
        out.push({
          ...one,
          label: `${run.label}${one.label ? ` · ${one.label}` : ''}`,
          color: CURVE_COLORS[index % CURVE_COLORS.length],
          dashed: at % 2 === 1,
        })
      })
    })
    return out
  }, [picked])

  const differences = useMemo(
    () =>
      diffOf(
        picked.map((run) => ({
          label: run.label,
          structure: run.structure,
          spec: run.spec,
        })),
      ),
    [picked],
  )

  function toggle(id: number) {
    setChosen((current) =>
      current.includes(id)
        ? current.filter((one) => one !== id)
        : [...current, id],
    )
  }

  return (
    <div className="compare">
      <section className="compare-picker">
        <h3>해석 고르기</h3>
        {runs.length === 0 ? (
          <p className="hint">저장된 해석이 아직 없습니다.</p>
        ) : (
          <ul>
            {runs.map((run) => (
              <li key={run.job_id}>
                <label>
                  <input
                    type="checkbox"
                    checked={chosen.includes(run.job_id)}
                    onChange={() => toggle(run.job_id)}
                  />
                  <strong>{run.label}</strong>
                  <span className="origin">{run.structure}</span>
                  {run.completed < run.total ? (
                    <em> ({run.completed}/{run.total}점)</em>
                  ) : null}
                </label>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="compare-body">
        {series.length === 0 ? (
          <p className="hint">둘 이상 고르면 겹쳐 그립니다.</p>
        ) : (
          <>
            <label className="field inline">
              <input
                type="checkbox"
                checked={logScale}
                onChange={(event) => setLogScale(event.target.checked)}
              />
              로그 축
            </label>
            <IvChart
              series={series}
              xLabel="스윕 전압 (V)"
              yLabel="I (A/µm)"
              logScale={logScale}
              height={340}
            />
            <FigureTable
              rows={series.map((one) => ({
                label: one.label,
                figures: figuresOf(one),
              }))}
            />
          </>
        )}

        {differences.length > 0 ? (
          <div className="diff">
            <h3>조건 차이</h3>
            <p className="hint">같은 항목은 지웠습니다. 남은 것이 원인 후보입니다.</p>
            <table>
              <thead>
                <tr>
                  <th scope="col">항목</th>
                  {picked.map((run) => (
                    <th scope="col" key={run.job_id}>
                      {run.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {differences.map((row) => (
                  <tr key={row.field}>
                    <th scope="row">{row.field}</th>
                    {row.values.map((value, index) => (
                      <td key={index}>{value}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : picked.length > 1 ? (
          <p className="hint">고른 해석들의 조건이 모두 같습니다.</p>
        ) : null}
      </section>
    </div>
  )
}
