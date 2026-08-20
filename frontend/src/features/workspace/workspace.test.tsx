/**
 * 작업 화면.
 *
 * 여기서 가장 중요한 규칙은 "실행 전에 저장한다"이다. 실행은 서버에 저장된
 * 최신 리비전을 돌리므로, 편집 중인 내용을 저장하지 않고 실행하면 방금 고친
 * 줄이 빠진 결과가 나온다. 사용자는 그걸 알아챌 방법이 없다.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { WorkspacePage } from './WorkspacePage'
import { AuthProvider } from '../auth/AuthContext'

const { auth, projects, files, jobs, plot, admin, docs, editor } = vi.hoisted(() => ({
  auth: {
    me: vi.fn(),
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    occupancy: vi.fn(),
  },
  projects: {
    list: vi.fn(),
    create: vi.fn(),
    saveSource: vi.fn(),
    latestSource: vi.fn(),
    submit: vi.fn(),
    jobs: vi.fn(),
    rename: vi.fn(),
    remove: vi.fn(),
  },
  files: {
    tree: vi.fn(),
    usage: vi.fn(),
    read: vi.fn(),
    write: vi.fn(),
    makeFolder: vi.fn(),
    rename: vi.fn(),
    remove: vi.fn(),
    run: vi.fn(),
  },
  jobs: { get: vi.fn(), artifact: vi.fn() },
  editor: { state: vi.fn(), save: vi.fn() },
  plot: { summary: vi.fn(), profile: vi.fn(), surface: vi.fn() },
  admin: { issueInvite: vi.fn(), listInvites: vi.fn(), revokeInvite: vi.fn() },
  docs: {
    sections: vi.fn(),
    section: vi.fn(),
    forCommand: vi.fn(),
    search: vi.fn(),
    reference: vi.fn(),
  },
}))

vi.mock('../../api/endpoints', () => ({
  auth,
  projects,
  files,
  jobs,
  plot,
  admin,
  docs,
  editor,
}))

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
  auth.occupancy.mockResolvedValue({ occupied: 2, capacity: 5, admins: 0 })
  // 편집기 상태는 서버가 맡아 둔다. 기본은 '열어 둔 것이 없음'.
  editor.state.mockResolvedValue({ tabs: [], active: null })
  editor.save.mockResolvedValue(null)
  admin.listInvites.mockResolvedValue([])
  docs.forCommand.mockRejectedValue(new Error('없음'))
  docs.search.mockResolvedValue({ query: '', hits: [] })
  docs.reference.mockResolvedValue({ groups: [] })
  files.tree.mockResolvedValue({
    entries: [
      { path: 'boron.in', name: 'boron.in', is_dir: false, size_bytes: 10 },
      { path: 'arsenic.in', name: 'arsenic.in', is_dir: false, size_bytes: 10 },
    ],
  })
  files.usage.mockResolvedValue({
    used_bytes: 20,
    quota_bytes: 50 * 1024 * 1024,
    remaining_bytes: 50 * 1024 * 1024 - 20,
  })
  files.read.mockResolvedValue({ path: 'boron.in', content: '저장된 소스\n' })
  files.write.mockResolvedValue({ path: 'boron.in', content: 'x' })
  files.run.mockResolvedValue({ id: 42, status: 'queued', source_path: 'boron.in' })
  projects.list.mockResolvedValue([PROJECT])
  files.write.mockResolvedValue({ id: 1, revision: 1 })
  projects.latestSource.mockResolvedValue({ id: 1, revision: 1, source: '저장된 소스\n' })
  files.run.mockResolvedValue({ id: 42, status: 'queued', source_revision_id: 1 })
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

/** 파일 하나를 연 상태까지 만든다. 예전에는 프로젝트가 자동으로 열렸다. */
async function openFile(name = 'boron.in') {
  const result = renderWorkspace()
  await userEvent.click(screen.getByRole('button', { name: '파일 열기' }))
  const dialog = await screen.findByRole('dialog', { name: '내 파일' })
  // 앞의 · 는 aria-hidden 이라 접근성 이름에 들어가지 않는다.
  await userEvent.click(within(dialog).getByRole('button', { name }))
  await screen.findByRole('tab', { name: name })
  return result
}

function renderWorkspace() {
  return render(
    <AuthProvider>
      <WorkspacePage />
    </AuthProvider>,
  )
}

describe('파일 열기', () => {
  it('처음에는 열린 파일이 없다', async () => {
    // 위쪽 탭은 "내가 연 파일" 목록이다. 작업공간 전체가 아니다.
    renderWorkspace()

    await waitFor(() =>
      expect(screen.getByRole('button', { name: '실행' })).toBeDisabled(),
    )
  })

  it('파일 열기로 브라우저를 띄운다', async () => {
    renderWorkspace()

    await userEvent.click(screen.getByRole('button', { name: '파일 열기' }))

    expect(await screen.findByRole('dialog', { name: '내 파일' })).toBeInTheDocument()
  })

  it('고른 파일이 탭에 붙는다', async () => {
    renderWorkspace()
    await userEvent.click(screen.getByRole('button', { name: '파일 열기' }))
    await screen.findByRole('dialog', { name: '내 파일' })

    await userEvent.click(await screen.findByRole('button', { name: /boron.in/ }))

    expect(
      await screen.findByRole('tab', { name: /boron.in/ }),
    ).toBeInTheDocument()
  })

  it('연 파일의 내용을 편집기에 채운다', async () => {
    renderWorkspace()
    await userEvent.click(screen.getByRole('button', { name: '파일 열기' }))
    await userEvent.click(await screen.findByRole('button', { name: /boron.in/ }))

    await waitFor(() => expect(files.read).toHaveBeenCalledWith('boron.in'))
    expect(await screen.findByDisplayValue(/저장된 소스/)).toBeInTheDocument()
  })

  it('같은 파일을 두 번 열어도 탭은 하나다', async () => {
    await openFile()

    await userEvent.click(screen.getByRole('button', { name: '파일 열기' }))
    const dialog = await screen.findByRole('dialog', { name: '내 파일' })
    await userEvent.click(within(dialog).getByRole('button', { name: 'boron.in' }))

    expect(screen.getAllByRole('tab')).toHaveLength(1)
  })
})

describe('탭', () => {
  it('활성 탭을 눈에 띄게 표시한다', async () => {
    // 전환은 되는데 표시가 없으면 "안 눌린다"고 느낀다(실제 제보).
    const { container } = await openFile()

    const tab = container.querySelector('.workspace header nav .tab')!
    expect(tab.className).toContain('active')
  })

  it('활성이 아닌 탭에는 표시가 없다', async () => {
    const { container } = renderWorkspace()
    for (const name of ['boron.in', 'arsenic.in']) {
      await userEvent.click(screen.getByRole('button', { name: '파일 열기' }))
      const dialog = await screen.findByRole('dialog', { name: '내 파일' })
      await userEvent.click(within(dialog).getByRole('button', { name }))
      await screen.findByRole('tab', { name })
    }

    const tabs = [...container.querySelectorAll('.workspace header nav .tab')]
    expect(tabs.filter((t) => t.className.includes('active'))).toHaveLength(1)
  })

  it('이름이 겹치면 경로를 붙인다', async () => {
    // 같은 boron.in 이 둘이면 어느 쪽인지 알 수 없다. 트리에서는 이름이 같아
    // 구분이 안 되므로 폴더를 펼쳐 순서대로 고른다.
    files.tree.mockResolvedValue({
      entries: [
        { path: 'semi', name: 'semi', is_dir: true, size_bytes: 0 },
        { path: 'semi/boron.in', name: 'boron.in', is_dir: false, size_bytes: 10 },
        { path: 'boron.in', name: 'boron.in', is_dir: false, size_bytes: 10 },
      ],
    })
    renderWorkspace()

    // 루트의 boron.in — 접힌 상태에서는 이것 하나만 보인다.
    await userEvent.click(screen.getByRole('button', { name: '파일 열기' }))
    let dialog = await screen.findByRole('dialog', { name: '내 파일' })
    await userEvent.click(within(dialog).getByRole('button', { name: 'boron.in' }))
    await screen.findByRole('tab', { name: 'boron.in' })

    // semi 를 펼치고 그 안의 boron.in.
    await userEvent.click(screen.getByRole('button', { name: '파일 열기' }))
    dialog = await screen.findByRole('dialog', { name: '내 파일' })
    await userEvent.click(within(dialog).getByRole('button', { name: 'semi' }))
    // 폴더가 먼저 오므로 semi/boron.in 이 앞이다. 인덱스로 짚으면 순서가
    // 바뀔 때 조용히 엉뚱한 것을 누르므로, 들여쓰기 깊이로 고른다.
    const rows = await within(dialog).findAllByRole('button', { name: 'boron.in' })
    const nested = rows.find(
      (row) => row.closest('li')!.getAttribute('style')?.includes('--depth: 1'),
    )!
    await userEvent.click(nested)

    expect(
      await screen.findByRole('tab', { name: 'semi/boron.in' }),
    ).toBeInTheDocument()
  })

  it('닫기 버튼으로 탭에서 뺀다', async () => {
    renderWorkspace()
    await userEvent.click(screen.getByRole('button', { name: '파일 열기' }))
    await userEvent.click(await screen.findByRole('button', { name: /boron.in/ }))
    await screen.findByRole('tab')

    await userEvent.click(screen.getByRole('button', { name: /탭 닫기/ }))

    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
  })

  it('탭을 닫아도 파일은 지우지 않는다', async () => {
    renderWorkspace()
    await userEvent.click(screen.getByRole('button', { name: '파일 열기' }))
    await userEvent.click(await screen.findByRole('button', { name: /boron.in/ }))
    await screen.findByRole('tab')

    await userEvent.click(screen.getByRole('button', { name: /탭 닫기/ }))

    expect(files.remove).not.toHaveBeenCalled()
  })
})

describe('저장', () => {
  it('연 파일 경로로 저장한다', async () => {
    await openFile()

    await userEvent.clear(screen.getByLabelText('소스'))
    await userEvent.type(screen.getByLabelText('소스'), 'init boron')
    await userEvent.click(screen.getByRole('button', { name: /저장/ }))

    await waitFor(() =>
      expect(files.write).toHaveBeenCalledWith('boron.in', 'init boron'),
    )
  })

  it('저장했다고 알린다', async () => {
    await openFile()

    await userEvent.click(screen.getByRole('button', { name: /저장/ }))

    expect(await screen.findByText(/저장됨/)).toBeInTheDocument()
  })
})

describe('실행', () => {
  it('편집한 내용이 있으면 저장하고 나서 실행한다', async () => {
    await openFile()

    await userEvent.type(screen.getByLabelText('소스'), 'x')
    await userEvent.click(screen.getByRole('button', { name: '실행' }))

    await waitFor(() => expect(files.run).toHaveBeenCalled())
    // 저장이 먼저 일어나야 방금 고친 줄이 반영된다.
    expect(files.write).toHaveBeenCalled()
    expect(files.write.mock.invocationCallOrder[0]).toBeLessThan(
      files.run.mock.invocationCallOrder[0],
    )
  })

  it('바뀐 것이 없으면 다시 저장하지 않는다', async () => {
    await openFile()
    await userEvent.click(screen.getByRole('button', { name: /저장/ }))
    files.write.mockClear()

    await userEvent.click(screen.getByRole('button', { name: '실행' }))

    await waitFor(() => expect(files.run).toHaveBeenCalled())
    expect(projects.saveSource).not.toHaveBeenCalled()
  })

  it('제출한 잡의 결과를 보여준다', async () => {
    await openFile()

    await userEvent.click(screen.getByRole('button', { name: '실행' }))

    expect(await screen.findByText('result.str')).toBeInTheDocument()
    expect(await screen.findByText('성공')).toBeInTheDocument()
  })
})

describe('오류', () => {
  it('서버 오류 메시지를 그대로 보여준다', async () => {
    const { ApiError } = await import('../../api/client')
    files.run.mockRejectedValue(
      new ApiError(400, '저장된 소스가 없습니다. 먼저 코드를 저장해 주세요.', null),
    )
    files.write.mockRejectedValue(
      new ApiError(400, '저장된 소스가 없습니다. 먼저 코드를 저장해 주세요.', null),
    )
    await openFile()

    await userEvent.click(screen.getByRole('button', { name: '실행' }))

    expect(await screen.findByText(/저장된 소스가 없습니다/)).toBeInTheDocument()
  })
})


describe('관리자 화면', () => {
  it('일반 사용자에게는 버튼이 없다', async () => {
    await openFile()

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
    await openFile()

    await userEvent.click(screen.getByRole('button', { name: '매뉴얼' }))
    expect(screen.getByLabelText('매뉴얼 검색')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '매뉴얼 닫기' }))
    expect(screen.queryByLabelText('매뉴얼 검색')).not.toBeInTheDocument()
  })
})


describe('탭 전환', () => {
  /** 파일 둘을 열어 둔 상태. */
  async function openTwo() {
    const result = renderWorkspace()
    for (const name of ['boron.in', 'arsenic.in']) {
      await userEvent.click(screen.getByRole('button', { name: '파일 열기' }))
      const dialog = await screen.findByRole('dialog', { name: '내 파일' })
      await userEvent.click(within(dialog).getByRole('button', { name }))
      await screen.findByRole('tab', { name })
    }
    return result
  }

  it('연 파일의 내용을 편집기에 채운다', async () => {
    await openFile()

    expect(await screen.findByDisplayValue(/저장된 소스/)).toBeInTheDocument()
  })

  it('탭을 누르면 그 파일 내용이 뜬다', async () => {
    // 이게 안 되면 탭만 강조되고 편집기에는 이전 내용이 남는다.
    files.read.mockImplementation(async (path: string) => ({
      path,
      content: `${path} 의 내용\n`,
    }))
    await openTwo()

    await userEvent.click(screen.getByRole('tab', { name: 'boron.in' }))

    expect(
      await screen.findByDisplayValue(/boron.in 의 내용/),
    ).toBeInTheDocument()
  })

  it('저장하지 않은 편집이 있어도 묻지 않고 옮긴다', async () => {
    // 저장은 곧 "실행 대상이 바뀐다"는 뜻이라, 잠깐 다른 파일을 들춰 보려고
    // 시킬 일이 아니다.
    await openTwo()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    await userEvent.type(screen.getByLabelText('소스'), 'x')

    await userEvent.click(screen.getByRole('tab', { name: 'boron.in' }))

    expect(confirm).not.toHaveBeenCalled()
    expect(screen.getByRole('tab', { name: /boron.in/ })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    confirm.mockRestore()
  })

  it('돌아오면 고치던 내용이 그대로 있다', async () => {
    // 이것이 탭 전환을 묻지 않는 근거다. 버리는 것이 아니라 들고 있는다.
    await openTwo()
    await userEvent.type(screen.getByLabelText('소스'), '고치던 중')

    await userEvent.click(screen.getByRole('tab', { name: 'boron.in' }))
    await userEvent.click(screen.getByRole('tab', { name: /arsenic.in/ }))

    expect(
      await screen.findByDisplayValue(/고치던 중/),
    ).toBeInTheDocument()
  })

  it('고친 탭에는 저장 안 됨 표시가 뜬다', async () => {
    // 옮길 때 묻지 않으므로 이 표시가 유일한 단서다.
    await openTwo()

    await userEvent.type(screen.getByLabelText('소스'), 'x')

    const tab = screen.getByRole('tab', { name: /arsenic.in/ })
    expect(within(tab).getByLabelText('저장되지 않음')).toBeInTheDocument()
  })

  it('저장하지 않은 탭을 닫을 때는 묻는다', async () => {
    // 전환과 달리 닫기는 버퍼를 버린다. 되돌릴 수 없으므로 여기서만 묻는다.
    await openFile()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    await userEvent.type(screen.getByLabelText('소스'), 'x')

    await userEvent.click(screen.getByRole('button', { name: /탭 닫기/ }))

    expect(confirm).toHaveBeenCalled()
    expect(screen.getByRole('tab', { name: /boron.in/ })).toBeInTheDocument()
    confirm.mockRestore()
  })

  it('고친 것이 없으면 닫을 때 묻지 않는다', async () => {
    await openFile()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)

    await userEvent.click(screen.getByRole('button', { name: /탭 닫기/ }))

    expect(confirm).not.toHaveBeenCalled()
    confirm.mockRestore()
  })
})

describe('열어 둔 파일이 없을 때', () => {
  it('무엇을 해야 하는지 알려준다', async () => {
    renderWorkspace()

    expect(await screen.findByText(/열어 둔 파일이 없습니다/)).toBeInTheDocument()
  })

  it('편집기를 띄우지 않는다', async () => {
    // 예제 소스가 든 편집기를 띄우면 어느 파일을 고치는 것인지 알 수 없고,
    // 저장을 눌러도 "먼저 파일을 열어 주세요"만 나온다.
    renderWorkspace()

    await screen.findByText(/열어 둔 파일이 없습니다/)
    expect(screen.queryByLabelText('소스')).not.toBeInTheDocument()
  })

  it('마지막 탭을 닫으면 다시 빈 화면이 된다', async () => {
    await openFile()

    await userEvent.click(screen.getByRole('button', { name: /탭 닫기/ }))

    expect(await screen.findByText(/열어 둔 파일이 없습니다/)).toBeInTheDocument()
  })
})

describe('세션 되살리기', () => {
  it('지난번에 열어 둔 탭이 그대로 뜬다', async () => {
    editor.state.mockResolvedValue({
      tabs: [{ path: 'boron.in', draft: null, cursor: null }],
      active: 'boron.in',
    })

    renderWorkspace()

    expect(await screen.findByRole('tab', { name: /boron.in/ })).toBeInTheDocument()
  })

  it('저장하지 않았던 내용까지 되살아난다', async () => {
    editor.state.mockResolvedValue({
      tabs: [{ path: 'boron.in', draft: '지난번에 고치던 중\n', cursor: null }],
      active: 'boron.in',
    })

    renderWorkspace()

    expect(
      await screen.findByDisplayValue(/지난번에 고치던 중/),
    ).toBeInTheDocument()
  })

  it('되살아난 초안은 저장 안 됨으로 보인다', async () => {
    editor.state.mockResolvedValue({
      tabs: [{ path: 'boron.in', draft: '지난번에 고치던 중\n', cursor: null }],
      active: 'boron.in',
    })

    renderWorkspace()

    const tab = await screen.findByRole('tab', { name: /boron.in/ })
    expect(within(tab).getByLabelText('저장되지 않음')).toBeInTheDocument()
  })
})

describe('접속 현황', () => {
  it('정원과 현재 인원을 머리말에 보여준다', async () => {
    renderWorkspace()

    expect(await screen.findByText('접속 2/5')).toBeInTheDocument()
  })

  it('가득 차면 눈에 띄게 표시한다', async () => {
    // 자리를 비워 줄지 판단하려면 가득 찼다는 것이 보여야 한다.
    auth.occupancy.mockResolvedValue({ occupied: 5, capacity: 5, admins: 0 })

    renderWorkspace()

    expect(await screen.findByText('접속 5/5')).toHaveClass('full')
  })

  it('현황을 못 가져와도 화면은 뜬다', async () => {
    auth.occupancy.mockRejectedValue(new Error('연결 실패'))

    renderWorkspace()

    expect(await screen.findByRole('button', { name: '실행' })).toBeInTheDocument()
  })
})
