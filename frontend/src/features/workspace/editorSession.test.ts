/**
 * 편집기 세션 상태.
 *
 * 여기서 지키려는 것은 하나다: **탭을 오가도 고치던 것을 잃지 않는다.**
 */
import { describe, expect, it } from 'vitest'
import {
  EMPTY_SESSION,
  activate,
  activeBuffer,
  anyDirty,
  closeTab,
  edit,
  isDirty,
  loaded,
  markSaved,
  moveCursor,
  needsLoad,
  openTab,
  renamePath,
} from './editorSession'
import { fromPersisted, toPersisted } from './editorSession.persist'

/** a.in 과 b.in 을 열고 내용까지 받아 둔 상태. */
function twoOpenFiles() {
  let session = openTab(EMPTY_SESSION, 'a.in')
  session = loaded(session, 'a.in', 'A 내용\n')
  session = openTab(session, 'b.in')
  session = loaded(session, 'b.in', 'B 내용\n')
  return session
}

describe('탭 열기', () => {
  it('연 순서를 지킨다', () => {
    const session = twoOpenFiles()

    expect(session.order).toEqual(['a.in', 'b.in'])
  })

  it('연 탭이 활성이 된다', () => {
    expect(twoOpenFiles().active).toBe('b.in')
  })

  it('같은 파일을 두 번 열어도 탭은 하나다', () => {
    const session = openTab(twoOpenFiles(), 'a.in')

    expect(session.order).toEqual(['a.in', 'b.in'])
  })

  it('이미 연 파일을 다시 열어도 고치던 내용을 되돌리지 않는다', () => {
    // 파일 브라우저에서 같은 파일을 다시 누르는 것만으로 작업이 사라지면 안 된다.
    let session = edit(twoOpenFiles(), 'a.in', '고치던 중\n')
    session = openTab(session, 'a.in')

    expect(session.buffers['a.in']!.text).toBe('고치던 중\n')
  })

  it('새로 연 탭은 아직 내용을 모른다', () => {
    const session = openTab(EMPTY_SESSION, 'c.in')

    expect(needsLoad(session, 'c.in')).toBe(true)
    expect(session.buffers['c.in']!.text).toBeNull()
  })
})

describe('탭 전환', () => {
  it('저장하지 않은 편집을 그대로 들고 간다', () => {
    // 이것이 이 모듈의 존재 이유다. 예전에는 전환할 때마다 버릴지 물었다.
    let session = edit(twoOpenFiles(), 'b.in', '고치던 중\n')
    session = activate(session, 'a.in')
    session = activate(session, 'b.in')

    expect(activeBuffer(session)!.text).toBe('고치던 중\n')
  })

  it('열려 있지 않은 파일로는 옮기지 않는다', () => {
    const session = activate(twoOpenFiles(), '없는파일.in')

    expect(session.active).toBe('b.in')
  })

  it('커서 자리를 탭마다 따로 기억한다', () => {
    let session = moveCursor(twoOpenFiles(), 'a.in', { line: 42, column: 3 })
    session = moveCursor(session, 'b.in', { line: 7, column: 1 })

    expect(session.buffers['a.in']!.cursor).toEqual({ line: 42, column: 3 })
    expect(session.buffers['b.in']!.cursor).toEqual({ line: 7, column: 1 })
  })
})

describe('더티 판정', () => {
  it('읽어온 그대로면 깨끗하다', () => {
    expect(isDirty(twoOpenFiles(), 'a.in')).toBe(false)
  })

  it('고치면 더럽다', () => {
    expect(isDirty(edit(twoOpenFiles(), 'a.in', '다른 내용'), 'a.in')).toBe(true)
  })

  it('되돌려 놓으면 다시 깨끗하다', () => {
    let session = edit(twoOpenFiles(), 'a.in', '다른 내용')
    session = edit(session, 'a.in', 'A 내용\n')

    expect(isDirty(session, 'a.in')).toBe(false)
  })

  it('저장하면 그 내용이 새 기준이 된다', () => {
    let session = edit(twoOpenFiles(), 'a.in', '새 내용')
    session = markSaved(session, 'a.in', '새 내용')

    expect(isDirty(session, 'a.in')).toBe(false)
  })

  it('아직 안 읽어온 탭은 더티가 아니다', () => {
    expect(isDirty(openTab(EMPTY_SESSION, 'c.in'), 'c.in')).toBe(false)
  })

  it('하나라도 더러우면 알려준다', () => {
    expect(anyDirty(twoOpenFiles())).toBe(false)
    expect(anyDirty(edit(twoOpenFiles(), 'b.in', 'x'))).toBe(true)
  })
})

describe('탭 닫기', () => {
  it('닫은 탭의 버퍼도 함께 버린다', () => {
    const session = closeTab(twoOpenFiles(), 'a.in')

    expect(session.order).toEqual(['b.in'])
    expect(session.buffers['a.in']).toBeUndefined()
  })

  it('활성 탭을 닫으면 남은 탭으로 옮긴다', () => {
    expect(closeTab(twoOpenFiles(), 'b.in').active).toBe('a.in')
  })

  it('다른 탭을 닫아도 보던 탭은 그대로다', () => {
    expect(closeTab(twoOpenFiles(), 'a.in').active).toBe('b.in')
  })

  it('마지막 탭을 닫으면 아무것도 열려 있지 않다', () => {
    let session = closeTab(twoOpenFiles(), 'a.in')
    session = closeTab(session, 'b.in')

    expect(session).toEqual(EMPTY_SESSION)
  })
})

describe('이름 바꾸기 따라가기', () => {
  it('탭 자리와 고치던 내용을 그대로 옮긴다', () => {
    let session = edit(twoOpenFiles(), 'b.in', '고치던 중\n')
    session = renamePath(session, 'b.in', 'renamed.in')

    expect(session.order).toEqual(['a.in', 'renamed.in'])
    expect(session.active).toBe('renamed.in')
    expect(session.buffers['renamed.in']!.text).toBe('고치던 중\n')
    expect(session.buffers['b.in']).toBeUndefined()
  })

  it('열려 있지 않은 파일이면 아무 일도 없다', () => {
    const session = twoOpenFiles()

    expect(renamePath(session, 'other.in', 'x.in')).toBe(session)
  })
})

describe('서버에 남기기', () => {
  it('저장하지 않은 것만 초안으로 보낸다', () => {
    // 저장된 내용까지 보내면 파일 사본이 DB 에 한 벌 더 생기고, 그쪽이 낡으면
    // 다음 접속에서 낡은 것이 뜬다.
    const session = edit(twoOpenFiles(), 'b.in', '고치던 중\n')

    const sent = toPersisted(session)

    expect(sent.tabs.find((t) => t.path === 'a.in')!.draft).toBeNull()
    expect(sent.tabs.find((t) => t.path === 'b.in')!.draft).toBe('고치던 중\n')
    expect(sent.active).toBe('b.in')
  })

  it('커서도 함께 보낸다', () => {
    const session = moveCursor(twoOpenFiles(), 'a.in', { line: 9, column: 2 })

    const sent = toPersisted(session)

    expect(sent.tabs[0]!.cursor).toEqual({ line: 9, column: 2 })
  })

  it('돌아오면 초안과 커서가 되살아난다', () => {
    const restored = fromPersisted({
      tabs: [
        { path: 'a.in', draft: null, cursor: { line: 5, column: 1 } },
        { path: 'b.in', draft: '고치던 중\n', cursor: null },
      ],
      active: 'b.in',
    })

    expect(restored.order).toEqual(['a.in', 'b.in'])
    expect(restored.active).toBe('b.in')
    expect(restored.buffers['b.in']!.text).toBe('고치던 중\n')
    expect(restored.buffers['a.in']!.cursor).toEqual({ line: 5, column: 1 })
  })

  it('되살아난 초안은 더티로 보인다', () => {
    // 저장하지 않았다는 표시가 사라지면 사용자는 저장된 줄 안다.
    const restored = fromPersisted({
      tabs: [{ path: 'b.in', draft: '고치던 중\n', cursor: null }],
      active: 'b.in',
    })

    expect(isDirty(restored, 'b.in')).toBe(true)
  })

  it('되살아난 탭은 원본을 다시 받아야 한다', () => {
    const restored = fromPersisted({
      tabs: [{ path: 'a.in', draft: null, cursor: null }],
      active: 'a.in',
    })

    expect(needsLoad(restored, 'a.in')).toBe(true)
  })

  it('원본을 받아도 초안을 덮지 않는다', () => {
    let restored = fromPersisted({
      tabs: [{ path: 'b.in', draft: '고치던 중\n', cursor: null }],
      active: 'b.in',
    })
    restored = loaded(restored, 'b.in', '파일에 저장된 내용\n')

    expect(restored.buffers['b.in']!.text).toBe('고치던 중\n')
    expect(isDirty(restored, 'b.in')).toBe(true)
  })

  it('빈 상태는 빈 상태로 돌아온다', () => {
    expect(fromPersisted({ tabs: [], active: null })).toEqual(EMPTY_SESSION)
  })

  it('활성 탭이 목록에 없으면 첫 탭을 고른다', () => {
    const restored = fromPersisted({
      tabs: [{ path: 'a.in', draft: null, cursor: null }],
      active: '없는파일.in',
    })

    expect(restored.active).toBe('a.in')
  })
})
