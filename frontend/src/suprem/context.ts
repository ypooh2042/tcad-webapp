/**
 * 커서 위치에서 무엇을 완성해야 하는지 판정한다.
 *
 * SUPREM 의 한 줄은 `[%]커맨드 [파라미터[=값]]...` 꼴이다. 문법은 예제 파일과
 * 실제 실행으로 확인했다:
 *   - 주석은 `#`. 따옴표 안의 `#` 은 주석이 아니다.
 *   - 커맨드 앞의 `%` 는 투명하다(`%structure` 와 `structure` 가 같게 동작).
 *   - `${var}` 로 변수를 끼워 넣는다. 안쪽은 카탈로그가 모르는 이름이다.
 *
 * 접두사 해석(`stru` → `structure`)은 여기서 하지 않는다. 사용자가 친 그대로
 * 넘겨야 서버가 모호함을 판정하고 후보를 돌려줄 수 있다.
 */

export type CompletionContext =
  | { kind: 'command'; prefix: string }
  | { kind: 'parameter'; command: string; prefix: string }
  | { kind: 'value'; command: string; parameter: string; prefix: string }
  | { kind: 'none' }

const NONE: CompletionContext = { kind: 'none' }

/** 커서 앞이 주석이나 문자열, 변수 안이면 완성하지 않는다. */
function isInert(text: string): boolean {
  let inString = false
  let inVariable = false

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i]

    if (inString) {
      if (char === '"') inString = false
      continue
    }
    if (inVariable) {
      if (char === '}') inVariable = false
      continue
    }
    if (char === '"') {
      inString = true
      continue
    }
    if (char === '$' && text[i + 1] === '{') {
      inVariable = true
      i += 1
      continue
    }
    // 주석은 줄 끝까지 이어지므로 되돌아올 일이 없다.
    if (char === '#') return true
  }

  return inString || inVariable
}

export function analyzeLine(line: string, column: number): CompletionContext {
  const before = line.slice(0, Math.max(0, column))

  if (isInert(before)) return NONE

  // 앞쪽 공백과 투명한 % 를 벗겨낸다.
  const body = before.replace(/^\s*%?/, '')

  // `=` 를 독립 토큰으로 떼어낸다. 예제 파일에는 `loc=0` 과 `loc = 0` 이 모두
  // 나오므로, 붙여 쓴 경우만 다루면 절반을 놓친다.
  const atoms: string[] = body.match(/=|[^\s=]+/g) ?? []

  // 지금 치고 있는 토큰. 공백이나 `=` 로 끝났다면 새 토큰을 막 시작한 것이라
  // 접두사가 비어 있다.
  const startingFresh =
    /\s$/.test(body) || atoms.length === 0 || atoms[atoms.length - 1] === '='
  const current = startingFresh ? '' : (atoms.pop() ?? '')

  if (atoms.length === 0) {
    return { kind: 'command', prefix: current }
  }

  const command = atoms[0] ?? ''

  if (atoms[atoms.length - 1] === '=') {
    return {
      kind: 'value',
      command,
      parameter: atoms.length >= 2 ? (atoms[atoms.length - 2] ?? '') : '',
      prefix: current,
    }
  }

  return { kind: 'parameter', command, prefix: current }
}
