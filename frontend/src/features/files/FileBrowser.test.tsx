/**
 * 파일 브라우저.
 *
 * 사용자에게는 자기 작업공간이 파일시스템 전부다. 폴더와 `.in` 파일만 보이고,
 * 여기서 만들고 이름 바꾸고 지운다.
 *
 * **파일을 고르면 탭으로 연다.** 브라우저는 탭 목록을 직접 건드리지 않고
 * 알리기만 한다 — 어느 파일이 열려 있는지는 작업 화면이 안다.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { FileBrowser } from './FileBrowser'

const { files } = vi.hoisted(() => ({
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
}))
vi.mock('../../api/endpoints', () => ({ files }))

const TREE = [
  { path: 'semi', name: 'semi', is_dir: true, size_bytes: 0 },
  { path: 'semi/boron.in', name: 'boron.in', is_dir: false, size_bytes: 120 },
  { path: 'top.in', name: 'top.in', is_dir: false, size_bytes: 42 },
]

beforeEach(() => {
  vi.clearAllMocks()
  files.tree.mockResolvedValue({ entries: TREE })
  files.usage.mockResolvedValue({
    used_bytes: 162,
    quota_bytes: 50 * 1024 * 1024,
    remaining_bytes: 50 * 1024 * 1024 - 162,
  })
  files.makeFolder.mockResolvedValue({})
  files.write.mockResolvedValue({})
  files.rename.mockResolvedValue({})
  files.remove.mockResolvedValue(null)
})

function open(props = {}) {
  return render(
    <FileBrowser onOpen={vi.fn()} onClose={vi.fn()} {...props} />,
  )
}

describe('트리', () => {
  it('폴더와 파일을 보여준다', async () => {
    open()

    expect(await screen.findByText('semi')).toBeInTheDocument()
    expect(screen.getByText('top.in')).toBeInTheDocument()
  })

  it('폴더 안 파일은 접혀 있다', async () => {
    // 파일이 많아지면 한 번에 다 펴는 것이 오히려 안 보인다.
    open()
    await screen.findByText('semi')

    expect(screen.queryByText('boron.in')).not.toBeInTheDocument()
  })

  it('폴더를 누르면 펼친다', async () => {
    open()

    await userEvent.click(await screen.findByRole('button', { name: /semi/ }))

    expect(await screen.findByText('boron.in')).toBeInTheDocument()
  })

  it('비어 있으면 안내한다', async () => {
    files.tree.mockResolvedValue({ entries: [] })
    open()

    expect(await screen.findByText(/파일이 없습니다/)).toBeInTheDocument()
  })
})

describe('열기', () => {
  it('파일을 누르면 알린다', async () => {
    const onOpen = vi.fn()
    open({ onOpen })

    await userEvent.click(await screen.findByRole('button', { name: /top.in/ }))

    expect(onOpen).toHaveBeenCalledWith('top.in')
  })

  it('폴더를 눌러도 열지 않는다', async () => {
    const onOpen = vi.fn()
    open({ onOpen })

    await userEvent.click(await screen.findByRole('button', { name: /semi/ }))

    expect(onOpen).not.toHaveBeenCalled()
  })
})

describe('만들기', () => {
  it('새 파일을 만든다', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue('새파일.in')
    open()
    await screen.findByText('top.in')

    await userEvent.click(screen.getByRole('button', { name: '새 파일' }))

    expect(files.write).toHaveBeenCalledWith('새파일.in', expect.any(String))
  })

  it('.in 이 없으면 붙여 준다', async () => {
    // 확장자를 빼먹으면 서버가 거절한다. 사용자가 규칙을 외울 이유가 없다.
    vi.spyOn(window, 'prompt').mockReturnValue('새파일')
    open()
    await screen.findByText('top.in')

    await userEvent.click(screen.getByRole('button', { name: '새 파일' }))

    expect(files.write).toHaveBeenCalledWith('새파일.in', expect.any(String))
  })

  it('새 폴더를 만든다', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue('새폴더')
    open()
    await screen.findByText('top.in')

    await userEvent.click(screen.getByRole('button', { name: '새 폴더' }))

    expect(files.makeFolder).toHaveBeenCalledWith('새폴더')
  })

  it('취소하면 아무 일도 없다', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue(null)
    open()
    await screen.findByText('top.in')

    await userEvent.click(screen.getByRole('button', { name: '새 파일' }))

    expect(files.write).not.toHaveBeenCalled()
  })

  it('만든 뒤 목록을 다시 읽는다', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue('새폴더')
    open()
    await screen.findByText('top.in')
    files.tree.mockClear()

    await userEvent.click(screen.getByRole('button', { name: '새 폴더' }))

    await waitFor(() => expect(files.tree).toHaveBeenCalled())
  })
})

describe('이름 바꾸기', () => {
  it('같은 폴더 안에서 이름만 바꾼다', async () => {
    // 경로째 물으면 사용자가 폴더 구조를 손으로 써야 한다.
    vi.spyOn(window, 'prompt').mockReturnValue('renamed.in')
    open()
    const row = (await screen.findByText('top.in')).closest('li')!

    await userEvent.click(within(row).getByRole('button', { name: '이름 바꾸기' }))

    expect(files.rename).toHaveBeenCalledWith('top.in', 'renamed.in')
  })

  it('하위 폴더 파일은 경로를 유지한다', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue('renamed.in')
    open()
    await userEvent.click(await screen.findByRole('button', { name: /semi/ }))
    const row = (await screen.findByText('boron.in')).closest('li')!

    await userEvent.click(within(row).getByRole('button', { name: '이름 바꾸기' }))

    expect(files.rename).toHaveBeenCalledWith('semi/boron.in', 'semi/renamed.in')
  })
})

describe('지우기', () => {
  it('확인을 받고 지운다', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    open()
    const row = (await screen.findByText('top.in')).closest('li')!

    await userEvent.click(within(row).getByRole('button', { name: '삭제' }))

    expect(files.remove).toHaveBeenCalledWith('top.in')
  })

  it('취소하면 지우지 않는다', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    open()
    const row = (await screen.findByText('top.in')).closest('li')!

    await userEvent.click(within(row).getByRole('button', { name: '삭제' }))

    expect(files.remove).not.toHaveBeenCalled()
  })

  it('폴더 삭제는 안의 내용도 사라진다고 알린다', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    open()
    const row = (await screen.findByText('semi')).closest('li')!

    await userEvent.click(within(row).getByRole('button', { name: '삭제' }))

    expect(confirm.mock.calls[0]![0]).toMatch(/안의 파일/)
  })
})

describe('사용량', () => {
  it('쓴 만큼과 상한을 보여준다', async () => {
    open()

    expect(await screen.findByText(/50.0MB/)).toBeInTheDocument()
  })
})

describe('오류', () => {
  it('서버 메시지를 그대로 보여준다', async () => {
    const { ApiError } = await import('../../api/client')
    vi.spyOn(window, 'prompt').mockReturnValue('중복')
    files.makeFolder.mockRejectedValue(
      new ApiError(409, '같은 이름이 이미 있습니다', null),
    )
    open()
    await screen.findByText('top.in')

    await userEvent.click(screen.getByRole('button', { name: '새 폴더' }))

    expect(await screen.findByText(/이미 있습니다/)).toBeInTheDocument()
  })
})

describe('끌어서 옮기기', () => {
  /** 드래그를 흉내 낸다. jsdom 은 실제 드래그를 하지 않는다. */
  function drag(from: HTMLElement, to: HTMLElement) {
    const data = new Map<string, string>()
    const dataTransfer = {
      setData: (type: string, value: string) => void data.set(type, value),
      getData: (type: string) => data.get(type) ?? '',
      effectAllowed: '',
      dropEffect: '',
    }
    fireEvent.dragStart(from, { dataTransfer })
    fireEvent.dragOver(to, { dataTransfer })
    fireEvent.drop(to, { dataTransfer })
  }

  it('파일을 폴더에 넣는다', async () => {
    open()
    const file = await screen.findByText('top.in')
    const folder = screen.getByText('semi')

    drag(file.closest('li')!, folder.closest('li')!)

    await waitFor(() =>
      expect(files.rename).toHaveBeenCalledWith('top.in', 'semi/top.in'),
    )
  })

  it('폴더도 옮길 수 있다', async () => {
    files.tree.mockResolvedValue({
      entries: [
        { path: 'a', name: 'a', is_dir: true, size_bytes: 0 },
        { path: 'b', name: 'b', is_dir: true, size_bytes: 0 },
      ],
    })
    open()
    const source = await screen.findByText('a')
    const target = screen.getByText('b')

    drag(source.closest('li')!, target.closest('li')!)

    await waitFor(() => expect(files.rename).toHaveBeenCalledWith('a', 'b/a'))
  })

  it('파일 위로 떨어뜨리면 그 파일이 있는 폴더로 넣는다', async () => {
    // 파일은 담을 수 없다. 같은 폴더로 옮기는 것이 자연스러운 해석이다.
    files.tree.mockResolvedValue({
      entries: [
        { path: 'semi', name: 'semi', is_dir: true, size_bytes: 0 },
        { path: 'semi/there.in', name: 'there.in', is_dir: false, size_bytes: 1 },
        { path: 'here.in', name: 'here.in', is_dir: false, size_bytes: 1 },
      ],
    })
    open()
    await userEvent.click(await screen.findByRole('button', { name: /semi/ }))
    const source = screen.getByText('here.in')
    const target = await screen.findByText('there.in')

    drag(source.closest('li')!, target.closest('li')!)

    await waitFor(() =>
      expect(files.rename).toHaveBeenCalledWith('here.in', 'semi/here.in'),
    )
  })

  it('자기 자신에게 떨어뜨리면 아무 일도 없다', async () => {
    open()
    const file = await screen.findByText('top.in')

    drag(file.closest('li')!, file.closest('li')!)

    expect(files.rename).not.toHaveBeenCalled()
  })

  it('폴더를 자기 안으로 넣지 않는다', async () => {
    // 허용하면 트리가 끊겨 되돌릴 수 없다. 서버도 막지만 화면에서 먼저 막는다.
    open()
    await userEvent.click(await screen.findByRole('button', { name: /semi/ }))
    const folder = screen.getByText('semi')
    const inside = await screen.findByText('boron.in')

    drag(folder.closest('li')!, inside.closest('li')!)

    expect(files.rename).not.toHaveBeenCalled()
  })

  it('이미 그 폴더에 있으면 옮기지 않는다', async () => {
    files.tree.mockResolvedValue({
      entries: [
        { path: 'semi', name: 'semi', is_dir: true, size_bytes: 0 },
        { path: 'semi/a.in', name: 'a.in', is_dir: false, size_bytes: 1 },
      ],
    })
    open()
    await userEvent.click(await screen.findByRole('button', { name: /semi/ }))
    const file = await screen.findByText('a.in')
    const folder = screen.getByText('semi')

    drag(file.closest('li')!, folder.closest('li')!)

    expect(files.rename).not.toHaveBeenCalled()
  })

  it('서버가 거절하면 알린다', async () => {
    const { ApiError } = await import('../../api/client')
    files.rename.mockRejectedValue(
      new ApiError(409, '같은 이름이 이미 있습니다', null),
    )
    open()
    const file = await screen.findByText('top.in')
    const folder = screen.getByText('semi')

    drag(file.closest('li')!, folder.closest('li')!)

    expect(await screen.findByText(/이미 있습니다/)).toBeInTheDocument()
  })
})
