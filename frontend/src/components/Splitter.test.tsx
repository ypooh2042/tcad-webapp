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

/**
 * 손잡이를 그리드 안에 놓고, 남는 폭을 가져가는 칸(편집기)의 크기를 정해 준다.
 * jsdom 은 배치를 하지 않으므로 폭은 직접 알려 줘야 한다.
 */
function renderInGrid(
  width: number,
  onChange: (next: number) => void,
  editorWidth = 900,
) {
  render(
    <div>
      <div data-testid="editor" />
      <Splitter width={width} onChange={onChange} label="크기" />
    </div>,
  )
  vi.spyOn(
    screen.getByTestId('editor'),
    'getBoundingClientRect',
  ).mockReturnValue({ width: editorWidth } as DOMRect)
  return screen.getByRole('separator')
}

/** jsdom 에는 PointerEvent 가 없다. clientX 를 실어 보내려면 MouseEvent 를 쓴다. */
function drag(handle: HTMLElement, from: number, to: number) {
  fireEvent.pointerDown(handle, { clientX: from })
  window.dispatchEvent(new MouseEvent('pointermove', { clientX: to }))
}

describe('드래그', () => {
  it('끈 거리만큼만 움직인다', () => {
    // 창 끝을 기준으로 재면 오른쪽에 다른 패널이 있을 때 그 폭만큼 부풀려진다.
    // 실제로 매뉴얼 손잡이가 그래서 편집기를 0 으로 접고 왼쪽 끝에 붙었다.
    const onChange = vi.fn()
    const handle = renderInGrid(400, onChange)

    drag(handle, 1000, 940)

    expect(onChange).toHaveBeenLastCalledWith(460)
  })

  it('오른쪽으로 끌면 좁아진다', () => {
    const onChange = vi.fn()
    const handle = renderInGrid(400, onChange)

    drag(handle, 1000, 1060)

    expect(onChange).toHaveBeenLastCalledWith(340)
  })

  it('옆 칸이 내줄 수 있는 만큼까지만 넓어진다', () => {
    // 편집기가 내줄 수 있는 폭을 넘기면 그리드가 넘쳐 편집기가 접힌다.
    const onChange = vi.fn()
    const handle = renderInGrid(400, onChange, 500)

    drag(handle, 1000, 200)

    // 400 + 500 = 900 을 편집기와 나눠 쓴다. 편집기 몫 320 을 남긴다.
    expect(onChange).toHaveBeenLastCalledWith(580)
  })

  it('놓은 뒤에는 따라오지 않는다', () => {
    const onChange = vi.fn()
    const handle = renderInGrid(400, onChange)

    drag(handle, 1000, 940)
    fireEvent.pointerUp(handle)
    window.dispatchEvent(new MouseEvent('pointermove', { clientX: 500 }))

    expect(onChange).toHaveBeenCalledTimes(1)
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
