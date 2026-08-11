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

const { auth, projects, jobs, plot, admin, docs } = vi.hoisted(() => ({
  auth: { me: vi.fn(), login: vi.fn(), register: vi.fn(), logout: vi.fn() },
  projects: {
    list: vi.fn(),
    create: vi.fn(),
    saveSource: vi.fn(),
    latestSource: vi.fn(),
    submit: vi.fn(),
    jobs: vi.fn(),
  },
  jobs: { get: vi.fn(), artifact: vi.fn() },
  plot: { summary: vi.fn(), profile: vi.fn(), surface: vi.fn() },
  admin: { issueInvite: vi.fn(), listInvites: vi.fn(), revokeInvite: vi.fn() },
  docs: { sections: vi.fn(), section: vi.fn(), forCommand: vi.fn(), search: vi.fn() },
}))

vi.mock('../../api/endpoints', () => ({ auth, projects, jobs, plot, admin, docs }))

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
  admin.listInvites.mockResolvedValue([])
  docs.forCommand.mockRejectedValue(new Error('없음'))
  docs.search.mockResolvedValue({ query: '', hits: [] })
  projects.list.mockResolvedValue([PROJECT])
  projects.saveSource.mockResolvedValue({ id: 1, revision: 1 })
  projects.latestSource.mockResolvedValue({ id: 1, revision: 1, source: '저장된 소스\n' })
  projects.submit.mockResolvedValue({ id: 42, status: 'queued', source_revision_id: 1 })
  plot.summary.mockResolvedValue({
    filename: 'result.str',
    dimension: 1,
    quantities: ['chem_boron'],
    materials: ['silicon'],
    bounds: { x_min: 0, x_max: 2, y_min: 0, y_max: 0 },
    node_count: 43,
    element_count: 42,
    warnings: [],
  })
  plot.profile.mockResolvedValue({
    quantity: 'chem_boron',
    cut_x: null,
    points: [{ depth: 0, value: 1e18, material: 'silicon' }],
  })
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


describe('관리자 화면', () => {
  it('일반 사용자에게는 버튼이 없다', async () => {
    renderWorkspace()
    await screen.findByRole('button', { name: 'cmos' })

    expect(screen.queryByRole('button', { name: '관리자' })).not.toBeInTheDocument()
  })

  it('관리자에게만 보인다', async () => {
    auth.me.mockResolvedValue({ id: 1, email: 'a@example.com', role: 'admin' })
    renderWorkspace()

    expect(
      await screen.findByRole('button', { name: '관리자' }),
    ).toBeInTheDocument()
  })

  it('열면 초대 발급 화면이 나온다', async () => {
    auth.me.mockResolvedValue({ id: 1, email: 'a@example.com', role: 'admin' })
    renderWorkspace()

    await userEvent.click(await screen.findByRole('button', { name: '관리자' }))

    expect(screen.getByRole('button', { name: '발급' })).toBeInTheDocument()
  })

  it('닫으면 사라진다', async () => {
    auth.me.mockResolvedValue({ id: 1, email: 'a@example.com', role: 'admin' })
    renderWorkspace()
    await userEvent.click(await screen.findByRole('button', { name: '관리자' }))

    await userEvent.click(screen.getByRole('button', { name: '닫기' }))

    expect(screen.queryByRole('button', { name: '발급' })).not.toBeInTheDocument()
  })
})


describe('매뉴얼 패널', () => {
  it('버튼으로 열고 닫는다', async () => {
    renderWorkspace()
    await screen.findByRole('button', { name: 'cmos' })

    await userEvent.click(screen.getByRole('button', { name: '매뉴얼' }))
    expect(screen.getByLabelText('매뉴얼 검색')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '매뉴얼 닫기' }))
    expect(screen.queryByLabelText('매뉴얼 검색')).not.toBeInTheDocument()
  })
})


describe('프로젝트 전환', () => {
  const SECOND = { id: 8, name: 'nmos' }

  it('연 프로젝트의 저장된 소스를 편집기에 채운다', async () => {
    renderWorkspace()

    expect(await screen.findByDisplayValue(/저장된 소스/)).toBeInTheDocument()
  })

  it('탭을 누르면 그 프로젝트를 읽는다', async () => {
    // 이게 안 되면 탭만 강조되고 편집기에는 이전 내용이 남는다.
    projects.list.mockResolvedValue([PROJECT, SECOND])
    renderWorkspace()
    await screen.findByRole('button', { name: 'nmos' })
    projects.latestSource.mockClear()

    await userEvent.click(screen.getByRole('button', { name: 'nmos' }))

    await waitFor(() => expect(projects.latestSource).toHaveBeenCalledWith(8))
  })

  it('저장한 적 없는 프로젝트는 예제로 시작한다', async () => {
    const { ApiError } = await import('../../api/client')
    projects.latestSource.mockRejectedValue(
      new ApiError(404, '저장된 소스가 없습니다', null),
    )
    renderWorkspace()

    expect(await screen.findByDisplayValue(/mode one.dim/)).toBeInTheDocument()
  })

  it('저장하지 않은 편집이 있으면 먼저 묻는다', async () => {
    // 말없이 덮어쓰면 사용자는 방금 쓴 것을 잃고 이유도 모른다.
    projects.list.mockResolvedValue([PROJECT, SECOND])
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderWorkspace()
    await screen.findByRole('button', { name: 'nmos' })
    await userEvent.type(screen.getByLabelText('소스'), 'x')
    projects.latestSource.mockClear()

    await userEvent.click(screen.getByRole('button', { name: 'nmos' }))

    expect(confirm).toHaveBeenCalled()
    expect(projects.latestSource).not.toHaveBeenCalled()
    confirm.mockRestore()
  })

  it('버리기로 하면 이동한다', async () => {
    projects.list.mockResolvedValue([PROJECT, SECOND])
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderWorkspace()
    await screen.findByRole('button', { name: 'nmos' })
    await userEvent.type(screen.getByLabelText('소스'), 'x')
    projects.latestSource.mockClear()

    await userEvent.click(screen.getByRole('button', { name: 'nmos' }))

    await waitFor(() => expect(projects.latestSource).toHaveBeenCalledWith(8))
    confirm.mockRestore()
  })

  it('같은 탭을 다시 눌러도 묻지 않는다', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderWorkspace()
    await screen.findByRole('button', { name: 'cmos' })
    await userEvent.type(screen.getByLabelText('소스'), 'x')

    await userEvent.click(screen.getByRole('button', { name: 'cmos' }))

    expect(confirm).not.toHaveBeenCalled()
    confirm.mockRestore()
  })
})

describe('소스 로드와 입력 경합', () => {
  it('읽어오는 동안 친 내용을 덮어쓰지 않는다', async () => {
    // 새 프로젝트를 만들고 바로 치기 시작하면, 뒤늦게 도착한 응답이 방금 친
    // 것을 지운다. E2E 가 이 문제로 실패했다.
    let resolve: (value: { id: number; revision: number; source: string }) => void =
      () => {}
    projects.latestSource.mockReturnValue(
      new Promise((r) => {
        resolve = r
      }),
    )
    renderWorkspace()
    await screen.findByRole('button', { name: 'cmos' })

    await userEvent.type(screen.getByLabelText('소스'), '내가 친 것')
    resolve({ id: 1, revision: 1, source: '서버가 준 것' })

    await waitFor(() =>
      expect(screen.getByLabelText('소스')).toHaveDisplayValue(/내가 친 것/),
    )
  })
})
