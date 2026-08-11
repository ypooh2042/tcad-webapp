/**
 * Monaco 를 로컬 번들에서 쓰도록 고정한다.
 *
 * `@monaco-editor/react` 는 기본적으로 CDN(jsdelivr)에서 Monaco 를 내려받는다.
 * 이 앱은 홈서버에서 자체 호스팅하므로 그대로 두면:
 *   - 외부 망이 끊기면 편집기가 아예 뜨지 않고,
 *   - 사용자의 접속 사실이 제3자에게 새어 나가며,
 *   - 배포한 버전과 실제로 실행되는 버전이 달라질 수 있다.
 *
 * 워커도 직접 물려야 한다. 그러지 않으면 Monaco 가 워커를 CDN 에서 찾는다.
 */
// editor.api 만 가져온다. 'monaco-editor' 를 통째로 import 하면 TypeScript·
// HTML·CSS 등 쓰지도 않는 언어와 워커가 전부 딸려 온다(ts.worker 만 7MB).
// 경로 주의: package.json 의 exports 가 `./*` 를 `./esm/vs/*` 로 매핑한다.
// 'monaco-editor/esm/vs/editor/editor.api' 라고 쓰면 esm/vs 가 두 번 붙어
// 존재하지 않는 경로가 된다.
import * as monaco from 'monaco-editor/editor/editor.api'
import { loader } from '@monaco-editor/react'
import editorWorker from 'monaco-editor/editor/editor.worker?worker'

declare global {
  interface Window {
    MonacoEnvironment?: monaco.Environment
  }
}

// SUPREM 은 직접 정의한 언어라 기본 편집기 워커 하나면 된다. TS/JSON 등의
// 전용 워커는 쓰지 않으므로 번들에 넣지 않는다.
self.MonacoEnvironment = {
  getWorker: () => new editorWorker(),
}

loader.config({ monaco })
