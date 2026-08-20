import { Suspense, lazy, useCallback, useState } from 'react'
import { AuthProvider, useAuth } from './features/auth/AuthContext'
import { LoginPage } from './features/auth/LoginPage'
import type { Handoff } from './features/devsim/DevSimPage'
import './App.css'

// 편집기(Monaco)를 포함한 작업 화면 묶음이 약 3.2MB 다(빌드 출력 실측). 로그인 화면에서는 쓰지 않으므로 로그인한 뒤에
// 받는다. 그러지 않으면 첫 화면이 뜨기까지 그만큼을 기다려야 한다.
const WorkspacePage = lazy(() =>
  import('./features/workspace/WorkspacePage').then((module) => ({
    default: module.WorkspacePage,
  })),
)

// 소자 해석 화면도 따로 받는다. 공정만 쓰는 사용자가 그 묶음까지 기다릴 이유가 없다.
const DevSimPage = lazy(() =>
  import('./features/devsim/DevSimPage').then((module) => ({
    default: module.DevSimPage,
  })),
)

type View = 'process' | 'device'

function Gate() {
  const { user, loading } = useAuth()
  const [view, setView] = useState<View>('process')
  // 공정 결과에서 "소자 해석" 을 누르면 구조를 들고 화면을 넘어간다.
  const [handoff, setHandoff] = useState<Handoff | null>(null)

  const handOff = useCallback((jobId: number, sequence: number) => {
    setHandoff({ jobId, sequence })
    setView('device')
  }, [])

  // 확인이 끝나기 전에 로그인 화면을 띄우면, 이미 로그인한 사용자에게도
  // 한 번 깜빡이며 보인다.
  if (loading) return <div className="centered muted">불러오는 중…</div>
  if (!user) return <LoginPage />

  const tabs = (
    <nav className="view-tabs" role="tablist" aria-label="화면">
      <button
        type="button"
        role="tab"
        aria-selected={view === 'process'}
        onClick={() => setView('process')}
      >
        공정
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={view === 'device'}
        onClick={() => setView('device')}
      >
        소자 해석
      </button>
    </nav>
  )

  return (
    <>
      {/*
        공정 화면은 **내려놓지 않는다.** 편집 중인 내용과 Monaco 모델이 살아
        있어야 소자 해석을 보고 돌아왔을 때 하던 자리가 그대로다.

        Suspense 경계를 화면마다 따로 둔다. 하나로 묶으면 소자 해석 묶음을
        받는 동안 이 경계가 통째로 대기 화면으로 바뀌면서 편집기가 떨어져
        나가고, Monaco 가 "InstantiationService has been disposed" 로 죽는다
        (브라우저 시험에서 앱 전체가 하얗게 되는 것으로 드러났다).
      */}
      <div hidden={view !== 'process'} className="view">
        <Suspense fallback={<div className="centered muted">편집기 준비 중…</div>}>
          <WorkspacePage viewTabs={tabs} onAnalyse={handOff} />
        </Suspense>
      </div>
      {view === 'device' ? (
        <div className="view">
          <header className="app-header">{tabs}</header>
          <Suspense
            fallback={<div className="centered muted">소자 해석 준비 중…</div>}
          >
            <DevSimPage handoff={handoff} onHandoffUsed={() => setHandoff(null)} />
          </Suspense>
        </div>
      ) : null}
    </>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  )
}
