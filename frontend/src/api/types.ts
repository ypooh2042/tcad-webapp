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

/** 잡의 종류. 화면이 어떤 결과 보기를 띄울지 이걸로 고른다. */
export type JobKind = 'suprem' | 'devsim'

export interface Job {
  id: number
  status: JobStatus
  kind: JobKind
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
  /**
   * 위 log 가 상한에 걸려 잘렸는지. 참이면 화면이 전문 내려받기를 안내한다.
   * 잘렸다는 말 없이 보여 주면 사용자는 로그가 그게 전부인 줄 안다.
   */
  log_truncated: boolean
  exit_code: number | null
  /** 제출 시각(시간대 포함). 화면은 잡 번호 대신 이걸로 실행을 가리킨다. */
  created_at: string
  /**
   * 실행에 걸린 시간(초). 도는 중이면 지금까지, 끝났으면 총 실행 시간.
   * 아직 큐에서 기다리는 중이면 null — 대기 시간은 실행 시간이 아니다.
   *
   * **서버가 계산해서 준다.** 브라우저가 제출 시각과 자기 시계를 빼서 구하면
   * 시계가 어긋난 만큼 그대로 틀린다.
   */
  elapsed_seconds: number | null
  /** 도는 동안의 공정 진행. 끝난 잡에는 없다. */
  progress: JobProgress | null
  artifacts: Artifact[]
}

/** 소스가 적어 둔 `structure out=` 중 몇 개가 저장됐는지. */
export interface JobProgress {
  done: number
  total: number
  /** 마지막으로 저장된 구조 파일 이름. 아직 하나도 없으면 null. */
  latest: string | null
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

/** 편집기에 열어 둔 탭 하나. 저장하지 않은 내용과 커서 자리를 함께 담는다. */
export interface PersistedTab {
  path: string
  /** 저장하지 않은 편집 내용. 파일 그대로면 null. */
  draft: string | null
  /** 1-based 줄·칸. */
  cursor: { line: number; column: number } | null
}

export interface PersistedEditorState {
  tabs: PersistedTab[]
  active: string | null
}

/** 동시 접속 정원 사용 현황. */
export interface Occupancy {
  /** 정원을 차지하고 있는 **사람** 수(세션 수가 아니다). */
  occupied: number
  capacity: number
  /** 접속 중인 관리자 수. 정원 밖이라 occupied 에 섞이지 않는다. */
  admins: number
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


/**
 * 구조에서 자동으로 찾은 전극 하나.
 *
 * 규칙은 SUPREM 원본의 것을 그대로 옮긴 것이다(같은 금속 덩어리에 닿은 계면은
 * 하나의 전극). 그래서 등전위가 **구성상** 보장되고, 사용자가 따로 묶어 줄
 * 필요가 없다.
 */
export interface DevSimElectrode {
  /** 조건이 이 전극을 가리킬 때 쓰는 열쇠. 같은 구조면 항상 같다. */
  key: string
  origin: 'detected' | 'backside' | 'picked'
  kind: 'semiconductor' | 'insulator'
  materials: string[]
  extent: { x_min: number; x_max: number; y_min: number; y_max: number }
  edge_count: number
  /** 화면에 그릴 선분들. `[x0, y0, x1, y1]`, 단위 µm. */
  segments: number[][]
}

export interface DevSimElectrodes {
  filename: string
  gate_model: GateModel
  electrodes: DevSimElectrode[]
}

export type GateModel = 'semiconductor' | 'conductor'

export type BiasRole = 'sweep' | 'step' | 'const'

/** 전압원 하나. 여기 묶인 전극들이 같은 전위를 갖는다. */
export interface Bias {
  name: string
  electrodes: string[]
  role: BiasRole
  /** role='const' */
  value?: number
  /** role='step' — 곡선족을 만든다. */
  values?: number[]
  /** role='sweep' — 곡선의 x 축. */
  sweep?: { start: number; stop: number; step: number }
}

export interface ElectrodeChoice {
  origin: 'detected' | 'backside' | 'picked'
  label: string
  key?: string
  box?: { x_min: number; x_max: number; y_min: number; y_max: number }
}

export interface DeviceSpec {
  label: string
  electrodes: ElectrodeChoice[]
  biases: Bias[]
  gate_model?: GateModel
  temperature_k?: number
}

/** 바이어스 점 하나의 결과. */
export interface IvRow {
  sweep: number
  steps: Record<string, number>
  /** 전압원별 전류. 단위는 A/µm. */
  currents: Record<string, number>
}

export interface IvDataset {
  sweep: string | null
  biases: string[]
  current_unit: string
  rows: IvRow[]
  total: number
  completed: number
  /** 도중에 멈췄으면 그 사유. 부분 곡선은 rows 에 남아 있다. */
  error: string | null
}

export interface DevSimRunSummary {
  job_id: number
  label: string
  structure: string
  created_at: string
  completed: number
  total: number
}

export interface DevSimRunDetail extends DevSimRunSummary {
  spec: DeviceSpec
  data: IvDataset
}

export interface StructureSource {
  job_id: number
  source_path: string | null
  created_at: string
  artifacts: { sequence: number; filename: string }[]
}

export interface DevSimSubmitResponse {
  id: number
  status: JobStatus
  total_points: number
}
