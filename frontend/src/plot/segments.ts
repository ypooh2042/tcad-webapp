/**
 * 프로파일을 물질 구간으로 끊는다.
 *
 * 계면에서는 같은 깊이에 물질별 값이 따로 있다(1d_boron.str 의 표면에서
 * chem_boron 은 oxide 쪽 1.14e19, silicon 쪽 5.86e18). 한 줄로 이으면 수직으로
 * 뚝 떨어지는 가짜 선이 생겨서, 물질이 바뀌는 지점인데 농도가 급락한 것처럼
 * 보인다.
 */
import type { ProfilePoint } from '../api/types'

export interface Segment {
  material: string
  /** 이 구간의 값 부호. net_doping 은 p 형에서 음수다. */
  negative: boolean
  points: ProfilePoint[]
}

/**
 * 물질과 **부호**가 같은 점끼리 묶는다.
 *
 * 부호까지 나누는 이유는 net_doping 때문이다. 로그 축에는 절댓값을 올리는데,
 * 부호가 바뀌는 지점이 바로 접합(junction)이다. 한 선으로 이으면 접합이
 * 그냥 골짜기처럼 보여서, 소자에서 가장 중요한 위치가 그림에서 사라진다.
 */
export function splitByMaterial(points: readonly ProfilePoint[]): Segment[] {
  const segments: Segment[] = []

  for (const point of points) {
    const negative = point.value < 0
    const current = segments[segments.length - 1]
    // 같은 물질이라도 중간에 끊겼다면 새 구간이다. oxide/silicon/oxide 처럼
    // 층이 반복될 때 떨어진 두 층이 선으로 이어지면 안 된다.
    if (current && current.material === point.material && current.negative === negative) {
      current.points.push(point)
    } else {
      segments.push({ material: point.material, negative, points: [point] })
    }
  }

  return segments
}
