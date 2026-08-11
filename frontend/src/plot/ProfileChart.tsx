/**
 * 깊이 프로파일 차트 (SVG).
 *
 * 세로축이 농도(로그), 가로축이 깊이다. 반도체 관례대로 깊이는 왼쪽이 표면이고
 * 오른쪽으로 갈수록 깊어진다. 증착층은 깊이가 음수라 표면보다 왼쪽에 놓인다.
 *
 * **두 축을 두 채널로 나눈다.**
 *     선 색   = 물리량 (무엇을 그리나)
 *     배경 띠 = 재질   (어디에 있나)
 *
 * 재질을 선 색으로 나타내면 물리량에 쓸 색이 남지 않는다. 여러 물리량을 겹쳐
 * 보는 순간 어느 색이 무엇인지 알 수 없게 된다.
 *
 * 선은 재질이 바뀌는 곳에서 여전히 끊는다. 계면에서 값이 실제로 불연속이기
 * 때문이다 — 이어 그리면 물질 경계가 농도 급락처럼 보인다.
 *
 * **부호 있는 값은 절댓값을 올린다.** net_doping 은 억셉터가 우세한 구간에서
 * 음수인데, 로그 축에 못 올린다고 버리면 p 형 기판에서는 그래프가 통째로
 * 비어 버린다(실측: 보론만 주입한 구조에서 44점 전부 음수). 절댓값을 그리고
 * 음수 구간을 점선으로 구분한다 — 부호가 바뀌는 자리가 곧 접합이다.
 */
import { useMemo } from 'react'
import type { ProfilePoint } from '../api/types'
import { linearTicks, logTicks, toLogDomain } from './scale'
import { materialBands, splitByMaterial } from './segments'

const WIDTH = 640
const HEIGHT = 380
const MARGIN = { top: 16, right: 16, bottom: 44, left: 68 }

/** 재질 배경 띠 색. 선을 가리지 않도록 어둡고 낮은 채도로 둔다. */
const MATERIAL_FILLS: Record<string, string> = {
  silicon: '#1d2a3a',
  oxide: '#332a1a',
  nitride: '#2a1f38',
  poly: '#1f3326',
  aluminum: '#2e3238',
  gaas: '#33202a',
}

function fillOf(material: string): string {
  return MATERIAL_FILLS[material] ?? '#262a31'
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

export interface Series {
  /** 범례에 쓸 이름. 보통 물리량 이름이다. */
  label: string
  points: ProfilePoint[]
  color: string
  /** 다른 공정 단계를 겹친 것인지. 흐리게 그려 기준선과 구분한다. */
  muted?: boolean
}

interface Props {
  series: Series[]
}

export function ProfileChart({ series }: Props) {
  const chart = useMemo(() => {
    const all = series.flatMap((one) => one.points)
    // 축은 그리는 모든 선을 담아야 한다. 하나만 보고 잡으면 나머지가 화면
    // 밖으로 나간다.
    const domain = toLogDomain(all.map((point) => Math.abs(point.value)))
    const depths = all.map((point) => point.depth)
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
      // 재질은 어느 선에서 읽어도 같다(같은 메시다). 첫 번째 것으로 띠를 만든다.
      bands: materialBands(series[0]?.points ?? []),
      ticks: logTicks(domain.min, domain.max),
      depthTicks: linearTicks(depthMin, depthMax),
      hasNegative: all.some((point) => point.value < 0),
    }
  }, [series])

  if (series.every((one) => one.points.length === 0)) {
    return <p className="muted">그릴 데이터가 없습니다.</p>
  }

  const depthStep =
    chart.depthTicks.length > 1
      ? Math.abs((chart.depthTicks[1] ?? 0) - (chart.depthTicks[0] ?? 0))
      : 1

  return (
    <figure className="chart">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`${series.map((one) => one.label).join(', ')} 깊이 프로파일`}
      >
        {/* 재질 띠를 가장 먼저 그려 모든 것의 뒤에 둔다. */}
        {chart.bands.map((band, index) => (
          <rect
            key={`${band.material}-${index}`}
            x={chart.xOf(band.from)}
            y={MARGIN.top}
            width={Math.max(0, chart.xOf(band.to) - chart.xOf(band.from))}
            height={chart.plotHeight}
            fill={fillOf(band.material)}
          >
            <title>{band.material}</title>
          </rect>
        ))}

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
        {chart.depthTicks.map((tick, index) => (
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
              {formatDepth(tick, depthStep)}
            </text>
          </g>
        ))}

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

        {series.map((one) =>
          splitByMaterial(one.points).map((segment, index) => (
            <polyline
              key={`${one.label}-${index}`}
              fill="none"
              stroke={one.color}
              strokeWidth={one.muted ? 1.4 : 1.8}
              strokeOpacity={one.muted ? 0.7 : 1}
              // 음수(억셉터 우세) 구간은 점선. 실선/점선이 바뀌는 자리가 접합이다.
              strokeDasharray={segment.negative ? '5 3' : undefined}
              points={segment.points
                .map((point) => `${chart.xOf(point.depth)},${chart.yOf(point.value)}`)
                .join(' ')}
            />
          )),
        )}

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
          {series.map((one) => (
            <span key={one.label}>
              <i style={{ background: one.color }} />
              {one.label}
            </span>
          ))}
        </span>
        <span className="legend materials">
          {[...new Set(chart.bands.map((band) => band.material))].map(
            (material) => (
              <span key={material}>
                <i className="band" style={{ background: fillOf(material) }} />
                {material}
              </span>
            ),
          )}
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
