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

export interface RevisionWithSource extends Revision {
  source: string
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
  /** 예전 프로젝트 모델의 잔재. 파일로 돌린 잡은 비어 있다. */
  source_revision_id: number | null
  /** 어느 파일을 돌렸는지(작업공간 기준 경로). */
  source_path: string | null
}

export interface Artifact {
  sequence: number
  filename: string
  size_bytes: number
}

export interface JobDetail extends Job {
  log: string | null
  exit_code: number | null
  /** 제출 시각(시간대 포함). 화면은 잡 번호 대신 이걸로 실행을 가리킨다. */
  created_at: string
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

/** 작업공간 항목. 경로는 루트 기준이다 — 서버 절대경로가 아니다. */
export interface FileEntry {
  path: string
  name: string
  is_dir: boolean
  size_bytes: number
}

export interface FileUsage {
  used_bytes: number
  quota_bytes: number
  remaining_bytes: number
}

export interface DocsSectionSummary {
  id: string
  kind: string
  title: string
  command: string | null
  page_start: string
}

export interface DocsSection extends DocsSectionSummary {
  aliases: string[]
  page_end: string
  pdf_page_start: number
  pdf_page_end: number
  /** SYNOPSIS / DESCRIPTION / EXAMPLES ... */
  subsections: Record<string, string>
  key_parameters: string[]
}

/** 목록에서 고르는 데 필요한 것만. 산문과 파라미터는 고른 뒤에 따로 읽는다. */
export interface DocsReferenceCommand {
  name: string
  summary: string
  /** 매뉴얼에 설명이 있는가. suprem.key 에만 있는 커맨드는 false. */
  documented: boolean
  parameter_count: number
  /** 본문을 읽을 때 쓸 id. 설명이 없으면 null. */
  manual_section_id: string | null
  manual_page: string | null
}

export interface DocsReferenceGroup {
  name: string
  /** 이 무리가 무엇인지. 이름만으로는 왜 묶였는지 알 수 없다. */
  note: string
  commands: DocsReferenceCommand[]
}

export interface DocsReference {
  groups: DocsReferenceGroup[]
}

export interface DocsSearchHit {
  id: string
  title: string
  command: string | null
  kind: string
  snippet: string
}
