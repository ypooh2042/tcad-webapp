import { useState } from 'react'
import { useJob } from './useJob'
import { ResultView } from '../../plot/ResultView'
import type { JobStatus } from '../../api/types'

const STATUS_LABEL: Record<JobStatus, string> = {
  queued: '대기 중',
  running: '실행 중',
  succeeded: '성공',
  failed: '실패',
  timed_out: '시간 초과',
  cancelled: '취소됨',
}

export function JobPanel({ jobId }: { jobId: number | null }) {
  const { job, error } = useJob(jobId)
  //: 실패한 잡에서는 로그가 전부다. 그때 차트 자리를 비켜 주면 한 화면에
  //: 더 많이 들어온다.
  const [logOnly, setLogOnly] = useState(false)

  if (jobId === null) {
    return (
      <div className="panel muted">
        실행하면 여기에 로그와 결과가 나옵니다.
      </div>
    )
  }

  return (
    <div className="panel">
      <div className="panel-head">
        <span className={`status status-${job?.status ?? 'queued'}`}>
          {job ? STATUS_LABEL[job.status] : '확인 중'}
        </span>
        <span className="muted">잡 #{jobId}</span>
        {error && <span className="error">연결이 불안정합니다</span>}
        <div className="spacer" />
        {job?.artifacts.length ? (
          <button className="link" onClick={() => setLogOnly((only) => !only)}>
            {logOnly ? '결과 보기' : '로그만 보기'}
          </button>
        ) : null}
      </div>

      {job?.artifacts.length && !logOnly ? (
        <ResultView jobId={jobId} artifacts={job.artifacts} />
      ) : null}

      {/* 로그에는 사용자가 쓴 코드가 그대로 들어 있다. textContent 로만 넣는다. */}
      <pre className={logOnly ? 'log expanded' : 'log'}>
        {job?.log ?? '아직 출력이 없습니다.'}
      </pre>
    </div>
  )
}
