/**
 * 로그인 화면과 세션 상태.
 *
 * 세션 쿠키는 httponly 라 JS 가 볼 수 없다. "로그인했는가"는 서버에 물어야만
 * 알 수 있고, 그 확인이 끝나기 전에 로그인 화면을 띄우면 이미 로그인한
 * 사용자에게도 한 번 깜빡이며 보인다.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from './AuthContext'
import { LoginPage } from './LoginPage'

const { auth } = vi.hoisted(() => ({
  auth: {
    me: vi.fn(),
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  },
}))

vi.mock('../../api/endpoints', () => ({ auth }))

const USER = { id: 1, email: 'a@example.com', role: 'user' }

beforeEach(() => {
  vi.clearAllMocks()
  auth.me.mockRejectedValue(new Error('로그인 안 됨'))
  auth.login.mockResolvedValue(USER)
  auth.register.mockResolvedValue(USER)
  auth.logout.mockResolvedValue(null)
})

function Probe() {
  const { user, loading } = useAuth()
  if (loading) return <span>확인 중</span>
  return <span>{user ? user.email : '비로그인'}</span>
}

function renderWithAuth(children: React.ReactNode) {
  return render(<AuthProvider>{children}</AuthProvider>)
}

describe('세션 확인', () => {
  it('처음에는 확인 중이다', () => {
    renderWithAuth(<Probe />)

    expect(screen.getByText('확인 중')).toBeInTheDocument()
  })

  it('세션이 있으면 그 사용자로 시작한다', async () => {
    auth.me.mockResolvedValue(USER)

    renderWithAuth(<Probe />)

    expect(await screen.findByText('a@example.com')).toBeInTheDocument()
  })

  it('세션이 없으면 비로그인으로 시작한다', async () => {
    renderWithAuth(<Probe />)

    expect(await screen.findByText('비로그인')).toBeInTheDocument()
  })
})

describe('로그인', () => {
  it('입력한 자격 증명으로 로그인한다', async () => {
    renderWithAuth(<LoginPage />)

    await userEvent.type(screen.getByLabelText('이메일'), 'a@example.com')
    await userEvent.type(screen.getByLabelText('비밀번호'), 'correct-horse-battery')
    await userEvent.click(screen.getByRole('button', { name: '로그인' }))

    await waitFor(() =>
      expect(auth.login).toHaveBeenCalledWith(
        'a@example.com',
        'correct-horse-battery',
      ),
    )
  })

  it('실패하면 서버가 준 메시지를 보여준다', async () => {
    const { ApiError } = await import('../../api/client')
    auth.login.mockRejectedValue(
      new ApiError(503, '동시 접속자가 많습니다. 잠시 후 다시 시도해 주세요', null),
    )
    renderWithAuth(<LoginPage />)

    await userEvent.type(screen.getByLabelText('이메일'), 'a@example.com')
    await userEvent.type(screen.getByLabelText('비밀번호'), 'correct-horse-battery')
    await userEvent.click(screen.getByRole('button', { name: '로그인' }))

    // 503 은 정원이 찼다는 뜻이다. 자격 증명 오류로 오해하게 두면 안 된다.
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '동시 접속자가 많습니다',
    )
  })

  it('가입으로 전환할 수 있다', async () => {
    renderWithAuth(<LoginPage />)

    await userEvent.click(screen.getByRole('button', { name: /가입/ }))

    expect(
      screen.getByRole('button', { name: '가입하고 시작' }),
    ).toBeInTheDocument()
  })

  it('가입하면 곧바로 로그인까지 한다', async () => {
    renderWithAuth(<LoginPage />)
    await userEvent.click(screen.getByRole('button', { name: /계정이 없으신가요/ }))

    await userEvent.type(screen.getByLabelText('이메일'), 'new@example.com')
    await userEvent.type(screen.getByLabelText('비밀번호'), 'correct-horse-battery')
    await userEvent.type(screen.getByLabelText('초대 코드'), 'invite-xyz')
    await userEvent.click(screen.getByRole('button', { name: '가입하고 시작' }))

    await waitFor(() =>
      expect(auth.register).toHaveBeenCalledWith(
        'new@example.com',
        'correct-horse-battery',
        'invite-xyz',
      ),
    )
    expect(auth.login).toHaveBeenCalled()
  })

  it('로그인 화면에는 초대 코드 칸이 없다', async () => {
    renderWithAuth(<LoginPage />)

    expect(screen.queryByLabelText('초대 코드')).not.toBeInTheDocument()
  })

  it('가입으로 바꾸면 초대 코드 칸이 나온다', async () => {
    renderWithAuth(<LoginPage />)

    await userEvent.click(screen.getByRole('button', { name: /계정이 없으신가요/ }))

    expect(screen.getByLabelText('초대 코드')).toBeRequired()
  })

  it('비밀번호에 최소 길이를 요구한다', async () => {
    renderWithAuth(<LoginPage />)

    expect(screen.getByLabelText('비밀번호')).toHaveAttribute('minLength', '12')
  })
})

describe('로그아웃', () => {
  function LogoutProbe() {
    const { user, logout } = useAuth()
    return (
      <>
        <span>{user ? user.email : '비로그인'}</span>
        <button onClick={() => void logout()}>로그아웃</button>
      </>
    )
  }

  it('서버가 거절해도 화면은 로그아웃 상태가 된다', async () => {
    // 남겨 두면 사용자는 로그아웃했다고 믿는데 세션이 살아 있다.
    auth.me.mockResolvedValue(USER)
    auth.logout.mockRejectedValue(new Error('네트워크 오류'))
    renderWithAuth(<LogoutProbe />)
    await screen.findByText('a@example.com')

    await userEvent.click(screen.getByRole('button', { name: '로그아웃' }))

    expect(await screen.findByText('비로그인')).toBeInTheDocument()
  })
})
