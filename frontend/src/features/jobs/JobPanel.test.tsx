import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { JobPanel } from './JobPanel'
import type { JobDetail } from '../../api/types'

const { get, cancel, plot } = vi.hoisted(() => ({
  get: vi.fn(),
  cancel: vi.fn(),
  plot: { summary: vi.fn(), profile: vi.fn(), surface: vi.fn() },
}))
vi.mock('../../api/endpoints', () => ({ jobs: { get, cancel }, plot }))

function detail(overrides: Partial<JobDetail> = {}): JobDetail {
  return {
    id: 42,
    status: 'succeeded',
    source_revision_id: 1,
    source_path: 'a.in',
    created_at: '2026-08-12T12:00:00+00:00',
    log: null,
    exit_code: 0,
    artifacts: [],
    ...overrides,
  }
}

beforeEach(() => {
  get.mockReset()
  cancel.mockReset()
  cancel.mockResolvedValue({ id: 42, status: 'cancelled' })
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
    expect(screen.getByText(/1\/2/)).toBeInTheDocument()
    // 첫 단계이므로 뒤로는 못 가고 앞으로만 갈 수 있다.
    expect(screen.getByRole('button', { name: /이전/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: /다음/ })).toBeEnabled()
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
    expect(screen.queryByRole('button', { name: /다음/ })).not.toBeInTheDocument()
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

describe('로그 공간', () => {
  const withArtifacts = () =>
    detail({ log: '실행 로그', artifacts: [{ sequence: 1, filename: 'a.str', size_bytes: 10 }] })

  it('결과가 있으면 로그만 보기 버튼이 있다', async () => {
    get.mockResolvedValue(withArtifacts())

    render(<JobPanel jobId={42} />)

    expect(await screen.findByRole('button', { name: '로그만 보기' })).toBeInTheDocument()
  })

  it('로그만 보기로 바꾸면 결과가 자리를 비켜준다', async () => {
    // 실패한 잡에서는 로그가 전부다. 차트가 자리를 차지하면 읽을 수 없다.
    get.mockResolvedValue(withArtifacts())
    render(<JobPanel jobId={42} />)

    await userEvent.click(await screen.findByRole('button', { name: '로그만 보기' }))

    expect(screen.queryByLabelText('물리량')).not.toBeInTheDocument()
    expect(screen.getByText('실행 로그')).toBeInTheDocument()
  })

  it('되돌릴 수 있다', async () => {
    get.mockResolvedValue(withArtifacts())
    render(<JobPanel jobId={42} />)
    await userEvent.click(await screen.findByRole('button', { name: '로그만 보기' }))

    await userEvent.click(screen.getByRole('button', { name: '결과 보기' }))

    expect(await screen.findByRole('button', { name: '로그만 보기' })).toBeInTheDocument()
  })

  it('결과가 없으면 버튼도 없다', async () => {
    get.mockResolvedValue(detail({ log: '실패 로그', artifacts: [] }))

    render(<JobPanel jobId={42} />)
    await screen.findByText('실패 로그')

    expect(screen.queryByRole('button', { name: '로그만 보기' })).not.toBeInTheDocument()
  })
})

describe('어느 실행인지 알려주기', () => {
  it('파일 이름과 시각을 보여준다', async () => {
    // 잡 번호는 전체 사용자가 공유하는 기본키라 혼자 두 번 돌려도 건너뛴다.
    // 무엇을 언제 돌렸는지가 훨씬 읽기 쉽다.
    get.mockResolvedValue(
      detail({
        source_path: 'semi/boron.in',
        created_at: '2026-08-12T12:03:00+00:00',
      }),
    )

    render(<JobPanel jobId={24} />)

    expect(await screen.findByText(/semi\/boron.in/)).toBeInTheDocument()
  })

  it('시각은 현지 시각으로 보여준다', async () => {
    // 서버는 UTC 로 보낸다. 그대로 찍으면 몇 시간 어긋난 값이 보인다.
    const iso = '2026-08-12T12:03:00+00:00'
    const expected = new Date(iso).toLocaleTimeString('ko-KR', {
      hour: '2-digit',
      minute: '2-digit',
    })
    get.mockResolvedValue(detail({ source_path: 'a.in', created_at: iso }))

    render(<JobPanel jobId={24} />)

    expect(await screen.findByText(new RegExp(expected))).toBeInTheDocument()
  })

  it('경로가 없으면 잡 번호로 돌아간다', async () => {
    // 예전 프로젝트 모델로 만든 잡에는 경로가 없다.
    get.mockResolvedValue(detail({ source_path: null }))

    render(<JobPanel jobId={24} />)

    expect(await screen.findByText(/#24/)).toBeInTheDocument()
  })

  it('아직 못 받았으면 잡 번호를 보여준다', () => {
    // 응답 전에는 아무것도 안 보이면 무엇을 기다리는지 알 수 없다.
    get.mockReturnValue(new Promise(() => {}))

    render(<JobPanel jobId={24} />)

    expect(screen.getByText(/#24/)).toBeInTheDocument()
  })
})


describe('실행 중단', () => {
  it('실행 중이면 중단 버튼이 있다', async () => {
    // 격자에 따라 몇 분씩 돈다. 잘못 짠 입력이면 타임아웃까지 기다려야 한다.
    get.mockResolvedValue(detail({ status: 'running' }))

    render(<JobPanel jobId={42} />)

    expect(await screen.findByRole('button', { name: '중단' })).toBeInTheDocument()
  })

  it('대기 중에도 중단할 수 있다', async () => {
    get.mockResolvedValue(detail({ status: 'queued' }))

    render(<JobPanel jobId={42} />)

    expect(await screen.findByRole('button', { name: '중단' })).toBeInTheDocument()
  })

  it('끝난 잡에는 중단 버튼이 없다', async () => {
    get.mockResolvedValue(detail({ status: 'succeeded' }))

    render(<JobPanel jobId={42} />)
    await screen.findByText('성공')

    expect(screen.queryByRole('button', { name: '중단' })).not.toBeInTheDocument()
  })

  it('누르면 서버에 중단을 요청한다', async () => {
    get.mockResolvedValue(detail({ status: 'running' }))
    render(<JobPanel jobId={42} />)

    await userEvent.click(await screen.findByRole('button', { name: '중단' }))

    expect(cancel).toHaveBeenCalledWith(42)
  })

  it('중단하면 곧바로 상태가 바뀐다', async () => {
    // 다음 폴링까지 기다리면 누르고도 한동안 "실행 중"으로 보인다.
    get.mockResolvedValue(detail({ status: 'running' }))
    render(<JobPanel jobId={42} />)

    await userEvent.click(await screen.findByRole('button', { name: '중단' }))

    expect(await screen.findByText('중단됨')).toBeInTheDocument()
  })

  it('중단이 실패하면 알린다', async () => {
    // 조용히 넘어가면 사용자는 멈춘 줄 알고 기다린다.
    get.mockResolvedValue(detail({ status: 'running' }))
    cancel.mockRejectedValue(new Error('이미 끝난 잡입니다'))
    render(<JobPanel jobId={42} />)

    await userEvent.click(await screen.findByRole('button', { name: '중단' }))

    expect(await screen.findByText(/중단하지 못했습니다/)).toBeInTheDocument()
  })
})
