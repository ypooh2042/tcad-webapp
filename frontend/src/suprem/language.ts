/**
 * Monaco 용 SUPREM 입력 언어 정의.
 *
 * 문법은 SUPREM4GS 예제 파일과 실제 실행으로 확인했다:
 *   - 주석은 `#`, 줄 끝까지
 *   - 커맨드 앞의 `%` 는 투명하다(`%structure` 도 그대로 실행됨)
 *   - `${var}` 로 변수를 끼워 넣는다
 *   - `movie="..."` 처럼 따옴표 문자열이 여러 줄에 걸치기도 한다
 */
import type * as monacoNs from 'monaco-editor'

export const LANGUAGE_ID = 'suprem'

export const languageConfiguration: monacoNs.languages.LanguageConfiguration = {
  comments: { lineComment: '#' },
  brackets: [['(', ')']],
  autoClosingPairs: [
    { open: '(', close: ')' },
    { open: '"', close: '"' },
  ],
}

export const monarchTokens: monacoNs.languages.IMonarchLanguage = {
  defaultToken: '',
  tokenizer: {
    root: [
      [/#.*$/, 'comment'],
      // 줄 첫머리의 커맨드. 앞의 % 는 별도 토큰으로 둔다.
      [/^\s*%/, 'keyword.control'],
      [/^\s*[A-Za-z][\w.]*/, 'keyword'],
      [/\$\{/, { token: 'variable', next: '@variable' }],
      [/"/, { token: 'string.quote', next: '@string' }],
      // 파라미터 이름은 = 앞에 오는 낱말이다.
      [/[A-Za-z][\w./]*(?=\s*=)/, 'attribute.name'],
      [/=/, 'operator'],
      [/[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?/, 'number'],
      [/[A-Za-z][\w./]*/, 'identifier'],
    ],
    variable: [
      [/[^}]+/, 'variable'],
      [/\}/, { token: 'variable', next: '@pop' }],
    ],
    string: [
      // 문자열은 여러 줄에 걸칠 수 있다. 닫는 따옴표를 만날 때까지 유지한다.
      [/[^"]+/, 'string'],
      [/"/, { token: 'string.quote', next: '@pop' }],
    ],
  },
}
