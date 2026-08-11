/**
 * Monaco 를 로컬 번들에서, 필요한 기능만 골라 쓴다.
 *
 * **왜 CDN 이 아닌가**
 * `@monaco-editor/react` 는 기본적으로 jsdelivr 에서 Monaco 를 내려받는다. 이
 * 앱은 홈서버에서 자체 호스팅하므로 그대로 두면 외부 망이 끊길 때 편집기가 아예
 * 뜨지 않고, 사용자의 접속 사실이 제3자에게 새어 나간다.
 *
 * **왜 editor.api 만으로는 안 되는가**
 * `editor.api` 는 API 표면만 담고 있다. 자동완성 위젯·호버 같은 에디터
 * 기여(contrib)가 통째로 빠져서, 제공자를 등록해도 Monaco 가 한 번도 부르지
 * 않는다. 등록은 성공하고 모델 언어도 맞는데 자동완성만 조용히 죽는다 —
 * 단위 테스트는 Monaco 를 목으로 바꾸므로 잡히지 않고 E2E 에서야 드러났다.
 *
 * **왜 editor.main 을 쓰지 않는가**
 * editor.main 은 기여를 전부 담지만 80여 개 언어 정의와 TypeScript·HTML·CSS
 * 언어 서비스까지 함께 끌고 온다(ts.worker 하나가 7MB). 우리는 직접 정의한
 * 언어 하나만 쓴다.
 *
 * 그래서 API + **쓰는 기여만** 명시적으로 가져온다. Monaco 버전을 올릴 때 이
 * 목록이 깨질 수 있다. 자동완성이 안 되면 여기부터 본다.
 *
 * 경로 주의: package.json 의 exports 가 `./*` 를 `./esm/vs/*` 로 매핑한다.
 * 'monaco-editor/esm/vs/...' 라고 쓰면 esm/vs 가 두 번 붙는다.
 */
import * as monaco from 'monaco-editor/editor/editor.api'

// 커서 이동·선택 같은 기본 편집 명령.
import 'monaco-editor/editor/browser/coreCommands'
// 자동완성 위젯. 이것이 없으면 제공자가 호출되지 않는다.
import 'monaco-editor/editor/contrib/suggest/browser/suggestController'
// 자동완성 항목을 끼워 넣을 때 스니펫 컨트롤러를 쓴다.
import 'monaco-editor/editor/contrib/snippet/browser/snippetController2'
// 호버 문서.
import 'monaco-editor/editor/contrib/hover/browser/hoverContribution'
// 편집기에서 당연히 되리라 기대하는 것들.
import 'monaco-editor/editor/contrib/bracketMatching/browser/bracketMatching'
import 'monaco-editor/editor/contrib/comment/browser/comment'
import 'monaco-editor/editor/contrib/contextmenu/browser/contextmenu'
import 'monaco-editor/editor/contrib/find/browser/findController'
import 'monaco-editor/editor/contrib/linesOperations/browser/linesOperations'
import 'monaco-editor/editor/contrib/multicursor/browser/multicursor'
import 'monaco-editor/editor/contrib/wordOperations/browser/wordOperations'

import { loader } from '@monaco-editor/react'
import editorWorker from 'monaco-editor/editor/editor.worker?worker'

declare global {
  interface Window {
    MonacoEnvironment?: monaco.Environment
  }
}

// SUPREM 은 직접 정의한 언어라 기본 편집기 워커 하나면 된다.
self.MonacoEnvironment = {
  getWorker: () => new editorWorker(),
}

loader.config({ monaco })
