/**
 * 구조 그림 위에 전극을 얹어 보여주고, 화면에서 경계를 찍게 한다.
 *
 * 그리기와 좌표 되돌리기가 `surfaceGeometry` 하나를 같이 쓴다. 각자 같은 수식을
 * 따로 갖고 있으면 여백을 고칠 때 한쪽만 고쳐져 찍은 자리와 그린 자리가 어긋난다
 * (플롯 쪽이 같은 이유로 그렇게 되어 있다).
 */
import { useEffect, useRef, useState } from 'react'
import type { SurfaceResponse } from '../../api/types'
import { solidOf } from '../../plot/materials'
import { surfaceGeometry } from '../../plot/surfaceGeometry'
import { CURVE_COLORS } from './IvChart'

export interface MappedElectrode {
  label: string
  segments: number[][]
  active: boolean
}

export interface PickedBox {
  x_min: number
  x_max: number
  y_min: number
  y_max: number
}

interface Props {
  surface: SurfaceResponse
  electrodes: MappedElectrode[]
  /** 켜면 끌어서 사각형을 그릴 수 있다. 놓으면 그 범위를 돌려준다. */
  picking: boolean
  onPick?: (box: PickedBox) => void
  height?: number
}

function boundsOf(surface: SurfaceResponse) {
  return {
    xMin: Math.min(...surface.x),
    xMax: Math.max(...surface.x),
    yMin: Math.min(...surface.y),
    yMax: Math.max(...surface.y),
  }
}

/** 찍었다고 볼 최소 크기(px). 이보다 작으면 그냥 클릭한 것이다. */
const MIN_DRAG_PX = 4

export function ElectrodeMap({
  surface,
  electrodes,
  picking,
  onPick,
  height = 320,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const [drag, setDrag] = useState<{
    x0: number
    y0: number
    x1: number
    y1: number
  } | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const context = canvas.getContext('2d')
    if (!context) return

    const ratio = window.devicePixelRatio || 1
    const width = canvas.clientWidth
    canvas.width = Math.max(1, Math.round(width * ratio))
    canvas.height = Math.max(1, Math.round(height * ratio))
    context.setTransform(ratio, 0, 0, ratio, 0, 0)
    context.clearRect(0, 0, width, height)

    if (surface.x.length === 0) return
    const geometry = surfaceGeometry(boundsOf(surface), width, height)

    // 재질 단면. 값은 그리지 않는다 — 여기서 볼 것은 어디에 무엇이 붙어 있는지다.
    surface.triangles.forEach((triangle, index) => {
      context.fillStyle = solidOf(surface.materials[index])
      context.beginPath()
      triangle.forEach((vertex, at) => {
        const x = geometry.px(surface.x[vertex])
        const y = geometry.py(surface.y[vertex])
        if (at === 0) context.moveTo(x, y)
        else context.lineTo(x, y)
      })
      context.closePath()
      context.fill()
    })

    // 전극. 굵게 덧그어 어디가 접촉면인지 한눈에 보이게 한다.
    electrodes.forEach((electrode, index) => {
      context.strokeStyle = CURVE_COLORS[index % CURVE_COLORS.length]
      context.lineWidth = electrode.active ? 4 : 2
      context.globalAlpha = electrode.active ? 1 : 0.45
      context.lineCap = 'round'
      context.beginPath()
      for (const [x0, y0, x1, y1] of electrode.segments) {
        context.moveTo(geometry.px(x0), geometry.py(y0))
        context.lineTo(geometry.px(x1), geometry.py(y1))
      }
      context.stroke()
    })
    context.globalAlpha = 1

    if (drag) {
      context.strokeStyle = '#ffffff'
      context.setLineDash([4, 3])
      context.lineWidth = 1
      context.strokeRect(
        Math.min(drag.x0, drag.x1),
        Math.min(drag.y0, drag.y1),
        Math.abs(drag.x1 - drag.x0),
        Math.abs(drag.y1 - drag.y0),
      )
      context.setLineDash([])
    }
  }, [surface, electrodes, drag, height])

  function at(event: React.PointerEvent<HTMLCanvasElement>) {
    const rect = event.currentTarget.getBoundingClientRect()
    return { x: event.clientX - rect.left, y: event.clientY - rect.top }
  }

  function start(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!picking) return
    const point = at(event)
    event.currentTarget.setPointerCapture(event.pointerId)
    setDrag({ x0: point.x, y0: point.y, x1: point.x, y1: point.y })
  }

  function move(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!drag) return
    const point = at(event)
    setDrag({ ...drag, x1: point.x, y1: point.y })
  }

  function finish(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!drag) return
    const canvas = event.currentTarget
    const width = canvas.clientWidth
    setDrag(null)
    if (
      Math.abs(drag.x1 - drag.x0) < MIN_DRAG_PX ||
      Math.abs(drag.y1 - drag.y0) < MIN_DRAG_PX
    ) {
      // 살짝 흔들린 클릭이다. 점 하나짜리 전극을 만들면 접촉 변이 없어 거절된다.
      return
    }
    const geometry = surfaceGeometry(boundsOf(surface), width, height)
    const xs = [geometry.unpx(drag.x0), geometry.unpx(drag.x1)].map(
      geometry.clampX,
    )
    const ys = [geometry.unpy(drag.y0), geometry.unpy(drag.y1)].map(
      geometry.clampY,
    )
    onPick?.({
      x_min: Math.min(...xs),
      x_max: Math.max(...xs),
      y_min: Math.min(...ys),
      y_max: Math.max(...ys),
    })
  }

  return (
    <canvas
      ref={canvasRef}
      className={`electrode-map${picking ? ' picking' : ''}`}
      style={{ width: '100%', height }}
      onPointerDown={start}
      onPointerMove={move}
      onPointerUp={finish}
      onPointerCancel={() => setDrag(null)}
      role="img"
      aria-label="전극 지도"
    />
  )
}
