/**
 * 꾹 누르면 반복하는 버튼 동작.
 *
 * 키보드 자동반복과 같은 규칙이다 — 누르는 순간 한 번, 잠깐 뜸을 들인 뒤부터
 * 빠르게 반복한다. 뜸이 없으면 평범한 클릭 한 번이 두세 번으로 번진다.
 *
 * **떼는 것은 버튼이 아니라 창에서 듣는다.** 끝에 닿으면 버튼이 비활성이 되는데,
 * 비활성 버튼은 pointerup 을 주지 않는다. 버튼에서만 듣고 있으면 손을 떼도
 * 반복이 멈추지 않는다.
 */
import { useCallback, useEffect, useRef } from 'react'

/** 반복이 시작되기까지의 뜸. 한 칸만 옮기려는 클릭과 구분하는 값이다. */
export const HOLD_DELAY_MS = 400

/**
 * 반복 주기.
 *
 * 단계를 옮길 때마다 서버에 다시 물어본다. 너무 짧으면 응답이 밀리기만 하고
 * 화면은 그만큼 빨라지지 않는다. 늦은 응답은 어차피 버려진다(ResultView).
 */
export const HOLD_INTERVAL_MS = 150

export function useHoldRepeat(action: () => void) {
  // 누르고 있는 동안 단계가 바뀌면 새 클로저가 만들어진다. 처음 것을 붙들면
  // 같은 자리에서 맴돈다.
  const latest = useRef(action)
  latest.current = action

  const timers = useRef<ReturnType<typeof setTimeout>[]>([])

  const stop = useCallback(() => {
    for (const timer of timers.current) clearTimeout(timer)
    timers.current = []
  }, [])

  useEffect(() => {
    window.addEventListener('pointerup', stop)
    window.addEventListener('pointercancel', stop)
    return () => {
      window.removeEventListener('pointerup', stop)
      window.removeEventListener('pointercancel', stop)
      stop()
    }
  }, [stop])

  const onPointerDown = useCallback(() => {
    stop()
    latest.current()

    const repeat = () => {
      latest.current()
      timers.current.push(setTimeout(repeat, HOLD_INTERVAL_MS))
    }
    timers.current.push(setTimeout(repeat, HOLD_DELAY_MS))
  }, [stop])

  return { onPointerDown }
}
