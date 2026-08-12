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
 *
 * **가로축은 확대할 수 있다.** 도핑 프로파일은 표면 0.1µm 안에서 대부분이
 * 일어나는데 꼬리는 몇 µm 까지 끌려서, 전체를 한 화면에 넣으면 정작 봐야 할
 * 접합부가 몇 픽셀로 뭉개진다. 세로축은 건드리지 않는다 — 확대할 때마다 세로
 * 눈금이 바뀌면 단계를 오갈 때 높이를 비교할 수 없다.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import type { ProfilePoint } from '../api/types'
import { linearTicks, logTicks, toLogDomain } from './scale'
import { fillOf } from './materials'
import { materialBands, splitByMaterial } from './segments'
import { clampView, panBy, resetView, zoomAround, type View } from './zoom'

const WIDTH = 640
const HEIGHT = 380
const MARGIN = { top: 16, right: 16, bottom: 44, left: 68 }


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
  //: 보고 있는 깊이 구간. null 이면 전체.
  const [view, setView] = useState<View | null>(null)
  // 콜백 ref 로 노드를 **상태에** 담는다. useRef + [] effect 로 하면 데이터가
  // 없어 일찍 반환한 첫 렌더에서 노드가 null 이라 리스너가 영영 안 붙는다
  // (실제로 그렇게 깨졌다 — 단위 테스트는 처음부터 데이터가 있어 못 잡았다).
  const [svgNode, setSvgNode] = useState<SVGSVGElement | null>(null)
  const svgRef = useRef<SVGSVGElement | null>(null)
  const attach = (node: SVGSVGElement | null) => {
    svgRef.current = node
    setSvgNode(node)
  }
  const dragging = useRef<{ x: number; view: View } | null>(null)

  const chart = useMemo(() => {
    const all = series.flatMap((one) => one.points)
    // 축은 그리는 모든 선을 담아야 한다. 하나만 보고 잡으면 나머지가 화면
    // 밖으로 나간다.
    const domain = toLogDomain(all.map((point) => Math.abs(point.value)))
    const depths = all.map((point) => point.depth)
    const full = { from: Math.min(...depths, 0), to: Math.max(...depths, 0) }
    // 확대 중이면 그 구간만 축에 올린다. 데이터는 그대로 두고 보이는 창만 옮긴다.
    const depthMin = view ? view.from : full.from
    const depthMax = view ? view.to : full.to

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
      full,
    }
  }, [series, view])

  // 데이터가 바뀌어도 **확대는 버리지 않는다.** 2D 에서 컷을 옮기면 같은 깊이
  // 범위의 새 값이 오는데, 그때마다 확대가 풀리면 매번 다시 확대해야 한다.
  // 다만 깊이 범위 자체가 달라졌으면(다른 공정 단계) 새 범위 안으로 밀어
  // 넣는다 — 그러지 않으면 빈 화면이 뜬다.
  const fullKey = `${chart.full.from},${chart.full.to}`
  useEffect(() => {
    setView((current) => (current ? clampView(current, chart.full) : null))
    // chart.full 은 매 렌더 새 객체다. 값이 바뀔 때만 돌도록 키를 쓴다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fullKey])


  /** 화면 x → 깊이. viewBox 가 CSS 폭에 맞춰 늘어나므로 비율을 되돌려야 한다. */
  function depthAt(clientX: number): number {
    const svg = svgRef.current
    if (!svg) return chart.depthMin
    const rect = svg.getBoundingClientRect()
    if (!(rect.width > 0)) return chart.depthMin
    const inViewBox = ((clientX - rect.left) / rect.width) * WIDTH
    const plotWidth = WIDTH - MARGIN.left - MARGIN.right
    const ratio = (inViewBox - MARGIN.left) / plotWidth
    return chart.depthMin + ratio * (chart.depthMax - chart.depthMin)
  }


  // 리스너는 한 번만 단다(등록/해제를 반복하면 굴리는 중에 이벤트가 샌다).
  // 그래서 최신 값은 ref 로 건넨다.
  const chartRef = useRef(chart)
  const depthAtRef = useRef(depthAt)
  chartRef.current = chart
  depthAtRef.current = depthAt

  // 휠은 **네이티브 리스너로** 단다. React 의 onWheel 은 루트에 passive 로
  // 붙어서 preventDefault 가 무시되고, 그러면 그래프를 확대하는 동안 바깥
  // 패널이 함께 스크롤된다. 커서가 그래프 위에 있는 동안은 확대만 일어나야
  // 한다 — 더 확대할 수 없는 상태에서도 막는다. 한계에서 스크롤이 뚫리면
  // 화면이 갑자기 튄다.
  useEffect(() => {
    if (!svgNode) return

    function onWheel(event: WheelEvent) {
      event.preventDefault()
      // 위로 굴리면(deltaY < 0) 확대. 브라우저 관례를 따른다.
      const factor = event.deltaY < 0 ? 0.8 : 1.25
      setView((current) =>
        zoomAround(
          current ?? chartRef.current.full,
          chartRef.current.full,
          factor,
          depthAtRef.current(event.clientX),
        ),
      )
    }

    svgNode.addEventListener('wheel', onWheel, { passive: false })
    return () => svgNode.removeEventListener('wheel', onWheel)
  }, [svgNode])

  function onPointerDown(event: React.PointerEvent<SVGSVGElement>) {
    // 전체를 보고 있으면 끌 곳이 없다.
    if (!view) return
    dragging.current = { x: event.clientX, view }
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  function onPointerMove(event: React.PointerEvent<SVGSVGElement>) {
    const drag = dragging.current
    const svg = svgRef.current
    if (!drag || !svg) return
    const rect = svg.getBoundingClientRect()
    if (!(rect.width > 0)) return
    const plotWidth = ((WIDTH - MARGIN.left - MARGIN.right) * rect.width) / WIDTH
    const perPixel = (drag.view.to - drag.view.from) / plotWidth
    // 잡은 지점이 손가락을 따라오게. 부호를 뒤집으면 그림이 반대로 달아난다.
    setView(panBy(drag.view, chart.full, -(event.clientX - drag.x) * perPixel))
  }

  function endDrag() {
    dragging.current = null
  }

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
        ref={attach}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`${series.map((one) => one.label).join(', ')} 깊이 프로파일`}
        className={view ? 'zoomed' : undefined}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        {/* 확대하면 범위 밖 점들이 좌우로 밀려난다. 잘라내지 않으면 눈금과
            범례 위에까지 선이 그려진다. */}
        <defs>
          <clipPath id="plot-area">
            <rect
              x={MARGIN.left}
              y={MARGIN.top}
              width={WIDTH - MARGIN.left - MARGIN.right}
              height={chart.plotHeight}
            />
          </clipPath>
        </defs>

        <g clipPath="url(#plot-area)">
        {/* 재질 띠를 가장 먼저 그려 모든 것의 뒤에 둔다. */}
        {chart.bands.map((band, index) => (
          <rect
            key={`${band.material}-${index}`}
            className="band-fill"
            x={chart.xOf(band.from)}
            y={MARGIN.top}
            width={Math.max(0, chart.xOf(band.to) - chart.xOf(band.from))}
            height={chart.plotHeight}
            fill={fillOf(band.material)}
          >
            <title>{band.material}</title>
          </rect>
        ))}

        {/* 재질 경계. 색이 비슷해도 여기가 층이 바뀌는 자리임이 보여야 한다. */}
        {chart.bands.slice(1).map((band, index) => (
          <line
            key={`edge-${band.material}-${index}`}
            className="material-edge"
            x1={chart.xOf(band.from)}
            x2={chart.xOf(band.from)}
            y1={MARGIN.top}
            y2={MARGIN.top + chart.plotHeight}
          />
        ))}

        {/* 띠 이름을 제자리에 적는다. 범례를 오가며 색을 맞춰 보지 않아도 된다. */}
        {chart.bands.map((band, index) => (
          <text
            key={`label-${band.material}-${index}`}
            className="band-label"
            x={(chart.xOf(band.from) + chart.xOf(band.to)) / 2}
            y={MARGIN.top + 12}
            textAnchor="middle"
          >
            {band.material}
          </text>
        ))}

        </g>

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

        <g clipPath="url(#plot-area)">
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
        </g>

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
        {view && (
          <button className="link" onClick={() => setView(resetView(chart.full))}>
            전체 보기
          </button>
        )}
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
