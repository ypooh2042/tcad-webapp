/**
 * 커맨드가 받는 파라미터 전체 목록.
 *
 * 자동완성과 호버로는 "지금 치고 있는 것" 하나만 보인다. 무엇을 쓸 수 있는지
 * 훑어보려면 표가 필요하다.
 *
 * 내용은 전부 카탈로그(suprem.key)에서 온다. 매뉴얼 산문과 짝을 이룬다 —
 * 매뉴얼은 "이 커맨드가 무엇을 하는가", 여기는 "무엇을 받는가"다.
 */
import { useEffect, useState } from 'react'
import { ApiError } from '../../api/client'
import { catalog } from '../../api/catalog'
import type { CatalogParameter } from '../../api/catalog'

/** 같은 묶음(switch)의 파라미터끼리 모아 보여준다. */
function groupOf(parameter: CatalogParameter): string {
  return parameter.group ?? ''
}

function defaultText(parameter: CatalogParameter): string {
  if (parameter.default !== null) return parameter.default
  // boolean 은 값을 받지 않는다. 빈칸으로 두면 "기본값 없음"과 헷갈린다.
  return parameter.type === 'boolean' ? '(플래그)' : '—'
}

export function ParameterTable({ command }: { command: string | null }) {
  const [parameters, setParameters] = useState<CatalogParameter[] | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    if (!command) {
      setParameters(null)
      setNotice(null)
      return
    }
    let cancelled = false

    catalog
      .command(command)
      .then((found) => {
        if (cancelled) return
        if (!found) {
          setParameters(null)
          setNotice(`'${command}' 에 해당하는 커맨드가 없습니다`)
          return
        }
        setParameters(found.parameters)
        setNotice(found.parameters.length ? null : '이 커맨드는 파라미터가 없습니다')
      })
      .catch((error) => {
        if (cancelled) return
        setNotice(
          error instanceof ApiError ? error.message : '불러오지 못했습니다',
        )
      })

    return () => {
      cancelled = true
    }
  }, [command])

  if (!command) {
    return (
      <p className="muted">
        편집기에서 커맨드에 커서를 두면 그 파라미터가 여기 나옵니다.
      </p>
    )
  }

  if (notice) return <p className="muted">{notice}</p>
  if (!parameters) return <p className="muted">불러오는 중…</p>

  // 묶음이 없는 것을 먼저, 그다음 묶음별로 모은다.
  const sorted = [...parameters].sort((a, b) =>
    groupOf(a).localeCompare(groupOf(b)),
  )

  return (
    <table className="params">
      <thead>
        <tr>
          <th>이름</th>
          <th>타입</th>
          <th>기본값</th>
          <th>설명</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((parameter) => (
          <tr
            key={parameter.name}
            className={parameter.unreachable ? 'unreachable' : ''}
          >
            <td>
              <code>{parameter.name}</code>
              {parameter.truncated && (
                // 문서에는 concentration 으로 적혀 있는데 시뮬레이터는
                // concentrati 만 받는다. 말해 주지 않으면 오타로 오해한다.
                <span
                  className="badge warn"
                  title={`문서상 이름은 ${parameter.source_name} 이지만 시뮬레이터는 11자까지만 인식합니다`}
                >
                  잘림
                </span>
              )}
              {parameter.unreachable && (
                // 다른 이름의 진접두사라 어떤 입력으로도 지목할 수 없다.
                <span
                  className="badge error"
                  title="다른 파라미터 이름의 앞부분과 겹쳐 지정할 수 없습니다"
                >
                  사용 불가
                </span>
              )}
              {parameter.group && (
                <span
                  className="badge group"
                  title={
                    parameter.group_message ??
                    `${parameter.group} 중 하나만 고를 수 있습니다`
                  }
                >
                  {parameter.group}
                </span>
              )}
            </td>
            <td className="muted">{parameter.type}</td>
            <td className="muted">{defaultText(parameter)}</td>
            <td>
              {parameter.units ?? parameter.description ?? ''}
              {parameter.error && (
                <div className="constraint">
                  제약: <code>{parameter.error}</code>
                  {parameter.message && ` — ${parameter.message}`}
                </div>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
