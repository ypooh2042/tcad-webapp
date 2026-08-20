/**
 * 잡 상태 폴링.
 *
 * 시뮬레이션은 몇 초에서 몇 분까지 걸린다. 끝났는데도 계속 물으면 홈서버에
 * 불필요한 부하가 쌓이고, 화면을 떠난 뒤에도 타이머가 남으면 누수가 된다.
 */
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useJob } from './useJob'
import type { JobDetail } from '../../api/types'

function detail(overrides: Partial<JobDetail> = {}): JobDetail {
  return {
    id: 1,
    status: 'queued',
    kind: 'suprem',
    source_revision_id: 1,
    source_path: 'a.in',
    created_at: '2026-08-12T12:00:00+00:00',
    log: null,
    log_truncated: false,
    exit_code: null,
    elapsed_seconds: null,
    progress: null,
    artifacts: [],
    ...overrides,
  }
}

// vi.mock 은 파일 맨 위로 끌어올려지므로, 목이 참조하는 값도 함께 올려야 한다.
const { get } = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('../../api/endpoints', () => ({ jobs: { get } }))

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  get.mockReset()
  get.mockResolvedValue(detail())
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('폴링', () => {
  it('잡 id 가 없으면 아무것도 하지 않는다', () => {
    renderHook(() => useJob(null))

    expect(get).not.toHaveBeenCalled()
  })

  it('즉시 한 번 가져온다', async () => {
    const { result } = renderHook(() => useJob(1))

    await waitFor(() => expect(result.current.job?.id).toBe(1))
  })

  it('끝나지 않은 잡은 계속 확인한다', async () => {
    renderHook(() => useJob(1))
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1))

    await vi.advanceTimersByTimeAsync(3000)

    expect(get.mock.calls.length).toBeGreaterThan(1)
  })

  it('끝난 잡은 더 이상 확인하지 않는다', async () => {
    get.mockResolvedValue(detail({ status: 'succeeded' }))
    renderHook(() => useJob(1))
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1))

    await vi.advanceTimersByTimeAsync(10_000)

    expect(get).toHaveBeenCalledTimes(1)
  })

  it('화면을 떠나면 타이머를 정리한다', async () => {
    const { unmount } = renderHook(() => useJob(1))
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1))

    unmount()
    await vi.advanceTimersByTimeAsync(10_000)

    expect(get).toHaveBeenCalledTimes(1)
  })

  it('오류가 나도 폴링을 멈추지 않는다', async () => {
    // 워커가 재시작 중이면 잠깐 실패할 수 있다. 한 번 실패했다고 화면이
    // 영영 갱신되지 않으면 안 된다.
    get.mockRejectedValueOnce(new Error('일시적 실패'))
    renderHook(() => useJob(1))
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1))

    await vi.advanceTimersByTimeAsync(3000)

    expect(get.mock.calls.length).toBeGreaterThan(1)
  })

  it('오류를 화면에 알린다', async () => {
    get.mockRejectedValue(new Error('연결 실패'))
    const { result } = renderHook(() => useJob(1))

    await waitFor(() => expect(result.current.error).not.toBeNull())
  })
})
