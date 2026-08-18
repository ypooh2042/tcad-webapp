/**
 * 꾹 누르면 반복.
 *
 * 키보드 자동반복과 같은 규칙이다 — 처음 한 번은 즉시, 잠깐 뜸을 들인 뒤부터
 * 빠르게 반복한다. 뜸이 없으면 평범한 클릭도 두세 번으로 번진다.
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HOLD_DELAY_MS, HOLD_INTERVAL_MS, useHoldRepeat } from './useHoldRepeat'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

function press(result: { current: ReturnType<typeof useHoldRepeat> }) {
  act(() => result.current.onPointerDown())
}

function release() {
  act(() => {
    window.dispatchEvent(new Event('pointerup'))
  })
}

describe('꾹 누르기', () => {
  it('누르는 순간 한 번 실행한다', () => {
    const step = vi.fn()
    const { result } = renderHook(() => useHoldRepeat(step))

    press(result)

    expect(step).toHaveBeenCalledTimes(1)
  })

  it('짧게 눌렀다 떼면 한 번뿐이다', () => {
    // 이게 깨지면 한 칸 옮기려다 여러 칸이 넘어간다.
    const step = vi.fn()
    const { result } = renderHook(() => useHoldRepeat(step))

    press(result)
    act(() => void vi.advanceTimersByTime(HOLD_DELAY_MS - 50))
    release()
    act(() => void vi.advanceTimersByTime(1000))

    expect(step).toHaveBeenCalledTimes(1)
  })

  it('계속 누르고 있으면 반복한다', () => {
    const step = vi.fn()
    const { result } = renderHook(() => useHoldRepeat(step))

    press(result)
    act(() => void vi.advanceTimersByTime(HOLD_DELAY_MS + HOLD_INTERVAL_MS * 3))

    expect(step).toHaveBeenCalledTimes(5) // 최초 1 + 반복 4
  })

  it('떼면 멈춘다', () => {
    const step = vi.fn()
    const { result } = renderHook(() => useHoldRepeat(step))
    press(result)
    act(() => void vi.advanceTimersByTime(HOLD_DELAY_MS + HOLD_INTERVAL_MS))
    const before = step.mock.calls.length

    release()
    act(() => void vi.advanceTimersByTime(HOLD_INTERVAL_MS * 10))

    expect(step).toHaveBeenCalledTimes(before)
  })

  it('버튼 밖에서 떼도 멈춘다', () => {
    // 끝 단계에 닿으면 버튼이 비활성이 된다. 비활성 버튼은 pointerup 을 주지
    // 않으므로 버튼에서 듣고 있으면 영영 멈추지 않는다. 창에서 듣는 이유다.
    const step = vi.fn()
    const { result } = renderHook(() => useHoldRepeat(step))
    press(result)
    act(() => void vi.advanceTimersByTime(HOLD_DELAY_MS + HOLD_INTERVAL_MS))
    const before = step.mock.calls.length

    act(() => {
      window.dispatchEvent(new Event('pointercancel'))
    })
    act(() => void vi.advanceTimersByTime(HOLD_INTERVAL_MS * 10))

    expect(step).toHaveBeenCalledTimes(before)
  })

  it('사라져도 타이머를 남기지 않는다', () => {
    const step = vi.fn()
    const { result, unmount } = renderHook(() => useHoldRepeat(step))
    press(result)

    unmount()
    act(() => void vi.advanceTimersByTime(HOLD_INTERVAL_MS * 20))

    expect(step).toHaveBeenCalledTimes(1)
  })

  it('최신 동작을 부른다', () => {
    // 단계가 바뀌면 새 클로저가 만들어진다. 처음 것을 붙들면 같은 자리에서
    // 맴돈다.
    const first = vi.fn()
    const second = vi.fn()
    const { result, rerender } = renderHook(
      ({ fn }) => useHoldRepeat(fn),
      { initialProps: { fn: first } },
    )
    press(result)
    rerender({ fn: second })

    act(() => void vi.advanceTimersByTime(HOLD_DELAY_MS + HOLD_INTERVAL_MS))

    expect(second).toHaveBeenCalled()
  })
})
