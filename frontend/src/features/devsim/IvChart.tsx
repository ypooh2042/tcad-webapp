/**
 * I-V 곡선. 캔버스로 직접 그린다 — 이 코드베이스는 차트 라이브러리를 쓰지 않는다.
 *
 * 세로축은 로그와 선형을 오간다. 전달 특성은 로그로 봐야 문턱 아래가 보이고,
 * 출력 특성은 선형으로 봐야 포화가 보인다. 하나만 두면 반은 못 읽는다.
 */
import { useEffect, useRef } from 'react'
import { linearTicks } from '../../plot/scale'
import type { Series } from './figures'

const MARGIN = { top: 12, right: 14, bottom: 40, left: 66 }

/** 곡선 색. 겹쳐 그릴 때 옆 색과 확실히 구분되도록 골랐다. */
export const CURVE_COLORS = [
  '#4a9eff',
  '#ff9f43',
  '#2ed573',
  '#ff6b81',
  '#a55eea',
  '#26d0ce',
  '#ffd32a',
  '#c8d6e5',
]

export interface ChartSeries extends Series {
  color?: string
  dashed?: boolean
}

interface Props {
  series: ChartSeries[]
  xLabel: string
  yLabel: string
  logScale: boolean
  height?: number
}

/** 로그 축에서 쓸 최소값. 0 과 음수는 로그를 못 취한다. */
const LOG_FLOOR = 1e-18

function magnitude(value: number): number {
  return Math.max(Math.abs(value), LOG_FLOOR)
}

function decadeTicks(min: number, max: number): number[] {
  const low = Math.floor(Math.log10(min))
  const high = Math.ceil(Math.log10(max))
  const ticks: number[] = []
  // 열 자리가 넘어가면 라벨이 겹친다. 건너뛰며 찍는다.
  const stride = Math.max(1, Math.ceil((high - low) / 8))
  for (let power = low; power <= high; power += stride) {
    ticks.push(10 ** power)
  }
  return ticks
}

function formatCurrent(value: number): string {
  if (value === 0) return '0'
  const exponent = Math.floor(Math.log10(Math.abs(value)))
  return `1e${exponent}`
}

export function IvChart({
  series,
  xLabel,
  yLabel,
  logScale,
  height = 280,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const context = canvas.getContext('2d')
    if (!context) return

    const ratio = window.devicePixelRatio || 1
    const width = canvas.clientWidth
    canvas.width = Math.max(1, Math.round(width * ratio))
    canvas.height = Math.max(1, Math.round(height * ratio))
    context.setTransform(ratio, 0, 0, ratio, 0, 0)
    context.clearRect(0, 0, width, height)

    const points = series.flatMap((one) => one.points)
    if (points.length === 0) return

    const xs = points.map((p) => p.x)
    const xMin = Math.min(...xs)
    const xMax = Math.max(...xs)

    const values = points.map((p) => (logScale ? magnitude(p.y) : p.y))
    let yMin = Math.min(...values)
    let yMax = Math.max(...values)
    if (!logScale) {
      // 0 을 축에 넣는다. off 전류가 바닥에 붙어야 크기를 가늠할 수 있다.
      yMin = Math.min(0, yMin)
      yMax = Math.max(0, yMax)
    }
    if (yMax === yMin) yMax = yMin + 1

    const plotWidth = Math.max(1, width - MARGIN.left - MARGIN.right)
    const plotHeight = Math.max(1, height - MARGIN.top - MARGIN.bottom)

    const px = (x: number) =>
      MARGIN.left + ((x - xMin) / (xMax - xMin || 1)) * plotWidth
    const py = (y: number) => {
      if (!logScale) {
        return MARGIN.top + (1 - (y - yMin) / (yMax - yMin)) * plotHeight
      }
      const low = Math.log10(yMin)
      const high = Math.log10(yMax)
      return (
        MARGIN.top +
        (1 - (Math.log10(magnitude(y)) - low) / (high - low || 1)) * plotHeight
      )
    }

    const style = getComputedStyle(canvas)
    const border = style.getPropertyValue('--border').trim() || '#333'
    const muted = style.getPropertyValue('--muted').trim() || '#888'

    context.font =
      '11px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace'
    context.strokeStyle = border
    context.fillStyle = muted

    const yTicks = logScale
      ? decadeTicks(yMin, yMax)
      : linearTicks(yMin, yMax, 5)
    context.textAlign = 'right'
    context.textBaseline = 'middle'
    for (const tick of yTicks) {
      const y = py(tick)
      if (y < MARGIN.top - 1 || y > MARGIN.top + plotHeight + 1) continue
      context.globalAlpha = 0.35
      context.beginPath()
      context.moveTo(MARGIN.left, y)
      context.lineTo(MARGIN.left + plotWidth, y)
      context.stroke()
      context.globalAlpha = 1
      context.fillText(
        logScale ? formatCurrent(tick) : tick.toExponential(1),
        MARGIN.left - 6,
        y,
      )
    }

    context.textAlign = 'center'
    context.textBaseline = 'top'
    for (const tick of linearTicks(xMin, xMax, 5)) {
      const x = px(tick)
      if (x < MARGIN.left - 1 || x > MARGIN.left + plotWidth + 1) continue
      context.globalAlpha = 0.35
      context.beginPath()
      context.moveTo(x, MARGIN.top)
      context.lineTo(x, MARGIN.top + plotHeight)
      context.stroke()
      context.globalAlpha = 1
      context.fillText(tick.toFixed(2), x, MARGIN.top + plotHeight + 6)
    }

    context.fillText(xLabel, MARGIN.left + plotWidth / 2, height - 14)
    context.save()
    context.translate(12, MARGIN.top + plotHeight / 2)
    context.rotate(-Math.PI / 2)
    context.textBaseline = 'middle'
    context.fillText(yLabel, 0, 0)
    context.restore()

    series.forEach((one, index) => {
      if (one.points.length === 0) return
      context.strokeStyle = one.color ?? CURVE_COLORS[index % CURVE_COLORS.length]
      context.lineWidth = 1.8
      context.setLineDash(one.dashed ? [5, 4] : [])
      context.beginPath()
      one.points.forEach((point, at) => {
        const x = px(point.x)
        const y = py(point.y)
        if (at === 0) context.moveTo(x, y)
        else context.lineTo(x, y)
      })
      context.stroke()

      context.fillStyle = context.strokeStyle
      for (const point of one.points) {
        context.beginPath()
        context.arc(px(point.x), py(point.y), 2, 0, Math.PI * 2)
        context.fill()
      }
    })
    context.setLineDash([])
  }, [series, xLabel, yLabel, logScale, height])

  return (
    <canvas
      ref={canvasRef}
      className="iv-chart"
      style={{ width: '100%', height }}
      aria-label={`${yLabel} 대 ${xLabel} 곡선`}
      role="img"
    />
  )
}
