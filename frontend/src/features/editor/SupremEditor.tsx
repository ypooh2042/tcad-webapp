/**
 * Monaco 편집기.
 *
 * 언어와 제공자 등록은 전역 상태라 여러 번 해서는 안 된다. 편집기를 다시 열
 * 때마다 등록하면 자동완성 목록에 같은 항목이 여러 번 뜬다.
 *
 * **등록은 반드시 beforeMount 에서 한다.** onMount 는 Monaco 가 모델을 이미
 * 만든 뒤에 불린다. 그 시점에는 `suprem` 이라는 언어가 없으므로 모델이
 * plaintext 로 잡히고, 나중에 제공자를 등록해도 이 모델에는 붙지 않는다.
 * 실제로 그 상태에서는 자동완성을 눌러도 카탈로그 요청이 한 건도 나가지
 * 않았다(E2E 로 확인).
 */
import Editor, { type Monaco } from '@monaco-editor/react'
import { useCallback, useEffect, useRef } from 'react'
// CDN 대신 로컬 번들을 쓰게 만든다. import 하는 것만으로 설정된다.
import '../../suprem/monacoSetup'
import {
  LANGUAGE_ID,
  languageConfiguration,
  monarchTokens,
} from '../../suprem/language'
import { commandOnLine } from '../../suprem/context'
import { registerSupremProviders } from '../../suprem/providers'

let registered = false

function registerOnce(monaco: Monaco) {
  if (registered) return
  registered = true

  monaco.languages.register({ id: LANGUAGE_ID, extensions: ['.in'] })
  monaco.languages.setLanguageConfiguration(LANGUAGE_ID, languageConfiguration)
  monaco.languages.setMonarchTokensProvider(LANGUAGE_ID, monarchTokens)
  registerSupremProviders(monaco)
}

export interface Cursor {
  line: number
  column: number
}

interface Props {
  /**
   * 지금 편집 중인 파일 경로.
   *
   * Monaco 에 그대로 넘긴다. 경로마다 **모델이 따로** 생기므로 되돌리기
   * 기록이 파일별로 나뉘고(탭을 옮긴 뒤 Ctrl+Z 가 남의 파일을 되돌리지
   * 않는다), 스크롤·커서 자리도 탭마다 알아서 보존된다.
   */
  path: string
  value: string
  /** 지난 세션에서 보던 자리. 이 경로를 처음 띄울 때 한 번만 적용한다. */
  cursor?: Cursor
  onChange: (value: string) => void
  onCursorChange?: (cursor: Cursor) => void
  onSave: () => void
  /** 커서가 놓인 줄의 커맨드. 매뉴얼 패널이 이걸 따라간다. */
  onCommandChange?: (command: string | null) => void
}

export function SupremEditor({
  path,
  value,
  cursor,
  onChange,
  onCursorChange,
  onSave,
  onCommandChange,
}: Props) {
  // ref 로 최신 핸들러를 부른다. 등록 시점의 낡은 클로저가 계속 불리면 안 된다.
  const saveRef = useRef(onSave)
  saveRef.current = onSave
  const commandRef = useRef(onCommandChange)
  commandRef.current = onCommandChange
  const cursorRef = useRef(onCursorChange)
  cursorRef.current = onCursorChange
  //: 커서를 되돌린 경로들. 경로마다 한 번만 되돌린다.
  const applied = useRef(new Set<string>())

  type EditorHandle = Parameters<
    NonNullable<React.ComponentProps<typeof Editor>['onMount']>
  >[0]
  const editorRef = useRef<EditorHandle | null>(null)

  // 지난 세션에서 보던 자리로 되돌린다. 같은 세션 안의 탭 전환은 Monaco 가
  // 스스로 기억하므로(saveViewState), 여기서 하는 일은 **그 기억이 없는 첫
  // 방문**을 채우는 것뿐이다. 경로마다 한 번만 적용한다 — 매번 적용하면
  // 사용자가 옮긴 커서가 지난 세션 자리로 되돌아간다.
  useEffect(() => {
    const editor = editorRef.current
    if (!editor || !cursor || applied.current.has(path)) return
    applied.current.add(path)
    const position = { lineNumber: cursor.line, column: cursor.column }
    editor.setPosition(position)
    editor.revealPositionInCenterIfOutsideViewport(position)
  }, [path, cursor])

  const handleMount = useCallback((editor: EditorHandle, monaco: Monaco) => {
    editorRef.current = editor
    // 저장은 편집기 안에서 Ctrl+S 로 하는 것이 자연스럽다. ref 로 최신
    // 핸들러를 부르지 않으면 등록 시점의 낡은 클로저가 계속 불린다.
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () =>
      saveRef.current(),
    )

    const report = () => {
      const position = editor.getPosition()
      const line = position
        ? (editor.getModel()?.getLineContent(position.lineNumber) ?? '')
        : ''
      commandRef.current?.(commandOnLine(line))
      if (position) {
        cursorRef.current?.({
          line: position.lineNumber,
          column: position.column,
        })
      }
    }
    editor.onDidChangeCursorPosition(report)
    // 편집 중에도 갱신한다. 커맨드 이름을 다 치는 순간 문서가 떠야 한다.
    editor.onDidChangeModelContent(report)
    report()
  }, [])

  return (
    <Editor
      height="100%"
      // 경로마다 모델이 따로 생긴다. 되돌리기 기록과 보던 자리가 파일별로
      // 나뉘는 것이 여기서 온다.
      path={path}
      language={LANGUAGE_ID}
      theme="vs-dark"
      value={value}
      onChange={(next) => onChange(next ?? '')}
      beforeMount={registerOnce}
      onMount={handleMount}
      // 모델을 붙들어 둔다. 탭을 처음 열 때 내용을 받아오는 동안 편집기가 잠깐
      // 내려가는데, 그때 모델이 버려지면 그 파일의 되돌리기 기록이 사라진다.
      keepCurrentModel
      options={{
        minimap: { enabled: false },
        fontSize: 13,
        scrollBeyondLastLine: false,
        tabSize: 4,
        renderWhitespace: 'selection',
      }}
    />
  )
}
