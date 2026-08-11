/**
 * 카탈로그 캐시.
 *
 * 자동완성은 키 입력마다 불린다. 카탈로그는 배포 중에 바뀌지 않으므로 한 번
 * 받아 두고 걸러 쓴다. 서버 왕복을 없애면 목록이 커서를 바로 따라온다.
 */
import { request } from './client'

export interface CatalogParameter {
  name: string
  type: string
  source_name: string
  truncated: boolean
  default: string | null
  units: string | null
  description: string | null
  error: string | null
  message: string | null
  group: string | null
  group_message: string | null
  unreachable: boolean
}

export interface CatalogCommand {
  name: string
  source_name: string
  description: string | null
  parameters: CatalogParameter[]
}

export interface Word {
  name: string
  kind: 'command' | 'keyword'
  description: string | null
}

interface CommandListResponse {
  commands: { name: string; description: string | null; parameter_count: number }[]
  keywords: { name: string; description: string }[]
}

export class CatalogCache {
  /** 진행 중인 요청을 그대로 들고 있어 겹친 호출이 하나로 합쳐지게 한다. */
  private wordsPromise: Promise<Word[]> | null = null
  private commands = new Map<string, Promise<CatalogCommand | null>>()

  words(): Promise<Word[]> {
    this.wordsPromise ??= request<CommandListResponse>('/api/catalog/commands')
      .then((body) => [
        ...body.commands.map((c) => ({
          name: c.name,
          kind: 'command' as const,
          description: c.description,
        })),
        ...body.keywords.map((k) => ({
          name: k.name,
          kind: 'keyword' as const,
          description: k.description,
        })),
      ])
      .catch(() => {
        // 다음 입력 때 다시 시도할 수 있게 실패한 약속은 버린다.
        this.wordsPromise = null
        return []
      })
    return this.wordsPromise
  }

  command(token: string): Promise<CatalogCommand | null> {
    const cached = this.commands.get(token)
    if (cached) return cached

    const pending = request<CatalogCommand>(
      `/api/catalog/commands/${encodeURIComponent(token)}`,
    )
      .then((command) => {
        // `stru` 로 받아 온 결과는 `structure` 의 것이다. 정식 이름으로도
        // 넣어 두면 같은 커맨드를 두 번 받지 않는다.
        this.commands.set(command.name, Promise.resolve(command))
        return command
      })
      .catch(() => {
        // 오타나 모호한 접두사에서는 404/409 가 정상적으로 난다. 자동완성이
        // 예외로 죽으면 안 되므로 없는 것으로 처리한다. 다만 캐시에는 남기지
        // 않는다 — 사용자가 더 치면 결과가 달라진다.
        this.commands.delete(token)
        return null
      })

    this.commands.set(token, pending)
    return pending
  }

  async parameters(token: string): Promise<CatalogParameter[]> {
    const command = await this.command(token)
    if (!command) return []
    // 도달 불가 파라미터는 고를 수 없다. 목록에 두면 사용자가 골랐다가
    // 시뮬레이터에게 ambiguous 로 거절당한다.
    return command.parameters.filter((parameter) => !parameter.unreachable)
  }
}

export const catalog = new CatalogCache()
