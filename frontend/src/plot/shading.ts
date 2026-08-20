/**
 * 삼각형을 값에 따라 칠하기 위한 준비.
 *
 * 캔버스 2D 에는 정점마다 색이 다른 삼각형을 그리는 기능이 없다. 그래서
 * 삼각형을 재귀로 잘게 나누고 각 조각을 단색으로 칠해 정점 보간(Gouraud)을
 * 흉내 낸다.
 *
 * **평균은 반드시 로그 공간에서 낸다.** 도핑은 1e5 에서 1e21 까지 자릿수를
 * 오간다. 산술평균 (1e5 + 1e5 + 1e20)/3 은 3.3e19 로 사실상 최댓값이라,
 * 도핑된 정점 하나에 닿기만 해도 삼각형 전체가 최고 농도로 칠해진다. 실측:
 * 그 탓에 증착 산화막 안의 저농도 영역이 통째로 메워져 화면에서 사라졌다.
 */

export interface Corners {
  ax: number
  ay: number
  bx: number
  by: number
  cx: number
  cy: number
}

export interface Shard extends Corners {
  /** 이 조각을 칠할 log10 농도. */
  logValue: number
}

/**
 * 로그를 못 취하는 값의 자리.
 *
 * 버리면 그 자리에 구멍이 뚫린다. 실제 데이터의 바닥은 1e5(=5)이므로 그보다
 * 한참 아래로 보내 배색의 맨 끝에 붙게 한다.
 */
const FLOOR = -30

export function logOf(value: number): number {
  return value > 0 && Number.isFinite(value) ? Math.log10(value) : FLOOR
}

/**
 * 삼각형 개수에 맞춘 세분화 깊이.
 *
 * 비용은 4^depth 로 는다. 성긴 격자에서는 깊게 나눠야 무늬가 사라지고, 촘촘한
 * 격자에서는 이미 화면상 몇 픽셀이라 나눌 이유가 없다.
 */
export function subdivisionDepth(triangleCount: number): number {
  if (triangleCount <= 4_000) return 3
  if (triangleCount <= 20_000) return 2
  if (triangleCount <= 60_000) return 1
  return 0
}

/**
 * 삼각형 하나를 4^depth 조각으로 나눈다.
 *
 * 각 조각의 색은 세 꼭짓점 log 값의 평균으로 정한다. 나눌수록 그 평균이
 * 실제 보간값에 가까워진다.
 */
export function shadeTriangle(
  corners: Corners,
  logValues: readonly [number, number, number] | readonly number[],
  depth: number,
  /**
   * 세 꼭짓점 값의 폭이 이보다 좁으면 더 나누지 않는다. 색이 눈에 띄게 변하지
   * 않는 삼각형까지 나누면, 대부분이 균일한 실제 구조에서 헛일만 수천 배로
   * 는다. 0 이면 언제나 끝까지 나눈다.
   */
  tolerance = 0,
): Shard[] {
  const [va, vb, vc] = logValues as readonly number[]
  const out: Shard[] = []

  const split = (
    ax: number, ay: number, a: number,
    bx: number, by: number, b: number,
    cx: number, cy: number, c: number,
    left: number,
  ): void => {
    const spread = Math.max(a, b, c) - Math.min(a, b, c)
    if (left <= 0 || spread <= tolerance) {
      out.push({ ax, ay, bx, by, cx, cy, logValue: (a + b + c) / 3 })
      return
    }
    // 각 변의 중점. 값도 함께 절반씩 나눈다 — 선형 보간이므로 이것이 정확하다.
    const abx = (ax + bx) / 2, aby = (ay + by) / 2, ab = (a + b) / 2
    const bcx = (bx + cx) / 2, bcy = (by + cy) / 2, bc = (b + c) / 2
    const cax = (cx + ax) / 2, cay = (cy + ay) / 2, ca = (c + a) / 2

    split(ax, ay, a, abx, aby, ab, cax, cay, ca, left - 1)
    split(abx, aby, ab, bx, by, b, bcx, bcy, bc, left - 1)
    split(cax, cay, ca, bcx, bcy, bc, cx, cy, c, left - 1)
    split(abx, aby, ab, bcx, bcy, bc, cax, cay, ca, left - 1)
  }

  split(
    corners.ax, corners.ay, va ?? FLOOR,
    corners.bx, corners.by, vb ?? FLOOR,
    corners.cx, corners.cy, vc ?? FLOOR,
    Math.max(0, Math.trunc(depth)),
  )
  return out
}
