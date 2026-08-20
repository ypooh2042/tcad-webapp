import { useState } from 'react'
import { useJob } from './useJob'
import { useElapsed } from './useElapsed'
import { formatDuration } from './duration'
import { ResultView } from '../../plot/ResultView'
import { jobs } from '../../api/endpoints'
import { isFinished, type JobProgress, type JobStatus } from '../../api/types'

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

/**
 * 지금 어느 단계까지 갔는지.
 *
 * 로그는 실행이 끝나야 도착한다. 그때까지 "실행 중" 세 글자만 보이면 사용자는
 * 멈춘 것인지 도는 것인지 알 수 없다 — 53단계 흐름은 몇 분씩 걸린다.
 */
function progressLabel(progress: JobProgress): string {
  const counted = `${progress.done}/${progress.total}`
  if (progress.latest === null) return `첫 단계 진행 중 · ${counted}`
  return `${progress.latest} 완료 · ${counted}`
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

  //: 서버가 준 값에서 이어 센다. 조회는 1.5초마다 오므로 그것만 쓰면 시계가
  //: 뚝뚝 끊겨 보이고, 브라우저 시계로 직접 계산하면 서버와 어긋난 만큼 틀린다.
  const elapsed = useElapsed(
    job?.elapsed_seconds ?? null,
    job?.status === 'running',
  )

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
        {elapsed !== null && (
          /* 도는 동안에는 늘어나는 시간을, 끝난 뒤에는 총 실행 시간을 보여준다. */
          <span className="muted elapsed">
            {job?.status === 'running'
              ? `${formatDuration(elapsed)}…`
              : `총 ${formatDuration(elapsed)}`}
          </span>
        )}
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
        {job?.log_truncated ? (
          /* 잘린 경우에만 띄운다. 늘 있으면 안내가 아니라 잡음이 된다. */
          <a className="link" href={jobs.logUrl(jobId)} download>
            로그 전문 내려받기
          </a>
        ) : null}
        {job?.artifacts.length ? (
          <button className="link" onClick={() => setLogOnly((only) => !only)}>
            {logOnly ? '결과 보기' : '로그만 보기'}
          </button>
        ) : null}
      </div>

      {/* 진행 문구는 **도는 동안에만** 있다. 서버가 끝난 잡에는 주지 않으므로
          여기서 따로 지울 필요가 없다. */}
      {job?.progress && (
        <div className="muted progress">{progressLabel(job.progress)}</div>
      )}

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
