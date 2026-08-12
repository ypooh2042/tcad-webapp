/**
 * 커맨드 목록.
 *
 * 검색과 역할이 다르다. 검색은 찾을 낱말을 알아야 쓸 수 있는데, 처음 쓰는
 * 사람은 그 낱말을 모른다 — "층을 쌓는 커맨드가 뭐지" 는 검색으로 알아낼 수
 * 없다. 그래서 무리별로 늘어놓아 눈으로 찾게 한다.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ReferenceBrowser } from './ReferenceBrowser'

const { docs } = vi.hoisted(() => ({ docs: { reference: vi.fn() } }))
vi.mock('../../api/endpoints', () => ({ docs }))

function command(overrides = {}) {
  return {
    name: 'implant',
    summary: 'Perform ion implantation.',
    documented: true,
    parameter_count: 28,
    manual_section_id: 'command-implant',
    manual_page: '67',
    ...overrides,
  }
}

const REFERENCE = {
  groups: [
    {
      name: '공정 시뮬레이션',
      note: '실제 공정 단계. 이 커맨드들이 웨이퍼를 바꾼다.',
      commands: [
        command(),
        command({ name: 'deposit', summary: 'Deposit a layer.' }),
      ],
    },
    {
      name: '결과 보기',
      note: '계산이 끝난 구조에서 값을 꺼내 그리거나 출력한다.',
      commands: [
        command({ name: 'plot.1d', summary: 'Plot a one dimensional cross section.' }),
      ],
    },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
  docs.reference.mockResolvedValue(REFERENCE)
})

describe('무리별 목록', () => {
  it('무리 이름을 보여준다', async () => {
    render(<ReferenceBrowser onSelect={vi.fn()} />)

    expect(await screen.findByText('공정 시뮬레이션')).toBeInTheDocument()
    expect(screen.getByText('결과 보기')).toBeInTheDocument()
  })

  it('무리가 무엇인지 설명한다', async () => {
    // 이름만으로는 왜 묶였는지 알 수 없다.
    render(<ReferenceBrowser onSelect={vi.fn()} />)

    expect(await screen.findByText(/웨이퍼를 바꾼다/)).toBeInTheDocument()
  })

  it('커맨드마다 한 줄 요약을 붙인다', async () => {
    // 요약이 없으면 이름 나열에 그쳐 무엇을 고를지 알 수 없다.
    render(<ReferenceBrowser onSelect={vi.fn()} />)

    expect(await screen.findByText('Perform ion implantation.')).toBeInTheDocument()
  })

  it('서버가 준 순서를 지킨다', async () => {
    // 매뉴얼이 세운 순서다 — 데이터를 넣고, 공정을 돌리고, 결과를 본다.
    render(<ReferenceBrowser onSelect={vi.fn()} />)
    await screen.findByText('공정 시뮬레이션')

    const headings = [...document.querySelectorAll('summary')].map(
      (node) => node.textContent,
    )
    expect(headings[0]).toContain('공정 시뮬레이션')
    expect(headings[1]).toContain('결과 보기')
  })
})

describe('고르기', () => {
  it('누르면 그 커맨드를 알린다', async () => {
    const onSelect = vi.fn()
    render(<ReferenceBrowser onSelect={onSelect} />)

    await userEvent.click(await screen.findByRole('button', { name: /implant/ }))

    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'implant' }),
    )
  })
})

describe('걸러 보기', () => {
  it('이름으로 좁힌다', async () => {
    render(<ReferenceBrowser onSelect={vi.fn()} />)
    await screen.findByText('Perform ion implantation.')

    await userEvent.type(screen.getByLabelText('커맨드 거르기'), 'depo')

    expect(screen.getByText('Deposit a layer.')).toBeInTheDocument()
    expect(screen.queryByText('Perform ion implantation.')).not.toBeInTheDocument()
  })

  it('요약으로도 좁힌다', async () => {
    // 이름을 모를 때 쓰는 것이므로 이름만 보면 반쪽이다.
    render(<ReferenceBrowser onSelect={vi.fn()} />)
    await screen.findByText('Perform ion implantation.')

    await userEvent.type(screen.getByLabelText('커맨드 거르기'), 'implantation')

    expect(screen.getByText('Perform ion implantation.')).toBeInTheDocument()
  })

  it('빈 무리는 감춘다', async () => {
    render(<ReferenceBrowser onSelect={vi.fn()} />)
    await screen.findByText('Perform ion implantation.')

    await userEvent.type(screen.getByLabelText('커맨드 거르기'), 'depo')

    expect(screen.queryByText('결과 보기')).not.toBeInTheDocument()
  })

  it('하나도 없으면 알린다', async () => {
    render(<ReferenceBrowser onSelect={vi.fn()} />)
    await screen.findByText('Perform ion implantation.')

    await userEvent.type(screen.getByLabelText('커맨드 거르기'), 'zzzz')

    expect(screen.getByText(/맞는 커맨드가 없습니다/)).toBeInTheDocument()
  })

  it('대소문자를 가리지 않는다', async () => {
    // 거르기는 시뮬레이터 입력이 아니라 사람의 검색이다.
    render(<ReferenceBrowser onSelect={vi.fn()} />)
    await screen.findByText('Perform ion implantation.')

    await userEvent.type(screen.getByLabelText('커맨드 거르기'), 'IMPLANT')

    expect(screen.getByText('Perform ion implantation.')).toBeInTheDocument()
  })
})

describe('문서 없는 커맨드', () => {
  beforeEach(() => {
    docs.reference.mockResolvedValue({
      groups: [
        {
          name: '문서 없음',
          note: 'suprem.key 에는 있지만 매뉴얼에 설명이 없다.',
          commands: [
            command({
              name: 'device',
              summary: '',
              documented: false,
              manual_section_id: null,
              manual_page: null,
              parameter_count: 7,
            }),
          ],
        },
      ],
    })
  })

  it('설명이 없다고 표시한다', async () => {
    render(<ReferenceBrowser onSelect={vi.fn()} />)

    expect(await screen.findByText(/매뉴얼 설명 없음/)).toBeInTheDocument()
  })

  it('그래도 고를 수 있다', async () => {
    // 파라미터는 알려줄 수 있다. 못 누르게 하면 존재만 알고 쓸 수 없다.
    const onSelect = vi.fn()
    render(<ReferenceBrowser onSelect={onSelect} />)

    await userEvent.click(await screen.findByRole('button', { name: /device/ }))

    expect(onSelect).toHaveBeenCalled()
  })
})

describe('불러오기 실패', () => {
  it('오류를 알린다', async () => {
    docs.reference.mockRejectedValue(new Error('boom'))

    render(<ReferenceBrowser onSelect={vi.fn()} />)

    await waitFor(() =>
      expect(screen.getByText(/불러오지 못했습니다/)).toBeInTheDocument(),
    )
  })

  it('한 번만 부른다', async () => {
    // 목록은 바뀌지 않는다. 탭을 오갈 때마다 받으면 낭비다.
    const { rerender } = render(<ReferenceBrowser onSelect={vi.fn()} />)
    await screen.findByText('Perform ion implantation.')

    rerender(<ReferenceBrowser onSelect={vi.fn()} />)

    expect(docs.reference).toHaveBeenCalledTimes(1)
  })
})
