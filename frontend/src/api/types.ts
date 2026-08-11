export interface User {
  id: number
  email: string
  role: string
}

export interface Project {
  id: number
  name: string
}

export interface Revision {
  id: number
  revision: number
}

export type JobStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'timed_out'
  | 'cancelled'

export interface Job {
  id: number
  status: JobStatus
  source_revision_id: number
}

export interface Artifact {
  sequence: number
  filename: string
  size_bytes: number
}

export interface JobDetail extends Job {
  log: string | null
  exit_code: number | null
  artifacts: Artifact[]
}

/** 더 이상 상태가 바뀌지 않는 잡. 폴링을 멈출 시점이다. */
export function isFinished(status: JobStatus): boolean {
  return status !== 'queued' && status !== 'running'
}
