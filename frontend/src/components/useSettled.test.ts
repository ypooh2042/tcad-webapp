/**
 * 값이 멎을 때까지 기다렸다가 알려주기.
 *
 * 단계를 빠르게 넘기면 지나치는 단계마다 서버에 물어보게 된다. 아무도 보지
 * 않는 화면을 위해 요청을 쏟아붓고, 실제로 nginx 레이트 리밋(20 req/s)에
 * 걸려 503 이 났다 — 단계당 요청이 4개(요약·물리량 2개·단면)라 꾹 누르면
 * 초당 27개가 나간다.
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useSettled } from './useSettled'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('멎을 때까지 기다리기', () => {
  it('처음 값은 곧바로 준다', () => {
    // 첫 화면까지 늦추면 결과가 늦게 뜨는 것처럼 보인다.
    const { result } = renderHook(() => useSettled(3, 200))

    expect(result.current).toBe(3)
  })

  it('바뀐 직후에는 옛 값을 유지한다', () => {
    const { result, rerender } = renderHook(({ v }) => useSettled(v, 200), {
      initialProps: { v: 0 },
    })

    rerender({ v: 1 })

    expect(result.current).toBe(0)
  })

  it('멎으면 마지막 값을 준다', () => {
    const { result, rerender } = renderHook(({ v }) => useSettled(v, 200), {
      initialProps: { v: 0 },
    })

    rerender({ v: 1 })
    act(() => void vi.advanceTimersByTime(200))

    expect(result.current).toBe(1)
  })

  it('계속 바뀌는 동안에는 중간 값을 내보내지 않는다', () => {
    // 이게 핵심이다. 15단계를 훑어도 마지막 하나만 불러오면 된다.
    const seen: number[] = []
    const { rerender } = renderHook(
      ({ v }) => {
        seen.push(useSettled(v, 200))
        return null
      },
      { initialProps: { v: 0 } },
    )

    for (const v of [1, 2, 3, 4, 5]) {
      rerender({ v })
      act(() => void vi.advanceTimersByTime(150)) // 멎기 전에 또 바뀐다
    }
    act(() => void vi.advanceTimersByTime(200))

    expect([...new Set(seen)]).toEqual([0, 5])
  })

  it('사라져도 타이머를 남기지 않는다', () => {
    const { rerender, unmount } = renderHook(({ v }) => useSettled(v, 200), {
      initialProps: { v: 0 },
    })
    rerender({ v: 1 })

    unmount()

    expect(() => vi.advanceTimersByTime(1000)).not.toThrow()
  })
})
