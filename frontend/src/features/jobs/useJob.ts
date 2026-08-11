/**
 * 잡 하나를 지켜본다.
 *
 * 서버가 알림을 밀어 주지 않으므로 주기적으로 물어본다. 이 규모(동시 4개)에서는
 * 폴링으로 충분하고, 웹소켓을 두면 워커·API·브라우저 사이에 상태가 어긋날
 * 경로가 하나 더 생긴다.
 */
import { useEffect, useState } from 'react'
import { jobs } from '../../api/endpoints'
import { isFinished, type JobDetail } from '../../api/types'

const POLL_INTERVAL_MS = 1500

export function useJob(jobId: number | null) {
  const [job, setJob] = useState<JobDetail | null>(null)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    if (jobId === null) return

    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined

    async function tick() {
      try {
        const next = await jobs.get(jobId!)
        if (cancelled) return
        setJob(next)
        setError(null)
        // 끝난 잡은 상태가 더 바뀌지 않는다. 계속 물어봐야 같은 답이다.
        if (isFinished(next.status)) return
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

  return { job, error }
}
