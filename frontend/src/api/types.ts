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

export interface ProfilePoint {
  depth: number
  value: number
  material: string
}

export interface ProfileResponse {
  quantity: string
  /** 2D 에서 어디를 잘랐는지. 1D 면 null. */
  cut_x: number | null
  points: ProfilePoint[]
}

export interface StructureSummary {
  filename: string
  dimension: number
  quantities: string[]
  materials: string[]
  bounds: { x_min: number; x_max: number; y_min: number; y_max: number }
  node_count: number
  element_count: number
  warnings: string[]
}

export interface SurfaceResponse {
  quantity: string
  x: number[]
  y: number[]
  triangles: [number, number, number][]
  /** 삼각형별 정점 3개의 값. 계면 정점은 물질마다 값이 다르므로 공유하지 않는다. */
  values: [number, number, number][]
  materials: string[]
  value_min: number
  value_max: number
}

export interface IssuedInvite {
  id: number
  /** 평문 코드. **이 응답에서만** 볼 수 있고 다시 조회할 수 없다. */
  code: string
  expires_at: string
  max_uses: number
}

export interface InviteSummary {
  id: number
  expires_at: string
  max_uses: number
  used_count: number
  revoked: boolean
  /** 지금 쓸 수 있는지. 만료·소진·회수를 서버가 합쳐서 판단해 준다. */
  usable: boolean
}
