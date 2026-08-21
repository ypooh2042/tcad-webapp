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
    exit_code: null,
    elapsed_seconds: null,
    progress: null,
    artifacts: [],
    ...overrides,
  }
}

// vi.mock 은 파일 맨 위로 끌어올려지므로, 목이 참조하는 값도 함께 올려야 한다.
const { get, console: getConsole } = vi.hoisted(() => ({
  get: vi.fn(),
  console: vi.fn(),
}))

vi.mock('../../api/endpoints', () => ({ jobs: { get, console: getConsole } }))

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  get.mockReset()
  get.mockResolvedValue(detail())
  getConsole.mockReset()
  getConsole.mockResolvedValue({ log: '출력', truncated: false })
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


describe('실행 출력은 따로 받는다', () => {
  it('도는 동안에는 받지 않는다', async () => {
    // 로그는 잡이 끝날 때 한 번 기록된다. 도는 중에 물어봐야 빈 값이고,
    // 폴링마다 부르면 로그를 상태 조회에 실었던 옛 문제로 되돌아간다.
    get.mockResolvedValue(detail({ status: 'running' }))
    const { result } = renderHook(() => useJob(1))

    await waitFor(() => expect(result.current.job?.status).toBe('running'))
    expect(getConsole).not.toHaveBeenCalled()
  })

  it('끝나면 한 번 받는다', async () => {
    get.mockResolvedValue(detail({ status: 'succeeded' }))
    const { result } = renderHook(() => useJob(1))

    await waitFor(() => expect(result.current.console?.log).toBe('출력'))
    expect(getConsole).toHaveBeenCalledTimes(1)
  })

  it('실패한 잡의 출력도 받는다', async () => {
    // 실패했을 때야말로 사용자가 로그를 본다.
    get.mockResolvedValue(detail({ status: 'failed' }))
    const { result } = renderHook(() => useJob(1))

    await waitFor(() => expect(result.current.console?.log).toBe('출력'))
  })

  it('잘렸다는 표시가 함께 온다', async () => {
    getConsole.mockResolvedValue({ log: '앞부분…', truncated: true })
    get.mockResolvedValue(detail({ status: 'succeeded' }))
    const { result } = renderHook(() => useJob(1))

    await waitFor(() => expect(result.current.console?.truncated).toBe(true))
  })

  it('출력을 못 받아도 상태는 그대로 둔다', async () => {
    // 로그는 곁다리다. 그것 때문에 "연결이 불안정" 이 뜨면 사용자는 잡이
    // 실패한 줄 안다.
    getConsole.mockRejectedValue(new Error('410'))
    get.mockResolvedValue(detail({ status: 'succeeded' }))
    const { result } = renderHook(() => useJob(1))

    await waitFor(() => expect(result.current.job?.status).toBe('succeeded'))
    expect(result.current.error).toBeNull()
  })

  it('잡이 바뀌면 앞의 출력을 보여주지 않는다', async () => {
    get.mockResolvedValue(detail({ status: 'succeeded' }))
    const { result, rerender } = renderHook(({ id }) => useJob(id), {
      initialProps: { id: 1 },
    })
    await waitFor(() => expect(result.current.console?.log).toBe('출력'))

    getConsole.mockResolvedValue({ log: '다른 출력', truncated: false })
    rerender({ id: 2 })

    await waitFor(() => expect(result.current.console?.log).toBe('다른 출력'))
  })
})
