/**
 * 커서 위치에서 무엇을 완성해야 하는가.
 *
 * 자동완성의 정확도는 거의 전부 이 판정에 달려 있다. 커맨드 자리인데 파라미터
 * 후보를 내밀면 목록이 통째로 쓸모없어진다.
 *
 * 문법은 SUPREM4GS 예제 파일과 실제 실행으로 확인했다:
 *   - 주석은 `#`
 *   - 커맨드 앞의 `%` 는 투명하다. `%structure` 도 `structure` 와 똑같이 돈다
 *   - `${var}` 로 변수를 끼워 넣는다
 *   - `movie="..."` 처럼 따옴표 문자열이 여러 줄에 걸치기도 한다
 */
import { describe, expect, it } from 'vitest'
import { analyzeLine, commandOnLine } from './context'

/** `|` 로 커서 위치를 표시한다. 테스트가 눈으로 읽힌다. */
function at(marked: string) {
  const column = marked.indexOf('|')
  return analyzeLine(marked.replace('|', ''), column)
}

describe('커맨드 자리', () => {
  it('빈 줄에서는 커맨드를 완성한다', () => {
    expect(at('|')).toEqual({ kind: 'command', prefix: '' })
  })

  it('첫 단어를 치는 중이면 커맨드다', () => {
    expect(at('stru|')).toEqual({ kind: 'command', prefix: 'stru' })
  })

  it('앞쪽 공백은 무시한다', () => {
    expect(at('    stru|')).toEqual({ kind: 'command', prefix: 'stru' })
  })

  it('% 접두사는 투명하다', () => {
    // %structure 는 structure 와 똑같이 실행된다(실제 확인).
    expect(at('%stru|')).toEqual({ kind: 'command', prefix: 'stru' })
  })

  it('단어 중간에 커서가 있으면 커서까지만 접두사로 본다', () => {
    expect(at('str|ucture')).toEqual({ kind: 'command', prefix: 'str' })
  })
})

describe('파라미터 자리', () => {
  it('커맨드 뒤 공백이면 파라미터를 완성한다', () => {
    expect(at('structure |')).toEqual({
      kind: 'parameter',
      command: 'structure',
      prefix: '',
    })
  })

  it('두 번째 단어를 치는 중이면 파라미터다', () => {
    expect(at('structure out|')).toEqual({
      kind: 'parameter',
      command: 'structure',
      prefix: 'out',
    })
  })

  it('커맨드는 사용자가 친 그대로 넘긴다', () => {
    // 접두사 해석은 서버가 한다. 여기서 풀어 버리면 모호할 때 알릴 방법이 없다.
    expect(at('stru out|')).toMatchObject({ command: 'stru' })
  })

  it('앞의 인자들을 건너뛴다', () => {
    expect(at('line x loc=0 spac=0.1 ta|')).toEqual({
      kind: 'parameter',
      command: 'line',
      prefix: 'ta',
    })
  })

  it('값 뒤 공백이면 다시 파라미터다', () => {
    expect(at('implant boron dose=3e14 |')).toMatchObject({
      kind: 'parameter',
      prefix: '',
    })
  })
})

describe('값 자리', () => {
  it('= 뒤는 값이다', () => {
    expect(at('structure outfile=|')).toEqual({
      kind: 'value',
      command: 'structure',
      parameter: 'outfile',
      prefix: '',
    })
  })

  it('값을 치는 중인 것도 값이다', () => {
    expect(at('init boron conc=1e1|')).toEqual({
      kind: 'value',
      command: 'init',
      parameter: 'conc',
      prefix: '1e1',
    })
  })

  it('= 양옆의 공백을 허용한다', () => {
    // 예제 파일에 `loc = 0` 처럼 띄어 쓴 줄이 실제로 있다.
    expect(at('line x loc = |')).toMatchObject({
      kind: 'value',
      parameter: 'loc',
    })
  })

  it('괄호가 든 값도 값으로 본다', () => {
    expect(at('select z=log10(bor|')).toMatchObject({
      kind: 'value',
      parameter: 'z',
      prefix: 'log10(bor',
    })
  })
})

describe('완성하면 안 되는 자리', () => {
  it('주석 안에서는 아무것도 완성하지 않는다', () => {
    expect(at('# the vertical def|')).toEqual({ kind: 'none' })
  })

  it('코드 뒤에 붙은 주석도 마찬가지다', () => {
    expect(at('structure out=a.str # save |')).toEqual({ kind: 'none' })
  })

  it('따옴표 안에서는 완성하지 않는다', () => {
    // diffuse movie="..." 안에는 임의의 텍스트가 들어간다.
    expect(at('diffuse movie="some tex|')).toEqual({ kind: 'none' })
  })

  it('따옴표가 닫히면 다시 완성한다', () => {
    expect(at('diffuse movie="x" tem|')).toMatchObject({
      kind: 'parameter',
      prefix: 'tem',
    })
  })

  it('따옴표 안의 # 은 주석이 아니다', () => {
    expect(at('printf "a#b" val|')).toMatchObject({ kind: 'parameter' })
  })
})

describe('변수 보간', () => {
  it('${...} 안에서는 완성하지 않는다', () => {
    // 변수 이름은 카탈로그가 모르는 사용자 정의값이다.
    expect(at('diffuse time=${tot|')).toEqual({ kind: 'none' })
  })

  it('닫힌 뒤에는 정상으로 돌아온다', () => {
    expect(at('diffuse time=${t} tem|')).toMatchObject({
      kind: 'parameter',
      prefix: 'tem',
    })
  })
})

describe('줄의 커맨드', () => {
  it('커맨드 이름을 뽑는다', () => {
    expect(commandOnLine('structure outfile=a.str')).toBe('structure')
  })

  it('파라미터만 있는 자리에서도 그 줄의 커맨드를 준다', () => {
    // 매뉴얼 패널은 커서가 어느 낱말 위인지와 무관하게 따라가야 한다.
    expect(commandOnLine('implant boron dose=3e14 energy=70')).toBe('implant')
  })

  it('접두사를 풀지 않는다', () => {
    // 서버가 시뮬레이터와 같은 규칙으로 해석해야 한다.
    expect(commandOnLine('stru out=a.str')).toBe('stru')
  })

  it('% 접두사를 벗긴다', () => {
    expect(commandOnLine('%diffuse time=30')).toBe('diffuse')
  })

  it('앞쪽 공백을 무시한다', () => {
    expect(commandOnLine('    deposit oxide')).toBe('deposit')
  })

  it('주석 줄에는 커맨드가 없다', () => {
    expect(commandOnLine('# implant boron')).toBeNull()
  })

  it('빈 줄에는 커맨드가 없다', () => {
    expect(commandOnLine('   ')).toBeNull()
  })

  it('숫자로 시작하는 줄은 커맨드가 아니다', () => {
    expect(commandOnLine('123 abc')).toBeNull()
  })
})
