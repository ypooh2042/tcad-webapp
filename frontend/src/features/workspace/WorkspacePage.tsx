/**
 * 작업 화면: 프로젝트 목록 + 편집기 + 실행 결과.
 *
 * 저장과 실행을 분리한다. 실행은 "저장된 최신 리비전"을 돌리므로, 편집 중인
 * 내용과 방금 돌린 내용이 다를 수 있다. 그 차이를 감추면 사용자는 고친 줄이
 * 반영됐다고 믿는다.
 */
import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../../api/client'
import { projects as projectApi } from '../../api/endpoints'
import type { Project } from '../../api/types'
import { useAuth } from '../auth/AuthContext'
import { AdminPanel } from '../admin/AdminPanel'
import { DocsPanel } from '../docs/DocsPanel'
import { SupremEditor } from '../editor/SupremEditor'
import { JobPanel } from '../jobs/JobPanel'

const STARTER_SOURCE = `# 1차원 보론 확산 예제
line x loc = 0    spacing = 0.02 tag = top
line x loc = 2.0  spacing = 0.25 tag = bottom
region silicon xlo = top xhi = bottom
bound exposed xlo = top xhi = top

init boron conc = 1.0e14
deposit oxide thick = 0.075
implant boron dose = 3e14 energy = 70 pearson

structure outfile = result.str
`

export function WorkspacePage() {
  const { user, logout, clear } = useAuth()
  const [projects, setProjects] = useState<Project[]>([])
  const [active, setActive] = useState<Project | null>(null)
  const [source, setSource] = useState(STARTER_SOURCE)
  const [jobId, setJobId] = useState<number | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)
  const [showAdmin, setShowAdmin] = useState(false)
  const [showDocs, setShowDocs] = useState(false)
  const [cursorCommand, setCursorCommand] = useState<string | null>(null)

  const report = useCallback(
    (error: unknown) => {
      if (error instanceof ApiError) {
        if (error.status === 401) clear()
        setMessage(error.message)
        return
      }
      setMessage('알 수 없는 오류입니다')
    },
    [clear],
  )

  useEffect(() => {
    projectApi
      .list()
      .then((list) => {
        setProjects(list)
        setActive((current) => current ?? list[0] ?? null)
      })
      .catch(report)
  }, [report])

  async function createProject() {
    const name = window.prompt('프로젝트 이름')
    if (!name) return
    try {
      const project = await projectApi.create(name)
      setProjects((list) => [project, ...list])
      setActive(project)
      setDirty(true)
    } catch (error) {
      report(error)
    }
  }

  const save = useCallback(async () => {
    if (!active) {
      setMessage('먼저 프로젝트를 만들어 주세요')
      return
    }
    try {
      const revision = await projectApi.saveSource(active.id, source)
      setDirty(false)
      setMessage(`리비전 ${revision.revision} 저장됨`)
    } catch (error) {
      report(error)
    }
  }, [active, source, report])

  async function run() {
    if (!active) return
    // 편집 중인 내용은 아직 서버에 없다. 저장하지 않고 돌리면 이전 리비전이
    // 돌아가서, 방금 고친 줄이 반영되지 않은 결과를 보게 된다.
    if (dirty) await save()
    try {
      const job = await projectApi.submit(active.id)
      setJobId(job.id)
      setMessage(null)
    } catch (error) {
      report(error)
    }
  }

  return (
    <div className="workspace">
      <header>
        <strong>TCAD</strong>
        <nav>
          {projects.map((project) => (
            <button
              key={project.id}
              className={project.id === active?.id ? 'tab active' : 'tab'}
              onClick={() => setActive(project)}
            >
              {project.name}
            </button>
          ))}
          <button className="tab" onClick={createProject}>
            + 새 프로젝트
          </button>
        </nav>
        <div className="spacer" />
        <span className="muted">{user?.email}</span>
        {/* 관리자에게만 보인다. 일반 사용자가 눌러 봐야 서버가 403 을 준다. */}
        {user?.role === 'admin' && (
          <button className="link" onClick={() => setShowAdmin(true)}>
            관리자
          </button>
        )}
        <button className="link" onClick={() => void logout()}>
          로그아웃
        </button>
      </header>

      <div className="toolbar">
        <button onClick={() => void save()} disabled={!active}>
          저장 {dirty && <span className="dot" aria-label="저장되지 않음" />}
        </button>
        <button className="primary" onClick={() => void run()} disabled={!active}>
          실행
        </button>
        <button onClick={() => setShowDocs((open) => !open)}>
          {showDocs ? '매뉴얼 닫기' : '매뉴얼'}
        </button>
        {message && <span className="message">{message}</span>}
      </div>

      {showAdmin && <AdminPanel onClose={() => setShowAdmin(false)} />}

      <main className={showDocs ? "with-docs" : ""}>
        <section className="editor">
          <SupremEditor
            value={source}
            onChange={(next) => {
              setSource(next)
              setDirty(true)
            }}
            onSave={() => void save()}
            onCommandChange={setCursorCommand}
          />
        </section>
        {showDocs && (
          <DocsPanel command={cursorCommand} onClose={() => setShowDocs(false)} />
        )}
        <aside>
          <JobPanel jobId={jobId} />
        </aside>
      </main>
    </div>
  )
}
