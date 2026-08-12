/**
 * 패널이 여럿일 때의 폭 배분.
 *
 * 손잡이 하나만 보면 옳은 폭도, 옆에 다른 패널이 있으면 편집기를 밀어낸다.
 * 그리드의 편집기 칸은 `minmax(0, 1fr)` 이라 넘치면 소리 없이 0 으로 접힌다 —
 * 화면에서는 패널이 왼쪽 끝에 붙은 것처럼 보인다.
 */
import { describe, expect, it } from 'vitest'
import { MIN_EDITOR_WIDTH, MIN_WIDTH } from '../../components/Splitter'
import { fitPanels } from './panelLayout'

const sum = (widths: number[]) => widths.reduce((total, w) => total + w, 0)

describe('패널 폭 배분', () => {
  it('여유가 있으면 그대로 둔다', () => {
    expect(fitPanels([360, 400], 1920)).toEqual([360, 400])
  })

  it('넘치면 편집기 자리를 남긴다', () => {
    // 예전 버전이 저장해 둔 과한 폭이 그대로 되살아나면 안 된다.
    const fitted = fitPanels([1400, 400], 1920)

    expect(sum(fitted)).toBeLessThanOrEqual(1920 - MIN_EDITOR_WIDTH)
  })

  it('넓은 쪽이 더 많이 내놓는다', () => {
    // 좁은 패널까지 똑같이 깎으면 읽을 수 없게 된다.
    const [wide, narrow] = fitPanels([1400, 400], 1920)

    expect(1400 - wide).toBeGreaterThan(400 - narrow)
  })

  it('아무리 줄여도 안 되면 하한은 지킨다', () => {
    // 0 으로 접으면 되돌릴 손잡이까지 사라진다.
    expect(fitPanels([800, 800], 700)).toEqual([MIN_WIDTH, MIN_WIDTH])
  })

  it('패널이 하나일 때도 편집기를 살린다', () => {
    expect(fitPanels([1800], 1920)).toEqual([1920 - MIN_EDITOR_WIDTH])
  })

  it('손잡이가 차지하는 폭도 센다', () => {
    // 손잡이를 빼먹으면 딱 그 몇 픽셀만큼 넘쳐 편집기가 접힌다.
    const fitted = fitPanels([1400, 400], 1920, 14)

    expect(sum(fitted)).toBeLessThanOrEqual(1920 - MIN_EDITOR_WIDTH - 14)
  })
})
