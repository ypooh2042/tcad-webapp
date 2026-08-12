/**
 * 커맨드 목록 — 무엇을 찾아야 할지 모를 때 훑어보는 화면.
 *
 * 검색과 역할이 다르다. 검색은 찾을 낱말을 알아야 쓸 수 있는데, 처음 쓰는
 * 사람은 그 낱말을 모른다 — "층을 쌓는 커맨드가 뭐지" 는 검색으로 알아낼 수
 * 없다. 무리별로 늘어놓아야 눈으로 찾을 수 있다.
 *
 * **분류는 매뉴얼 p.51 이 나눈 것을 그대로 쓴다.** 임의로 다시 묶으면 매뉴얼과
 * 대조할 수 없다.
 *
 * 거르기는 서버를 다시 부르지 않는다. 목록 전체가 이미 손에 있고(30KB) 53개뿐
 * 이라, 한 글자마다 왕복하면 느려지기만 한다.
 */
import { useEffect, useMemo, useState } from 'react'
import { docs } from '../../api/endpoints'
import type { DocsReference, DocsReferenceCommand } from '../../api/types'

interface Props {
  onSelect: (command: DocsReferenceCommand) => void
}

function matches(command: DocsReferenceCommand, needle: string): boolean {
  if (!needle) return true
  // 이름만 보면 반쪽이다 — 이름을 모를 때 쓰는 화면이므로 요약도 본다.
  return (
    command.name.toLowerCase().includes(needle) ||
    command.summary.toLowerCase().includes(needle)
  )
}

export function ReferenceBrowser({ onSelect }: Props) {
  const [reference, setReference] = useState<DocsReference | null>(null)
  const [error, setError] = useState(false)
  const [filter, setFilter] = useState('')

  // 목록은 바뀌지 않는다. 탭을 오갈 때마다 받으면 낭비다.
  useEffect(() => {
    let cancelled = false

    docs
      .reference()
      .then((next) => !cancelled && setReference(next))
      .catch(() => !cancelled && setError(true))

    return () => {
      cancelled = true
    }
  }, [])

  const groups = useMemo(() => {
    if (!reference) return []
    const needle = filter.trim().toLowerCase()
    return reference.groups
      .map((group) => ({
        ...group,
        commands: group.commands.filter((command) => matches(command, needle)),
      }))
      // 빈 무리를 남기면 걸러낸 뒤 화면이 제목만 늘어선 모습이 된다.
      .filter((group) => group.commands.length > 0)
  }, [reference, filter])

  if (error) {
    return <p className="muted">커맨드 목록을 불러오지 못했습니다.</p>
  }

  return (
    <div className="reference">
      <label className="reference-filter">
        <span className="sr-only">커맨드 거르기</span>
        <input
          type="search"
          aria-label="커맨드 거르기"
          placeholder="커맨드 거르기 (이름·설명)"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        />
      </label>

      {reference && groups.length === 0 && (
        <p className="muted">맞는 커맨드가 없습니다.</p>
      )}

      {groups.map((group) => (
        // <details> 를 쓰면 접기·펼치기가 브라우저 몫이 되고 키보드로도 열린다.
        <details key={group.name} open>
          <summary>
            {group.name}
            <span className="muted"> {group.commands.length}</span>
          </summary>
          <p className="muted note">{group.note}</p>
          <ul>
            {group.commands.map((command) => (
              <li key={command.name}>
                <button className="link" onClick={() => onSelect(command)}>
                  <code>{command.name}</code>
                </button>
                <span className="muted count">{command.parameter_count}</span>
                {command.documented ? (
                  <p className="muted">{command.summary}</p>
                ) : (
                  // 파라미터는 알려줄 수 있다. 감추면 존재조차 모른다.
                  <p className="muted">매뉴얼 설명 없음 — 파라미터만 있습니다</p>
                )}
              </li>
            ))}
          </ul>
        </details>
      ))}
    </div>
  )
}
