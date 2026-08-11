/**
 * 패널 크기 조절 손잡이.
 *
 * 핵심은 폭을 어디까지 허용하느냐다. 제한이 없으면 패널을 0 으로 끌어 사라지게
 * 하거나 편집기를 못 쓸 만큼 좁힐 수 있고, 되돌릴 방법도 없다.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MIN_EDITOR_WIDTH, MIN_WIDTH, Splitter, clampWidth } from './Splitter'

describe('폭 제한', () => {
  it('원하는 폭을 그대로 쓴다', () => {
    expect(clampWidth(500, 1600)).toBe(500)
  })

  it('너무 좁으면 하한까지만', () => {
    // 0 으로 끌어 패널을 사라지게 하면 되돌릴 손잡이도 같이 사라진다.
    expect(clampWidth(10, 1600)).toBe(MIN_WIDTH)
  })

  it('편집기 자리를 남긴다', () => {
    // 이 도구의 본체는 편집기다. 패널이 편집기를 밀어내면 안 된다.
    expect(clampWidth(1500, 1600)).toBe(1600 - MIN_EDITOR_WIDTH)
  })

  it('창이 좁으면 편집기를 살린다', () => {
    // 둘 다 하한을 지킬 수 없는 상황이다. 편집기 쪽을 택한다.
    const width = clampWidth(400, 400)

    expect(width).toBe(MIN_WIDTH)
  })
})

describe('접근성', () => {
  it('separator 로 알린다', () => {
    render(<Splitter width={360} onChange={vi.fn()} label="결과 패널 크기" />)

    const handle = screen.getByRole('separator', { name: '결과 패널 크기' })
    expect(handle).toHaveAttribute('aria-valuenow', '360')
  })

  it('키보드로 넓힌다', () => {
    // 드래그만 되면 포인터를 쓸 수 없는 사람은 조절할 방법이 없다.
    const onChange = vi.fn()
    render(<Splitter width={360} onChange={onChange} label="크기" />)

    fireEvent.keyDown(screen.getByRole('separator'), { key: 'ArrowLeft' })

    expect(onChange).toHaveBeenCalledWith(384)
  })

  it('키보드로 좁힌다', () => {
    const onChange = vi.fn()
    render(<Splitter width={360} onChange={onChange} label="크기" />)

    fireEvent.keyDown(screen.getByRole('separator'), { key: 'ArrowRight' })

    expect(onChange).toHaveBeenCalledWith(336)
  })

  it('다른 키는 무시한다', () => {
    const onChange = vi.fn()
    render(<Splitter width={360} onChange={onChange} label="크기" />)

    fireEvent.keyDown(screen.getByRole('separator'), { key: 'a' })

    expect(onChange).not.toHaveBeenCalled()
  })

  it('키보드 조작도 하한을 지킨다', () => {
    const onChange = vi.fn()
    render(<Splitter width={MIN_WIDTH} onChange={onChange} label="크기" />)

    fireEvent.keyDown(screen.getByRole('separator'), { key: 'ArrowRight' })

    expect(onChange).toHaveBeenCalledWith(MIN_WIDTH)
  })
})
