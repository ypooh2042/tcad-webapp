/**
 * 관리자 화면.
 *
 * 가장 중요한 것은 **평문 코드를 놓치지 않게 하는 것**이다. 서버는 해시만
 * 저장하므로 발급 응답에서만 볼 수 있다. 모르고 화면을 닫으면 재발급밖에
 * 방법이 없다.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminPanel } from './AdminPanel'

const { admin } = vi.hoisted(() => ({
  admin: { issueInvite: vi.fn(), listInvites: vi.fn(), revokeInvite: vi.fn() },
}))
vi.mock('../../api/endpoints', () => ({ admin }))

const FUTURE = new Date(Date.now() + 7 * 86_400_000).toISOString()
const PAST = new Date(Date.now() - 86_400_000).toISOString()

function summary(overrides = {}) {
  return {
    id: 1,
    expires_at: FUTURE,
    max_uses: 1,
    used_count: 0,
    revoked: false,
    usable: true,
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  admin.listInvites.mockResolvedValue([])
  admin.issueInvite.mockResolvedValue({
    id: 9,
    code: 'SUPER-SECRET-CODE',
    expires_at: FUTURE,
    max_uses: 1,
  })
  admin.revokeInvite.mockResolvedValue(null)
  Object.assign(navigator, {
    clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
  })
})

describe('발급', () => {
  it('기본값은 1회용 7일이다', async () => {
    render(<AdminPanel onClose={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: '발급' }))

    await waitFor(() => expect(admin.issueInvite).toHaveBeenCalledWith(1, 7))
  })

  it('사용 횟수와 기간을 바꿔 발급한다', async () => {
    render(<AdminPanel onClose={vi.fn()} />)

    await userEvent.clear(screen.getByLabelText('사용 횟수'))
    await userEvent.type(screen.getByLabelText('사용 횟수'), '3')
    await userEvent.clear(screen.getByLabelText('유효 기간(일)'))
    await userEvent.type(screen.getByLabelText('유효 기간(일)'), '30')
    await userEvent.click(screen.getByRole('button', { name: '발급' }))

    await waitFor(() => expect(admin.issueInvite).toHaveBeenCalledWith(3, 30))
  })

  it('발급한 코드를 보여준다', async () => {
    render(<AdminPanel onClose={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: '발급' }))

    expect(await screen.findByText('SUPER-SECRET-CODE')).toBeInTheDocument()
  })

  it('다시 볼 수 없다는 사실을 알린다', async () => {
    // 이 경고가 없으면 사용자는 나중에 목록에서 찾을 수 있다고 생각한다.
    render(<AdminPanel onClose={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: '발급' }))

    expect(await screen.findByText(/다시 확인할 수 없습니다/)).toBeInTheDocument()
  })

  it('복사 버튼이 클립보드에 넣는다', async () => {
    render(<AdminPanel onClose={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: '발급' }))

    await userEvent.click(await screen.findByRole('button', { name: '복사' }))

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('SUPER-SECRET-CODE')
    expect(await screen.findByRole('button', { name: '복사됨' })).toBeInTheDocument()
  })

  it('클립보드가 막혀도 코드는 화면에 남는다', async () => {
    vi.mocked(navigator.clipboard.writeText).mockRejectedValue(new Error('거부'))
    render(<AdminPanel onClose={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: '발급' }))

    await userEvent.click(await screen.findByRole('button', { name: '복사' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/복사하지 못했습니다/)
    expect(screen.getByText('SUPER-SECRET-CODE')).toBeInTheDocument()
  })

  it('발급 실패는 이유를 보여준다', async () => {
    const { ApiError } = await import('../../api/client')
    admin.issueInvite.mockRejectedValue(new ApiError(403, '권한이 없습니다', null))
    render(<AdminPanel onClose={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: '발급' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('권한이 없습니다')
  })
})

describe('목록', () => {
  it('사용 현황을 보여준다', async () => {
    admin.listInvites.mockResolvedValue([summary({ used_count: 1, max_uses: 3 })])

    render(<AdminPanel onClose={vi.fn()} />)

    expect(await screen.findByText('1/3')).toBeInTheDocument()
  })

  it.each([
    [{ revoked: true, usable: false }, '회수됨'],
    [{ used_count: 1, max_uses: 1, usable: false }, '모두 사용'],
    [{ expires_at: PAST, usable: false }, '기한 지남'],
    [{}, '사용 가능'],
  ])('상태를 구분해 보여준다: %o', async (overrides, label) => {
    admin.listInvites.mockResolvedValue([summary(overrides)])

    render(<AdminPanel onClose={vi.fn()} />)

    // 헤더에도 비슷한 낱말이 있으므로 본문 행에서만 찾는다.
    const table = await screen.findByRole('table')
    const body = within(table).getAllByRole('rowgroup')[1]!
    expect(within(body).getByText(label)).toBeInTheDocument()
  })

  it('발급하면 목록을 다시 읽는다', async () => {
    render(<AdminPanel onClose={vi.fn()} />)
    await waitFor(() => expect(admin.listInvites).toHaveBeenCalledTimes(1))

    await userEvent.click(screen.getByRole('button', { name: '발급' }))

    await waitFor(() => expect(admin.listInvites).toHaveBeenCalledTimes(2))
  })
})

describe('회수', () => {
  it('회수를 요청한다', async () => {
    admin.listInvites.mockResolvedValue([summary({ id: 42 })])
    render(<AdminPanel onClose={vi.fn()} />)

    await userEvent.click(await screen.findByRole('button', { name: '회수' }))

    await waitFor(() => expect(admin.revokeInvite).toHaveBeenCalledWith(42))
  })

  it('이미 회수된 것에는 버튼이 없다', async () => {
    admin.listInvites.mockResolvedValue([summary({ revoked: true })])
    render(<AdminPanel onClose={vi.fn()} />)
    await screen.findByText('회수됨')

    expect(screen.queryByRole('button', { name: '회수' })).not.toBeInTheDocument()
  })

  it('방금 발급한 코드를 회수하면 화면에서도 지운다', async () => {
    // 남겨 두면 이미 못 쓰는 코드를 그대로 전달하게 된다.
    render(<AdminPanel onClose={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: '발급' }))
    await screen.findByText('SUPER-SECRET-CODE')

    // 발급분이 목록에 보이도록 갱신 결과를 바꾼다.
    admin.listInvites.mockResolvedValue([summary({ id: 9 })])
    await userEvent.click(screen.getByRole('button', { name: '발급' }))
    const table = await screen.findByRole('table')

    await userEvent.click(within(table).getByRole('button', { name: '회수' }))

    await waitFor(() =>
      expect(screen.queryByText('SUPER-SECRET-CODE')).not.toBeInTheDocument(),
    )
  })
})

describe('닫기', () => {
  it('닫기를 알린다', async () => {
    const onClose = vi.fn()
    render(<AdminPanel onClose={onClose} />)

    await userEvent.click(screen.getByRole('button', { name: '닫기' }))

    expect(onClose).toHaveBeenCalled()
  })
})

describe('숫자 칸을 비웠을 때', () => {
  // `Number('')` 은 0 이다. 칸을 지우는 순간 상태가 0 이 되고, 그대로 발급을
  // 누르면 서버의 `ge=1` 에 걸려 422 가 온다. 사용자는 값을 바꾸려고 지웠을
  // 뿐인데 "요청이 실패했습니다" 를 본다.
  it('사용 횟수를 지웠다가 다시 칠 수 있다', async () => {
    render(<AdminPanel onClose={vi.fn()} />)

    const input = await screen.findByLabelText('사용 횟수')
    await userEvent.clear(input)
    await userEvent.type(input, '5')

    expect(input).toHaveValue(5)
  })

  it('비운 채로 발급하면 서버로 0 을 보내지 않는다', async () => {
    render(<AdminPanel onClose={vi.fn()} />)

    await userEvent.clear(await screen.findByLabelText('사용 횟수'))
    await userEvent.click(screen.getByRole('button', { name: '발급' }))

    // 보내더라도 서버가 받아 주는 값이어야 한다. 0 이나 NaN 은 422 다.
    if (admin.issueInvite.mock.calls.length > 0) {
      const [maxUses] = admin.issueInvite.mock.calls.at(-1)!
      expect(maxUses).toBeGreaterThanOrEqual(1)
    }
  })

  it('유효 기간도 지웠다가 다시 칠 수 있다', async () => {
    render(<AdminPanel onClose={vi.fn()} />)

    const input = await screen.findByLabelText('유효 기간(일)')
    await userEvent.clear(input)
    await userEvent.type(input, '30')

    expect(input).toHaveValue(30)
  })

  it('비운 채로 발급하면 유효 기간도 1 이상이다', async () => {
    render(<AdminPanel onClose={vi.fn()} />)

    await userEvent.clear(await screen.findByLabelText('유효 기간(일)'))
    await userEvent.click(screen.getByRole('button', { name: '발급' }))

    if (admin.issueInvite.mock.calls.length > 0) {
      const [, validDays] = admin.issueInvite.mock.calls.at(-1)!
      expect(validDays).toBeGreaterThanOrEqual(1)
    }
  })
})
