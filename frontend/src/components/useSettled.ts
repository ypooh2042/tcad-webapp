/**
 * 값이 멎을 때까지 기다렸다가 알려준다.
 *
 * 단계를 빠르게 넘길 때 **지나치는 단계마다 서버에 묻지 않기 위해** 쓴다.
 * 사람이 읽을 수 없는 속도로 지나가는 화면을 위해 요청을 쏟아부을 이유가 없고,
 * 실제로 nginx 레이트 리밋에 걸려 503 이 났다.
 *
 * 첫 값은 늦추지 않는다. 처음 화면까지 기다리게 하면 결과가 느린 것처럼 보인다.
 */
import { useEffect, useState } from 'react'

export function useSettled<T>(value: T, delayMs: number): T {
  const [settled, setSettled] = useState(value)

  useEffect(() => {
    if (value === settled) return
    const timer = setTimeout(() => setSettled(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, settled, delayMs])

  return settled
}
