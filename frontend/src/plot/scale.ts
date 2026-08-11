/**
 * 로그 축과 색 매핑.
 *
 * 도핑 농도는 1e14~1e21 로 7제곱을 오간다. 선형 축이면 가장 큰 값 하나만 보이고
 * 나머지는 바닥에 붙는다. 그래서 로그가 기본이다.
 *
 * 0 과 음수를 어떻게 다루느냐가 관건이다. net_doping 은 p 형 영역에서 음수인데,
 * 로그를 취할 수 없다고 버리면 정작 봐야 할 접합 위치가 그림에서 사라진다.
 * 축 정의역에서는 빼되, 그런 값이 있었다는 사실은 화면에 알린다.
 */

export interface LogDomain {
  min: number
  max: number
  /** 0 이나 음수가 섞여 있었는지. 화면이 그 사실을 알려줄 근거다. */
  hasNonPositive: boolean
  /** 로그 축에 그릴 수 있는 값이 하나도 없는지. */
  empty: boolean
}

const FALLBACK: LogDomain = {
  min: 1,
  max: 10,
  hasNonPositive: true,
  empty: true,
}

export function toLogDomain(values: readonly number[]): LogDomain {
  const positive = values.filter((value) => value > 0 && Number.isFinite(value))
  const hasNonPositive = positive.length !== values.length

  if (positive.length === 0) return { ...FALLBACK, hasNonPositive }

  let min = Math.min(...positive)
  let max = Math.max(...positive)

  // 균일 도핑 기판이면 모든 값이 같다. 정의역이 한 점이면 축이 그려지지 않으므로
  // 위아래로 한 자릿수씩 벌린다.
  if (min === max) {
    min /= 10
    max *= 10
  }

  return { min, max, hasNonPositive, empty: false }
}

/** 눈금이 이보다 많으면 축 글자가 겹쳐 읽을 수 없다. */
const MAX_TICKS = 12

export function logTicks(min: number, max: number): number[] {
  if (!(min > 0) || !(max > 0) || max < min) return []

  const first = Math.ceil(Math.log10(min))
  const last = Math.floor(Math.log10(max))

  // 범위가 넓으면 10의 거듭제곱을 한 칸씩 건너뛴다.
  const step = Math.max(1, Math.ceil((last - first + 1) / MAX_TICKS))

  const ticks: number[] = []
  for (let exponent = first; exponent <= last; exponent += step) {
    ticks.push(10 ** exponent)
  }

  // 한 자릿수 안에 갇히면 거듭제곱 눈금이 하나도 없다. 그럴 땐 양끝을 쓴다.
  if (ticks.length === 0) return [min, max]
  return ticks
}

/**
 * 값 → 색. viridis 를 근사한 5색 구간 보간.
 *
 * 색상환(hue)을 그대로 도는 무지개 배색은 밝기가 들쭉날쭉해서, 실제로는 값이
 * 단조 증가하는데도 중간에 띠가 있는 것처럼 보인다. 밝기가 단조 증가하는
 * 배색이라야 농도 분포를 왜곡 없이 읽을 수 있다.
 */
const RAMP: readonly [number, number, number][] = [
  [68, 1, 84], // 짙은 보라
  [59, 82, 139],
  [33, 145, 140],
  [94, 201, 98],
  [253, 231, 37], // 노랑
]

/** 로그 축에 못 올리는 값(0·음수)의 색. 투명하게 두면 메시에 구멍처럼 보인다. */
const NON_POSITIVE_COLOR = '#3a3f4a'

export function colorFor(value: number, min: number, max: number): string {
  if (!(value > 0)) return NON_POSITIVE_COLOR

  const low = Math.log10(min)
  const high = Math.log10(max)
  // 정의역이 한 점이면 어디에 놓을지 정할 수 없다. 배색 중앙을 쓴다.
  const t =
    high === low
      ? 0.5
      : Math.min(1, Math.max(0, (Math.log10(value) - low) / (high - low)))

  const position = t * (RAMP.length - 1)
  const index = Math.min(RAMP.length - 2, Math.floor(position))
  const local = position - index

  const start = RAMP[index]!
  const end = RAMP[index + 1]!
  const channel = (i: number) =>
    Math.round(start[i]! + local * (end[i]! - start[i]!))

  return `rgb(${channel(0)}, ${channel(1)}, ${channel(2)})`
}
