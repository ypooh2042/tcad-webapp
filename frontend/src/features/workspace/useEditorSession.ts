/**
 * 편집기 세션을 서버와 잇는다.
 *
 * 세 가지를 한다:
 *
 *   1. **들어올 때 되살린다.** 세션은 30분 유휴로 끊긴다. 다시 들어왔을 때
 *      빈 화면이면 어느 파일을 보고 있었는지 사용자가 기억해서 되짚어야 한다.
 *   2. **바뀌면 남긴다.** 한 번 멎을 때까지 기다렸다가 한 번만 보낸다 —
 *      글자마다 보내면 타이핑 속도로 요청이 나간다.
 *   3. **보려는 탭만 읽어온다.** 스무 개를 한꺼번에 받으면 nginx 레이트
 *      리밋(20 req/s)에 그대로 걸린다.
 *
 * 상태 규칙 자체는 editorSession.ts 에 있다. 여기는 붙이는 일만 한다.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { editor as editorApi, files as fileApi } from '../../api/endpoints'
import {
  type Cursor,
  type EditorSession,
  EMPTY_SESSION,
  activate,
  closeTab,
  edit,
  loaded,
  markSaved,
  moveCursor,
  needsLoad,
  openTab,
  renamePath,
} from './editorSession'
import { fromPersisted, toPersisted } from './editorSession.persist'

//: 마지막 변경 뒤 이만큼 조용하면 서버에 남긴다. 사람이 손을 뗀 것을 알아챌
//: 만큼 짧고, 타이핑 중에 요청이 나가지 않을 만큼은 길다.
const PERSIST_DEBOUNCE_MS = 1000

export function useEditorSession(report: (error: unknown) => void) {
  const [session, setSession] = useState<EditorSession>(EMPTY_SESSION)
  //: 되살리기가 끝나기 전에는 아무것도 남기지 않는다. 빈 상태를 먼저 보내면
  //: 서버에 있던 탭 목록을 지워 버린다.
  const [restoring, setRestoring] = useState(true)

  useEffect(() => {
    let cancelled = false
    editorApi
      .state()
      .then((stored) => {
        if (!cancelled) setSession(fromPersisted(stored))
      })
      // 되살리기에 실패해도 빈 편집기로 시작할 수 있다. 여기서 막으면 화면이
      // 아예 안 뜬다.
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setRestoring(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // 보고 있는 탭의 원본을 받아온다. 초안이 있으면 화면은 이미 초안을 보여주고
  // 있고, 이 요청은 "고쳤는지" 판정에 쓸 기준을 채운다.
  const active = session.active
  const wants = active !== null && needsLoad(session, active)
  useEffect(() => {
    if (active === null || !wants) return
    let cancelled = false

    fileApi
      .read(active)
      .then((file) => {
        if (!cancelled) setSession((current) => loaded(current, active, file.content))
      })
      .catch((error) => {
        if (!cancelled) report(error)
      })

    return () => {
      cancelled = true
    }
  }, [active, wants, report])

  // 바뀐 것을 서버에 남긴다.
  const latest = useRef(session)
  latest.current = session
  useEffect(() => {
    if (restoring) return
    const timer = setTimeout(() => {
      // 남기기에 실패해도 편집은 계속되어야 한다. 다음 변경에서 다시 시도한다.
      void editorApi.save(toPersisted(latest.current)).catch(() => undefined)
    }, PERSIST_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [session, restoring])

  return {
    session,
    restoring,
    open: useCallback((path: string) => setSession((s) => openTab(s, path)), []),
    close: useCallback((path: string) => setSession((s) => closeTab(s, path)), []),
    switchTo: useCallback((path: string) => setSession((s) => activate(s, path)), []),
    change: useCallback(
      (path: string, text: string) => setSession((s) => edit(s, path, text)),
      [],
    ),
    applySaved: useCallback(
      (path: string, text: string) => setSession((s) => markSaved(s, path, text)),
      [],
    ),
    setCursor: useCallback(
      (path: string, cursor: Cursor) => setSession((s) => moveCursor(s, path, cursor)),
      [],
    ),
    followRename: useCallback(
      (from: string, to: string) => setSession((s) => renamePath(s, from, to)),
      [],
    ),
  }
}
