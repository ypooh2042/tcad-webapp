/**
 * 2D 단면의 좌표 변환과 눈금.
 *
 * **그리기와 클릭 처리가 이 하나를 같이 쓴다.** 예전에는 각자 같은 수식을 따로
 * 갖고 있었는데, 그 상태로 눈금 여백을 넣으면 한쪽만 고쳐져 클릭한 자리와 컷
 * 선이 어긋난다.
 *
 * 캔버스는 jsdom 에서 그릴 수 없어 그리기 자체는 단위 테스트가 안 된다. 수식을
 * 떼어 두면 적어도 좌표는 검증할 수 있다.
 */
import { linearTicks } from './scale'

export interface Bounds {
  xMin: number
  xMax: number
  yMin: number
  yMax: number
}

/**
 * 눈금 라벨이 들어갈 자리. 없으면 캔버스 밖으로 나가 잘린다.
 *
 * 아래쪽은 두 줄이 들어간다 — 눈금 숫자와 축 이름. 한 줄로 붙이면 축 이름이
 * 첫 눈금("0")과 겹쳐서 둘 다 읽히지 않는다(실측).
 */
const MARGIN = { top: 6, right: 10, bottom: 34, left: 38 }

export interface SurfaceGeometry {
  left: number
  top: number
  plotWidth: number
  plotHeight: number
  /** 모델 x(µm) → 캔버스 x(px). */
  px: (x: number) => number
  /** 모델 y(깊이, µm) → 캔버스 y(px). 아래로 갈수록 깊다. */
  py: (y: number) => number
  /** 캔버스 x(px) → 모델 x(µm). px 의 역함수. */
  unpx: (px: number) => number
  clampX: (x: number) => number
  xTicks: number[]
  yTicks: number[]
  formatX: (value: number) => string
  formatY: (value: number) => string
}

/** 눈금 간격에 맞춰 자릿수를 정한다. 0.02 간격에 "0.0" 이면 전부 같아 보인다. */
function formatter(ticks: number[]): (value: number) => string {
  const step =
    ticks.length > 1 ? Math.abs((ticks[1] ?? 0) - (ticks[0] ?? 0)) : 1
  const decimals = Math.max(0, Math.ceil(-Math.log10(step || 1)))
  return (value: number) => value.toFixed(decimals)
}

export function surfaceGeometry(
  bounds: Bounds,
  width: number,
  height: number,
): SurfaceGeometry {
  const { xMin, xMax, yMin, yMax } = bounds
  const plotWidth = Math.max(0, width - MARGIN.left - MARGIN.right)
  const plotHeight = Math.max(0, height - MARGIN.top - MARGIN.bottom)

  const spanX = xMax - xMin
  const spanY = yMax - yMin

  // 한 점짜리 구조에서는 0 으로 나뉜다. 배율을 1 로 두고 가운데에 찍는다.
  const scale =
    spanX > 0 || spanY > 0
      ? Math.min(
          spanX > 0 ? plotWidth / spanX : Infinity,
          spanY > 0 ? plotHeight / spanY : Infinity,
        )
      : 1

  // 세로/가로 비율을 유지한다. 늘려 그리면 접합 깊이가 실제와 달라 보인다.
  const offsetX = MARGIN.left + (plotWidth - spanX * scale) / 2
  const offsetY = MARGIN.top + (plotHeight - spanY * scale) / 2

  const xTicks = linearTicks(xMin, xMax, 5)
  const yTicks = linearTicks(yMin, yMax, 5)

  return {
    left: MARGIN.left,
    top: MARGIN.top,
    plotWidth,
    plotHeight,
    px: (x) => offsetX + (x - xMin) * scale,
    py: (y) => offsetY + (y - yMin) * scale,
    unpx: (px) => (px - offsetX) / scale + xMin,
    clampX: (x) => Math.min(xMax, Math.max(xMin, x)),
    xTicks,
    yTicks,
    formatX: formatter(xTicks),
    formatY: formatter(yTicks),
  }
}
