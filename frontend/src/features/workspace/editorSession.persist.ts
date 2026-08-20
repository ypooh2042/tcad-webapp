/**
 * 편집기 상태를 서버 표현으로 옮기고 되돌린다.
 *
 * 서버로 나가는 것은 **초안과 커서**뿐이다. 저장된 내용까지 보내면 파일의
 * 사본이 DB 에 한 벌 더 생기고, 그쪽이 낡으면 어느 것이 진짜인지 알 수 없다.
 */
import {
  type Cursor,
  type EditorSession,
  EMPTY_SESSION,
  isDirty,
} from './editorSession'

export interface PersistedTab {
  path: string
  draft: string | null
  cursor: Cursor | null
}

export interface PersistedSession {
  tabs: PersistedTab[]
  active: string | null
}

export function toPersisted(session: EditorSession): PersistedSession {
  return {
    tabs: session.order.map((path) => {
      const buffer = session.buffers[path]
      return {
        path,
        // 저장된 내용과 같으면 초안이 아니다. 그대로 보내면 파일을 고쳤을 때
        // 낡은 사본이 남아 다음 접속에서 그것이 뜬다.
        draft: isDirty(session, path) ? (buffer?.text ?? null) : null,
        cursor: buffer?.cursor ?? null,
      }
    }),
    active: session.active,
  }
}

export function fromPersisted(state: PersistedSession): EditorSession {
  const order = state.tabs.map((tab) => tab.path)
  const buffers: EditorSession['buffers'] = {}
  for (const tab of state.tabs) {
    buffers[tab.path] = {
      // 초안이 있으면 곧바로 보여준다. 파일을 읽어올 때까지 기다리면 고치던
      // 내용이 잠깐 빈 화면으로 보인다.
      text: tab.draft,
      // 원본은 아직 모른다. 받아오기 전까지 더티 판정을 초안 쪽에 맡긴다.
      saved: null,
      ...(tab.cursor ? { cursor: tab.cursor } : {}),
    }
  }
  const active =
    state.active && order.includes(state.active) ? state.active : (order[0] ?? null)
  return order.length === 0 ? EMPTY_SESSION : { order, active, buffers }
}
