/**
 * 단면 위에서 커서에 가장 가까운 계면을 찾는다.
 *
 * 계면은 선분 묶음이라 사각형 판정으로는 못 고른다 — 뒷면은 구조 전체 폭을
 * 가로지르고, 게이트 접촉은 폴리 윗면을 따라 꺾인다. 두 계면의 외접 사각형은
 * 얼마든지 겹칠 수 있다.
 */

/** 점과 선분 사이의 거리. */
export function distanceToSegment(
  px: number,
  py: number,
  x0: number,
  y0: number,
  x1: number,
  y1: number,
): number {
  const dx = x1 - x0
  const dy = y1 - y0
  const lengthSquared = dx * dx + dy * dy
  if (lengthSquared === 0) return Math.hypot(px - x0, py - y0)
  // 선분 위로 투영한 뒤 양 끝으로 자른다. 자르지 않으면 선분을 무한히 늘린
  // 직선까지의 거리가 되어, 멀리 떨어진 계면이 커서 옆에 있는 것처럼 잡힌다.
  const t = Math.max(
    0,
    Math.min(1, ((px - x0) * dx + (py - y0) * dy) / lengthSquared),
  )
  return Math.hypot(px - (x0 + t * dx), py - (y0 + t * dy))
}

export interface HitCandidate {
  key: string
  /** 화면 좌표(px)로 옮긴 선분들. `[x0, y0, x1, y1]` */
  segments: number[][]
}

/**
 * 문턱 안에서 가장 가까운 계면. 없으면 null.
 *
 * 문턱을 두는 이유: 늘 무언가가 잡히면 커서를 어디에 둬도 화면이 어두워진다.
 */
export function nearestInterface(
  px: number,
  py: number,
  candidates: HitCandidate[],
  threshold: number,
): string | null {
  let best: string | null = null
  let closest = threshold
  for (const candidate of candidates) {
    for (const [x0, y0, x1, y1] of candidate.segments) {
      const distance = distanceToSegment(px, py, x0, y0, x1, y1)
      if (distance <= closest) {
        closest = distance
        best = candidate.key
      }
    }
  }
  return best
}
