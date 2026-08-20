/**
 * 작업 화면: 열어 둔 파일 탭 + 편집기 + 실행 결과.
 *
 * 위쪽 탭은 **"내가 연 파일"** 이지 작업공간 전체가 아니다. 파일을 만들고
 * 지우고 이름 바꾸는 일은 파일 브라우저에서 하고, 여기서는 열어 둔 것만
 * 오간다. 탭을 닫아도 파일은 남는다.
 *
 * **탭을 옮길 때 저장을 묻지 않는다.** 고치던 내용은 버퍼에 그대로 남고,
 * 커서 자리까지 기억했다가 돌아온다. 저장은 곧 "실행 대상이 바뀐다"는 뜻이라
 * 잠깐 다른 파일을 들춰 보려고 시킬 일이 아니다. 규칙은 editorSession.ts 에,
 * 서버와 주고받는 일은 useEditorSession.ts 에 있다.
 *
 * 저장과 실행은 여전히 분리한다. 실행은 서버에 저장된 파일을 돌리므로,
 * 편집 중인 내용과 방금 돌린 내용이 다를 수 있다. 그 차이를 감추면 사용자는
 * 고친 줄이 반영됐다고 믿는다 — 그래서 실행 전에 저장한다.
 */
import { useCallback, useState } from 'react'
import { ApiError } from '../../api/client'
import { files as fileApi } from '../../api/endpoints'
import { FileBrowser } from '../files/FileBrowser'
import { tabLabels } from '../files/tabLabels'
import { useAuth } from '../auth/AuthContext'
import {
  occupancyLabel,
  occupancyTitle,
  useOccupancy,
} from '../auth/useOccupancy'
import { AdminPanel } from '../admin/AdminPanel'
import { DocsPanel } from '../docs/DocsPanel'
import { SupremEditor } from '../editor/SupremEditor'
import { JobPanel } from '../jobs/JobPanel'
import { SPLITTER_WIDTH, Splitter } from '../../components/Splitter'
import { usePanelWidth } from './usePanelWidth'
import { fitPanels, useViewportWidth } from './panelLayout'
import { activeBuffer, isDirty } from './editorSession'
import { useEditorSession } from './useEditorSession'

export function WorkspacePage() {
  const { user, logout, clear } = useAuth()
  const [showFiles, setShowFiles] = useState(false)
  const [jobId, setJobId] = useState<number | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [showAdmin, setShowAdmin] = useState(false)
  const [showDocs, setShowDocs] = useState(false)
  const [cursorCommand, setCursorCommand] = useState<string | null>(null)
  const [resultWidth, setResultWidth] = usePanelWidth('tcad.width.result', 400)
  const [docsWidth, setDocsWidth] = usePanelWidth('tcad.width.docs', 360)
  const viewport = useViewportWidth()
  //: 지금 몇 명이 쓰고 있는지. 정원이 차면 다음 사람이 못 들어오므로, 자리를
  //: 비워 줄지 판단하려면 들어와 있는 사람이 볼 수 있어야 한다.
  const occupancy = useOccupancy()

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

  const {
    session,
    restoring,
    open,
    close,
    switchTo,
    change,
    applySaved,
    setCursor,
    followRename,
  } = useEditorSession(report)

  const active = session.active
  const buffer = activeBuffer(session)
  const labels = tabLabels(session.order)

  // 저장된 폭이 지금 창에 맞는다는 보장이 없다. 창을 줄였거나, 매뉴얼을 함께
  // 열었거나, 예전 버전이 과한 값을 저장해 뒀을 수 있다. 그리는 폭은 늘 다시
  // 맞춘다 — 저장된 값 자체는 건드리지 않아 창을 넓히면 되돌아온다.
  const [docsFit, resultFit] = showDocs
    ? fitPanels([docsWidth, resultWidth], viewport, SPLITTER_WIDTH * 2)
    : [docsWidth, fitPanels([resultWidth], viewport, SPLITTER_WIDTH)[0]]

  /** 브라우저에서 고른 파일을 탭에 붙이고 연다. */
  function openFile(path: string) {
    open(path)
    setShowFiles(false)
  }

  /** 탭에서만 뺀다. **파일은 지우지 않는다.**
   *
   * 전환과 달리 닫기는 되돌릴 수 없다 — 버퍼가 사라지므로 고치던 내용도
   * 함께 없어진다. 그래서 여기서만 묻는다. */
  function closeTab(path: string) {
    if (
      isDirty(session, path) &&
      !window.confirm('저장하지 않은 변경이 있습니다. 버리고 닫을까요?')
    ) {
      return
    }
    // 닫은 파일의 결과가 남으면 다음 파일의 것으로 오해한다.
    if (path === active) setJobId(null)
    close(path)
  }

  const save = useCallback(async () => {
    if (active === null || buffer?.text == null) {
      setMessage('먼저 파일을 열어 주세요')
      return
    }
    const text = buffer.text
    try {
      await fileApi.write(active, text)
      applySaved(active, text)
      setMessage('저장됨')
    } catch (error) {
      report(error)
    }
  }, [active, buffer, applySaved, report])

  async function run() {
    if (active === null) return
    // 편집 중인 내용은 아직 서버에 없다. 저장하지 않고 돌리면 예전 내용이
    // 돌아가서, 방금 고친 줄이 반영되지 않은 결과를 보게 된다.
    if (isDirty(session, active)) await save()
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
          {session.order.map((path, index) => (
            <span key={path} className={path === active ? 'tab active' : 'tab'}>
              <button
                role="tab"
                aria-selected={path === active}
                className="link"
                onClick={() => switchTo(path)}
              >
                {labels[index]}
                {/* 어느 탭에 저장하지 않은 것이 있는지 탭에서 바로 보여야
                    한다. 옮길 때 묻지 않으므로 이 표시가 유일한 단서다. */}
                {isDirty(session, path) && (
                  <span className="dot" aria-label="저장되지 않음" />
                )}
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
        {occupancy && (
          <span
            className={
              occupancy.occupied >= occupancy.capacity
                ? 'muted occupancy full'
                : 'muted occupancy'
            }
            title={occupancyTitle(occupancy)}
          >
            {occupancyLabel(occupancy)}
          </span>
        )}
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
        <button onClick={() => void save()} disabled={active === null}>
          저장{' '}
          {active !== null && isDirty(session, active) && (
            <span className="dot" aria-label="저장되지 않음" />
          )}
        </button>
        <button
          className="primary"
          onClick={() => void run()}
          disabled={active === null}
        >
          실행
        </button>
        <button onClick={() => setShowDocs((openDocs) => !openDocs)}>
          {showDocs ? '매뉴얼 닫기' : '매뉴얼'}
        </button>
        {message && <span className="message">{message}</span>}
      </div>

      {showAdmin && <AdminPanel onClose={() => setShowAdmin(false)} />}

      {showFiles && (
        <FileBrowser
          onOpen={openFile}
          onClose={() => setShowFiles(false)}
          onRenamed={followRename}
          onDeleted={close}
        />
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
          {active !== null && buffer?.text != null ? (
            <SupremEditor
              path={active}
              value={buffer.text}
              cursor={buffer.cursor}
              onChange={(next) => change(active, next)}
              onCursorChange={(cursor) => setCursor(active, cursor)}
              onSave={() => void save()}
              onCommandChange={setCursorCommand}
            />
          ) : (
            <EmptyEditor
              restoring={restoring}
              loading={active !== null}
              onOpen={() => setShowFiles(true)}
            />
          )}
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

/**
 * 열어 둔 파일이 없을 때의 편집기 자리.
 *
 * 예전에는 예제 소스가 들어간 편집기를 띄웠다. 그러면 어느 파일을 고치고 있는
 * 것인지 알 수 없고, 저장을 누르면 "먼저 파일을 열어 주세요"만 나왔다.
 */
function EmptyEditor({
  restoring,
  loading,
  onOpen,
}: {
  restoring: boolean
  /** 탭은 열려 있는데 내용을 아직 못 받은 상태. */
  loading: boolean
  onOpen: () => void
}) {
  if (restoring || loading) {
    return <div className="empty-editor muted">불러오는 중…</div>
  }
  return (
    <div className="empty-editor">
      <p className="muted">열어 둔 파일이 없습니다.</p>
      <button onClick={onOpen}>파일 열기</button>
    </div>
  )
}
