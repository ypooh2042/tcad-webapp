/** 백엔드 엔드포인트를 이름 있는 함수로 감싼다. 화면에서 경로 문자열을 다루지 않게. */
import { request } from './client'
import type { JobStatus,
  Artifact,
  DocsReference,
  DocsSearchHit,
  DocsSection,
  DocsSectionSummary,
  FileEntry,
  FileUsage,
  Job,
  IssuedInvite,
  InviteSummary,
  JobDetail,
  ProfileResponse,
  Project,
  Revision,
  RevisionWithSource,
  StructureSummary,
  SurfaceResponse,
  User,
} from './types'

export const auth = {
  register: (email: string, password: string, inviteCode: string) =>
    request<User>('/api/auth/register', {
      method: 'POST',
      // 초대 없이는 가입할 수 없다. 이 서버는 제출된 코드를 컨테이너에서
      // 실행하므로 누가 쓰는지 모르는 상태로 열어 둘 수 없다.
      body: { email, password, invite_code: inviteCode },
    }),

  login: (email: string, password: string) =>
    request<User>('/api/auth/login', {
      method: 'POST',
      body: { email, password },
    }),

  logout: () => request<null>('/api/auth/logout', { method: 'POST' }),

  me: () => request<User>('/api/auth/me'),
}

export const projects = {
  list: () => request<Project[]>('/api/projects'),

  create: (name: string) =>
    request<Project>('/api/projects', { method: 'POST', body: { name } }),

  rename: (projectId: number, name: string) =>
    request<Project>(`/api/projects/${projectId}`, {
      method: 'PATCH',
      body: { name },
    }),

  /** 소스·잡·산출물이 함께 사라진다. 되돌릴 수 없다. */
  remove: (projectId: number) =>
    request<null>(`/api/projects/${projectId}`, { method: 'DELETE' }),

  /** 마지막으로 저장한 소스. 프로젝트를 열 때 편집기를 채운다. */
  latestSource: (projectId: number) =>
    request<RevisionWithSource>(`/api/projects/${projectId}/revisions/latest`),

  saveSource: (projectId: number, source: string) =>
    request<Revision>(`/api/projects/${projectId}/revisions`, {
      method: 'POST',
      body: { source },
    }),

  jobs: (projectId: number) =>
    request<Job[]>(`/api/projects/${projectId}/jobs`),

  submit: (projectId: number) =>
    request<Job>(`/api/projects/${projectId}/jobs`, { method: 'POST' }),
}

/** 사용자 작업공간. 폴더와 `.in` 파일만 다룬다. */
export const files = {
  tree: () => request<{ entries: FileEntry[] }>('/api/files'),

  usage: () => request<FileUsage>('/api/files/usage'),

  read: (path: string) =>
    request<{ path: string; content: string }>(
      `/api/files/content?path=${encodeURIComponent(path)}`,
    ),

  write: (path: string, content: string) =>
    request<{ path: string; content: string }>('/api/files/content', {
      method: 'PUT',
      body: { path, content },
    }),

  makeFolder: (path: string) =>
    request<FileEntry>('/api/files/folder', { method: 'POST', body: { path } }),

  /** 이름 바꾸기와 옮기기는 같은 연산이다. */
  rename: (path: string, destination: string) =>
    request<FileEntry>('/api/files/rename', {
      method: 'POST',
      body: { path, destination },
    }),

  remove: (path: string) =>
    request<null>(`/api/files?path=${encodeURIComponent(path)}`, {
      method: 'DELETE',
    }),

  /** 파일을 직접 실행한다. 서버가 제출 시점 내용을 스냅샷으로 남긴다. */
  run: (path: string) =>
    request<{ id: number; status: string; source_path: string }>(
      '/api/files/jobs',
      { method: 'POST', body: { path } },
    ),
}

export const jobs = {
  get: (jobId: number) => request<JobDetail>(`/api/jobs/${jobId}`),

  /** 대기 중이거나 실행 중인 잡을 멈춘다. 끝난 잡이면 서버가 409 로 거절한다. */
  cancel: (jobId: number) =>
    request<{ id: number; status: JobStatus }>(`/api/jobs/${jobId}/cancel`, {
      method: 'POST',
    }),

  artifact: (jobId: number, sequence: number) =>
    request<{ filename: string; content: string }>(
      `/api/jobs/${jobId}/artifacts/${sequence}`,
    ),
}

/** 매뉴얼. 카탈로그와 마찬가지로 인증이 필요 없다. */
export const docs = {
  sections: (kind?: string) =>
    request<DocsSectionSummary[]>(
      `/api/docs/sections${kind ? `?kind=${encodeURIComponent(kind)}` : ''}`,
    ),

  section: (id: string) =>
    request<DocsSection>(`/api/docs/sections/${encodeURIComponent(id)}`),

  /** 커서 아래 커맨드의 문서. 접두사를 서버가 해석한다. */
  forCommand: (token: string) =>
    request<DocsSection>(`/api/docs/for-command/${encodeURIComponent(token)}`),

  search: (query: string) =>
    request<{ query: string; hits: DocsSearchHit[] }>(
      `/api/docs/search?q=${encodeURIComponent(query)}`,
    ),

  /** 무리별 커맨드 목록. 찾을 낱말을 모를 때 훑어보는 것이라 검색과 다르다. */
  reference: () => request<DocsReference>('/api/docs/reference'),
}

/** 관리자 전용. 일반 사용자가 부르면 403 이 온다. */
export const admin = {
  issueInvite: (maxUses: number, validDays: number) =>
    request<IssuedInvite>('/api/admin/invites', {
      method: 'POST',
      body: { max_uses: maxUses, valid_days: validDays },
    }),

  listInvites: () => request<InviteSummary[]>('/api/admin/invites'),

  revokeInvite: (inviteId: number) =>
    request<null>(`/api/admin/invites/${inviteId}`, { method: 'DELETE' }),
}

/** 그림용으로 서버가 풀어 준 구조 데이터. */
export const plot = {
  summary: (jobId: number, sequence: number) =>
    request<StructureSummary>(
      `/api/jobs/${jobId}/artifacts/${sequence}/structure`,
    ),

  /** 1D 는 x 를 주지 않는다(깊이가 곧 x 축). 2D 는 자를 가로 위치가 필요하다. */
  profile: (jobId: number, sequence: number, quantity: string, x?: number) => {
    const params = new URLSearchParams({ quantity })
    if (x !== undefined) params.set('x', String(x))
    return request<ProfileResponse>(
      `/api/jobs/${jobId}/artifacts/${sequence}/profile?${params}`,
    )
  },

  /**
   * 2D 단면. quantity 가 null 이면 **재질만** 받는다.
   *
   * 물리량을 끼워 보내면 서버가 그 물리량의 해가 없는 요소를 버리므로, 재질
   * 그림에서 층이 통째로 빠질 수 있다.
   */
  surface: (jobId: number, sequence: number, quantity: string | null) =>
    request<SurfaceResponse>(
      `/api/jobs/${jobId}/artifacts/${sequence}/surface` +
        (quantity === null ? '' : `?quantity=${encodeURIComponent(quantity)}`),
    ),
}

export type {
  Artifact,
  DocsReference,
  DocsSearchHit,
  DocsSection,
  DocsSectionSummary,
  FileEntry,
  FileUsage,
  Job,
  IssuedInvite,
  InviteSummary,
  JobDetail,
  ProfileResponse,
  Project,
  Revision,
  RevisionWithSource,
  StructureSummary,
  SurfaceResponse,
  User,
}
