/**
 * 파라미터 참조 표.
 *
 * 자동완성과 호버로는 "지금 치고 있는 것" 하나만 보인다. 무엇을 쓸 수 있는지
 * 훑어보려면 표가 필요하다.
 *
 * 여기서 반드시 보여야 하는 두 가지는 실측으로 확인한 함정들이다:
 *   - 11자로 잘린 이름 (문서엔 concentration, 시뮬레이터는 concentrati 만 받음)
 *   - 도달 불가 파라미터 (structure backside 는 backside.y 때문에 지목 불가)
 */
import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ParameterTable } from './ParameterTable'
import type { CatalogParameter } from '../../api/catalog'

const { catalog } = vi.hoisted(() => ({
  catalog: { command: vi.fn(), parameters: vi.fn(), words: vi.fn() },
}))
vi.mock('../../api/catalog', () => ({ catalog }))

function param(overrides: Partial<CatalogParameter> = {}): CatalogParameter {
  return {
    name: 'conc',
    type: 'float',
    source_name: 'conc',
    truncated: false,
    default: null,
    units: '배경 농도',
    description: null,
    error: null,
    message: null,
    group: null,
    group_message: null,
    unreachable: false,
    ...overrides,
  }
}

function command(parameters: CatalogParameter[]) {
  return {
    name: 'initialize',
    source_name: 'initialize',
    description: null,
    parameters,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  catalog.command.mockResolvedValue(command([param()]))
})

describe('기본', () => {
  it('커맨드가 없으면 안내를 보여준다', () => {
    render(<ParameterTable command={null} />)

    expect(screen.getByText(/커서를 두면/)).toBeInTheDocument()
    expect(catalog.command).not.toHaveBeenCalled()
  })

  it('이름·타입·단위를 보여준다', async () => {
    render(<ParameterTable command="initialize" />)

    expect(await screen.findByText('conc')).toBeInTheDocument()
    expect(screen.getByText('float')).toBeInTheDocument()
    expect(screen.getByText('배경 농도')).toBeInTheDocument()
  })

  it('접두사를 그대로 넘긴다', async () => {
    render(<ParameterTable command="init" />)

    expect(catalog.command).toHaveBeenCalledWith('init')
  })

  it('기본값을 보여준다', async () => {
    catalog.command.mockResolvedValue(command([param({ default: '1.0e10' })]))

    render(<ParameterTable command="deposit" />)

    expect(await screen.findByText('1.0e10')).toBeInTheDocument()
  })

  it('boolean 은 값을 받지 않는다고 표시한다', async () => {
    // 빈칸으로 두면 "기본값 없음"과 헷갈린다.
    catalog.command.mockResolvedValue(
      command([param({ name: 'boron', type: 'boolean' })]),
    )

    render(<ParameterTable command="initialize" />)

    expect(await screen.findByText('(플래그)')).toBeInTheDocument()
  })

  it('파라미터가 없는 커맨드를 알린다', async () => {
    catalog.command.mockResolvedValue(command([]))

    render(<ParameterTable command="echo" />)

    expect(await screen.findByText(/파라미터가 없습니다/)).toBeInTheDocument()
  })

  it('없는 커맨드를 알린다', async () => {
    catalog.command.mockResolvedValue(null)

    render(<ParameterTable command="zzz" />)

    expect(await screen.findByText(/커맨드가 없습니다/)).toBeInTheDocument()
  })
})

describe('11자로 잘린 이름', () => {
  it('잘림을 표시한다', async () => {
    // 문서에는 concentration 으로 적혀 있는데 시뮬레이터는 concentrati 만
    // 받는다. 말해 주지 않으면 사용자가 오타로 오해한다.
    catalog.command.mockResolvedValue(
      command([
        param({
          name: 'concentrati',
          source_name: 'concentration',
          truncated: true,
        }),
      ]),
    )

    render(<ParameterTable command="deposit" />)

    expect(await screen.findByText('잘림')).toBeInTheDocument()
  })

  it('원형 이름을 설명에 담는다', async () => {
    catalog.command.mockResolvedValue(
      command([
        param({
          name: 'concentrati',
          source_name: 'concentration',
          truncated: true,
        }),
      ]),
    )

    render(<ParameterTable command="deposit" />)

    expect(await screen.findByTitle(/concentration/)).toBeInTheDocument()
  })

  it('잘리지 않은 이름에는 표시가 없다', async () => {
    render(<ParameterTable command="initialize" />)
    await screen.findByText('conc')

    expect(screen.queryByText('잘림')).not.toBeInTheDocument()
  })
})

describe('도달 불가 파라미터', () => {
  it('사용할 수 없다고 표시한다', async () => {
    // structure backside 는 backside.y 때문에 어떤 입력으로도 지목할 수 없다.
    // 목록에서 아예 빼면 매뉴얼에 있는 이름이 왜 없는지 알 수 없다.
    catalog.command.mockResolvedValue(
      command([param({ name: 'backside', type: 'boolean', unreachable: true })]),
    )

    render(<ParameterTable command="structure" />)

    expect(await screen.findByText('사용 불가')).toBeInTheDocument()
  })

  it('행을 흐리게 구분한다', async () => {
    catalog.command.mockResolvedValue(
      command([param({ name: 'backside', unreachable: true })]),
    )

    const { container } = render(<ParameterTable command="structure" />)
    await screen.findByText('backside')

    expect(container.querySelector('tr.unreachable')).toBeInTheDocument()
  })
})

describe('상호배타 묶음', () => {
  it('묶음 이름을 보여준다', async () => {
    catalog.command.mockResolvedValue(
      command([
        param({ name: 'boron', group: 'impurity', group_message: '불순물은 하나만' }),
      ]),
    )

    render(<ParameterTable command="initialize" />)

    expect(await screen.findByText('impurity')).toBeInTheDocument()
  })

  it('같이 쓸 수 없다는 설명을 담는다', async () => {
    catalog.command.mockResolvedValue(
      command([
        param({ name: 'boron', group: 'impurity', group_message: '불순물은 하나만' }),
      ]),
    )

    render(<ParameterTable command="initialize" />)

    expect(await screen.findByTitle('불순물은 하나만')).toBeInTheDocument()
  })
})

describe('제약', () => {
  it('오류 조건을 보여준다', async () => {
    catalog.command.mockResolvedValue(
      command([
        param({ error: 'conc < 0.0', message: '농도는 양수여야 합니다' }),
      ]),
    )

    render(<ParameterTable command="initialize" />)

    const row = (await screen.findByText('conc')).closest('tr')!
    expect(within(row).getByText(/conc < 0.0/)).toBeInTheDocument()
    expect(within(row).getByText(/농도는 양수여야 합니다/)).toBeInTheDocument()
  })
})
