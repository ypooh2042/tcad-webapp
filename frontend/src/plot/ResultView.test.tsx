/**
 * 결과 보기.
 *
 * 산출물 하나가 공정 한 단계다. 단계마다 존재하는 물리량이 다르다 — 주입 전
 * 구조에는 arsenic 컬럼이 아예 없다. 그래서 단계를 옮기면 무엇을 그릴 수 있는지
 * 부터 다시 물어야 한다.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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

//: 처음 보여주는 단계. 결과가 오면 **마지막** 단계부터 보여주므로, 단계와
//: 무관한 시험들이 기대하는 순번도 이것이다.
const LAST_SEQUENCE = 2

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
  it('이전 단계로 돌아가면 그 단계를 읽는다', async () => {
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    await waitFor(() => expect(plot.summary).toHaveBeenCalledWith(1, 2))
    plot.summary.mockClear()

    await userEvent.click(screen.getByRole('button', { name: /이전/ }))

    await waitFor(() => expect(plot.summary).toHaveBeenCalledWith(1, 1))
  })

  it('다시 다음 단계로 간다', async () => {
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    await screen.findByText(/after_diffuse.str/)

    await userEvent.click(screen.getByRole('button', { name: /이전/ }))
    await screen.findByText(/1\/2/)
    await userEvent.click(screen.getByRole('button', { name: /다음/ }))

    expect(await screen.findByText(/2\/2/)).toBeInTheDocument()
  })

  it('첫 단계에서는 이전이 눌리지 않는다', async () => {
    // 슬라이더와 달리 버튼은 끝에서 무엇이 막혔는지 보여줄 수 있다.
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    await userEvent.click(await screen.findByRole('button', { name: /이전/ }))

    expect(await screen.findByRole('button', { name: /이전/ })).toBeDisabled()
  })

  it('마지막 단계에서는 다음이 눌리지 않는다', async () => {
    // 기본이 마지막 단계이므로 처음부터 막혀 있어야 한다.
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    expect(await screen.findByRole('button', { name: /다음/ })).toBeDisabled()
  })

  it('꾹 누르기가 버튼에 연결돼 있다', async () => {
    // 반복 타이밍 자체는 useHoldRepeat.test 가 가짜 타이머로 따로 본다.
    // 여기서는 버튼이 pointerdown 에 반응하는지(= 훅이 붙었는지)만 확인한다.
    // 클릭 대신 pointerdown 으로 한 칸 넘어가야 한다.
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    await screen.findByText(/2\/2/)

    fireEvent.pointerDown(screen.getByRole('button', { name: /이전/ }))

    expect(await screen.findByText(/1\/2/)).toBeInTheDocument()
  })

  it('빠르게 훑는 동안 지나친 단계는 불러오지 않는다', async () => {
    // 단계당 요청이 4개(요약·물리량·단면)라, 지나치는 단계까지 받으면 꾹
    // 누르기(150ms)에서 초당 27개가 나가 nginx 레이트 리밋(20 req/s)에 걸린다.
    // 실제로 503 이 떴다.
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    await screen.findByText(/2\/2/)
    plot.summary.mockClear()

    // 멎기 전에 앞뒤로 훑는다. 마지막에 머문 단계만 불러와야 한다.
    const next = screen.getByRole('button', { name: /다음/ })
    const prev = screen.getByRole('button', { name: /이전/ })
    fireEvent.pointerDown(prev)
    fireEvent.pointerDown(next)
    fireEvent.pointerDown(prev)

    await waitFor(() => expect(plot.summary).toHaveBeenCalled())
    expect(plot.summary).toHaveBeenCalledTimes(1)
    expect(plot.summary).toHaveBeenLastCalledWith(1, 1)
  })

  it('표시는 곧바로 바뀐다', async () => {
    // 불러오기를 늦추더라도 번호는 즉시 움직여야 누른 것이 느껴진다.
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    await screen.findByText(/2\/2/)

    fireEvent.pointerDown(screen.getByRole('button', { name: /이전/ }))

    expect(await screen.findByText(/1\/2/)).toBeInTheDocument()
  })

  it('아직 옛 단계를 보고 있으면 그렇다고 알린다', async () => {
    // 번호만 먼저 바뀌면 옛 그림을 새 단계의 것으로 읽게 된다.
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    await screen.findByText(/2\/2/)

    fireEvent.pointerDown(screen.getByRole('button', { name: /이전/ }))

    expect(screen.getByText(/불러오는 중/)).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.queryByText(/불러오는 중/)).not.toBeInTheDocument(),
    )
  })

  it('단계 이름은 버튼 줄 밖에 둔다', async () => {
    // 이름이 길면 버튼과 같은 줄에서 접혀 줄바꿈되고 UI 가 흐트러진다.
    // 아래 줄로 내려 이름이 아무리 길어도 버튼 배치가 흔들리지 않게 한다.
    const { container } = render(
      <ResultView jobId={1} artifacts={ARTIFACTS} />,
    )
    const name = await screen.findByText('after_diffuse.str')

    expect(container.querySelector('.scrubber')).not.toContainElement(name)
    expect(name.closest('.stage-name')).not.toBeNull()
  })

  it('단계가 하나여도 이름은 보여준다', async () => {
    // 지금 무엇을 보고 있는지 아는 유일한 단서다.
    render(<ResultView jobId={1} artifacts={[ARTIFACTS[0]]} />)

    expect(await screen.findByText('after_implant.str')).toBeInTheDocument()
  })

  it('단계가 하나면 버튼을 두지 않는다', async () => {
    // 누를 수 없는 버튼 두 개는 자리만 차지한다.
    render(<ResultView jobId={1} artifacts={[ARTIFACTS[0]]} />)

    await screen.findByText(/after_implant.str/)
    expect(screen.queryByRole('button', { name: /다음/ })).not.toBeInTheDocument()
  })
})

describe('물리량 선택', () => {
  it('체크박스로 모든 물리량을 내놓는다', async () => {
    // 콤보박스로 하나만 고르게 하면 겹쳐 보기가 부가 기능처럼 된다.
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    expect(await screen.findByLabelText('chem_boron')).toBeInTheDocument()
    expect(screen.getByLabelText('net_doping')).toBeInTheDocument()
  })

  it('첫 물리량을 기본으로 골라 준다', async () => {
    // 빈 차트로 시작하면 무엇을 해야 할지 알기 어렵다.
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    expect(await screen.findByLabelText('chem_boron')).toBeChecked()
  })

  it('고른 것을 모두 읽는다', async () => {
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    await screen.findByLabelText('net_doping')
    plot.profile.mockClear()

    await userEvent.click(screen.getByLabelText('net_doping'))

    await waitFor(() => {
      expect(plot.profile).toHaveBeenCalledWith(1, LAST_SEQUENCE, 'chem_boron', undefined)
      expect(plot.profile).toHaveBeenCalledWith(1, LAST_SEQUENCE, 'net_doping', undefined)
    })
  })

  it('둘 다 범례에 나온다', async () => {
    const { container } = render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    await screen.findByLabelText('net_doping')

    await userEvent.click(screen.getByLabelText('net_doping'))

    await waitFor(() => {
      const legend = container.querySelector('.legend')
      expect(legend).toHaveTextContent('chem_boron')
      expect(legend).toHaveTextContent('net_doping')
    })
  })

  it('모두 해제하면 안내한다', async () => {
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    await screen.findByLabelText('chem_boron')

    await userEvent.click(screen.getByLabelText('chem_boron'))

    expect(await screen.findByText(/하나 이상 골라/)).toBeInTheDocument()
  })

  it('이 단계에 없는 물리량은 떨어뜨린다', async () => {
    // 주입 전 구조에는 arsenic 컬럼이 아예 없다.
    plot.summary.mockResolvedValue(summary({ quantities: ['chem_boron'] }))

    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    await screen.findByLabelText('chem_boron')
    expect(screen.queryByLabelText('net_doping')).not.toBeInTheDocument()
  })
})

describe('1D', () => {
  it('컷 위치를 보내지 않는다', async () => {
    // 1D 는 깊이가 곧 x 축이라 자를 위치가 없다.
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    await waitFor(() =>
      expect(plot.profile).toHaveBeenCalledWith(1, LAST_SEQUENCE, 'chem_boron', undefined),
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
      expect(plot.profile).toHaveBeenCalledWith(1, LAST_SEQUENCE, 'chem_boron', 2),
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

describe('단계 비교는 없앴다', () => {
  it('비교 선택이 없다', async () => {
    // 같은 물리량을 두 단계로 겹치면 선이 배가 되어 무엇이 무엇인지 알 수
    // 없었다. 단계 슬라이더로 옮겨 보는 것으로 충분하다.
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    await screen.findByLabelText('chem_boron')

    expect(screen.queryByLabelText('단계 비교')).not.toBeInTheDocument()
  })
})

describe('단면과 수직선 물리량 분리', () => {
  beforeEach(() => {
    plot.summary.mockResolvedValue(
      summary({
        dimension: 2,
        bounds: { x_min: 0, x_max: 4, y_min: 0, y_max: 3 },
      }),
    )
  })

  it('단면 물리량은 콤보박스로 하나만 고른다', async () => {
    // 단면은 색으로 값을 칠하는 그림이라 한 번에 하나만 의미가 있다.
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    const select = await screen.findByLabelText('구조 단면')
    expect(select.tagName).toBe('SELECT')
    expect(
      within(select).getAllByRole('option').map((o) => o.textContent),
    ).toEqual(['재질', 'chem_boron', 'net_doping'])
  })

  it('격자 보기는 기본으로 꺼져 있다', async () => {
    // 촘촘한 메시를 항상 얹으면 정작 값이 안 보인다.
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    expect(await screen.findByLabelText('격자 보기')).not.toBeChecked()
  })

  it('격자 보기를 켜면 단면에 전달한다', async () => {
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    await userEvent.click(await screen.findByLabelText('격자 보기'))

    expect(screen.getByLabelText('격자 보기')).toBeChecked()
  })

  it('1D 구조에는 격자 보기가 없다', async () => {
    // 단면 그림이 없으므로 얹을 곳도 없다.
    plot.summary.mockResolvedValue(summary({ dimension: 1 }))
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    await screen.findByText(/1D/)
    expect(screen.queryByLabelText('격자 보기')).not.toBeInTheDocument()
  })

  it('수직선 물리량은 체크박스로 여러 개 고른다', async () => {
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    expect(await screen.findByLabelText('chem_boron')).toBeInTheDocument()
    expect(screen.getByLabelText('net_doping')).toBeInTheDocument()
  })

  it('단면을 바꿔도 수직선 그래프는 그대로다', async () => {
    // 둘이 묶여 있으면 단면 색을 바꾸려다 그래프가 통째로 바뀐다 — 이게
    // 분리한 이유다.
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    // 초기 프로파일 호출이 끝난 뒤에 세기 시작한다. 먼저 지우면 그 호출이
    // 뒤늦게 도착해 간헐적으로 실패한다.
    await waitFor(() => expect(plot.profile).toHaveBeenCalled())
    plot.profile.mockClear()

    await userEvent.selectOptions(screen.getByLabelText('구조 단면'), 'net_doping')

    await waitFor(() =>
      expect(plot.surface).toHaveBeenCalledWith(1, LAST_SEQUENCE, 'net_doping'),
    )
    // 프로파일은 다시 읽지 않는다.
    expect(plot.profile).not.toHaveBeenCalled()
  })

  it('수직선 물리량을 바꿔도 단면은 그대로다', async () => {
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    // 처음 한 번은 단면을 읽는다. 그 호출이 끝나기 전에 세어 두면 뒤늦게
    // 도착해서 간헐적으로 실패한다 — 실제로 6회 중 1회 그렇게 깨졌다.
    await waitFor(() => expect(plot.surface).toHaveBeenCalled())
    plot.surface.mockClear()

    await userEvent.click(screen.getByLabelText('net_doping'))

    await waitFor(() =>
      expect(plot.profile).toHaveBeenCalledWith(1, LAST_SEQUENCE, 'net_doping', 2),
    )
    expect(plot.surface).not.toHaveBeenCalled()
  })

  it('1D 에는 단면 선택이 없다', async () => {
    // 1D 는 깊이가 곧 x 축이라 자를 단면이 없다.
    plot.summary.mockResolvedValue(summary({ dimension: 1 }))

    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    await screen.findByLabelText('chem_boron')
    expect(screen.queryByLabelText('구조 단면')).not.toBeInTheDocument()
  })
})

describe('재질만 보기', () => {
  beforeEach(() => {
    plot.summary.mockResolvedValue(
      summary({
        dimension: 2,
        bounds: { x_min: 0, x_max: 4, y_min: 0, y_max: 3 },
      }),
    )
  })

  it('단면 옵션에 재질이 들어 있다', async () => {
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    const select = await screen.findByLabelText('구조 단면')
    expect(
      within(select).getAllByRole('option').map((o) => o.textContent),
    ).toEqual(['재질', 'chem_boron', 'net_doping'])
  })

  it('재질이 기본값이다', async () => {
    // 구조가 어떻게 생겼는지부터 보는 것이 자연스럽다. 값 분포는 그다음이다.
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    expect(await screen.findByLabelText('구조 단면')).toHaveValue('재질')
  })

  it('기본 상태에서 물리량 없이 부른다', async () => {
    // 물리량을 끼워 보내면 서버가 해 없는 요소를 버려서 층이 사라진다.
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    await waitFor(() => expect(plot.surface).toHaveBeenCalledWith(1, LAST_SEQUENCE, null))
  })

  it('물리량으로 바꿨다가 돌아올 수 있다', async () => {
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    await screen.findByLabelText('구조 단면')

    await userEvent.selectOptions(screen.getByLabelText('구조 단면'), 'net_doping')
    await waitFor(() =>
      expect(plot.surface).toHaveBeenCalledWith(1, LAST_SEQUENCE, 'net_doping'),
    )

    await userEvent.selectOptions(screen.getByLabelText('구조 단면'), '재질')
    await waitFor(() => expect(plot.surface).toHaveBeenCalledWith(1, LAST_SEQUENCE, null))
  })

  it('재질 보기에서도 수직선 그래프는 그대로다', async () => {
    // 단면과 수직선은 따로다.
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    await waitFor(() => expect(plot.profile).toHaveBeenCalled())
    plot.profile.mockClear()

    await userEvent.selectOptions(screen.getByLabelText('구조 단면'), '재질')

    await waitFor(() => expect(plot.surface).toHaveBeenCalledWith(1, LAST_SEQUENCE, null))
    expect(plot.profile).not.toHaveBeenCalled()
  })

  it('물리량이 하나도 없어도 재질은 볼 수 있다', async () => {
    // 값이 없는 구조에서도 층 모양은 볼 가치가 있다.
    plot.summary.mockResolvedValue(
      summary({
        dimension: 2,
        quantities: [],
        bounds: { x_min: 0, x_max: 4, y_min: 0, y_max: 3 },
      }),
    )

    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    await waitFor(() => expect(plot.surface).toHaveBeenCalledWith(1, LAST_SEQUENCE, null))
  })
})

describe('체크박스 위치', () => {
  beforeEach(() => {
    plot.summary.mockResolvedValue(
      summary({
        dimension: 2,
        bounds: { x_min: 0, x_max: 4, y_min: 0, y_max: 3 },
      }),
    )
  })

  it('그래프 바로 위에 둔다', async () => {
    // 2D 단면이 사이에 끼면 체크박스를 누를 때마다 스크롤을 오르내려야 한다.
    const { container } = render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    // 차트는 프로파일을 받은 뒤에야 그려진다. 먼저 읽으면 null 이다.
    await waitFor(() => expect(container.querySelector('.chart')).toBeTruthy())

    const quantities = container.querySelector('.quantities')!
    const chart = container.querySelector('.chart')!

    // DOM 순서상 체크박스가 차트 바로 앞이어야 한다.
    expect(
      quantities.compareDocumentPosition(chart) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    expect(quantities.nextElementSibling).toBe(chart)
  })

  it('단면보다 아래에 있다', async () => {
    const { container } = render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    // 단면은 surface 응답을 받은 뒤에야 붙는다. 먼저 읽으면 null 이고,
    // `!` 가 그것을 가려 간헐적으로만 깨진다(5회 중 1회 실측).
    await waitFor(() =>
      expect(container.querySelector('canvas.surface')).toBeTruthy(),
    )

    const surface = container.querySelector('canvas.surface')!
    const quantities = container.querySelector('.quantities')!

    expect(
      surface.compareDocumentPosition(quantities) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
  })
})

describe('처음 보여줄 단계', () => {
  it('마지막 단계부터 보여준다', async () => {
    // 사용자가 보려는 것은 보통 공정이 끝난 모습이다. 15단계짜리 흐름에서
    // 거기까지 '다음' 을 열네 번 눌러 가는 것은 번거롭다.
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    expect(await screen.findByText('after_diffuse.str')).toBeInTheDocument()
    expect(screen.getByText(/2\/2/)).toBeInTheDocument()
  })

  it('마지막 단계만 불러온다', async () => {
    // 첫 단계를 한 번 그렸다가 마지막으로 뛰면 요청이 두 벌 나간다.
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)

    await waitFor(() => expect(plot.summary).toHaveBeenCalled())
    expect(plot.summary).toHaveBeenCalledTimes(1)
    expect(plot.summary).toHaveBeenCalledWith(1, 2)
  })

  it('새 실행 결과가 오면 다시 마지막으로 간다', async () => {
    const { rerender } = render(
      <ResultView jobId={1} artifacts={ARTIFACTS} />,
    )
    await screen.findByText(/2\/2/)
    await userEvent.click(screen.getByRole('button', { name: /이전/ }))
    await screen.findByText(/1\/2/)

    rerender(
      <ResultView
        jobId={2}
        artifacts={[
          ...ARTIFACTS,
          { sequence: 3, filename: 'after_etch.str', size_bytes: 512 },
        ]}
      />,
    )

    expect(await screen.findByText(/3\/3/)).toBeInTheDocument()
  })

  it('같은 실행을 다시 그려도 보던 단계를 빼앗지 않는다', async () => {
    // 폴링은 1.5초마다 새 배열을 만든다. 그때마다 마지막으로 끌려가면
    // 앞 단계를 들여다볼 수가 없다.
    const { rerender } = render(
      <ResultView jobId={1} artifacts={ARTIFACTS} />,
    )
    await screen.findByText(/2\/2/)
    await userEvent.click(screen.getByRole('button', { name: /이전/ }))
    await screen.findByText(/1\/2/)

    rerender(<ResultView jobId={1} artifacts={[...ARTIFACTS]} />)

    expect(screen.getByText(/1\/2/)).toBeInTheDocument()
  })
})

describe('소자 해석으로 넘기기', () => {
  it('금속이 있는 단계에만 버튼이 보인다', async () => {
    // 전극은 알루미늄이 실리콘이나 폴리실리콘에 닿아야 생긴다. 금속이 아예
    // 없는 단계에서 넘겨 봐야 "전극이 없습니다"만 보게 된다.
    plot.summary.mockResolvedValue(summary({ materials: ['silicon', 'aluminum'] }))
    render(
      <ResultView jobId={1} artifacts={ARTIFACTS} onAnalyse={vi.fn()} />,
    )
    expect(
      await screen.findByRole('button', { name: '소자 해석' }),
    ).toBeInTheDocument()
  })

  it('금속이 없으면 버튼을 두지 않는다', async () => {
    plot.summary.mockResolvedValue(summary({ materials: ['silicon', 'oxide'] }))
    render(
      <ResultView jobId={1} artifacts={ARTIFACTS} onAnalyse={vi.fn()} />,
    )
    // 요약이 도착한 뒤에 봐야 한다. 도착 전에는 어차피 아무것도 없다.
    expect(await screen.findByText(/after_diffuse\.str/)).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: '소자 해석' }),
    ).not.toBeInTheDocument()
  })

  it('넘길 곳이 없으면 금속이 있어도 버튼을 두지 않는다', async () => {
    plot.summary.mockResolvedValue(summary({ materials: ['aluminum'] }))
    render(<ResultView jobId={1} artifacts={ARTIFACTS} />)
    expect(await screen.findByText(/after_diffuse\.str/)).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: '소자 해석' }),
    ).not.toBeInTheDocument()
  })
})
