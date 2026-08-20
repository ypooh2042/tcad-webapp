import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const { auth, projects, files, editor } = vi.hoisted(() => ({
  auth: {
    me: vi.fn(),
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    occupancy: vi.fn(),
  },
  projects: { list: vi.fn(), create: vi.fn(), saveSource: vi.fn(), submit: vi.fn(), jobs: vi.fn() },
  files: { tree: vi.fn(), usage: vi.fn(), read: vi.fn() },
  editor: { state: vi.fn(), save: vi.fn() },
}))

vi.mock('./api/endpoints', () => ({
  auth,
  projects,
  files,
  editor,
  jobs: { get: vi.fn() },
}))
vi.mock('./features/editor/SupremEditor', () => ({
  SupremEditor: () => <div>편집기</div>,
}))

beforeEach(() => {
  vi.clearAllMocks()
  projects.list.mockResolvedValue([])
  auth.occupancy.mockResolvedValue({ occupied: 1, capacity: 5, admins: 0 })
  editor.state.mockResolvedValue({ tabs: [], active: null })
  editor.save.mockResolvedValue(null)
  files.tree.mockResolvedValue({ entries: [] })
})

describe('첫 화면', () => {
  it('세션을 확인하는 동안에는 로그인 화면을 띄우지 않는다', () => {
    // 여기서 로그인 화면을 먼저 그리면 이미 로그인한 사용자에게도 한 번
    // 깜빡이며 보인다.
    auth.me.mockReturnValue(new Promise(() => undefined))

    render(<App />)

    expect(screen.getByText(/불러오는 중/)).toBeInTheDocument()
    expect(screen.queryByLabelText('비밀번호')).not.toBeInTheDocument()
  })

  it('세션이 없으면 로그인 화면을 보여준다', async () => {
    auth.me.mockRejectedValue(new Error('로그인 안 됨'))

    render(<App />)

    expect(await screen.findByLabelText('비밀번호')).toBeInTheDocument()
  })

  it('세션이 있으면 작업 화면으로 들어간다', async () => {
    auth.me.mockResolvedValue({ id: 1, email: 'a@example.com', role: 'user' })

    render(<App />)

    expect(await screen.findByText('a@example.com')).toBeInTheDocument()
  })
})
