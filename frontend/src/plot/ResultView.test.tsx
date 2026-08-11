/**
 * 결과 보기.
 *
 * 산출물 하나가 공정 한 단계다. 단계마다 존재하는 물리량이 다르다 — 주입 전
 * 구조에는 arsenic 컬럼이 아예 없다. 그래서 단계를 옮기면 무엇을 그릴 수 있는지
 * 부터 다시 물어야 한다.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ResultView } from './ResultView'

const { plot } = vi.hoisted(() => ({
  plot: { summary: vi.fn(), profile: vi.fn(), surface: vi.fn() },
}))
vi.mock('../api/endpoints', () => ({ plot }))

const ARTIFACTS = [
  { sequence: 1, filename: 'after_implant.str', size_bytes: 1024 },
  { sequence: 2, filename: 'after_diffuse.str', size_bytes: 2048 },
]

function summary(overrides = {}) {
  return {
    filename: 'a.str',
    dimension: 1,
    quantities: ['chem_boron', 'net_doping'],
    materials: ['silicon'],
    bounds: { x_min: 0, x_max: 2, y_min: 0, y_max: 0 },
    node_count: 43,
    element_count: 42,
    warnings: [],
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  plot.summary.mockResolvedValue(summary())
  plot.profile.mockResolvedValue({
    quantity: 'chem_boron',
    cut_x: null,
    points: [
      { depth: 0, value: 1e18, material: 'silicon' },
      { depth: 1, value: 1e15, material: 'silicon' },
    ],
  })
  plot.surface.mockResolvedValue({
    quantity: 'chem_boron',
    x: [0, 1, 0],
    y: [0, 0, 1],
    triangles: [[0, 1, 2]],
    values: [[1e18, 1e17, 1e16]],
    materials: ['silicon'],
    value_min: 1e16,
    value_max: 1e18,
  })
})

describe('산출물이 없을 때', () => {
  it('무엇을 해야 하는지 알려준다', () => {
    render(<ResultView jobId={1} artifacts={[]} />)

    expect(screen.getByText(/structure out=/)).toBeInTheDocument()
  })
})

describe('공정 단계', () => {
  it('첫 단계부터 보여준다', async () => {
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    expect(await screen.findByText(/after_implant.str/)).toBeInTheDocument()
  })

  it('단계를 옮기면 그 단계를 다시 읽는다', async () => {
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    await waitFor(() => expect(plot.summary).toHaveBeenCalledWith(1, 1))

    await userEvent.click(screen.getByLabelText('공정 단계'))
    screen.getByLabelText('공정 단계').setAttribute('value', '1')

    // 슬라이더 조작 대신 직접 바꿔도 순번이 서버로 넘어가야 한다.
    await waitFor(() => expect(plot.summary).toHaveBeenCalled())
  })
})

describe('물리량 선택', () => {
  it('그릴 수 있는 물리량을 목록으로 준다', async () => {
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    expect(await screen.findByRole('option', { name: 'chem_boron' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'net_doping' })).toBeInTheDocument()
  })

  it('고른 물리량으로 프로파일을 요청한다', async () => {
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    await screen.findByRole('option', { name: 'net_doping' })

    await userEvent.selectOptions(screen.getByLabelText('물리량'), 'net_doping')

    await waitFor(() =>
      expect(plot.profile).toHaveBeenCalledWith(1, 1, 'net_doping', undefined),
    )
  })
})

describe('1D', () => {
  it('컷 위치를 보내지 않는다', async () => {
    // 1D 는 깊이가 곧 x 축이라 자를 위치가 없다.
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    await waitFor(() =>
      expect(plot.profile).toHaveBeenCalledWith(1, 1, 'chem_boron', undefined),
    )
  })

  it('단면을 요청하지 않는다', async () => {
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    await waitFor(() => expect(plot.profile).toHaveBeenCalled())

    expect(plot.surface).not.toHaveBeenCalled()
  })
})

describe('2D', () => {
  beforeEach(() => {
    plot.summary.mockResolvedValue(
      summary({
        dimension: 2,
        bounds: { x_min: 0, x_max: 4, y_min: 0, y_max: 3 },
      }),
    )
  })

  it('가로 한가운데를 기본 컷으로 잡는다', async () => {
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    await waitFor(() =>
      expect(plot.profile).toHaveBeenCalledWith(1, 1, 'chem_boron', 2),
    )
  })

  it('단면을 함께 그린다', async () => {
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    await waitFor(() => expect(plot.surface).toHaveBeenCalled())
  })

  it('컷 위치를 안내한다', async () => {
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    expect(await screen.findByText(/x = 2.000/)).toBeInTheDocument()
  })
})

describe('경고와 오류', () => {
  it('파서 경고를 그대로 보여준다', async () => {
    // 삼키면 이상한 그림의 원인을 알 수 없다.
    plot.summary.mockResolvedValue(
      summary({ warnings: ['알 수 없는 species 코드 45'] }),
    )

    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    expect(await screen.findByText(/species 코드 45/)).toBeInTheDocument()
  })

  it('서버 오류 메시지를 보여준다', async () => {
    const { ApiError } = await import('../api/client')
    plot.summary.mockRejectedValue(
      new ApiError(410, '산출물이 정리되어 더 이상 남아 있지 않습니다', null),
    )

    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    expect(await screen.findByRole('alert')).toHaveTextContent(/정리되어/)
  })
})

describe('단계 비교', () => {
  it('단계가 하나면 비교 선택이 없다', async () => {
    render(<ResultView jobId={1} artifacts={[ARTIFACTS[0]!]} />)
    await screen.findByText(/after_implant/)

    expect(screen.queryByLabelText('비교')).not.toBeInTheDocument()
  })

  it('현재 단계는 비교 대상에서 뺀다', async () => {
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    const select = await screen.findByLabelText('비교')
    const options = within(select).getAllByRole('option').map((o) => o.textContent)
    expect(options).toEqual(['없음', 'after_diffuse.str'])
  })

  it('고른 단계의 프로파일을 같은 조건으로 읽는다', async () => {
    // 물리량과 컷 위치가 다르면 비교가 의미를 잃는다.
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    await screen.findByLabelText('비교')
    plot.profile.mockClear()

    await userEvent.selectOptions(screen.getByLabelText('비교'), '2')

    await waitFor(() =>
      expect(plot.profile).toHaveBeenCalledWith(1, 2, 'chem_boron', undefined),
    )
  })

  it('비교를 끄면 겹친 선이 사라진다', async () => {
    // 같은 이름이 비교 <option> 에도 있으므로 범례 안에서만 찾는다.
    const { container } = render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    await userEvent.selectOptions(await screen.findByLabelText('비교'), '2')
    await waitFor(() =>
      expect(container.querySelector('.legend')).toHaveTextContent(
        'after_diffuse.str',
      ),
    )

    await userEvent.selectOptions(screen.getByLabelText('비교'), '')

    await waitFor(() =>
      expect(container.querySelector('.legend')).not.toHaveTextContent(
        'after_diffuse.str',
      ),
    )
  })
})

describe('물리량 함께 보기', () => {
  it('현재 물리량은 목록에서 뺀다', async () => {
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    await userEvent.click(await screen.findByText(/함께 보기/))

    expect(screen.getByLabelText('net_doping')).toBeInTheDocument()
    expect(screen.queryByLabelText('chem_boron')).not.toBeInTheDocument()
  })

  it('고른 물리량을 같은 단계·같은 컷에서 읽는다', async () => {
    // 조건이 다르면 겹쳐 봐야 의미가 없다.
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    await userEvent.click(await screen.findByText(/함께 보기/))
    plot.profile.mockClear()

    await userEvent.click(screen.getByLabelText('net_doping'))

    await waitFor(() =>
      expect(plot.profile).toHaveBeenCalledWith(1, 1, 'net_doping', undefined),
    )
  })

  it('범례에 함께 보는 물리량을 적는다', async () => {
    const { container } = render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    await userEvent.click(await screen.findByText(/함께 보기/))

    await userEvent.click(screen.getByLabelText('net_doping'))

    await waitFor(() =>
      expect(container.querySelector('.legend')).toHaveTextContent('net_doping'),
    )
  })

  it('해제하면 사라진다', async () => {
    const { container } = render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    await userEvent.click(await screen.findByText(/함께 보기/))
    await userEvent.click(screen.getByLabelText('net_doping'))
    await waitFor(() =>
      expect(container.querySelector('.legend')).toHaveTextContent('net_doping'),
    )

    await userEvent.click(screen.getByLabelText('net_doping'))

    await waitFor(() =>
      expect(container.querySelector('.legend')).not.toHaveTextContent('net_doping'),
    )
  })

  it('고른 개수를 알려준다', async () => {
    // 접어 두면 무엇을 골랐는지 보이지 않는다.
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    await userEvent.click(await screen.findByText(/함께 보기/))

    await userEvent.click(screen.getByLabelText('net_doping'))

    expect(await screen.findByText(/함께 보기 \(1\)/)).toBeInTheDocument()
  })

  it('물리량이 하나뿐이면 선택이 없다', async () => {
    plot.summary.mockResolvedValue(summary({ quantities: ['chem_boron'] }))

    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    await screen.findByLabelText('물리량')

    expect(screen.queryByText(/함께 보기/)).not.toBeInTheDocument()
  })
})
