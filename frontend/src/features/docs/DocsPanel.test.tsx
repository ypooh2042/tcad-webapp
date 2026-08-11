/**
 * 매뉴얼 패널.
 *
 * 기본 동작은 **커서를 따라가는 것**이다. 문서를 보려고 손을 멈추는 순간이 가장
 * 흔한 마찰이라, 커서가 놓인 줄의 커맨드 문서가 저절로 떠야 한다.
 *
 * 다만 검색해서 직접 고른 문서는 커서가 움직여도 유지해야 한다. 그러지 않으면
 * 읽는 도중 편집기를 건드리는 순간 사라진다.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DocsPanel } from './DocsPanel'

const { docs } = vi.hoisted(() => ({
  docs: { sections: vi.fn(), section: vi.fn(), forCommand: vi.fn(), search: vi.fn() },
}))
vi.mock('../../api/endpoints', () => ({ docs }))

function section(overrides = {}) {
  return {
    id: 'implant',
    kind: 'command',
    title: 'IMPLANT',
    command: 'implant',
    aliases: ['implant'],
    page_start: '75',
    page_end: '78',
    pdf_page_start: 75,
    pdf_page_end: 78,
    subsections: {
      DESCRIPTION: '이온 주입을 수행한다.',
      SYNOPSIS: 'implant dose= energy=',
    },
    key_parameters: ['dose', 'energy'],
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  docs.forCommand.mockResolvedValue(section())
  docs.section.mockResolvedValue(section())
  docs.search.mockResolvedValue({ query: '', hits: [] })
})

describe('커서 따라가기', () => {
  it('커서가 놓인 커맨드의 문서를 띄운다', async () => {
    render(<DocsPanel command="implant" onClose={vi.fn()} />)

    await waitFor(() => expect(docs.forCommand).toHaveBeenCalledWith('implant'))
    expect(await screen.findByText('IMPLANT')).toBeInTheDocument()
  })

  it('접두사를 그대로 서버에 넘긴다', async () => {
    // 서버가 시뮬레이터와 같은 규칙으로 해석해야 한다.
    render(<DocsPanel command="stru" onClose={vi.fn()} />)

    await waitFor(() => expect(docs.forCommand).toHaveBeenCalledWith('stru'))
  })

  it('커맨드가 바뀌면 다시 읽는다', async () => {
    const { rerender } = render(<DocsPanel command="implant" onClose={vi.fn()} />)
    await waitFor(() => expect(docs.forCommand).toHaveBeenCalledTimes(1))

    rerender(<DocsPanel command="diffuse" onClose={vi.fn()} />)

    await waitFor(() => expect(docs.forCommand).toHaveBeenCalledWith('diffuse'))
  })

  it('커맨드가 없으면 아무것도 요청하지 않는다', () => {
    render(<DocsPanel command={null} onClose={vi.fn()} />)

    expect(docs.forCommand).not.toHaveBeenCalled()
  })

  it('문서가 없는 커맨드는 조용히 알린다', async () => {
    // 모호한 접두사(str)이거나 아직 다 치지 않은 이름이다. 흔한 상황이라
    // 오류처럼 보이면 안 된다.
    docs.forCommand.mockRejectedValue(new Error('404'))

    render(<DocsPanel command="str" onClose={vi.fn()} />)

    expect(await screen.findByText(/'str' 에 해당하는 문서가 없습니다/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('매뉴얼 쪽수를 알려준다', async () => {
    render(<DocsPanel command="implant" onClose={vi.fn()} />)

    expect(await screen.findByText(/75–78 쪽/)).toBeInTheDocument()
  })

  it('소제목을 정해진 순서로 보여준다', async () => {
    // SYNOPSIS 가 DESCRIPTION 보다 먼저 와야 쓰는 법을 먼저 본다.
    render(<DocsPanel command="implant" onClose={vi.fn()} />)
    await screen.findByText('IMPLANT')

    const headings = screen.getAllByRole('heading', { level: 4 })
    expect(headings.map((h) => h.textContent)).toEqual(['SYNOPSIS', 'DESCRIPTION'])
  })
})

describe('검색', () => {
  it('두 글자 미만은 서버에 보내지 않는다', async () => {
    render(<DocsPanel command={null} onClose={vi.fn()} />)

    await userEvent.type(screen.getByLabelText('매뉴얼 검색'), 'a')
    await userEvent.click(screen.getByRole('button', { name: '찾기' }))

    expect(docs.search).not.toHaveBeenCalled()
    expect(screen.getByText(/두 글자 이상/)).toBeInTheDocument()
  })

  it('결과를 목록으로 보여준다', async () => {
    docs.search.mockResolvedValue({
      query: 'oxide',
      hits: [{ id: 'diffuse', title: 'DIFFUSE', command: 'diffuse', kind: 'command', snippet: '…산화…' }],
    })
    render(<DocsPanel command={null} onClose={vi.fn()} />)

    await userEvent.type(screen.getByLabelText('매뉴얼 검색'), 'oxide')
    await userEvent.click(screen.getByRole('button', { name: '찾기' }))

    expect(await screen.findByRole('button', { name: 'DIFFUSE' })).toBeInTheDocument()
    expect(screen.getByText(/산화/)).toBeInTheDocument()
  })

  it('결과가 없으면 알린다', async () => {
    render(<DocsPanel command={null} onClose={vi.fn()} />)

    await userEvent.type(screen.getByLabelText('매뉴얼 검색'), 'zzzz')
    await userEvent.click(screen.getByRole('button', { name: '찾기' }))

    expect(await screen.findByText(/검색 결과가 없습니다/)).toBeInTheDocument()
  })

  it('결과를 고르면 그 문서를 연다', async () => {
    docs.search.mockResolvedValue({
      query: 'oxide',
      hits: [{ id: 'diffuse', title: 'DIFFUSE', command: 'diffuse', kind: 'command', snippet: '…' }],
    })
    render(<DocsPanel command={null} onClose={vi.fn()} />)
    await userEvent.type(screen.getByLabelText('매뉴얼 검색'), 'oxide')
    await userEvent.click(screen.getByRole('button', { name: '찾기' }))

    await userEvent.click(await screen.findByRole('button', { name: 'DIFFUSE' }))

    await waitFor(() => expect(docs.section).toHaveBeenCalledWith('diffuse'))
  })
})

describe('고정', () => {
  it('직접 고른 문서는 커서가 움직여도 유지된다', async () => {
    // 읽는 도중 편집기를 건드렸다고 문서가 사라지면 안 된다.
    docs.search.mockResolvedValue({
      query: 'x',
      hits: [{ id: 'diffuse', title: 'DIFFUSE', command: 'diffuse', kind: 'command', snippet: '…' }],
    })
    const { rerender } = render(<DocsPanel command="implant" onClose={vi.fn()} />)
    await userEvent.type(screen.getByLabelText('매뉴얼 검색'), 'xx')
    await userEvent.click(screen.getByRole('button', { name: '찾기' }))
    await userEvent.click(await screen.findByRole('button', { name: 'DIFFUSE' }))
    docs.forCommand.mockClear()

    rerender(<DocsPanel command="deposit" onClose={vi.fn()} />)

    expect(docs.forCommand).not.toHaveBeenCalled()
  })

  it('커서 따라가기로 되돌릴 수 있다', async () => {
    docs.search.mockResolvedValue({
      query: 'x',
      hits: [{ id: 'diffuse', title: 'DIFFUSE', command: 'diffuse', kind: 'command', snippet: '…' }],
    })
    render(<DocsPanel command="implant" onClose={vi.fn()} />)
    await userEvent.type(screen.getByLabelText('매뉴얼 검색'), 'xx')
    await userEvent.click(screen.getByRole('button', { name: '찾기' }))
    await userEvent.click(await screen.findByRole('button', { name: 'DIFFUSE' }))
    docs.forCommand.mockClear()

    await userEvent.click(screen.getByRole('button', { name: '커서 따라가기' }))

    await waitFor(() => expect(docs.forCommand).toHaveBeenCalledWith('implant'))
  })
})

describe('닫기', () => {
  it('닫기를 알린다', async () => {
    const onClose = vi.fn()
    render(<DocsPanel command={null} onClose={onClose} />)

    await userEvent.click(screen.getByRole('button', { name: '닫기' }))

    expect(onClose).toHaveBeenCalled()
  })
})
