/**
 * 2D 단면 (canvas).
 *
 * 삼각형 수천 개를 그린다. SVG 로 하면 DOM 노드가 그만큼 생겨 컷 라인을 끄는
 * 동안 브라우저가 버티지 못한다.
 *
 * 값은 삼각형마다 정점 3개가 따로 온다. 계면 정점은 물질에 따라 값이 다르기
 * 때문이다.
 *
 * 한동안 세 값의 **산술평균으로 단색** 칠했다. 두 가지가 틀렸다.
 *   - 도핑은 자릿수를 오간다. (1e5 + 1e5 + 1e20)/3 은 3.3e19 로 사실상
 *     최댓값이라, 도핑된 정점 하나에 닿기만 해도 삼각형 전체가 최고 농도로
 *     칠해졌다. 실측: 증착 산화막 안의 저농도 영역이 통째로 메워져 사라졌다.
 *   - 단색이라 격자가 성긴 곳에서는 삼각형 무늬가 그대로 드러나, 데이터에
 *     없는 조각남을 만들어 냈다.
 *
 * 그래서 로그 공간에서 정점 보간을 하고(shading.ts), 캔버스 2D 에 그런 기능이
 * 없으므로 삼각형을 잘게 나눠 흉내 낸다.
 *
 * **두 가지 보기가 있다.** 서버가 무엇을 보냈는지로 구분한다:
 *     quantity 가 있으면 → 값을 색으로 칠한다(컨투어).
 *     quantity 가 비어 있으면 → 재질로 칠하고 범례를 붙인다.
 * 재질 보기는 서버가 요소를 하나도 버리지 않으므로 층이 빠지지 않는다.
 *
 * y 축이 깊이다. 화면 아래로 갈수록 깊어지게 그린다.
 *
 * 좌표 변환은 surfaceGeometry 하나에 모아 두고 그리기와 클릭이 같이 쓴다.
 * 따로 두면 여백을 넣을 때 한쪽만 고쳐져 클릭한 자리와 컷 선이 어긋난다.
 */
import { useEffect, useRef } from 'react'
import type { SurfaceResponse } from '../api/types'
import { solidOf } from './materials'
import { colorForLog, NON_POSITIVE_COLOR, toLogDomain } from './scale'
import { logOf, shadeTriangle, subdivisionDepth, type Corners } from './shading'
import { surfaceGeometry } from './surfaceGeometry'

interface Props {
  surface: SurfaceResponse
  /** 세로 컷 위치(µm). 없으면 표시하지 않는다. */
  cutX: number | null
  onPickCut: (x: number) => void
  /** 삼각형 격자를 위에 얹을지. 기본은 끔. */
  showMesh?: boolean
}

const AXIS = '#8b929e'

/**
 * 격자선 색.
 *
 * 반투명 어두운 선이라 재질 판(밝은 색)과 컨투어 배색 양쪽에서 읽힌다.
 * 불투명한 검정은 촘촘한 메시에서 그림을 덮어 버린다.
 */
export const MESH_COLOR = 'rgba(18, 22, 28, 0.5)'

function boundsOf(surface: SurfaceResponse) {
  return {
    xMin: Math.min(...surface.x),
    xMax: Math.max(...surface.x),
    yMin: Math.min(...surface.y),
    yMax: Math.max(...surface.y),
  }
}

export function SurfaceView({
  surface,
  cutX,
  onPickCut,
  showMesh = false,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  /**
   * 삼각형만 미리 그려 둔 층.
   *
   * 컷 선은 클릭할 때마다 바뀌는데, 그때마다 삼각형 수만 개를 다시 칠하면
   * 눈에 띄게 버벅인다. 삼각형은 구조·격자표시·캔버스 크기가 그대로면
   * 바뀌지 않으므로 한 번 그려 두고 얹기만 한다.
   */
  const layerRef = useRef<{
    canvas: HTMLCanvasElement
    surface: SurfaceResponse
    key: string
  } | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const context = canvas?.getContext('2d')
    if (!canvas || !context) return

    // 흐릿하게 보이지 않도록 물리 픽셀 밀도에 맞춘다.
    const ratio = window.devicePixelRatio || 1
    const width = canvas.clientWidth
    const height = canvas.clientHeight
    // **크기가 0 이면 아무것도 하지 않는다.** 화면이 숨겨져 있거나 패널이 아직
    // 자리를 못 잡았을 때 그렇게 된다. 그대로 진행하면 아래 drawImage 가
    // "width or height of 0" 로 던지고, 오류 경계가 없으므로 React 트리 전체가
    // 무너진다(최상위 화면 전환을 붙이자마자 실제로 그렇게 됐다).
    if (width === 0 || height === 0) return
    canvas.width = width * ratio
    canvas.height = height * ratio
    context.setTransform(ratio, 0, 0, ratio, 0, 0)
    context.clearRect(0, 0, width, height)

    const g = surfaceGeometry(boundsOf(surface), width, height)
    // 값이 없으면 재질 보기다. 값 기준으로 색을 고르려 들면 아무것도 안 그린다.
    const byMaterial = surface.values.length === 0
    const domain = byMaterial
      ? { min: 0, max: 0 }
      : toLogDomain(surface.values.flat())

    // 재질 보기는 삼각형 안에서 색이 변하지 않으므로 나눌 이유가 없다.
    const depth = byMaterial ? 0 : subdivisionDepth(surface.triangles.length)
    // 배색 전체 폭의 1/80 보다 좁은 차이는 화면에서 구분되지 않는다. 그보다
    // 고른 삼각형은 나누지 않아, 균일한 구간이 넓은 실제 구조에서 비용이
    // 실제로 색이 변하는 곳에만 든다.
    const tolerance =
      byMaterial || !(domain.min > 0) || !(domain.max > 0)
        ? Number.POSITIVE_INFINITY
        : (Math.log10(domain.max) - Math.log10(domain.min)) / 80

    const key = `${width}x${height}@${ratio}|${showMesh}`
    const cached = layerRef.current
    const reuse =
      cached !== null && cached.surface === surface && cached.key === key

    const layer = reuse
      ? cached.canvas
      : (() => {
          const made = document.createElement('canvas')
          made.width = canvas.width
          made.height = canvas.height
          return made
        })()
    const lc = reuse ? null : layer.getContext('2d')
    if (!reuse && !lc) return
    lc?.setTransform(ratio, 0, 0, ratio, 0, 0)

    const paint = (s: Corners, color: string) => {
      const context = lc!
      context.beginPath()
      context.moveTo(s.ax, s.ay)
      context.lineTo(s.bx, s.by)
      context.lineTo(s.cx, s.cy)
      context.closePath()
      context.fillStyle = color
      // 조각 사이에 배경색 실선이 비쳐 격자무늬로 보이는 것을 막는다.
      context.strokeStyle = color
      context.lineWidth = 0.5
      context.fill()
      context.stroke()
    }

    if (!reuse) surface.triangles.forEach((triangle, index) => {
      const [a, b, c] = triangle
      const corners: Corners = {
        ax: g.px(surface.x[a]!),
        ay: g.py(surface.y[a]!),
        bx: g.px(surface.x[b]!),
        by: g.py(surface.y[b]!),
        cx: g.px(surface.x[c]!),
        cy: g.py(surface.y[c]!),
      }

      if (byMaterial) {
        paint(corners, solidOf(surface.materials[index] ?? ''))
        return
      }

      const triple = surface.values[index]!
      // 세 값이 모두 로그 축에 못 올라가면 그 자리를 따로 표시한다. 배색의 맨
      // 아래로 칠하면 "농도가 낮다"로 잘못 읽힌다.
      if (triple.every((value) => !(value > 0))) {
        paint(corners, NON_POSITIVE_COLOR)
        return
      }

      const logs = [logOf(triple[0]!), logOf(triple[1]!), logOf(triple[2]!)]
      for (const shard of shadeTriangle(corners, logs, depth, tolerance)) {
        paint(shard, colorForLog(shard.logValue, domain.min, domain.max))
      }
    })

    // 격자는 삼각형을 **다 칠한 뒤에** 얹는다. 먼저 그리면 덮인다.
    //
    // 변을 삼각형마다 따로 그리지 않고 경로 하나에 모아 한 번만 stroke 한다.
    // 따로 그리면 이웃과 공유하는 변이 두 번 칠해져 반투명 선이 얼룩덜룩해지고,
    // 삼각형 수천 개에서는 호출 수만큼 느려진다.
    if (!reuse && showMesh && lc) {
      lc.beginPath()
      for (const [a, b, c] of surface.triangles) {
        lc.moveTo(g.px(surface.x[a]!), g.py(surface.y[a]!))
        lc.lineTo(g.px(surface.x[b]!), g.py(surface.y[b]!))
        lc.lineTo(g.px(surface.x[c]!), g.py(surface.y[c]!))
        lc.closePath()
      }
      lc.strokeStyle = MESH_COLOR
      lc.lineWidth = 0.5
      lc.stroke()
    }

    if (!reuse) layerRef.current = { canvas: layer, surface, key }
    // 미리 그려 둔 삼각형 층을 얹는다. 버퍼는 물리 픽셀 크기이고 이 컨텍스트는
    // 논리 좌표계이므로 크기를 지정해 그린다.
    context.drawImage(layer, 0, 0, width, height)

    // 눈금은 그림 위에 얹는다. 먼저 그리면 삼각형에 덮인다.
    context.font = '10px ui-sans-serif, system-ui, sans-serif'
    context.fillStyle = AXIS
    context.strokeStyle = AXIS
    context.lineWidth = 1

    context.textAlign = 'center'
    context.textBaseline = 'top'
    for (const tick of g.xTicks) {
      const x = g.px(tick)
      context.beginPath()
      context.moveTo(x, g.top + g.plotHeight)
      context.lineTo(x, g.top + g.plotHeight + 4)
      context.stroke()
      context.fillText(g.formatX(tick), x, g.top + g.plotHeight + 6)
    }

    context.textAlign = 'right'
    context.textBaseline = 'middle'
    for (const tick of g.yTicks) {
      const y = g.py(tick)
      context.beginPath()
      context.moveTo(g.left - 4, y)
      context.lineTo(g.left, y)
      context.stroke()
      context.fillText(g.formatY(tick), g.left - 6, y)
    }

    // 어느 축이 무엇인지. 둘 다 µm 라 숫자만 보면 구분할 수 없다.
    // 눈금 숫자보다 한 줄 아래에 둔다 — 같은 줄에 놓으면 첫 눈금과 겹친다.
    context.textAlign = 'center'
    context.textBaseline = 'top'
    context.fillText(
      'x (µm)',
      g.left + g.plotWidth / 2,
      g.top + g.plotHeight + 19,
    )
    context.save()
    context.translate(10, g.top)
    context.rotate(-Math.PI / 2)
    context.textAlign = 'right'
    context.fillText('깊이 (µm)', 0, 0)
    context.restore()

    // 재질 범례. 색만 칠하면 무엇이 무엇인지 알 수 없다. 오른쪽 위에 작게 둔다
    // — 구조는 보통 위쪽(표면)에 층이 몰려 있지만 오른쪽 끝은 비어 있다.
    if (byMaterial) {
      const seen = [...new Set(surface.materials)]
      const box = 9
      const gap = 14
      const pad = 6
      const right = g.left + g.plotWidth - 6

      // 글자 폭을 재서 판을 깐다. 배경 없이 얹으면 구조 위에 겹친 글자가
      // 묻힌다 — 회색 글씨가 amber 산화막 위에 놓여 첫 글자가 사라졌다(실측).
      const textWidth = Math.max(
        ...seen.map((material) => context.measureText(material).width),
      )
      const panelWidth = textWidth + box + 5 + pad * 2
      const panelHeight = seen.length * gap + pad * 2 - (gap - box) + 2

      context.fillStyle = 'rgba(22, 24, 29, 0.82)'
      context.fillRect(right - panelWidth + pad, g.top, panelWidth, panelHeight)

      seen.forEach((material, index) => {
        const y = g.top + pad + index * gap
        context.fillStyle = solidOf(material)
        context.fillRect(right - box, y, box, box)
        context.fillStyle = AXIS
        context.textAlign = 'right'
        context.textBaseline = 'top'
        context.fillText(material, right - box - 5, y)
      })
    }

    if (cutX !== null) {
      context.beginPath()
      context.moveTo(g.px(cutX), g.top)
      context.lineTo(g.px(cutX), g.top + g.plotHeight)
      context.strokeStyle = '#ffffff'
      context.lineWidth = 1.5
      context.setLineDash([4, 4])
      context.stroke()
      context.setLineDash([])
    }
  // showMesh 를 빠뜨리면 체크박스를 눌러도 다시 그리지 않는다. 단위 테스트는
  // 매번 새로 렌더해서 이걸 못 잡는다 — E2E 가 잡았다.
  }, [surface, cutX, showMesh])

  function pick(event: React.MouseEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()

    const g = surfaceGeometry(
      boundsOf(surface),
      canvas.clientWidth,
      canvas.clientHeight,
    )
    // 도메인 밖을 찍으면 빈 프로파일이 나온다. 가장자리로 잘라 준다.
    onPickCut(g.clampX(g.unpx(event.clientX - rect.left)))
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
