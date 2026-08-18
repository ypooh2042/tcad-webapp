/**
 * 백엔드 호출 한 곳.
 *
 * 인증은 세션 쿠키(httponly)로 한다. 토큰을 JS 가 들고 있으면 XSS 한 번에
 * 새어 나가므로, 브라우저가 알아서 실어 보내게 두고 여기서는 손대지 않는다.
 * 그래서 요청은 반드시 같은 출처로 나가야 한다(개발 중에는 Vite 프록시).
 */

/** FastAPI 의 `detail`. 문자열일 때도 있고 객체일 때도 있다. */
export type ErrorDetail = string | { message?: string; [key: string]: unknown }

export class ApiError extends Error {
  /** 네트워크 자체가 실패하면 0. */
  readonly status: number
  readonly detail: ErrorDetail | null

  constructor(status: number, message: string, detail: ErrorDetail | null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

interface RequestOptions {
  method?: string
  body?: unknown
  signal?: AbortSignal
}

//: 프록시가 막은 응답은 본문이 JSON 이 아니라 상태 코드밖에 단서가 없다.
//: 숫자만 보여주면 고장인지 자기 탓인지 알 수 없다.
const STATUS_MESSAGE: Record<number, string> = {
  429: '요청이 너무 잦습니다. 잠시 뒤 다시 시도해 주세요.',
  502: '서버에 연결하지 못했습니다. 잠시 뒤 다시 시도해 주세요.',
  503: '서버가 요청을 처리할 수 없습니다. 잠시 뒤 다시 시도해 주세요.',
  504: '서버 응답이 너무 늦습니다. 잠시 뒤 다시 시도해 주세요.',
}

function messageFrom(detail: ErrorDetail | null, status: number): string {
  if (typeof detail === 'string') return detail
  if (detail && typeof detail.message === 'string') return detail.message
  return STATUS_MESSAGE[status] ?? `요청이 실패했습니다 (HTTP ${status})`
}

export async function request<T = unknown>(
  path: string,
  { method = 'GET', body, signal }: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  let response: Response
  try {
    response = await fetch(path, {
      method,
      headers,
      signal,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, '서버에 연결할 수 없습니다', null)
  }

  if (!response.ok) {
    // 오류 본문이 JSON 이 아닐 수 있다(nginx 의 502 HTML 등).
    const payload = await response.json().catch(() => null)
    const detail = (payload as { detail?: ErrorDetail } | null)?.detail ?? null
    throw new ApiError(response.status, messageFrom(detail, response.status), detail)
  }

  if (response.status === 204) return null as T
  return (await response.json().catch(() => null)) as T
}
