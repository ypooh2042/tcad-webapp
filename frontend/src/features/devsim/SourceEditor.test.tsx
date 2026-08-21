/**
 * 전극 이름을 고치는 자리.
 *
 * 실제 앱처럼 스펙을 들고 되먹임하는 껍데기로 감싸 본다. 이름이 곧 전극의
 * 열쇠라, 고치는 도중의 상태가 그대로 목록에 반영되면 무슨 일이 벌어지는지는
 * 되먹임 없이는 드러나지 않는다.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { DeviceSpec, DevSimInterface } from '../../api/types'
import { defaultSpec, renameElectrode } from './deviceSpec'
import { SourceEditor } from './SourceEditor'

function detected(key: string, x: number): DevSimInterface {
  return {
    key,
    origin: 'metal',
    kind: 'semiconductor',
    materials: ['silicon'],
    extent: { x_min: x, x_max: x + 0.3, y_min: 0, y_max: 0.05 },
    edge_count: 4,
    segments: [[x, 0, x + 0.3, 0]],
  }
}

const INTERFACES = [
  detected('source', 0.2),
  detected('gate', 0.9),
  detected('drain', 1.5),
]

/** 앱과 같은 되먹임. 고친 이름이 바로 목록으로 돌아온다. */
function Harness({ onSpec }: { onSpec?: (spec: DeviceSpec) => void } = {}) {
  const [spec, setSpec] = useState<DeviceSpec>(() => defaultSpec(INTERFACES))
  return (
    <SourceEditor
      spec={spec}
      onChange={(next) => {
        setSpec(next)
        onSpec?.(next)
      }}
      onAddElectrode={vi.fn()}
      onRemoveElectrode={vi.fn()}
      onRenameElectrode={(from, to) =>
        setSpec((current) => {
          const next = renameElectrode(current, from, to)
          onSpec?.(next)
          return next
        })
      }
      describeInterface={(key) => key}
      nameOf={(key) => key}
    />
  )
}

describe('전극 이름 고치기', () => {
  it('여러 글자를 이어서 칠 수 있다', async () => {
    // 예전에는 목록 항목의 key 가 이름이었다. 한 글자 칠 때마다 key 가 바뀌어
    // React 가 그 항목을 새로 만들었고, 입력칸이 포커스를 잃어 한 글자밖에
    // 못 쳤다.
    const user = userEvent.setup()
    render(<Harness />)

    const input = screen.getByLabelText('전극 1 이름')
    await user.clear(input)
    await user.type(input, 'pmos 소스')

    expect(input).toHaveValue('pmos 소스')
  })

  it('backspace 로 이어서 지울 수 있다', async () => {
    const user = userEvent.setup()
    render(<Harness />)

    const input = screen.getByLabelText('전극 1 이름')
    input.focus()
    await user.keyboard('{End}{Backspace}{Backspace}{Backspace}')

    expect(input).toHaveValue('sou')
  })

  it('빈칸으로 지웠다가 다시 칠 수 있다', async () => {
    // 이름이 비면 스펙에 넣을 수 없다. 그렇다고 화면까지 옛 이름으로 되돌리면
    // 지우고 다시 칠 방법이 없어진다.
    const user = userEvent.setup()
    render(<Harness />)

    const input = screen.getByLabelText('전극 1 이름')
    await user.clear(input)
    expect(input).toHaveValue('')

    await user.type(input, 'S')
    expect(input).toHaveValue('S')
  })

  it('다 치고 나면 전압원이 가리키는 곳도 따라간다', async () => {
    const user = userEvent.setup()
    let latest: DeviceSpec | null = null
    render(<Harness onSpec={(spec) => (latest = spec)} />)

    const input = screen.getByLabelText('전극 3 이름')
    await user.clear(input)
    await user.type(input, '출력')
    await user.tab()

    const spec = latest as DeviceSpec | null
    expect(spec?.electrodes.map((one) => one.label)).toContain('출력')
    expect(spec?.biases.some((one) => one.electrode === '출력')).toBe(true)
  })

  it('이미 있는 이름으로는 바뀌지 않는다', async () => {
    const user = userEvent.setup()
    let latest: DeviceSpec | null = null
    render(<Harness onSpec={(spec) => (latest = spec)} />)

    const input = screen.getByLabelText('전극 1 이름')
    await user.clear(input)
    await user.type(input, 'gate')
    await user.tab()

    const spec = latest as DeviceSpec | null
    // 겹친 이름을 받아들이면 두 전극이 같은 열쇠를 갖게 된다.
    expect(
      spec?.electrodes.filter((one) => one.label === 'gate'),
    ).toHaveLength(1)
    expect(input).toHaveValue('source')
  })

  it('다른 전극의 이름은 건드리지 않는다', async () => {
    const user = userEvent.setup()
    render(<Harness />)

    await user.clear(screen.getByLabelText('전극 1 이름'))
    await user.type(screen.getByLabelText('전극 1 이름'), 'S')
    await user.tab()

    expect(screen.getByLabelText('전극 2 이름')).toHaveValue('gate')
    expect(screen.getByLabelText('전극 3 이름')).toHaveValue('drain')
  })
})
