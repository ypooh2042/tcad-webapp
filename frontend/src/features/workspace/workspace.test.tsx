/**
 * 작업 화면.
 *
 * 여기서 가장 중요한 규칙은 "실행 전에 저장한다"이다. 실행은 서버에 저장된
 * 최신 리비전을 돌리므로, 편집 중인 내용을 저장하지 않고 실행하면 방금 고친
 * 줄이 빠진 결과가 나온다. 사용자는 그걸 알아챌 방법이 없다.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { WorkspacePage } from './WorkspacePage'
import { AuthProvider } from '../auth/AuthContext'

const { auth, projects, jobs } = vi.hoisted(() => ({
  auth: { me: vi.fn(), login: vi.fn(), register: vi.fn(), logout: vi.fn() },
  projects: {
    list: vi.fn(),
    create: vi.fn(),
    saveSource: vi.fn(),
    submit: vi.fn(),
    jobs: vi.fn(),
  },
  jobs: { get: vi.fn(), artifact: vi.fn() },
}))

vi.mock('../../api/endpoints', () => ({ auth, projects, jobs }))

// Monaco 는 jsdom 에서 뜨지 않는다. 편집 동작 자체는 E2E 의 몫이고, 여기서는
// 저장·실행 흐름만 본다.
vi.mock('../editor/SupremEditor', () => ({
  SupremEditor: ({
    value,
    onChange,
  }: {
    value: string
    onChange: (v: string) => void
  }) => (
    <textarea
      aria-label="소스"
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}))

const PROJECT = { id: 7, name: 'cmos' }

beforeEach(() => {
  vi.clearAllMocks()
  auth.me.mockResolvedValue({ id: 1, email: 'a@example.com', role: 'user' })
  auth.logout.mockResolvedValue(null)
  projects.list.mockResolvedValue([PROJECT])
  projects.saveSource.mockResolvedValue({ id: 1, revision: 1 })
  projects.submit.mockResolvedValue({ id: 42, status: 'queued', source_revision_id: 1 })
  jobs.get.mockResolvedValue({
    id: 42,
    status: 'succeeded',
    source_revision_id: 1,
    log: '완료',
    exit_code: 0,
    artifacts: [{ sequence: 1, filename: 'result.str', size_bytes: 2048 }],
  })
})

function renderWorkspace() {
  return render(
    <AuthProvider>
      <WorkspacePage />
    </AuthProvider>,
  )
}

describe('프로젝트', () => {
  it('내 프로젝트를 보여준다', async () => {
    renderWorkspace()

    expect(await screen.findByRole('button', { name: 'cmos' })).toBeInTheDocument()
  })

  it('첫 프로젝트를 자동으로 연다', async () => {
    renderWorkspace()

    await waitFor(() =>
      expect(screen.getByRole('button', { name: '실행' })).toBeEnabled(),
    )
  })

  it('프로젝트가 없으면 저장과 실행을 막는다', async () => {
    projects.list.mockResolvedValue([])
    renderWorkspace()

    await waitFor(() =>
      expect(screen.getByRole('button', { name: '실행' })).toBeDisabled(),
    )
  })
})

describe('저장', () => {
  it('편집한 내용을 리비전으로 저장한다', async () => {
    renderWorkspace()
    await screen.findByRole('button', { name: 'cmos' })

    await userEvent.clear(screen.getByLabelText('소스'))
    await userEvent.type(screen.getByLabelText('소스'), 'init boron')
    await userEvent.click(screen.getByRole('button', { name: /저장/ }))

    await waitFor(() =>
      expect(projects.saveSource).toHaveBeenCalledWith(7, 'init boron'),
    )
  })

  it('저장하면 리비전 번호를 알려준다', async () => {
    projects.saveSource.mockResolvedValue({ id: 9, revision: 3 })
    renderWorkspace()
    await screen.findByRole('button', { name: 'cmos' })

    await userEvent.click(screen.getByRole('button', { name: /저장/ }))

    expect(await screen.findByText(/리비전 3 저장됨/)).toBeInTheDocument()
  })
})

describe('실행', () => {
  it('편집한 내용이 있으면 저장하고 나서 실행한다', async () => {
    renderWorkspace()
    await screen.findByRole('button', { name: 'cmos' })

    await userEvent.type(screen.getByLabelText('소스'), 'x')
    await userEvent.click(screen.getByRole('button', { name: '실행' }))

    await waitFor(() => expect(projects.submit).toHaveBeenCalled())
    // 저장이 먼저 일어나야 방금 고친 줄이 반영된다.
    expect(projects.saveSource).toHaveBeenCalled()
    expect(projects.saveSource.mock.invocationCallOrder[0]).toBeLessThan(
      projects.submit.mock.invocationCallOrder[0],
    )
  })

  it('바뀐 것이 없으면 다시 저장하지 않는다', async () => {
    renderWorkspace()
    await screen.findByRole('button', { name: 'cmos' })
    await userEvent.click(screen.getByRole('button', { name: /저장/ }))
    projects.saveSource.mockClear()

    await userEvent.click(screen.getByRole('button', { name: '실행' }))

    await waitFor(() => expect(projects.submit).toHaveBeenCalled())
    expect(projects.saveSource).not.toHaveBeenCalled()
  })

  it('제출한 잡의 결과를 보여준다', async () => {
    renderWorkspace()
    await screen.findByRole('button', { name: 'cmos' })

    await userEvent.click(screen.getByRole('button', { name: '실행' }))

    expect(await screen.findByText('result.str')).toBeInTheDocument()
    expect(await screen.findByText('성공')).toBeInTheDocument()
  })
})

describe('오류', () => {
  it('서버 오류 메시지를 그대로 보여준다', async () => {
    const { ApiError } = await import('../../api/client')
    projects.submit.mockRejectedValue(
      new ApiError(400, '저장된 소스가 없습니다. 먼저 코드를 저장해 주세요.', null),
    )
    projects.saveSource.mockRejectedValue(
      new ApiError(400, '저장된 소스가 없습니다. 먼저 코드를 저장해 주세요.', null),
    )
    renderWorkspace()
    await screen.findByRole('button', { name: 'cmos' })

    await userEvent.click(screen.getByRole('button', { name: '실행' }))

    expect(await screen.findByText(/저장된 소스가 없습니다/)).toBeInTheDocument()
  })
})
