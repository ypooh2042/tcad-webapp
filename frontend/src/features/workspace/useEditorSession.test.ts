/**
 * 편집기 세션과 서버의 연결.
 *
 * 규칙 자체는 editorSession.test 가 본다. 여기서는 **언제 무엇을 주고받는가**를
 * 본다 — 잘못 보내면 서버에 남은 탭 목록이 지워지고, 잘못 읽으면 고치던 내용이
 * 파일 원본으로 되돌아간다.
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useEditorSession } from './useEditorSession'

const { editor, files } = vi.hoisted(() => ({
  editor: { state: vi.fn(), save: vi.fn() },
  files: { read: vi.fn() },
}))
vi.mock('../../api/endpoints', () => ({ editor, files }))

const report = vi.fn()

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.clearAllMocks()
  editor.state.mockResolvedValue({ tabs: [], active: null })
  editor.save.mockResolvedValue(null)
  files.read.mockResolvedValue({ path: 'a.in', content: '파일 내용\n' })
})

afterEach(() => vi.useRealTimers())

async function ready() {
  const view = renderHook(() => useEditorSession(report))
  await waitFor(() => expect(view.result.current.restoring).toBe(false))
  return view
}

describe('되살리기', () => {
  it('들어오면 서버에 남은 상태를 불러온다', async () => {
    editor.state.mockResolvedValue({
      tabs: [{ path: 'a.in', draft: '고치던 중\n', cursor: { line: 3, column: 1 } }],
      active: 'a.in',
    })

    const { result } = await ready()

    expect(result.current.session.order).toEqual(['a.in'])
    expect(result.current.session.buffers['a.in']!.text).toBe('고치던 중\n')
  })

  it('되살리기 전에는 서버에 아무것도 남기지 않는다', async () => {
    // 빈 상태를 먼저 보내면 서버에 있던 탭 목록을 지운다.
    let resolveState: (value: unknown) => void = () => {}
    editor.state.mockReturnValue(new Promise((resolve) => (resolveState = resolve)))

    renderHook(() => useEditorSession(report))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000)
    })

    expect(editor.save).not.toHaveBeenCalled()
    resolveState({ tabs: [], active: null })
  })

  it('되살리기가 실패해도 편집기는 뜬다', async () => {
    editor.state.mockRejectedValue(new Error('연결 실패'))

    const { result } = await ready()

    expect(result.current.session.order).toEqual([])
  })
})

describe('내용 읽어오기', () => {
  it('보고 있는 탭만 읽어온다', async () => {
    const { result } = await ready()

    act(() => result.current.open('a.in'))
    await waitFor(() => expect(files.read).toHaveBeenCalledWith('a.in'))

    act(() => result.current.open('b.in'))
    await waitFor(() => expect(files.read).toHaveBeenCalledWith('b.in'))
    expect(files.read).toHaveBeenCalledTimes(2)
  })

  it('한 번 읽은 탭은 다시 읽지 않는다', async () => {
    // 탭을 오갈 때마다 다시 읽으면 고치던 내용이 원본으로 되돌아간다.
    const { result } = await ready()
    act(() => result.current.open('a.in'))
    await waitFor(() => expect(files.read).toHaveBeenCalledTimes(1))

    act(() => result.current.open('b.in'))
    await waitFor(() => expect(files.read).toHaveBeenCalledTimes(2))
    act(() => result.current.switchTo('a.in'))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })

    expect(files.read).toHaveBeenCalledTimes(2)
  })

  it('되살아난 탭도 원본을 한 번 받아 기준을 채운다', async () => {
    editor.state.mockResolvedValue({
      tabs: [{ path: 'a.in', draft: '고치던 중\n', cursor: null }],
      active: 'a.in',
    })

    const { result } = await ready()
    await waitFor(() => expect(files.read).toHaveBeenCalledWith('a.in'))

    // 원본을 받아도 초안이 화면에 남아야 한다.
    await waitFor(() =>
      expect(result.current.session.buffers['a.in']!.saved).toBe('파일 내용\n'),
    )
    expect(result.current.session.buffers['a.in']!.text).toBe('고치던 중\n')
  })

  it('읽기에 실패하면 알린다', async () => {
    files.read.mockRejectedValue(new Error('없는 파일'))
    const { result } = await ready()

    act(() => result.current.open('gone.in'))

    await waitFor(() => expect(report).toHaveBeenCalled())
  })
})

describe('남기기', () => {
  it('바뀌면 잠시 뒤 한 번 보낸다', async () => {
    const { result } = await ready()

    act(() => result.current.open('a.in'))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })

    expect(editor.save).toHaveBeenCalled()
    expect(editor.save.mock.lastCall![0].active).toBe('a.in')
  })

  it('타이핑하는 동안에는 보내지 않는다', async () => {
    // 글자마다 보내면 타이핑 속도로 요청이 나간다.
    const { result } = await ready()
    act(() => result.current.open('a.in'))
    await waitFor(() => expect(files.read).toHaveBeenCalled())
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })
    editor.save.mockClear()

    for (const text of ['a', 'ab', 'abc']) {
      act(() => result.current.change('a.in', text))
      await act(async () => {
        await vi.advanceTimersByTimeAsync(300)
      })
    }

    expect(editor.save).not.toHaveBeenCalled()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })
    expect(editor.save).toHaveBeenCalledTimes(1)
  })

  it('남기기에 실패해도 편집은 계속된다', async () => {
    editor.save.mockRejectedValue(new Error('연결 실패'))
    const { result } = await ready()

    act(() => result.current.open('a.in'))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })

    expect(report).not.toHaveBeenCalled()
    expect(result.current.session.order).toEqual(['a.in'])
  })
})
