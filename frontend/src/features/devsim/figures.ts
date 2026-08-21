/**
 * 곡선에서 소자 지표를 뽑는다.
 *
 * 비교 화면이 이걸 쓴다. 곡선만 겹쳐 놓으면 "다르다"는 것만 보이고 **얼마나
 * 다른지**는 안 보인다. 문턱전압이 0.1V 옮겨간 것과 온전류가 두 배가 된 것은
 * 눈으로 구분되지 않는다.
 *
 * 낼 수 없는 값은 억지로 만들지 않고 null 을 준다. 점이 셋도 안 되는 곡선에서
 * 뽑은 문턱전압을 표에 적으면, 그게 측정값인 줄 알고 읽게 된다.
 */
import type { IvDataset } from '../../api/types'

export interface Point {
  x: number
  y: number
}

export interface Series {
  /** 범례에 쓸 이름. 단계가 없으면 빈 문자열. */
  label: string
  steps: Record<string, number>
  points: Point[]
}

/**
 * 저장된 곡선을 µA/µm 로 맞춘다.
 *
 * 해석기가 내는 단위를 A/µm 에서 µA/µm 로 바꾸었다. 그 전에 저장해 둔 결과는
 * 여전히 A/µm 이고, 그대로 겹쳐 그리면 한쪽 곡선이 바닥에 눌려 붙어 비교가
 * 되지 않는다. 모르는 단위는 **건드리지 않는다** — 조용히 배수를 곱하면 틀린
 * 값을 맞는 것처럼 보여준다.
 */
export function toMicroAmps(value: number, unit: string | undefined): number {
  return unit === 'A/um' ? value * 1e6 : value
}

export interface Figures {
  /** 최대 |전류| (µA/µm). */
  iOn: number
  /** 0 이 아닌 최소 |전류|. 전부 0 이면 null. */
  iOff: number | null
  onOff: number | null
  /** 최대 상호컨덕턴스 dI/dV. */
  gmMax: number | null
  /** 최대 gm 접선을 x 축까지 늘려 얻은 문턱전압. 전달 특성에서만 뜻이 있다. */
  vth: number | null
  /** 문턱 아래 기울기(mV/dec). */
  ss: number | null
  /** 원점 부근 기울기의 역수(Ω·µm). 출력 특성에서만 뜻이 있다. */
  ron: number | null
}

const EMPTY: Figures = {
  iOn: 0,
  iOff: null,
  onOff: null,
  gmMax: null,
  vth: null,
  ss: null,
  ron: null,
}

function formatVolts(value: number): string {
  return `${Number(value.toPrecision(4))}V`
}

/**
 * 전류가 가장 많이 움직인 전압원.
 *
 * 게이트 전류는 절연막 너머라 늘 0 근처다. 스윕 전압원의 전류를 그대로 쓰면
 * 전달 특성에서 빈 그래프가 나온다.
 */
export function dominantBias(dataset: IvDataset): string | null {
  const spans = new Map<string, { min: number; max: number }>()
  for (const row of dataset.rows) {
    for (const [name, value] of Object.entries(row.currents)) {
      const seen = spans.get(name)
      if (!seen) spans.set(name, { min: value, max: value })
      else {
        seen.min = Math.min(seen.min, value)
        seen.max = Math.max(seen.max, value)
      }
    }
  }
  let best: string | null = null
  let widest = -1
  for (const [name, span] of spans) {
    const width = Math.abs(span.max - span.min)
    if (width > widest) {
      widest = width
      best = name
    }
  }
  return best
}

/** 단계 조합마다 곡선 하나. 스윕 값 순으로 정렬한다. */
export function seriesOf(dataset: IvDataset, bias: string): Series[] {
  const grouped = new Map<string, Series>()
  for (const row of dataset.rows) {
    const key = JSON.stringify(row.steps)
    let series = grouped.get(key)
    if (!series) {
      series = {
        label: Object.entries(row.steps)
          .map(([name, value]) => `${name}=${formatVolts(value)}`)
          .join(', '),
        steps: { ...row.steps },
        points: [],
      }
      grouped.set(key, series)
    }
    series.points.push({
      x: row.sweep,
      y: toMicroAmps(row.currents[bias] ?? 0, dataset.current_unit),
    })
  }
  const result = [...grouped.values()]
  for (const series of result) {
    series.points.sort((a, b) => a.x - b.x)
  }
  return result
}

/** 이웃한 두 점 사이의 기울기. */
function slopes(points: Point[]): { x: number; y: number; slope: number }[] {
  const out: { x: number; y: number; slope: number }[] = []
  for (let i = 1; i < points.length; i++) {
    const dx = points[i].x - points[i - 1].x
    if (dx === 0) continue
    out.push({
      x: (points[i].x + points[i - 1].x) / 2,
      y: (Math.abs(points[i].y) + Math.abs(points[i - 1].y)) / 2,
      slope: (Math.abs(points[i].y) - Math.abs(points[i - 1].y)) / dx,
    })
  }
  return out
}

function subthresholdSwing(points: Point[], iOn: number): number | null {
  // 문턱 아래 구간만 본다. 포화 근처를 섞으면 기울기가 완만해져 실제보다
  // 나쁜 값이 나온다.
  let best: number | null = null
  for (let i = 1; i < points.length; i++) {
    const low = Math.abs(points[i - 1].y)
    const high = Math.abs(points[i].y)
    if (low <= 0 || high <= 0 || high <= low) continue
    if (high > iOn * 0.1) continue
    const decades = Math.log10(high / low)
    if (decades <= 0) continue
    const swing = ((points[i].x - points[i - 1].x) / decades) * 1000
    if (best === null || swing < best) best = swing
  }
  return best
}

export function figuresOf(series: Series): Figures {
  const points = series.points
  if (points.length === 0) return EMPTY

  const magnitudes = points.map((p) => Math.abs(p.y))
  const iOn = Math.max(...magnitudes)
  const positive = magnitudes.filter((value) => value > 0)
  const iOff = positive.length ? Math.min(...positive) : null
  const onOff = iOff && iOn > 0 ? iOn / iOff : null

  if (points.length < 3) {
    return { ...EMPTY, iOn, iOff, onOff }
  }

  const derivative = slopes(points)
  const peak = derivative.reduce((a, b) => (b.slope > a.slope ? b : a))
  const gmMax = peak.slope > 0 ? peak.slope : null

  // 최대 gm 지점의 접선을 x 축까지 늘린다. 교과서의 선형 외삽법이다.
  const vth = gmMax ? peak.x - peak.y / gmMax : null

  const ss = subthresholdSwing(points, iOn)

  // 원점 부근 기울기의 역수. 전류가 0 이면 저항이 아니라 열린 회로다.
  const first = derivative[0]
  const ron = first && first.slope > 0 ? 1 / first.slope : null

  return { iOn, iOff, onOff, gmMax, vth, ss, ron }
}
