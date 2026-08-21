/**
 * 도는 해석을 멈추는 버튼.
 *
 * 재메시가 잡 작업디렉토리에서 돌지 않던 시절, 서버 쪽에서는 중단이 재메시
 * 구간(실측 12초, 큰 구조는 더) 동안 먹지 않았다. 그쪽은 백엔드에서 막았고,
 * 여기서는 버튼이 **도는 동안에만** 뜨는지를 본다 — 끝난 해석에 남아 있으면
 * 사용자가 눌러 보고 아무 일도 안 일어나는 것을 겪는다.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { JobDetail } from '../../api/types'
import { RunResult } from './RunResult'

function job(status: JobDetail['status']): JobDetail {
  return {
    id: 7,
    kind: 'devsim',
    status,
    source: '',
    created_at: '2026-08-21T00:00:00Z',
    elapsed_seconds: 3,
    artifacts: [],
  } as unknown as JobDetail
}

describe('해석 중단', () => {
  it('도는 동안에는 버튼이 있다', () => {
    render(<RunResult job={job('running')} onCancel={vi.fn()} />)
    expect(screen.getByRole('button', { name: '중단' })).toBeInTheDocument()
  })

  it('큐에서 기다리는 동안에도 멈출 수 있다', () => {
    // 큐에 있을 때가 오히려 멈추기 쉬운 때다. 여기서 버튼이 없으면 사용자는
    // 시작될 때까지 기다렸다 눌러야 한다.
    render(<RunResult job={job('queued')} onCancel={vi.fn()} />)
    expect(screen.getByRole('button', { name: '중단' })).toBeInTheDocument()
  })

  it('끝난 뒤에는 버튼이 없다', () => {
    render(<RunResult job={job('succeeded')} onCancel={vi.fn()} />)
    expect(screen.queryByRole('button', { name: '중단' })).toBeNull()
  })

  it('이미 멈춘 해석에는 버튼이 없다', () => {
    render(<RunResult job={job('cancelled')} onCancel={vi.fn()} />)
    expect(screen.queryByRole('button', { name: '중단' })).toBeNull()
  })

  it('누르면 한 번 알린다', async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    render(<RunResult job={job('running')} onCancel={onCancel} />)

    await user.click(screen.getByRole('button', { name: '중단' }))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('멈출 방법을 안 주면 버튼도 없다', () => {
    render(<RunResult job={job('running')} />)
    expect(screen.queryByRole('button', { name: '중단' })).toBeNull()
  })
})
