/**
 * 동시 접속 현황을 주기적으로 확인한다.
 *
 * 자주 볼 값이 아니다. 잡 상태(1.5초)와 달리 사람이 드나드는 빈도라, 30초면
 * 충분하고 홈서버를 두드릴 이유도 없다.
 */
import { useEffect, useState } from 'react'
import { auth } from '../../api/endpoints'
import type { Occupancy } from '../../api/types'

const POLL_INTERVAL_MS = 30_000

export function useOccupancy(): Occupancy | null {
  const [occupancy, setOccupancy] = useState<Occupancy | null>(null)

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined

    async function tick() {
      try {
        const next = await auth.occupancy()
        if (!cancelled) setOccupancy(next)
      } catch {
        // 잠깐 끊겼다고 숫자를 지우면 화면이 깜빡인다. 마지막으로 안 값을
        // 그대로 두고 다음 차례를 기다린다.
      }
      if (!cancelled) timer = setTimeout(tick, POLL_INTERVAL_MS)
    }

    void tick()

    return () => {
      cancelled = true
      if (timer !== undefined) clearTimeout(timer)
    }
  }, [])

  return occupancy
}

/** 헤더에 들어갈 짧은 표기. 자리가 몇 개 남았는지 한눈에 보이는 것이 목적이다. */
export function occupancyLabel(occupancy: Occupancy): string {
  return `접속 ${occupancy.occupied}/${occupancy.capacity}`
}

/**
 * 위 표기의 설명.
 *
 * 숫자만 보면 관리자가 빠져 있다는 것을 알 수 없다. "1/5" 인데 세 명이 쓰고
 * 있으면 숫자가 고장 난 것처럼 보인다.
 */
export function occupancyTitle(occupancy: Occupancy): string {
  const base = `동시 접속 정원 ${occupancy.capacity}명 중 ${occupancy.occupied}명이 접속 중입니다`
  if (occupancy.admins === 0) return `${base}.`
  return `${base}. 관리자 ${occupancy.admins}명은 정원과 무관하게 접속합니다.`
}
