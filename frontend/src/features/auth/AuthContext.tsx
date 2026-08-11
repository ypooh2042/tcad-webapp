/**
 * 로그인 상태.
 *
 * 세션은 httponly 쿠키라 JS 가 볼 수 없다. 그래서 "로그인했는가"는 서버에
 * 물어야만 알 수 있고, 여기서 그 답을 한 번만 받아 들고 있는다.
 *
 * 30분 유휴 시 서버가 세션을 만료시킨다. 그때 화면은 여전히 로그인 상태로
 * 보이므로, 어떤 요청이든 401 이 오면 즉시 로그아웃 상태로 되돌린다.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { ApiError } from '../../api/client'
import { auth } from '../../api/endpoints'
import type { User } from '../../api/types'

interface AuthState {
  user: User | null
  /** 최초 확인이 끝나기 전에는 로그인 화면을 띄우면 안 된다(깜빡임). */
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, inviteCode: string) => Promise<void>
  logout: () => Promise<void>
  /** 401 을 받은 쪽에서 부른다. */
  clear: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    auth
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  const clear = useCallback(() => setUser(null), [])

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      clear,
      login: async (email, password) => setUser(await auth.login(email, password)),
      register: async (email, password, inviteCode) => {
        await auth.register(email, password, inviteCode)
        setUser(await auth.login(email, password))
      },
      logout: async () => {
        // 서버가 거절해도 화면은 로그아웃 상태로 만든다. 남겨 두면 사용자는
        // 로그아웃했다고 믿는데 세션이 살아 있다.
        await auth.logout().catch(() => undefined)
        setUser(null)
      },
    }),
    [user, loading, clear],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext)
  if (!context) throw new Error('AuthProvider 안에서만 쓸 수 있습니다')
  return context
}

/** 세션 만료를 화면 전체에서 일관되게 처리한다. */
export function useSessionGuard() {
  const { clear } = useAuth()
  return useCallback(
    (error: unknown) => {
      if (error instanceof ApiError && error.status === 401) clear()
      throw error
    },
    [clear],
  )
}
