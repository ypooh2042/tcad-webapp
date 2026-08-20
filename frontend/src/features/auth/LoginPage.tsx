import { useState, type FormEvent } from 'react'
import { ApiError } from '../../api/client'
import { useAuth } from './AuthContext'

export function LoginPage() {
  const { login, register } = useAuth()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await (mode === 'login'
        ? login(email, password)
        : register(email, password, inviteCode))
    } catch (caught) {
      // 503 은 동시 접속 정원이 찼다는 뜻이다. 자격 증명 문제로
      // 오해하지 않게 그대로 보여 준다.
      setError(
        caught instanceof ApiError ? caught.message : '알 수 없는 오류입니다',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="centered">
      <form className="card auth" onSubmit={submit}>
        <h1>TCAD</h1>
        <p className="muted">SUPREM-IV.GS 공정 시뮬레이션</p>

        <label htmlFor="email">이메일</label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />

        <label htmlFor="password">비밀번호</label>
        <input
          id="password"
          type="password"
          autoComplete={
            mode === 'login' ? 'current-password' : 'new-password'
          }
          required
          minLength={6}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />

        {mode === 'register' && (
          <>
            <label htmlFor="invite">초대 코드</label>
            <input
              id="invite"
              type="text"
              required
              autoComplete="off"
              value={inviteCode}
              onChange={(event) => setInviteCode(event.target.value)}
            />
            <p className="muted hint">
              관리자에게 받은 코드가 필요합니다.
            </p>
          </>
        )}

        {error && <p role="alert" className="error">{error}</p>}

        <button type="submit" disabled={busy}>
          {mode === 'login' ? '로그인' : '가입하고 시작'}
        </button>

        <button
          type="button"
          className="link"
          onClick={() => {
            setMode(mode === 'login' ? 'register' : 'login')
            setError(null)
          }}
        >
          {mode === 'login' ? '계정이 없으신가요? 가입' : '이미 계정이 있습니다'}
        </button>
      </form>
    </div>
  )
}
