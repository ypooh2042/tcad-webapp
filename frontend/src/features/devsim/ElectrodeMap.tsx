/**
 * 단면 위에서 계면을 고르고 전극에 붙인다.
 *
 * 전극 지정이 여기서 일어난다. 목록에서 하는 것은 전극을 만들고·지우고·이름을
 * 붙이는 것까지고, **어느 계면이 어느 전극인지는 그림 위에서 정한다** — 이름만
 * 보고 고르면 그게 구조의 어디인지 알 수 없다.
 *
 * 커서를 계면 가까이 가져가면 배경이 어두워지고 그 계면만 밝게 남는다. 누르면
 * 어느 전극에 붙일지 고르는 쪽지가 뜬다.
 *
 * 그리기와 좌표 되돌리기가 `surfaceGeometry` 하나를 같이 쓴다. 각자 같은 수식을
 * 따로 갖고 있으면 여백을 고칠 때 한쪽만 고쳐져 짚은 자리와 그린 자리가 어긋난다.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import type { DevSimInterface, SurfaceResponse } from '../../api/types'
import { solidOf } from '../../plot/materials'
import { surfaceGeometry } from '../../plot/surfaceGeometry'
import { nearestInterface, type HitCandidate } from './hitTest'

/** 계면으로 칠 커서 거리(px). 늘 무언가 잡히면 화면이 계속 어두워진다. */
const HOVER_RADIUS = 14

/** 아직 전극에 안 붙은 계면의 색. */
const UNASSIGNED = '#8892a0'

export interface ElectrodeChip {
  label: string
  color: string
}

interface Props {
  surface: SurfaceResponse
  interfaces: DevSimInterface[]
  /** 계면 열쇠 → 전극 이름. 안 붙었으면 없다. */
  owners: Record<string, string>
  electrodes: ElectrodeChip[]
  onAssign: (key: string, label: string) => void
  onUnassign: (key: string) => void
  /** 이 계면을 담을 전극을 새로 만든다. */
  onCreate: (key: string) => void
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

interface Picked {
  key: string
  x: number
  y: number
}

export function ElectrodeMap({
  surface,
  interfaces,
  owners,
  electrodes,
  onAssign,
  onUnassign,
  onCreate,
  height = 360,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const [hovered, setHovered] = useState<string | null>(null)
  const [picked, setPicked] = useState<Picked | null>(null)
  const [width, setWidth] = useState(0)

  const colorOf = useMemo(() => {
    const byLabel = new Map(electrodes.map((one) => [one.label, one.color]))
    return (key: string) => byLabel.get(owners[key] ?? '') ?? UNASSIGNED
  }, [electrodes, owners])

  // 히트테스트에 쓸 화면 좌표. 그리기와 같은 변환을 쓴다.
  const candidates: HitCandidate[] = useMemo(() => {
    if (width === 0 || surface.x.length === 0) return []
    const geometry = surfaceGeometry(boundsOf(surface), width, height)
    return interfaces.map((one) => ({
      key: one.key,
      segments: one.segments.map(([x0, y0, x1, y1]) => [
        geometry.px(x0),
        geometry.py(y0),
        geometry.px(x1),
        geometry.py(y1),
      ]),
    }))
  }, [interfaces, surface, width, height])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const context = canvas.getContext('2d')
    if (!context) return

    const ratio = window.devicePixelRatio || 1
    const shown = canvas.clientWidth
    // 크기가 0 이면 그리지 않는다. 화면이 숨겨져 있을 때 그렇게 된다.
    if (shown === 0 || height === 0) return
    if (shown !== width) setWidth(shown)

    canvas.width = Math.max(1, Math.round(shown * ratio))
    canvas.height = Math.max(1, Math.round(height * ratio))
    context.setTransform(ratio, 0, 0, ratio, 0, 0)
    context.clearRect(0, 0, shown, height)
    if (surface.x.length === 0) return

    const geometry = surfaceGeometry(boundsOf(surface), shown, height)

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

    const strokeInterface = (one: DevSimInterface, bold: boolean) => {
      context.strokeStyle = colorOf(one.key)
      context.lineWidth = bold ? 5 : 2.5
      context.lineCap = 'round'
      context.beginPath()
      for (const [x0, y0, x1, y1] of one.segments) {
        context.moveTo(geometry.px(x0), geometry.py(y0))
        context.lineTo(geometry.px(x1), geometry.py(y1))
      }
      context.stroke()
    }

    for (const one of interfaces) {
      if (one.key === hovered) continue
      strokeInterface(one, false)
    }

    const focus = interfaces.find((one) => one.key === hovered)
    if (focus) {
      // 배경을 덮어 어둡게 한 뒤 그 위에 짚은 계면만 다시 그린다. 순서가 반대면
      // 밝힌 계면까지 같이 어두워진다.
      context.fillStyle = 'rgba(10, 12, 16, 0.62)'
      context.fillRect(0, 0, shown, height)
      strokeInterface(focus, true)

      const owner = owners[focus.key]
      const text = owner ? `${focus.key} → ${owner}` : `${focus.key} · 전극 없음`
      context.font =
        '12px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace'
      const padding = 6
      const textWidth = context.measureText(text).width
      let left = geometry.px((focus.extent.x_min + focus.extent.x_max) / 2)
      left = Math.min(
        Math.max(left - textWidth / 2 - padding, 2),
        shown - textWidth - padding * 2 - 2,
      )
      const top = Math.max(2, geometry.py(focus.extent.y_min) - 26)
      context.fillStyle = 'rgba(0, 0, 0, 0.8)'
      context.fillRect(left, top, textWidth + padding * 2, 20)
      context.fillStyle = '#ffffff'
      context.textBaseline = 'middle'
      context.fillText(text, left + padding, top + 10)
    }
  }, [surface, interfaces, owners, hovered, height, width, colorOf])

  function at(event: React.PointerEvent<HTMLCanvasElement>) {
    const rect = event.currentTarget.getBoundingClientRect()
    return { x: event.clientX - rect.left, y: event.clientY - rect.top }
  }

  return (
    <div className="electrode-map-wrap">
      <canvas
        ref={canvasRef}
        className="electrode-map"
        style={{ width: '100%', height }}
        onPointerMove={(event) => {
          const point = at(event)
          setHovered(nearestInterface(point.x, point.y, candidates, HOVER_RADIUS))
        }}
        onPointerLeave={() => setHovered(null)}
        onClick={(event) => {
          const rect = event.currentTarget.getBoundingClientRect()
          const x = event.clientX - rect.left
          const y = event.clientY - rect.top
          const key = nearestInterface(x, y, candidates, HOVER_RADIUS)
          setPicked(key ? { key, x, y } : null)
        }}
        role="img"
        aria-label="단면 — 계면을 눌러 전극에 붙입니다"
      />

      {picked ? (
        <div
          className="interface-popover"
          style={{ left: picked.x, top: picked.y }}
          role="dialog"
          aria-label={`${picked.key} 계면`}
        >
          <div className="popover-head">
            <strong>{picked.key}</strong>
            <span className="origin">
              {interfaces.find((one) => one.key === picked.key)?.origin ===
              'backside'
                ? '뒷면 경계'
                : '금속 접촉'}
            </span>
            <button
              type="button"
              className="ghost"
              aria-label="닫기"
              onClick={() => setPicked(null)}
            >
              ×
            </button>
          </div>
          <p className="hint">어느 전극에 붙일까요?</p>
          <ul className="popover-choices">
            {electrodes.map((electrode) => {
              const mine = owners[picked.key] === electrode.label
              return (
                <li key={electrode.label}>
                  <button
                    type="button"
                    className={mine ? 'on' : ''}
                    onClick={() => {
                      onAssign(picked.key, electrode.label)
                      setPicked(null)
                    }}
                  >
                    <span
                      className="swatch"
                      style={{ background: electrode.color }}
                      aria-hidden="true"
                    />
                    {electrode.label}
                    {mine ? ' ✓' : ''}
                  </button>
                </li>
              )
            })}
          </ul>
          <div className="popover-actions">
            <button
              type="button"
              onClick={() => {
                onCreate(picked.key)
                setPicked(null)
              }}
            >
              새 전극으로
            </button>
            {owners[picked.key] ? (
              <button
                type="button"
                className="ghost"
                onClick={() => {
                  onUnassign(picked.key)
                  setPicked(null)
                }}
              >
                떼어 내기
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  )
}
