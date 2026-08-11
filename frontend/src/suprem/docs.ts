/** 호버·자동완성에 띄울 마크다운 문서를 만든다. */
import type { CatalogParameter } from '../api/catalog'

export function parameterDocs(
  command: string,
  parameter: CatalogParameter,
): string {
  const lines: string[] = []

  let signature = `\`${command}\` · **${parameter.name}** \`${parameter.type}\``
  if (parameter.default !== null) signature += ` = \`${parameter.default}\``
  lines.push(signature)

  if (parameter.units) lines.push(parameter.units)
  if (parameter.description && parameter.description !== parameter.units) {
    lines.push(`_${parameter.description}_`)
  }

  if (parameter.truncated) {
    // 문서에 적힌 이름과 실제로 써야 하는 이름이 다르다. 말해 주지 않으면
    // 사용자는 오타로 오해하고 원형을 쳤다가 거절당한다.
    lines.push(
      `⚠ 문서상 이름은 \`${parameter.source_name}\` 이지만 시뮬레이터는 ` +
        `이름을 11자까지만 인식합니다. \`${parameter.name}\` 로 써야 합니다.`,
    )
  }

  if (parameter.group) {
    const note = parameter.group_message ?? `\`${parameter.group}\` 중 하나만`
    lines.push(`⚠ 상호배타 (\`${parameter.group}\`): ${note}`)
  }

  if (parameter.error) {
    const note = parameter.message ? ` — ${parameter.message}` : ''
    lines.push(`제약: 다음이면 거절됩니다 \`${parameter.error}\`${note}`)
  }

  return lines.join('\n\n')
}
