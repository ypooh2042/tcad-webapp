/**
 * 작업 화면: 열어 둔 파일 탭 + 편집기 + 실행 결과.
 *
 * 위쪽 탭은 **"내가 연 파일"** 이지 작업공간 전체가 아니다. 파일을 만들고
 * 지우고 이름 바꾸는 일은 파일 브라우저에서 하고, 여기서는 열어 둔 것만
 * 오간다. 탭을 닫아도 파일은 남는다.
 *
 * 저장과 실행을 분리한다. 실행은 서버에 저장된 파일을 돌리므로, 편집 중인
 * 내용과 방금 돌린 내용이 다를 수 있다. 그 차이를 감추면 사용자는 고친 줄이
 * 반영됐다고 믿는다 — 그래서 실행 전에 저장한다.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../../api/client'
import { files as fileApi } from '../../api/endpoints'
import { FileBrowser } from '../files/FileBrowser'
import { tabLabels } from '../files/tabLabels'
import { useAuth } from '../auth/AuthContext'
import { AdminPanel } from '../admin/AdminPanel'
import { DocsPanel } from '../docs/DocsPanel'
import { SupremEditor } from '../editor/SupremEditor'
import { JobPanel } from '../jobs/JobPanel'
import { SPLITTER_WIDTH, Splitter } from '../../components/Splitter'
import { usePanelWidth } from './usePanelWidth'
import { fitPanels, useViewportWidth } from './panelLayout'

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
  //: 열어 둔 파일 경로. 순서는 사용자가 연 순서다 — 정렬하면 탭이 제멋대로
  //  움직인다.
  const [openPaths, setOpenPaths] = useState<string[]>([])
  const [active, setActive] = useState<string | null>(null)
  const [showFiles, setShowFiles] = useState(false)
  const [source, setSource] = useState(STARTER_SOURCE)
  const [jobId, setJobId] = useState<number | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)
  //: 사용자가 편집기를 건드린 횟수. 소스를 읽어오는 동안 타이핑했다면 그
  //: 결과로 덮어쓰면 안 된다 — 새 프로젝트를 만들고 바로 치기 시작하면
  //: 뒤늦게 도착한 응답이 방금 친 것을 지운다(E2E 가 잡았다).
  const edits = useRef(0)
  const [showAdmin, setShowAdmin] = useState(false)
  const [showDocs, setShowDocs] = useState(false)
  const [cursorCommand, setCursorCommand] = useState<string | null>(null)
  const [resultWidth, setResultWidth] = usePanelWidth('tcad.width.result', 400)
  const [docsWidth, setDocsWidth] = usePanelWidth('tcad.width.docs', 360)
  const viewport = useViewportWidth()

  // 저장된 폭이 지금 창에 맞는다는 보장이 없다. 창을 줄였거나, 매뉴얼을 함께
  // 열었거나, 예전 버전이 과한 값을 저장해 뒀을 수 있다. 그리는 폭은 늘 다시
  // 맞춘다 — 저장된 값 자체는 건드리지 않아 창을 넓히면 되돌아온다.
  const [docsFit, resultFit] = showDocs
    ? fitPanels([docsWidth, resultWidth], viewport, SPLITTER_WIDTH * 2)
    : [docsWidth, fitPanels([resultWidth], viewport, SPLITTER_WIDTH)[0]]

  const labels = tabLabels(openPaths)

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

  /** 탭을 전환한다. 저장하지 않은 편집이 있으면 먼저 묻는다. */
  const switchTo = useCallback(
    (path: string) => {
      if (path === active) return
      // 편집 중이던 내용은 서버에 없다. 말없이 덮어쓰면 사용자는 방금 쓴 것을
      // 잃고 이유도 모른다.
      if (dirty && !window.confirm('저장하지 않은 변경이 있습니다. 버리고 이동할까요?')) {
        return
      }
      setActive(path)
    },
    [active, dirty],
  )

  /** 브라우저에서 고른 파일을 탭에 붙이고 연다. */
  function openFile(path: string) {
    setOpenPaths((current) =>
      // 같은 파일을 두 번 열어도 탭은 하나다.
      current.includes(path) ? current : [...current, path],
    )
    setActive(path)
    setShowFiles(false)
  }

  /** 탭에서만 뺀다. **파일은 지우지 않는다.** */
  function closeTab(path: string) {
    setOpenPaths((current) => {
      const remaining = current.filter((item) => item !== path)
      setActive((currentActive) =>
        currentActive === path ? (remaining[0] ?? null) : currentActive,
      )
      // 닫은 파일의 결과가 남으면 다음 파일의 것으로 오해한다.
      if (path === active) setJobId(null)
      return remaining
    })
  }

  // 연 파일의 내용을 편집기에 채운다. 이게 없으면 탭을 눌러도 이전 파일의
  // 내용이 그대로 남아 엉뚱한 소스를 고치게 된다.
  useEffect(() => {
    if (!active) return
    let cancelled = false

    const startedAt = edits.current
    // 요청이 도는 동안 사용자가 쳤으면 그 입력을 살린다.
    const stale = () => cancelled || edits.current !== startedAt

    fileApi
      .read(active)
      .then((file) => {
        if (stale()) return
        setSource(file.content)
        setDirty(false)
        setMessage(null)
      })
      .catch((error) => {
        if (stale()) return
        report(error)
      })

    return () => {
      cancelled = true
    }
  }, [active, report])

  const save = useCallback(async () => {
    if (!active) {
      setMessage('먼저 파일을 열어 주세요')
      return
    }
    try {
      await fileApi.write(active, source)
      setDirty(false)
      setMessage('저장됨')
    } catch (error) {
      report(error)
    }
  }, [active, source, report])

  async function run() {
    if (!active) return
    // 편집 중인 내용은 아직 서버에 없다. 저장하지 않고 돌리면 예전 내용이
    // 돌아가서, 방금 고친 줄이 반영되지 않은 결과를 보게 된다.
    if (dirty) await save()
    try {
      const job = await fileApi.run(active)
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
        <nav role="tablist">
          {/* 탭 이름은 보통 파일 이름만. 다른 폴더에 같은 이름이 있을 때만
              구분될 만큼 경로를 붙인다. */}
          {openPaths.map((path, index) => (
            <span
              key={path}
              className={path === active ? 'tab active' : 'tab'}
            >
              <button
                role="tab"
                aria-selected={path === active}
                className="link"
                onClick={() => switchTo(path)}
              >
                {labels[index]}
              </button>
              {/* 탭에서만 뺀다. 파일은 그대로 남는다. */}
              <button
                className="link close"
                aria-label={`${labels[index]} 탭 닫기`}
                onClick={() => closeTab(path)}
              >
                ×
              </button>
            </span>
          ))}
        </nav>
        <button className="link" onClick={() => setShowFiles(true)}>
          파일 열기
        </button>
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

      {showFiles && (
        <FileBrowser onOpen={openFile} onClose={() => setShowFiles(false)} />
      )}

      {/* 폭은 인라인 스타일로 준다. 드래그 중에는 값이 계속 바뀌므로 CSS
          클래스로는 표현할 수 없다. */}
      <main
        className={showDocs ? 'with-docs' : ''}
        style={{
          gridTemplateColumns: showDocs
            ? `minmax(0, 1fr) auto ${docsFit}px auto ${resultFit}px`
            : `minmax(0, 1fr) auto ${resultFit}px`,
        }}
      >
        <section className="editor">
          <SupremEditor
            value={source}
            onChange={(next) => {
              edits.current += 1
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
              width={docsFit}
              onChange={setDocsWidth}
              label="매뉴얼 패널 크기"
            />
            <DocsPanel command={cursorCommand} onClose={() => setShowDocs(false)} />
          </>
        )}
        <Splitter
          width={resultFit}
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
