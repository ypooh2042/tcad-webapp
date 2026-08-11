import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { JobPanel } from './JobPanel'
import type { JobDetail } from '../../api/types'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../../api/endpoints', () => ({ jobs: { get } }))

function detail(overrides: Partial<JobDetail> = {}): JobDetail {
  return {
    id: 42,
    status: 'succeeded',
    source_revision_id: 1,
    log: null,
    exit_code: 0,
    artifacts: [],
    ...overrides,
  }
}

beforeEach(() => {
  get.mockReset()
  get.mockResolvedValue(detail())
})

describe('실행 전', () => {
  it('안내를 보여준다', () => {
    render(<JobPanel jobId={null} />)

    expect(screen.getByText(/실행하면/)).toBeInTheDocument()
  })

  it('잡을 가져오지 않는다', () => {
    render(<JobPanel jobId={null} />)

    expect(get).not.toHaveBeenCalled()
  })
})

describe('상태 표시', () => {
  it.each([
    ['queued', '대기 중'],
    ['running', '실행 중'],
    ['succeeded', '성공'],
    ['failed', '실패'],
    ['timed_out', '시간 초과'],
  ] as const)('%s 를 %s 로 보여준다', async (status, label) => {
    get.mockResolvedValue(detail({ status }))

    render(<JobPanel jobId={42} />)

    expect(await screen.findByText(label)).toBeInTheDocument()
  })
})

describe('결과', () => {
  it('로그를 보여준다', async () => {
    get.mockResolvedValue(detail({ log: 'Mesh statistics' }))

    render(<JobPanel jobId={42} />)

    expect(await screen.findByText(/Mesh statistics/)).toBeInTheDocument()
  })

  it('산출물을 생성 순서대로 보여준다', async () => {
    // 이름순이 아니라 이 순서여야 공정 흐름과 일치한다.
    get.mockResolvedValue(
      detail({
        artifacts: [
          { sequence: 1, filename: 'after_implant.str', size_bytes: 1024 },
          { sequence: 2, filename: 'a_final.str', size_bytes: 2048 },
        ],
      }),
    )

    render(<JobPanel jobId={42} />)

    const items = await screen.findAllByRole('listitem')
    expect(items.map((item) => item.textContent)).toEqual([
      expect.stringContaining('after_implant.str'),
      expect.stringContaining('a_final.str'),
    ])
  })

  it('출력이 없으면 그렇다고 말한다', async () => {
    render(<JobPanel jobId={42} />)

    expect(await screen.findByText(/아직 출력이 없습니다/)).toBeInTheDocument()
  })

  it('연결이 끊기면 알린다', async () => {
    get.mockRejectedValue(new Error('연결 실패'))

    render(<JobPanel jobId={42} />)

    expect(await screen.findByText(/연결이 불안정/)).toBeInTheDocument()
  })
})
