/**
 * 드래그로 옆 패널의 폭을 바꾸는 손잡이.
 *
 * 폭은 저장한다. 매번 다시 끌어야 하면 안 쓰게 된다.
 *
 * 키보드로도 움직인다. 드래그만 되면 포인터를 쓸 수 없는 사람은 폭을 조절할
 * 방법이 없다.
 */
import { useCallback, useEffect, useRef } from 'react'

/** 패널이 이보다 좁아지면 안의 내용이 읽히지 않는다. */
export const MIN_WIDTH = 240

/** 편집기가 이보다 좁아지면 코드를 쓸 수 없다. */
export const MIN_EDITOR_WIDTH = 320

/**
 * 드래그 결과 폭을 상한·하한 안으로 넣는다.
 *
 * 창 전체가 좁으면 하한을 다 지킬 수 없다. 그럴 때는 **편집기 쪽을 살린다** —
 * 이 도구의 본체는 편집기다.
 */
export function clampWidth(
  desired: number,
  available: number,
  minWidth = MIN_WIDTH,
  minEditor = MIN_EDITOR_WIDTH,
): number {
  const max = Math.max(minWidth, available - minEditor)
  return Math.min(max, Math.max(minWidth, desired))
}

interface Props {
  width: number
  onChange: (width: number) => void
  /** 왼쪽으로 끌면 넓어지는가(오른쪽 패널) 좁아지는가. */
  side?: 'left' | 'right'
  label: string
}

const KEYBOARD_STEP = 24

export function Splitter({ width, onChange, side = 'right', label }: Props) {
  const dragging = useRef(false)

  const move = useCallback(
    (clientX: number) => {
      const available = window.innerWidth
      const desired =
        side === 'right' ? available - clientX : clientX
      onChange(clampWidth(desired, available))
    },
    [onChange, side],
  )

  useEffect(() => {
    function onPointerMove(event: PointerEvent) {
      if (!dragging.current) return
      // 드래그 중 텍스트가 선택되면 화면이 파랗게 물든다.
      event.preventDefault()
      move(event.clientX)
    }
    function onPointerUp() {
      dragging.current = false
      document.body.classList.remove('resizing')
    }

    // 포인터가 손잡이 밖으로 나가도 계속 따라가야 한다. 창 전체에서 듣는다.
    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', onPointerUp)
    return () => {
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerup', onPointerUp)
      document.body.classList.remove('resizing')
    }
  }, [move])

  return (
    <div
      className="splitter"
      role="separator"
      aria-label={label}
      aria-orientation="vertical"
      aria-valuenow={Math.round(width)}
      tabIndex={0}
      onPointerDown={(event) => {
        dragging.current = true
        document.body.classList.add('resizing')
        event.currentTarget.setPointerCapture(event.pointerId)
      }}
      onKeyDown={(event) => {
        const delta =
          event.key === 'ArrowLeft'
            ? -KEYBOARD_STEP
            : event.key === 'ArrowRight'
              ? KEYBOARD_STEP
              : 0
        if (!delta) return
        event.preventDefault()
        const signed = side === 'right' ? -delta : delta
        onChange(clampWidth(width + signed, window.innerWidth))
      }}
    />
  )
}
