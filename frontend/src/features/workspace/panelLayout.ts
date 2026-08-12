/**
 * 여러 패널이 편집기와 폭을 나눠 갖는 방법.
 *
 * 손잡이는 자기 패널만 본다. 그것만으로는 부족하다 — 매뉴얼과 결과가 함께 열려
 * 있으면 각자 옳은 폭이어도 합이 창을 넘길 수 있고, 넘치면 `minmax(0, 1fr)` 인
 * 편집기 칸이 소리 없이 0 으로 접힌다. 저장해 둔 폭을 되살릴 때와 창을 줄일 때
 * 실제로 그렇게 된다.
 */
import { useEffect, useState } from 'react'
import { MIN_EDITOR_WIDTH, MIN_WIDTH } from '../../components/Splitter'

/**
 * 편집기 자리가 남도록 패널 폭을 함께 줄인다.
 *
 * 넓은 패널이 더 많이 내놓는다. 똑같이 깎으면 좁은 쪽이 먼저 못 읽게 된다.
 * 다 줄여도 모자라면 하한에서 멈춘다 — 0 으로 접으면 되돌릴 손잡이도 사라진다.
 *
 * @param widths 패널 폭들.
 * @param available 창 폭.
 * @param reserved 손잡이처럼 패널도 편집기도 아닌 것이 쓰는 폭.
 */
export function fitPanels(
  widths: number[],
  available: number,
  reserved = 0,
): number[] {
  const budget = available - MIN_EDITOR_WIDTH - reserved
  const total = widths.reduce((sum, width) => sum + width, 0)
  if (total <= budget) return widths

  const floors = widths.map(() => MIN_WIDTH)
  const floorTotal = MIN_WIDTH * widths.length
  if (budget <= floorTotal) return floors

  // 하한 위로 남은 몫을 폭에 비례해 나눈다.
  const slack = widths.map((width) => Math.max(0, width - MIN_WIDTH))
  const slackTotal = slack.reduce((sum, extra) => sum + extra, 0)
  const scale = (budget - floorTotal) / slackTotal
  return slack.map((extra) => Math.floor(MIN_WIDTH + extra * scale))
}

/** 창 폭. 창을 줄이면 배분도 다시 해야 한다. */
export function useViewportWidth(): number {
  const [width, setWidth] = useState(() => window.innerWidth)

  useEffect(() => {
    function onResize() {
      setWidth(window.innerWidth)
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  return width
}
