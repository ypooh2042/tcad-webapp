import { Suspense, lazy } from 'react'
import { AuthProvider, useAuth } from './features/auth/AuthContext'
import { LoginPage } from './features/auth/LoginPage'
import './App.css'

// 편집기(Monaco)를 포함한 작업 화면 묶음이 약 3.2MB 다(빌드 출력 실측). 로그인 화면에서는 쓰지 않으므로 로그인한 뒤에
// 받는다. 그러지 않으면 첫 화면이 뜨기까지 그만큼을 기다려야 한다.
const WorkspacePage = lazy(() =>
  import('./features/workspace/WorkspacePage').then((module) => ({
    default: module.WorkspacePage,
  })),
)

function Gate() {
  const { user, loading } = useAuth()

  // 확인이 끝나기 전에 로그인 화면을 띄우면, 이미 로그인한 사용자에게도
  // 한 번 깜빡이며 보인다.
  if (loading) return <div className="centered muted">불러오는 중…</div>
  if (!user) return <LoginPage />

  return (
    <Suspense fallback={<div className="centered muted">편집기 준비 중…</div>}>
      <WorkspacePage />
    </Suspense>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  )
}
