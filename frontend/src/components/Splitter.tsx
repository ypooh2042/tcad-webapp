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

/** 손잡이가 차지하는 폭. App.css 의 `.splitter` 와 같아야 한다. */
export const SPLITTER_WIDTH = 7

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

/**
 * 이 손잡이가 폭을 나눠 갖는 상대. 그리드에서 남는 폭을 가져가는 첫 칸이다.
 *
 * 손잡이가 첫 칸이면(옆에 유연한 칸이 없으면) 잴 것이 없으므로 창 폭으로
 * 대신한다.
 */
function flexibleWidth(handle: HTMLElement): number {
  const first = handle.parentElement?.firstElementChild
  if (!first || first === handle) return window.innerWidth
  return first.getBoundingClientRect().width
}

/**
 * 이 패널과 편집기가 나눠 쓸 수 있는 폭.
 *
 * 드래그 중에는 변하지 않는다 — 한쪽이 넓어지면 다른 쪽이 그만큼 좁아질 뿐이다.
 */
function availableFor(handle: HTMLElement, width: number): number {
  return width + flexibleWidth(handle)
}

interface Props {
  width: number
  onChange: (width: number) => void
  /** 왼쪽으로 끌면 넓어지는가(오른쪽 패널) 좁아지는가. */
  side?: 'left' | 'right'
  label: string
}

const KEYBOARD_STEP = 24

/** 드래그를 시작한 지점. 끝날 때까지 바뀌지 않는다. */
interface Grip {
  x: number
  width: number
  available: number
}

export function Splitter({ width, onChange, side = 'right', label }: Props) {
  const grip = useRef<Grip | null>(null)

  const move = useCallback(
    (clientX: number) => {
      const start = grip.current
      if (!start) return

      // **끈 거리로 잰다.** 창 끝을 기준으로 재면 이 패널 오른쪽에 다른 패널이
      // 있을 때 그 폭만큼 부풀려진다 — 매뉴얼 손잡이가 실제로 그래서 편집기를
      // 0 으로 접고 왼쪽 끝에 붙었다. 거리로 재면 손잡이가 어디에 있든 맞는다.
      const travelled = side === 'right' ? start.x - clientX : clientX - start.x
      onChange(clampWidth(start.width + travelled, start.available))
    },
    [onChange, side],
  )

  useEffect(() => {
    function onPointerMove(event: PointerEvent) {
      if (!grip.current) return
      // 드래그 중 텍스트가 선택되면 화면이 파랗게 물든다.
      event.preventDefault()
      move(event.clientX)
    }
    function onPointerUp() {
      grip.current = null
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
        const handle = event.currentTarget
        grip.current = {
          x: event.clientX,
          width,
          available: availableFor(handle, width),
        }
        document.body.classList.add('resizing')
        handle.setPointerCapture?.(event.pointerId)
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
        onChange(
          clampWidth(width + signed, availableFor(event.currentTarget, width)),
        )
      }}
    />
  )
}
