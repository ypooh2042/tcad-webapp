/**
 * 패널 폭을 기억한다.
 *
 * 매번 다시 끌어야 하면 조절 기능을 안 쓰게 된다. localStorage 를 쓰되, 읽기가
 * 실패해도(사생활 보호 모드 등) 앱이 죽지 않게 기본값으로 넘어간다.
 */
import { useCallback, useEffect, useState } from 'react'
import { clampWidth } from '../../components/Splitter'

export function usePanelWidth(key: string, initial: number) {
  const [width, setWidth] = useState(() => {
    try {
      const stored = Number(localStorage.getItem(key))
      // 저장값이 지금 창에 안 맞을 수 있다(다른 화면에서 저장했거나 창을 줄였거나).
      return stored > 0 ? clampWidth(stored, window.innerWidth) : initial
    } catch {
      return initial
    }
  })

  useEffect(() => {
    try {
      localStorage.setItem(key, String(width))
    } catch {
      // 저장하지 못해도 이번 세션 동안은 조절이 유지된다.
    }
  }, [key, width])

  return [width, useCallback((next: number) => setWidth(next), [])] as const
}
