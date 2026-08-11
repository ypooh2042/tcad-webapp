/**
 * 깊이 프로파일 차트 (SVG).
 *
 * 세로축이 농도(로그), 가로축이 깊이다. 반도체 관례대로 깊이는 왼쪽이 표면이고
 * 오른쪽으로 갈수록 깊어진다. 증착층은 깊이가 음수라 표면보다 왼쪽에 놓인다.
 *
 * 선은 물질이 바뀌는 곳에서 끊는다. 이어 그리면 계면에서 수직으로 뚝 떨어지는
 * 가짜 선이 생겨, 물질 경계가 농도 급락처럼 보인다.
 *
 * **부호 있는 값은 절댓값을 올린다.** net_doping 은 억셉터가 우세한 구간에서
 * 음수인데, 로그 축에 못 올린다고 버리면 p 형 기판에서는 그래프가 통째로
 * 비어 버린다(실측: 보론만 주입한 구조에서 44점 전부 음수). 절댓값을 그리고
 * 음수 구간을 점선으로 구분한다 — 부호가 바뀌는 자리가 곧 접합이다.
 */
import { useMemo } from 'react'
import type { ProfilePoint } from '../api/types'
import { linearTicks, logTicks, toLogDomain } from './scale'
import { splitByMaterial } from './segments'

const WIDTH = 640
const HEIGHT = 380
const MARGIN = { top: 16, right: 16, bottom: 44, left: 68 }

const MATERIAL_COLORS: Record<string, string> = {
  silicon: '#4a9eff',
  oxide: '#ff9f43',
  nitride: '#a55eea',
  poly: '#4ade80',
  aluminum: '#c8d0dc',
}

function colorOf(material: string): string {
  return MATERIAL_COLORS[material] ?? '#8b929e'
}

function formatValue(value: number): string {
  const exponent = Math.round(Math.log10(value))
  return `1e${exponent}`
}

/** 깊이 눈금 라벨. 간격에 맞춰 자릿수를 정한다 — 0.5um 간격에 "0.500" 은
 *  군더더기고, 0.02um 간격에 "0.0" 은 전부 같은 값으로 보인다. */
function formatDepth(value: number, step: number): string {
  const decimals = Math.max(0, Math.ceil(-Math.log10(step)))
  return value.toFixed(decimals)
}

interface Props {
  points: ProfilePoint[]
  quantity: string
}

export function ProfileChart({ points, quantity }: Props) {
  const chart = useMemo(() => {
    // 절댓값을 축에 올린다. 부호는 선 모양으로 구분한다.
    const domain = toLogDomain(points.map((point) => Math.abs(point.value)))
    const depths = points.map((point) => point.depth)
    const depthMin = Math.min(...depths, 0)
    const depthMax = Math.max(...depths, 0)

    const plotWidth = WIDTH - MARGIN.left - MARGIN.right
    const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom

    const xOf = (depth: number) =>
      MARGIN.left +
      (depthMax === depthMin
        ? plotWidth / 2
        : ((depth - depthMin) / (depthMax - depthMin)) * plotWidth)

    const logSpan = Math.log10(domain.max) - Math.log10(domain.min)
    const yOf = (value: number) => {
      const magnitude = Math.abs(value)
      if (!(magnitude > 0) || logSpan === 0) return MARGIN.top + plotHeight
      const t = (Math.log10(magnitude) - Math.log10(domain.min)) / logSpan
      return MARGIN.top + plotHeight - Math.min(1, Math.max(0, t)) * plotHeight
    }

    return {
      domain,
      depthMin,
      depthMax,
      xOf,
      yOf,
      plotHeight,
      segments: splitByMaterial(points),
      ticks: logTicks(domain.min, domain.max),
      depthTicks: linearTicks(depthMin, depthMax),
      hasNegative: points.some((point) => point.value < 0),
    }
  }, [points])

  if (points.length === 0) {
    return <p className="muted">그릴 데이터가 없습니다.</p>
  }

  return (
    <figure className="chart">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`${quantity} 깊이 프로파일`}
      >
        {chart.ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={MARGIN.left}
              x2={WIDTH - MARGIN.right}
              y1={chart.yOf(tick)}
              y2={chart.yOf(tick)}
              className="grid"
            />
            <text
              x={MARGIN.left - 8}
              y={chart.yOf(tick)}
              className="tick"
              textAnchor="end"
              dominantBaseline="middle"
            >
              {formatValue(tick)}
            </text>
          </g>
        ))}

        {/* 깊이 눈금. 이게 없으면 접합 깊이를 읽을 수 없다 — 도핑 프로파일에서
            가장 먼저 보는 숫자다. */}
        {chart.depthTicks.map((tick, index) => {
          const step =
            chart.depthTicks.length > 1
              ? Math.abs(
                  (chart.depthTicks[1] ?? 0) - (chart.depthTicks[0] ?? 0),
                )
              : 1
          return (
            <g key={`depth-${index}`}>
              <line
                x1={chart.xOf(tick)}
                x2={chart.xOf(tick)}
                y1={MARGIN.top + chart.plotHeight}
                y2={MARGIN.top + chart.plotHeight + 4}
                className="grid"
              />
              <text
                x={chart.xOf(tick)}
                y={MARGIN.top + chart.plotHeight + 16}
                className="tick"
                textAnchor="middle"
              >
                {formatDepth(tick, step)}
              </text>
            </g>
          )
        })}

        {/* 표면(깊이 0). 증착층이 있으면 이 선 왼쪽에 그려진다. */}
        {chart.depthMin < 0 && (
          <line
            x1={chart.xOf(0)}
            x2={chart.xOf(0)}
            y1={MARGIN.top}
            y2={MARGIN.top + chart.plotHeight}
            className="surface-line"
          />
        )}

        {chart.segments.map((segment, index) => (
          <polyline
            key={`${segment.material}-${index}`}
            fill="none"
            stroke={colorOf(segment.material)}
            strokeWidth={1.8}
            // 음수(억셉터 우세) 구간은 점선. 실선/점선이 바뀌는 자리가 접합이다.
            strokeDasharray={segment.negative ? '5 3' : undefined}
            points={segment.points
              .map((point) => `${chart.xOf(point.depth)},${chart.yOf(point.value)}`)
              .join(' ')}
          />
        ))}

        <text
          x={MARGIN.left + (WIDTH - MARGIN.left - MARGIN.right) / 2}
          y={HEIGHT - 6}
          className="axis-label"
          textAnchor="middle"
        >
          깊이 (µm)
        </text>
      </svg>

      <figcaption>
        <span className="legend">
          {[...new Set(chart.segments.map((s) => s.material))].map((material) => (
            <span key={material}>
              <i style={{ background: colorOf(material) }} />
              {material}
            </span>
          ))}
        </span>
        {chart.hasNegative && (
          // 버리지 않고 절댓값으로 그린다. 어느 쪽이 음수인지 알려주지 않으면
          // p 형 구간을 n 형으로 오해한다.
          <span className="muted">점선 = 음수 (절댓값을 로그 축에 표시)</span>
        )}
      </figcaption>
    </figure>
  )
}
