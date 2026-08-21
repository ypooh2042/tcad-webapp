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
  //: 어느 전극의 전류를 볼지. 비어 있으면 런마다 가장 많이 움직인 것을 고른다.
  const [bias, setBias] = useState<string>('')
  //: 이름을 고치는 중인 해석.
  const [editing, setEditing] = useState<number | null>(null)
  const [draft, setDraft] = useState('')

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

  // 고른 해석들이 가진 전압원 이름의 합집합. 해석마다 전극 이름이 다를 수
  // 있으므로 교집합으로 좁히면 고를 것이 없어진다.
  const availableBiases = useMemo(() => {
    const names = new Set<string>()
    for (const run of picked) for (const one of run.data.biases ?? []) names.add(one)
    return [...names].sort()
  }, [picked])

  const series = useMemo<ChartSeries[]>(() => {
    const out: ChartSeries[] = []
    picked.forEach((run, index) => {
      // 고른 것이 이 해석에 없으면 그 해석에서 가장 많이 움직인 전류를 쓴다.
      const chosenBias =
        bias && (run.data.biases ?? []).includes(bias)
          ? bias
          : dominantBias(run.data)
      if (!chosenBias) return
      // 런은 색으로, 그 안의 곡선족은 선 스타일로 나눈다. 둘 다 색으로 하면
      // 어느 곡선이 어느 런의 것인지 못 읽는다.
      seriesOf(run.data, chosenBias).forEach((one, at) => {
        out.push({
          ...one,
          label: `${run.label}${one.label ? ` · ${one.label}` : ''}`,
          color: CURVE_COLORS[index % CURVE_COLORS.length],
          dashed: at % 2 === 1,
        })
      })
    })
    return out
  }, [picked, bias])

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

  async function commitRename(jobId: number) {
    const name = draft.trim()
    setEditing(null)
    const current = runs.find((one) => one.job_id === jobId)
    if (!name || !current || name === current.label) return
    try {
      const updated = await devsim.rename(jobId, name)
      setRuns((list) =>
        list.map((one) => (one.job_id === jobId ? { ...one, label: updated.label } : one)),
      )
      setLoaded((map) => {
        const next = new Map(map)
        const detail = next.get(jobId)
        if (detail) next.set(jobId, { ...detail, label: updated.label })
        return next
      })
    } catch {
      // 이름만 못 바꾼 것이다. 곡선은 그대로 두고 넘어간다.
    }
  }

  /**
   * 저장한 해석을 지운다.
   *
   * 되돌릴 수 없으므로 먼저 묻는다. 곡선은 잡 산출물에도 남아 있지만 그쪽은
   * 청소에 지워지므로, 여기서 지운 것은 사실상 사라진다.
   */
  async function forget(run: DevSimRunSummary) {
    const ok = window.confirm(
      `"${run.label}" 을(를) 비교 목록에서 지웁니다.\n되돌릴 수 없습니다.`,
    )
    if (!ok) return
    try {
      await devsim.forget(run.job_id)
    } catch {
      // 이미 지워졌을 수 있다. 화면에서도 치우는 것이 맞다.
    }
    setRuns((list) => list.filter((one) => one.job_id !== run.job_id))
    setChosen((current) => current.filter((one) => one !== run.job_id))
    setLoaded((map) => {
      const next = new Map(map)
      next.delete(run.job_id)
      return next
    })
  }

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
                  <span className="origin">
                    {run.source_path || run.structure}
                  </span>
                  {run.completed < run.total ? (
                    <em> ({run.completed}/{run.total}점)</em>
                  ) : null}
                </label>
                <button
                  type="button"
                  className="ghost"
                  aria-label={`${run.label} 지우기`}
                  onClick={() => void forget(run)}
                >
                  ×
                </button>
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
            <div className="chart-controls">
              <select
                value={bias}
                aria-label="볼 전류"
                onChange={(event) => setBias(event.target.value)}
              >
                <option value="">가장 많이 움직인 전류</option>
                {availableBiases.map((name) => (
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

            {/* 어느 공정 코드에서 나온 결과인지. 구조 파일 이름만으로는 여러
                흐름에서 같은 이름이 나올 수 있다. */}
            <ul className="origins">
              {picked.map((run, index) => (
                <li key={run.job_id}>
                  <span
                    className="swatch"
                    style={{ background: CURVE_COLORS[index % CURVE_COLORS.length] }}
                    aria-hidden="true"
                  />
                  {editing === run.job_id ? (
                    <input
                      autoFocus
                      value={draft}
                      aria-label={`${run.label} 이름 바꾸기`}
                      onChange={(event) => setDraft(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') void commitRename(run.job_id)
                        if (event.key === 'Escape') setEditing(null)
                      }}
                      onBlur={() => void commitRename(run.job_id)}
                    />
                  ) : (
                    <button
                      type="button"
                      className="link"
                      title="눌러서 이름 바꾸기"
                      onClick={() => {
                        setEditing(run.job_id)
                        setDraft(run.label)
                      }}
                    >
                      {run.label}
                    </button>
                  )}
                  <span className="origin">
                    {run.source_path || '출처 모름'} · {run.structure}
                  </span>
                </li>
              ))}
            </ul>
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
