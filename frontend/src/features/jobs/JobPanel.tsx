import { useState } from 'react'
import { useJob } from './useJob'
import { ResultView } from '../../plot/ResultView'
import { jobs } from '../../api/endpoints'
import { isFinished, type JobStatus } from '../../api/types'

/**
 * 어느 실행인지 가리키는 이름.
 *
 * 잡 번호는 **전체 사용자가 공유하는 기본키**라 혼자 두 번 돌려도 건너뛴다
 * (#23 다음이 #27). 무엇을 언제 돌렸는지가 훨씬 읽기 쉽다. 경로가 없는
 * 예전 잡이나 아직 응답을 못 받은 동안에는 번호로 돌아간다.
 */
function runLabel(
  jobId: number,
  sourcePath: string | null | undefined,
  createdAt: string | undefined,
): string {
  if (!sourcePath) return `잡 #${jobId}`
  if (!createdAt) return sourcePath
  // 서버는 UTC 로 보낸다. 현지 시각으로 바꿔야 몇 시간 어긋나 보이지 않는다.
  const at = new Date(createdAt).toLocaleTimeString('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
  })
  return `${sourcePath} · ${at}`
}

const STATUS_LABEL: Record<JobStatus, string> = {
  queued: '대기 중',
  running: '실행 중',
  succeeded: '성공',
  failed: '실패',
  timed_out: '시간 초과',
  cancelled: '중단됨',
}

export function JobPanel({ jobId }: { jobId: number | null }) {
  const { job, error, applyStatus } = useJob(jobId)
  //: 실패한 잡에서는 로그가 전부다. 그때 차트 자리를 비켜 주면 한 화면에
  //: 더 많이 들어온다.
  const [logOnly, setLogOnly] = useState(false)
  //: 중단 요청이 실패했을 때만 채워진다. 조용히 넘어가면 사용자는 멈춘 줄
  //: 알고 계속 기다린다.
  const [cancelError, setCancelError] = useState<string | null>(null)

  //: 대기 중이거나 실행 중일 때만 멈출 수 있다. 끝난 잡에 버튼을 두면 눌러도
  //: 서버가 409 로 거절할 뿐이다.
  const live = job !== null && !isFinished(job.status)

  async function stop() {
    if (jobId === null) return
    try {
      const result = await jobs.cancel(jobId)
      applyStatus(result.status)
      setCancelError(null)
    } catch (caught) {
      setCancelError(
        caught instanceof Error ? caught.message : '알 수 없는 오류',
      )
    }
  }

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
        <span className="muted" title={`잡 #${jobId}`}>
          {runLabel(jobId, job?.source_path, job?.created_at)}
        </span>
        {error && <span className="error">연결이 불안정합니다</span>}
        {cancelError && (
          <span className="error">중단하지 못했습니다: {cancelError}</span>
        )}
        <div className="spacer" />
        {live && (
          <button className="link danger" onClick={() => void stop()}>
            중단
          </button>
        )}
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
