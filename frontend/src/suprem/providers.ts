/**
 * Monaco 자동완성·호버 제공자.
 *
 * 후보는 카탈로그 캐시에서 걸러 낸다. 커서 위치 판정은 context.ts 가 하고,
 * 접두사 해석은 서버가 한다(모호함을 판정하려면 전체 이름 집합이 필요하다).
 */
import type * as monacoNs from 'monaco-editor'
import { catalog } from '../api/catalog'
import { analyzeLine } from './context'
import { parameterDocs } from './docs'
import { LANGUAGE_ID } from './language'

type Monaco = typeof monacoNs

/** 커서가 걸쳐 있는 낱말. 호버 대상을 찾는 데 쓴다. */
function wordAt(
  model: monacoNs.editor.ITextModel,
  position: monacoNs.Position,
): string | null {
  return model.getWordAtPosition(position)?.word ?? null
}

function lineUpTo(
  model: monacoNs.editor.ITextModel,
  position: monacoNs.Position,
): { line: string; column: number } {
  return {
    line: model.getLineContent(position.lineNumber),
    // Monaco 의 column 은 1부터 센다.
    column: position.column - 1,
  }
}

export function registerSupremProviders(monaco: Monaco): monacoNs.IDisposable[] {
  const completion = monaco.languages.registerCompletionItemProvider(
    LANGUAGE_ID,
    {
      // `=` 뒤와 공백 뒤에서도 목록이 뜨게 한다. 기본값은 낱말 문자뿐이다.
      triggerCharacters: [' ', '=', '.'],

      async provideCompletionItems(model, position) {
        const { line, column } = lineUpTo(model, position)
        const context = analyzeLine(line, column)
        if (context.kind === 'none' || context.kind === 'value') {
          // 값은 카탈로그가 모른다(파일 이름, 수식, 사용자 변수).
          return { suggestions: [] }
        }

        const word = model.getWordUntilPosition(position)
        const range = {
          startLineNumber: position.lineNumber,
          endLineNumber: position.lineNumber,
          startColumn: word.startColumn,
          endColumn: word.endColumn,
        }

        if (context.kind === 'command') {
          const words = await catalog.words()
          return {
            suggestions: words
              .filter((entry) => entry.name.startsWith(context.prefix))
              .map((entry) => ({
                label: entry.name,
                kind:
                  entry.kind === 'keyword'
                    ? monaco.languages.CompletionItemKind.Keyword
                    : monaco.languages.CompletionItemKind.Function,
                insertText: entry.name,
                detail: entry.description ?? undefined,
                range,
              })),
          }
        }

        const parameters = await catalog.parameters(context.command)
        return {
          suggestions: parameters
            .filter((parameter) => parameter.name.startsWith(context.prefix))
            .map((parameter) => ({
              label: parameter.name,
              kind:
                parameter.type === 'boolean'
                  ? monaco.languages.CompletionItemKind.EnumMember
                  : monaco.languages.CompletionItemKind.Property,
              // boolean 은 값을 받지 않는다. `=` 를 붙이면 오히려 틀린 줄이 된다.
              insertText:
                parameter.type === 'boolean'
                  ? parameter.name
                  : `${parameter.name}=`,
              detail: parameter.units ?? undefined,
              documentation: {
                value: parameterDocs(context.command, parameter),
              },
              range,
            })),
        }
      },
    },
  )

  const hover = monaco.languages.registerHoverProvider(LANGUAGE_ID, {
    async provideHover(model, position) {
      const word = wordAt(model, position)
      if (!word) return null

      const { line } = lineUpTo(model, position)
      const context = analyzeLine(line, position.column - 1)

      if (context.kind === 'command') {
        const words = await catalog.words()
        const entry = words.find((candidate) => candidate.name === word)
        if (!entry) return null
        return {
          contents: [
            { value: `**${entry.name}** \`${entry.kind}\`` },
            { value: entry.description ?? '' },
          ],
        }
      }

      const command =
        context.kind === 'none' ? null : context.command
      if (!command) return null

      const parameters = await catalog.parameters(command)
      const parameter = parameters.find((candidate) => candidate.name === word)
      if (!parameter) return null

      return { contents: [{ value: parameterDocs(command, parameter) }] }
    },
  })

  return [completion, hover]
}
