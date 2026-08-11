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
import { useCallback, useRef } from 'react'
// CDN 대신 로컬 번들을 쓰게 만든다. import 하는 것만으로 설정된다.
import '../../suprem/monacoSetup'
import {
  LANGUAGE_ID,
  languageConfiguration,
  monarchTokens,
} from '../../suprem/language'
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

interface Props {
  value: string
  onChange: (value: string) => void
  onSave: () => void
}

export function SupremEditor({ value, onChange, onSave }: Props) {
  const saveRef = useRef(onSave)
  saveRef.current = onSave

  const handleMount = useCallback((editor: Parameters<
    NonNullable<React.ComponentProps<typeof Editor>['onMount']>
  >[0], monaco: Monaco) => {
    // 저장은 편집기 안에서 Ctrl+S 로 하는 것이 자연스럽다. ref 로 최신
    // 핸들러를 부르지 않으면 등록 시점의 낡은 클로저가 계속 불린다.
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () =>
      saveRef.current(),
    )
  }, [])

  return (
    <Editor
      height="100%"
      language={LANGUAGE_ID}
      theme="vs-dark"
      value={value}
      onChange={(next) => onChange(next ?? '')}
      beforeMount={registerOnce}
      onMount={handleMount}
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
