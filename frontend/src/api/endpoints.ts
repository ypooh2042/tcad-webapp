/** 백엔드 엔드포인트를 이름 있는 함수로 감싼다. 화면에서 경로 문자열을 다루지 않게. */
import { request } from './client'
import type {
  Artifact,
  Job,
  JobDetail,
  Project,
  Revision,
  User,
} from './types'

export const auth = {
  register: (email: string, password: string) =>
    request<User>('/api/auth/register', {
      method: 'POST',
      body: { email, password },
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

export type { Artifact, Job, JobDetail, Project, Revision, User }
