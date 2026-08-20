/**
 * 실행 시간을 1초마다 이어 센다.
 *
 * 시작값은 **서버가 계산해서 내려준다.** 브라우저가 제출 시각과 자기 시계를
 * 빼서 구하면 시계가 어긋난 만큼 그대로 틀린 시간을 보여준다. 여기서는 그
 * 값에 흐른 시간만 더하고, 다음 조회(1.5초)가 다시 맞춰 준다.
 *
 * 흐른 시간은 두 시각의 **차이**로만 쓰므로 브라우저 시계가 서버와 몇 분
 * 어긋나 있어도 영향을 받지 않는다.
 */
import { useEffect, useRef, useState } from 'react'

const TICK_MS = 1000

/**
 * @param serverSeconds 서버가 알려준 실행 시간(초). 아직 시작 전이면 null.
 * @param running 도는 중인지. 끝난 잡은 멈춰야 총 실행 시간이 고정된다.
 */
export function useElapsed(
  serverSeconds: number | null,
  running: boolean,
): number | null {
  const [seconds, setSeconds] = useState<number | null>(serverSeconds)
  //: 마지막으로 서버 값을 받은 시점. 여기서부터 흐른 만큼을 더한다.
  const anchor = useRef({ at: Date.now(), value: serverSeconds ?? 0 })

  useEffect(() => {
    anchor.current = { at: Date.now(), value: serverSeconds ?? 0 }
    setSeconds(serverSeconds)
  }, [serverSeconds])

  useEffect(() => {
    if (!running || serverSeconds === null) return

    const timer = setInterval(() => {
      const { at, value } = anchor.current
      setSeconds(value + (Date.now() - at) / 1000)
    }, TICK_MS)

    return () => clearInterval(timer)
  }, [running, serverSeconds])

  return seconds
}
