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
import { Splitter } from '../../components/Splitter'
import { usePanelWidth } from './usePanelWidth'

//: 새 프로젝트를 열면 이 소스가 들어 있다. **반드시 그대로 실행되어야 한다** —
//: 처음 들어온 사람이 가장 먼저 누르는 것이 실행 버튼이다.
//:
//: `mode one.dim` 이 없으면 SUPREM 은 2D 로 해석해서 y 격자와 ylo/yhi 를
//: 요구하고 "No mesh defined!" 로 끝난다. 실제로 그 상태로 배포했었다.
const STARTER_SOURCE = `# 1차원 보론 확산 예제
mode one.dim

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
  const [resultWidth, setResultWidth] = usePanelWidth('tcad.width.result', 400)
  const [docsWidth, setDocsWidth] = usePanelWidth('tcad.width.docs', 360)

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

  /** 프로젝트를 연다. 저장하지 않은 편집이 있으면 먼저 묻는다. */
  const openProject = useCallback(
    (project: Project) => {
      if (project.id === active?.id) return
      // 편집 중이던 내용은 서버에 없다. 말없이 덮어쓰면 사용자는 방금 쓴 것을
      // 잃고 이유도 모른다.
      if (dirty && !window.confirm('저장하지 않은 변경이 있습니다. 버리고 이동할까요?')) {
        return
      }
      setActive(project)
    },
    [active, dirty],
  )

  // 연 프로젝트의 저장된 소스를 편집기에 채운다. 이게 없으면 탭을 눌러도
  // 이전 프로젝트의 내용이 그대로 남아 엉뚱한 소스를 고치게 된다.
  useEffect(() => {
    if (!active) return
    let cancelled = false

    projectApi
      .latestSource(active.id)
      .then((revision) => {
        if (cancelled) return
        setSource(revision.source)
        setDirty(false)
        setMessage(null)
      })
      .catch((error) => {
        if (cancelled) return
        if (error instanceof ApiError && error.status === 404) {
          // 아직 한 번도 저장하지 않은 프로젝트다. 예제로 시작하게 둔다.
          setSource(STARTER_SOURCE)
          setDirty(true)
          setMessage(null)
          return
        }
        report(error)
      })

    return () => {
      cancelled = true
    }
  }, [active, report])

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
              onClick={() => openProject(project)}
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

      {/* 폭은 인라인 스타일로 준다. 드래그 중에는 값이 계속 바뀌므로 CSS
          클래스로는 표현할 수 없다. */}
      <main
        className={showDocs ? 'with-docs' : ''}
        style={{
          gridTemplateColumns: showDocs
            ? `minmax(0, 1fr) auto ${docsWidth}px auto ${resultWidth}px`
            : `minmax(0, 1fr) auto ${resultWidth}px`,
        }}
      >
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
          <>
            <Splitter
              width={docsWidth}
              onChange={setDocsWidth}
              label="매뉴얼 패널 크기"
            />
            <DocsPanel command={cursorCommand} onClose={() => setShowDocs(false)} />
          </>
        )}
        <Splitter
          width={resultWidth}
          onChange={setResultWidth}
          label="결과 패널 크기"
        />
        <aside>
          <JobPanel jobId={jobId} />
        </aside>
      </main>
    </div>
  )
}
