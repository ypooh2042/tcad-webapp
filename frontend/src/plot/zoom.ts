/**
 * 가로축 확대·축소.
 *
 * 도핑 프로파일은 표면 0.1µm 안에서 대부분이 일어나는데 꼬리는 몇 µm 까지
 * 끌린다. 전체를 한 화면에 넣으면 정작 봐야 할 접합부가 몇 픽셀로 뭉개진다.
 *
 * 세로축은 건드리지 않는다. 로그 축이 이미 모든 자릿수를 담고 있고, 확대할
 * 때마다 세로 눈금이 바뀌면 단계를 오갈 때 높이를 비교할 수 없다.
 */

export interface View {
  from: number
  to: number
}

/**
 * 확대해 들어갈 수 있는 최소 폭 — 전체의 이 비율까지.
 *
 * 없으면 폭이 0 으로 수렴해 좌표 변환이 0 으로 나뉜다.
 */
const MIN_SPAN_RATIO = 1e-4

/**
 * 전체 범위 안으로 밀어 넣는다. 폭은 (담을 수 있는 한) 유지한다.
 *
 * 데이터가 바뀌었을 때 확대를 버리지 않고 살려 두는 데 쓴다 — 컷 위치만
 * 옮겼는데 확대가 풀리면 매번 다시 확대해야 한다. 새 범위가 더 좁거나
 * 어긋나면 안으로 밀어 넣어서 빈 화면이 뜨지 않게 한다.
 */
export function clampView(view: View, full: View): View {
  return clamp(view, full)
}

function clamp(view: View, full: View): View {
  const span = Math.min(view.to - view.from, full.to - full.from)
  let from = view.from
  if (from < full.from) from = full.from
  if (from + span > full.to) from = full.to - span
  return { from, to: from + span }
}

/**
 * `at` 지점을 제자리에 둔 채 확대/축소한다.
 *
 * @param factor 1 보다 작으면 확대, 크면 축소.
 */
export function zoomAround(view: View, full: View, factor: number, at: number): View {
  const span = view.to - view.from
  const fullSpan = full.to - full.from
  // 한 점짜리 데이터. 확대할 것이 없다.
  if (!(fullSpan > 0)) return view

  const next = Math.min(fullSpan, Math.max(fullSpan * MIN_SPAN_RATIO, span * factor))
  // 커서 아래가 움직이면 확대할수록 보려던 곳에서 멀어진다.
  const ratio = span > 0 ? (at - view.from) / span : 0.5

  return clamp({ from: at - ratio * next, to: at - ratio * next + next }, full)
}

/** 폭을 유지한 채 옮긴다. */
export function panBy(view: View, full: View, delta: number): View {
  return clamp({ from: view.from + delta, to: view.to + delta }, full)
}

export function resetView(full: View): View {
  return { ...full }
}
