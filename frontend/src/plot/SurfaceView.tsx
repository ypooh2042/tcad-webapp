/**
 * 2D 단면 (canvas).
 *
 * 삼각형 수천 개를 그린다. SVG 로 하면 DOM 노드가 그만큼 생겨 컷 라인을 끄는
 * 동안 브라우저가 버티지 못한다.
 *
 * 값은 삼각형마다 정점 3개가 따로 온다. 계면 정점은 물질에 따라 값이 다르기
 * 때문이다. 여기서는 세 값의 평균으로 삼각형을 단색 칠한다 — 메시가 촘촘해서
 * 육안으로는 연속으로 보이고, 정점 보간을 흉내 내려다 계면을 뭉개는 것보다 낫다.
 *
 * y 축이 깊이다. 화면 아래로 갈수록 깊어지게 그린다.
 */
import { useEffect, useRef } from 'react'
import type { SurfaceResponse } from '../api/types'
import { colorFor, toLogDomain } from './scale'

interface Props {
  surface: SurfaceResponse
  /** 세로 컷 위치(µm). 없으면 표시하지 않는다. */
  cutX: number | null
  onPickCut: (x: number) => void
}

export function SurfaceView({ surface, cutX, onPickCut }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const context = canvas?.getContext('2d')
    if (!canvas || !context) return

    const xMin = Math.min(...surface.x)
    const xMax = Math.max(...surface.x)
    const yMin = Math.min(...surface.y)
    const yMax = Math.max(...surface.y)

    // 흐릿하게 보이지 않도록 물리 픽셀 밀도에 맞춘다.
    const ratio = window.devicePixelRatio || 1
    const width = canvas.clientWidth
    const height = canvas.clientHeight
    canvas.width = width * ratio
    canvas.height = height * ratio
    context.setTransform(ratio, 0, 0, ratio, 0, 0)
    context.clearRect(0, 0, width, height)

    // 세로/가로 비율을 유지한다. 늘려 그리면 접합 깊이가 실제와 달라 보인다.
    const scale = Math.min(width / (xMax - xMin), height / (yMax - yMin))
    const offsetX = (width - (xMax - xMin) * scale) / 2
    const offsetY = (height - (yMax - yMin) * scale) / 2
    const px = (x: number) => offsetX + (x - xMin) * scale
    const py = (y: number) => offsetY + (y - yMin) * scale

    const domain = toLogDomain(surface.values.flat())

    surface.triangles.forEach((triangle, index) => {
      const triple = surface.values[index]!
      const mean = (triple[0] + triple[1] + triple[2]) / 3

      context.beginPath()
      const [a, b, c] = triangle
      context.moveTo(px(surface.x[a]!), py(surface.y[a]!))
      context.lineTo(px(surface.x[b]!), py(surface.y[b]!))
      context.lineTo(px(surface.x[c]!), py(surface.y[c]!))
      context.closePath()

      const color = colorFor(mean, domain.min, domain.max)
      context.fillStyle = color
      // 삼각형 사이에 배경색 실선이 비쳐 격자무늬로 보이는 것을 막는다.
      context.strokeStyle = color
      context.lineWidth = 0.5
      context.fill()
      context.stroke()
    })

    if (cutX !== null) {
      context.beginPath()
      context.moveTo(px(cutX), 0)
      context.lineTo(px(cutX), height)
      context.strokeStyle = '#ffffff'
      context.lineWidth = 1.5
      context.setLineDash([4, 4])
      context.stroke()
      context.setLineDash([])
    }
  }, [surface, cutX])

  function pick(event: React.MouseEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()

    const xMin = Math.min(...surface.x)
    const xMax = Math.max(...surface.x)
    const yMin = Math.min(...surface.y)
    const yMax = Math.max(...surface.y)
    const scale = Math.min(
      canvas.clientWidth / (xMax - xMin),
      canvas.clientHeight / (yMax - yMin),
    )
    const offsetX = (canvas.clientWidth - (xMax - xMin) * scale) / 2

    const modelX = (event.clientX - rect.left - offsetX) / scale + xMin
    // 도메인 밖을 찍으면 빈 프로파일이 나온다. 가장자리로 잘라 준다.
    onPickCut(Math.min(xMax, Math.max(xMin, modelX)))
  }

  return (
    <canvas
      ref={canvasRef}
      className="surface"
      onClick={pick}
      aria-label={`${surface.quantity} 단면. 클릭하면 그 위치의 깊이 프로파일을 봅니다.`}
    />
  )
}
