import { useJob } from './useJob'
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
      </div>

      {job?.artifacts.length ? (
        <ul className="artifacts">
          {job.artifacts.map((artifact) => (
            <li key={artifact.sequence}>
              <span className="seq">{artifact.sequence}</span>
              {artifact.filename}
              <span className="muted">
                {(artifact.size_bytes / 1024).toFixed(1)} KB
              </span>
            </li>
          ))}
        </ul>
      ) : null}

      {/* 로그에는 사용자가 쓴 코드가 그대로 들어 있다. textContent 로만 넣는다. */}
      <pre className="log">{job?.log ?? '아직 출력이 없습니다.'}</pre>
    </div>
  )
}
