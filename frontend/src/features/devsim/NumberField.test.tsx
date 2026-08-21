import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { NumberField, NumberListField, parseNumberList } from './NumberField'

describe('parseNumberList', () => {
  it('쉼표로 나눈 숫자를 읽는다', () => {
    expect(parseNumberList('0, 1.5, 2')).toEqual([0, 1.5, 2])
  })

  it('아직 숫자가 아닌 조각은 버린다', () => {
    // 치는 도중의 "0, " 같은 상태다.
    expect(parseNumberList('0, ')).toEqual([0])
    expect(parseNumberList('')).toEqual([])
  })

  it('음수와 소수를 읽는다', () => {
    expect(parseNumberList('-1.5, -0.25')).toEqual([-1.5, -0.25])
  })

  it('"0." 은 아직 완성되지 않은 입력이지만 0 으로 읽는다', () => {
    expect(parseNumberList('0.')).toEqual([0])
  })
})

describe('NumberListField', () => {
  it('소수점을 칠 수 있다', async () => {
    // 예전에는 값을 매번 다시 문자열로 만들어 넣어서, "0." 이 "0" 으로
    // 되돌아가 소수를 아예 못 쳤다.
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<NumberListField label="단계 전압" values={[]} onChange={onChange} />)

    const input = screen.getByLabelText('단계 전압')
    await user.type(input, '0.5')

    expect(input).toHaveValue('0.5')
    expect(onChange).toHaveBeenLastCalledWith([0.5])
  })

  it('여러 값을 이어서 칠 수 있다', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<NumberListField label="단계 전압" values={[]} onChange={onChange} />)

    const input = screen.getByLabelText('단계 전압')
    await user.type(input, '0, 0.8, 1.6')

    expect(input).toHaveValue('0, 0.8, 1.6')
    expect(onChange).toHaveBeenLastCalledWith([0, 0.8, 1.6])
  })

  it('음수도 칠 수 있다', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<NumberListField label="단계 전압" values={[]} onChange={onChange} />)

    await user.type(screen.getByLabelText('단계 전압'), '-1.2')
    expect(onChange).toHaveBeenLastCalledWith([-1.2])
  })

  it('밖에서 값이 바뀌면 글자도 따라간다', () => {
    // 구조를 바꾸면 조건이 통째로 새로 만들어진다.
    const { rerender } = render(
      <NumberListField label="단계 전압" values={[0, 1]} onChange={vi.fn()} />,
    )
    expect(screen.getByLabelText('단계 전압')).toHaveValue('0, 1')

    rerender(
      <NumberListField label="단계 전압" values={[0, 2, 4]} onChange={vi.fn()} />,
    )
    expect(screen.getByLabelText('단계 전압')).toHaveValue('0, 2, 4')
  })
})

describe('NumberField', () => {
  it('소수점을 칠 수 있다', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<NumberField label="간격" value={0} onChange={onChange} />)

    const input = screen.getByLabelText('간격')
    await user.clear(input)
    await user.type(input, '0.05')

    expect(input).toHaveValue('0.05')
    expect(onChange).toHaveBeenLastCalledWith(0.05)
  })

  it('빈칸으로 지워도 0 으로 되돌아가지 않는다', async () => {
    // 되돌아가면 지우고 다시 칠 수가 없다.
    const user = userEvent.setup()
    render(<NumberField label="끝" value={2} onChange={vi.fn()} />)

    const input = screen.getByLabelText('끝')
    await user.clear(input)
    expect(input).toHaveValue('')
  })

  it('숫자가 아닌 동안은 알리지 않는다', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<NumberField label="시작" value={0} onChange={onChange} />)

    const input = screen.getByLabelText('시작')
    await user.clear(input)
    await user.type(input, '-')

    expect(onChange).not.toHaveBeenCalled()
    expect(input).toHaveValue('-')
  })

  it('밖에서 값이 바뀌면 글자도 따라간다', () => {
    const { rerender } = render(
      <NumberField label="끝" value={2} onChange={vi.fn()} />,
    )
    rerender(<NumberField label="끝" value={3.5} onChange={vi.fn()} />)
    expect(screen.getByLabelText('끝')).toHaveValue('3.5')
  })
})
