/**
 * 접속 현황 폴링.
 *
 * 정원이 몇 명이고 지금 몇 명이 쓰는지. 503 을 받고 나서야 아는 것과, 미리
 * 보이는 것은 다르다.
 */
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { occupancyLabel, occupancyTitle, useOccupancy } from './useOccupancy'

const { occupancy } = vi.hoisted(() => ({ occupancy: vi.fn() }))
vi.mock('../../api/endpoints', () => ({ auth: { occupancy } }))

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  occupancy.mockReset()
  occupancy.mockResolvedValue({ occupied: 2, capacity: 5, admins: 0 })
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('접속 현황', () => {
  it('바로 한 번 가져온다', async () => {
    const { result } = renderHook(() => useOccupancy())

    await waitFor(() => expect(result.current?.occupied).toBe(2))
  })

  it('주기적으로 다시 확인한다', async () => {
    renderHook(() => useOccupancy())
    await waitFor(() => expect(occupancy).toHaveBeenCalledTimes(1))

    await vi.advanceTimersByTimeAsync(60_000)

    expect(occupancy.mock.calls.length).toBeGreaterThan(1)
  })

  it('실패해도 마지막으로 안 값을 남긴다', async () => {
    const { result } = renderHook(() => useOccupancy())
    await waitFor(() => expect(result.current?.occupied).toBe(2))

    occupancy.mockRejectedValue(new Error('연결 실패'))
    await vi.advanceTimersByTimeAsync(60_000)

    // 잠깐 끊겼다고 숫자가 사라지면 화면이 깜빡인다.
    expect(result.current?.occupied).toBe(2)
  })

  it('화면을 떠나면 폴링을 멈춘다', async () => {
    const { unmount } = renderHook(() => useOccupancy())
    await waitFor(() => expect(occupancy).toHaveBeenCalledTimes(1))

    unmount()
    const seen = occupancy.mock.calls.length
    await vi.advanceTimersByTimeAsync(120_000)

    expect(occupancy).toHaveBeenCalledTimes(seen)
  })
})

describe('표기', () => {
  it('몇 명 중 몇 명인지 보여준다', () => {
    expect(occupancyLabel({ occupied: 2, capacity: 5, admins: 0 })).toBe('접속 2/5')
  })

  it('설명에 정원과 현재 인원을 풀어 쓴다', () => {
    const title = occupancyTitle({ occupied: 5, capacity: 5, admins: 0 })

    expect(title).toContain('5명 중 5명')
    expect(title).not.toContain('관리자')
  })

  it('관리자가 있으면 정원 밖이라는 것을 밝힌다', () => {
    // 숫자만 보면 "1/5" 인데 세 명이 쓰고 있는 상황을 설명할 길이 없다.
    const title = occupancyTitle({ occupied: 1, capacity: 5, admins: 2 })

    expect(title).toContain('관리자 2명')
    expect(title).toContain('정원과 무관')
  })
})
