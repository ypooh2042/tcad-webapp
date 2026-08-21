/**
 * 잡 하나를 지켜본다.
 *
 * 서버가 알림을 밀어 주지 않으므로 주기적으로 물어본다. 이 규모(동시 4개)에서는
 * 폴링으로 충분하고, 웹소켓을 두면 워커·API·브라우저 사이에 상태가 어긋날
 * 경로가 하나 더 생긴다.
 */
import { useEffect, useState } from 'react'
import { jobs } from '../../api/endpoints'
import { isFinished, type JobConsole, type JobDetail } from '../../api/types'

const POLL_INTERVAL_MS = 1500

export function useJob(jobId: number | null) {
  const [job, setJob] = useState<JobDetail | null>(null)
  const [error, setError] = useState<Error | null>(null)
  //: 실행 출력. 잡이 끝난 뒤 한 번만 받는다 — 상태 조회에 실으면 폴링마다
  //: 출력 전체가 따라온다(`JobConsole` 주석 참조).
  const [console, setConsole] = useState<JobConsole | null>(null)

  useEffect(() => {
    if (jobId === null) return

    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined

    // 잡이 바뀌면 앞의 출력을 지운다. 남겨 두면 새 잡의 화면에 옛 로그가
    // 잠깐 보인다.
    setConsole(null)

    async function loadConsole() {
      try {
        const body = await jobs.console(jobId!)
        if (!cancelled) setConsole(body)
      } catch {
        // 출력은 곁다리다. 여기서 error 를 세우면 "연결이 불안정합니다" 가
        // 떠서, 잡은 멀쩡히 끝났는데 실패한 것처럼 보인다.
      }
    }

    async function tick() {
      try {
        const next = await jobs.get(jobId!)
        if (cancelled) return
        setJob(next)
        setError(null)
        // 끝난 잡은 상태가 더 바뀌지 않는다. 계속 물어봐야 같은 답이다.
        // 출력은 끝날 때 한 번 기록되므로 이때 받으면 된다.
        if (isFinished(next.status)) {
          void loadConsole()
          return
        }
      } catch (caught) {
        if (cancelled) return
        // 워커 재시작 중에는 잠깐 실패할 수 있다. 한 번 실패했다고 멈추면
        // 화면이 영영 갱신되지 않는다.
        setError(caught as Error)
      }
      timer = setTimeout(tick, POLL_INTERVAL_MS)
    }

    void tick()

    return () => {
      cancelled = true
      if (timer !== undefined) clearTimeout(timer)
    }
  }, [jobId])

  /** 서버 응답을 기다리지 않고 상태를 반영한다.
   *
   * 중단을 누르고 다음 폴링(1.5초)까지 "실행 중"으로 보이면 눌린 것인지 알 수
   * 없다. 폴링이 곧 같은 값을 확인해 주므로 어긋날 위험은 없다. */
  function applyStatus(status: JobDetail['status']) {
    setJob((current) => (current ? { ...current, status } : current))
  }

  return { job, error, console, applyStatus }
}
