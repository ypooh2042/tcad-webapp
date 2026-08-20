/**
 * 편집기에 열어 둔 것들의 상태.
 *
 * React 밖의 순수 함수로 둔다. 탭 전환·초안 보관·더티 판정은 규칙이 얽혀 있어
 * 화면과 섞이면 무엇이 언제 바뀌는지 따라가기 어렵다.
 *
 * 핵심 규칙 두 가지:
 *
 *   1. **탭을 옮길 때 저장을 요구하지 않는다.** 고치던 내용은 버퍼에 그대로
 *      남고 돌아오면 이어서 고칠 수 있다. 저장은 곧 "실행 대상이 바뀐다"는
 *      뜻이라 잠깐 다른 파일을 들춰 보려고 시킬 일이 아니다.
 *   2. **커서 자리를 기억한다.** 300줄짜리 공정 흐름에서 탭을 오갈 때마다
 *      맨 위로 돌아가면 보던 자리를 매번 다시 찾아야 한다.
 *
 * 전부 불변이다. 새 객체를 만들어 돌려주고 인자는 건드리지 않는다.
 */

export interface Cursor {
  /** 1-based. Monaco 규약을 그대로 쓴다. */
  line: number
  column: number
}

export interface Buffer {
  /** 편집 중인 내용. 아직 읽어오지 않았으면 null. */
  text: string | null
  /** 마지막으로 서버와 맞춘 내용. 아직 모르면 null. */
  saved: string | null
  cursor?: Cursor
}

export interface EditorSession {
  /** 탭 순서. 사용자가 연 순서다 — 정렬하면 탭이 제멋대로 움직인다. */
  order: string[]
  active: string | null
  buffers: Record<string, Buffer>
}

export const EMPTY_SESSION: EditorSession = {
  order: [],
  active: null,
  buffers: {},
}

/** 아직 서버에서 내용을 못 받은 버퍼. 화면은 이때 "불러오는 중"을 띄운다. */
export function needsLoad(session: EditorSession, path: string): boolean {
  const buffer = session.buffers[path]
  return buffer !== undefined && buffer.saved === null
}

/** 저장하지 않은 편집이 있는가. */
export function isDirty(session: EditorSession, path: string): boolean {
  const buffer = session.buffers[path]
  if (!buffer || buffer.text === null) return false
  return buffer.text !== buffer.saved
}

export function anyDirty(session: EditorSession): boolean {
  return session.order.some((path) => isDirty(session, path))
}

export function activeBuffer(session: EditorSession): Buffer | null {
  return session.active ? (session.buffers[session.active] ?? null) : null
}

export function openTab(session: EditorSession, path: string): EditorSession {
  // 같은 파일을 두 번 열어도 탭은 하나다. 이미 있으면 내용을 건드리지 않는다 —
  // 고치던 초안을 파일 원본으로 되돌리면 작업을 잃는다.
  const order = session.order.includes(path)
    ? session.order
    : [...session.order, path]
  const buffers = session.buffers[path]
    ? session.buffers
    : { ...session.buffers, [path]: { text: null, saved: null } }
  return { order, active: path, buffers }
}

export function closeTab(session: EditorSession, path: string): EditorSession {
  const order = session.order.filter((item) => item !== path)
  const buffers = { ...session.buffers }
  delete buffers[path]
  const active =
    session.active === path ? (order[order.length - 1] ?? null) : session.active
  return { order, active, buffers }
}

export function activate(session: EditorSession, path: string): EditorSession {
  if (!session.order.includes(path)) return session
  return { ...session, active: path }
}

export function edit(
  session: EditorSession,
  path: string,
  text: string,
): EditorSession {
  const buffer = session.buffers[path]
  if (!buffer) return session
  return {
    ...session,
    buffers: { ...session.buffers, [path]: { ...buffer, text } },
  }
}

/** 서버에서 읽어온 원본을 반영한다. 초안이 있으면 **초안을 지키고** 기준만 채운다. */
export function loaded(
  session: EditorSession,
  path: string,
  content: string,
): EditorSession {
  const buffer = session.buffers[path]
  if (!buffer) return session
  return {
    ...session,
    buffers: {
      ...session.buffers,
      [path]: { ...buffer, text: buffer.text ?? content, saved: content },
    },
  }
}

/** 저장이 끝났다. 이 시점의 내용이 곧 새 기준이 된다. */
export function markSaved(
  session: EditorSession,
  path: string,
  text: string,
): EditorSession {
  const buffer = session.buffers[path]
  if (!buffer) return session
  return {
    ...session,
    buffers: { ...session.buffers, [path]: { ...buffer, text, saved: text } },
  }
}

export function moveCursor(
  session: EditorSession,
  path: string,
  cursor: Cursor,
): EditorSession {
  const buffer = session.buffers[path]
  if (!buffer) return session
  return {
    ...session,
    buffers: { ...session.buffers, [path]: { ...buffer, cursor } },
  }
}

/** 이름이 바뀐 파일을 따라간다. 탭 자리와 고치던 내용을 그대로 옮긴다. */
export function renamePath(
  session: EditorSession,
  from: string,
  to: string,
): EditorSession {
  const buffer = session.buffers[from]
  if (!buffer) return session
  const buffers = { ...session.buffers, [to]: buffer }
  delete buffers[from]
  return {
    order: session.order.map((path) => (path === from ? to : path)),
    active: session.active === from ? to : session.active,
    buffers,
  }
}
