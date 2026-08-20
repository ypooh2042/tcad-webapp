/**
 * 실행 시간 이어 세기.
 *
 * 서버가 계산해 준 값에서 시작해 1초마다 스스로 센다. 조회는 1.5초마다
 * 오므로 서버 값만 쓰면 시계가 뚝뚝 끊겨 보이고, 반대로 브라우저 시계만
 * 쓰면 서버와 어긋난 만큼 계속 틀린다.
 */
import { renderHook, act } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useElapsed } from './useElapsed'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('실행 시간 이어 세기', () => {
  it('아직 시작하지 않았으면 아무 값도 없다', () => {
    const { result } = renderHook(() => useElapsed(null, false))

    expect(result.current).toBeNull()
  })

  it('서버가 준 값에서 시작한다', () => {
    const { result } = renderHook(() => useElapsed(42, true))

    expect(result.current).toBe(42)
  })

  it('도는 동안 스스로 센다', () => {
    const { result } = renderHook(() => useElapsed(42, true))

    act(() => void vi.advanceTimersByTime(3000))

    expect(result.current).toBeGreaterThanOrEqual(45)
    expect(result.current).toBeLessThan(46)
  })

  it('끝난 잡은 멈춘다', () => {
    // 총 실행 시간이 화면을 열어 둔 동안 계속 늘어나면 안 된다.
    const { result } = renderHook(() => useElapsed(95, false))

    act(() => void vi.advanceTimersByTime(10_000))

    expect(result.current).toBe(95)
  })

  it('새 조회가 오면 그 값으로 다시 맞춘다', () => {
    const { result, rerender } = renderHook(
      ({ seconds }) => useElapsed(seconds, true),
      { initialProps: { seconds: 10 } },
    )

    act(() => void vi.advanceTimersByTime(5000))
    rerender({ seconds: 30 })

    expect(result.current).toBe(30)
  })

  it('화면을 떠나면 타이머를 정리한다', () => {
    const { unmount } = renderHook(() => useElapsed(1, true))
    const clear = vi.spyOn(globalThis, 'clearInterval')

    unmount()

    expect(clear).toHaveBeenCalled()
  })
})
