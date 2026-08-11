/** 백엔드 엔드포인트를 이름 있는 함수로 감싼다. 화면에서 경로 문자열을 다루지 않게. */
import { request } from './client'
import type {
  Artifact,
  Job,
  IssuedInvite,
  InviteSummary,
  JobDetail,
  ProfileResponse,
  Project,
  Revision,
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

export const jobs = {
  get: (jobId: number) => request<JobDetail>(`/api/jobs/${jobId}`),

  artifact: (jobId: number, sequence: number) =>
    request<{ filename: string; content: string }>(
      `/api/jobs/${jobId}/artifacts/${sequence}`,
    ),
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

  surface: (jobId: number, sequence: number, quantity: string) =>
    request<SurfaceResponse>(
      `/api/jobs/${jobId}/artifacts/${sequence}/surface` +
        `?quantity=${encodeURIComponent(quantity)}`,
    ),
}

export type {
  Artifact,
  Job,
  IssuedInvite,
  InviteSummary,
  JobDetail,
  ProfileResponse,
  Project,
  Revision,
  StructureSummary,
  SurfaceResponse,
  User,
}
