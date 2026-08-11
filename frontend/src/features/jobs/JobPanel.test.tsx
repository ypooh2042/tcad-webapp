import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { JobPanel } from './JobPanel'
import type { JobDetail } from '../../api/types'

const { get, plot } = vi.hoisted(() => ({
  get: vi.fn(),
  plot: { summary: vi.fn(), profile: vi.fn(), surface: vi.fn() },
}))
vi.mock('../../api/endpoints', () => ({ jobs: { get }, plot }))

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
  plot.summary.mockResolvedValue({
    filename: 'a.str',
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
  plot.surface.mockResolvedValue(null)
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

  it('공정 단계를 생성 순서대로 훑을 수 있다', async () => {
    // 이름순으로 정렬하면 a_final 이 먼저 와서 공정 흐름이 뒤집힌다.
    get.mockResolvedValue(
      detail({
        artifacts: [
          { sequence: 1, filename: 'after_implant.str', size_bytes: 1024 },
          { sequence: 2, filename: 'a_final.str', size_bytes: 2048 },
        ],
      }),
    )

    render(<JobPanel jobId={42} />)

    // 첫 단계가 먼저 보인다.
    expect(await screen.findByText(/after_implant.str/)).toBeInTheDocument()
    const slider = screen.getByLabelText('공정 단계')
    expect(slider).toHaveAttribute('max', '1')
  })

  it('산출물이 하나여도 파일 이름을 보여준다', async () => {
    // 지금 무엇을 보고 있는지 알 수 있는 유일한 단서다.
    get.mockResolvedValue(
      detail({
        artifacts: [{ sequence: 1, filename: 'only.str', size_bytes: 10 }],
      }),
    )

    render(<JobPanel jobId={42} />)

    expect(await screen.findByText(/only.str/)).toBeInTheDocument()
    expect(screen.queryByLabelText('공정 단계')).not.toBeInTheDocument()
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
