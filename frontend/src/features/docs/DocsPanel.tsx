/**
 * 매뉴얼 패널.
 *
 * 기본 동작은 **커서를 따라가는 것**이다. 편집기에서 커서가 놓인 줄의 커맨드
 * 문서를 자동으로 띄운다 — 문서를 보려고 손을 멈추는 순간이 가장 흔한 마찰이기
 * 때문이다. 검색으로 직접 찾아볼 수도 있다.
 *
 * 접두사 해석은 서버가 한다. 사용자가 `stru` 라고 치면 시뮬레이터가 structure
 * 로 받아들이므로 문서도 같아야 한다.
 */
import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../../api/client'
import { docs } from '../../api/endpoints'
import type {
  DocsReferenceCommand,
  DocsSearchHit,
  DocsSection,
} from '../../api/types'
import { ParameterTable } from './ParameterTable'
import { ReferenceBrowser } from './ReferenceBrowser'

type Tab = 'manual' | 'parameters' | 'reference'

/** 매뉴얼은 고정폭으로 조판돼 있어 그대로 두면 줄이 어색하게 끊긴다. */
const SUBSECTION_ORDER = [
  'SUMMARY',
  'SYNOPSIS',
  'DESCRIPTION',
  'EXAMPLES',
  'REFERENCES',
  'SEE ALSO',
]

function orderedEntries(subsections: Record<string, string>) {
  const known = SUBSECTION_ORDER.filter((name) => subsections[name])
  const rest = Object.keys(subsections).filter(
    (name) => !SUBSECTION_ORDER.includes(name),
  )
  return [...known, ...rest].map((name) => [name, subsections[name]!] as const)
}

interface Props {
  /** 편집기 커서가 놓인 줄의 커맨드. 없으면 안내를 보여준다. */
  command: string | null
  onClose: () => void
}

export function DocsPanel({ command, onClose }: Props) {
  const [section, setSection] = useState<DocsSection | null>(null)
  const [hits, setHits] = useState<DocsSearchHit[] | null>(null)
  const [query, setQuery] = useState('')
  const [notice, setNotice] = useState<string | null>(null)
  const [pinned, setPinned] = useState(false)
  const [tab, setTab] = useState<Tab>('manual')
  //: 목록에서 고른 커맨드. 매뉴얼 본문이 없는 커맨드도 있어서(suprem.key 에만
  //  있는 것들) 섹션과 따로 들고 있어야 파라미터를 보여줄 수 있다.
  const [picked, setPicked] = useState<string | null>(null)

  const load = useCallback((id: string) => {
    docs
      .section(id)
      .then((next) => {
        setSection(next)
        setHits(null)
        setNotice(null)
        // 직접 고른 문서는 커서가 움직여도 유지한다. 그러지 않으면 읽는 도중
        // 편집기를 건드리는 순간 사라진다.
        setPinned(true)
      })
      .catch((error) =>
        setNotice(error instanceof ApiError ? error.message : '불러오지 못했습니다'),
      )
  }, [])

  // 커서를 따라간다. 직접 고른 문서가 있으면 그대로 둔다.
  useEffect(() => {
    if (pinned || !command) return
    let cancelled = false

    docs
      .forCommand(command)
      .then((next) => {
        if (cancelled) return
        setSection(next)
        setNotice(null)
      })
      .catch(() => {
        if (cancelled) return
        // 모호한 접두사(str)이거나 아직 다 치지 않은 이름이다. 흔한 상황이라
        // 오류로 보여주지 않는다.
        setSection(null)
        setNotice(`'${command}' 에 해당하는 문서가 없습니다`)
      })

    return () => {
      cancelled = true
    }
  }, [command, pinned])

  function pick(command: DocsReferenceCommand) {
    setPicked(command.name)
    if (command.manual_section_id) {
      load(command.manual_section_id)
      setTab('manual')
      return
    }
    // 매뉴얼에 본문이 없다. 매뉴얼 탭으로 보내면 빈 화면만 뜨므로 알려줄 것이
    // 있는 쪽(파라미터)으로 보낸다.
    setSection(null)
    setNotice(`'${command.name}' 은 매뉴얼에 설명이 없습니다. 파라미터만 있습니다.`)
    setPinned(true)
    setTab('parameters')
  }

  async function runSearch(event: React.FormEvent) {
    event.preventDefault()
    if (query.trim().length < 2) {
      setNotice('두 글자 이상 입력해 주세요')
      return
    }
    try {
      const result = await docs.search(query)
      setHits(result.hits)
      setNotice(result.hits.length ? null : '검색 결과가 없습니다')
    } catch (error) {
      setNotice(error instanceof ApiError ? error.message : '검색하지 못했습니다')
    }
  }

  return (
    <aside className="docs" aria-label="매뉴얼">
      <header>
        <h2>매뉴얼</h2>
        {pinned && (
          <button
            className="link"
            onClick={() => {
              setPinned(false)
              setHits(null)
              setPicked(null)
            }}
          >
            커서 따라가기
          </button>
        )}
        <div className="spacer" />
        <button className="link" onClick={onClose}>
          닫기
        </button>
      </header>

      <div className="tabs" role="tablist">
        {/* 매뉴얼은 "무엇을 하는가", 파라미터는 "무엇을 받는가"다. 출처도
            다르다 — 전자는 PDF, 후자는 suprem.key. */}
        <button
          role="tab"
          aria-selected={tab === 'manual'}
          className={tab === 'manual' ? 'tab active' : 'tab'}
          onClick={() => setTab('manual')}
        >
          매뉴얼
        </button>
        <button
          role="tab"
          aria-selected={tab === 'parameters'}
          className={tab === 'parameters' ? 'tab active' : 'tab'}
          onClick={() => setTab('parameters')}
        >
          파라미터
        </button>
        {/* 검색은 찾을 낱말을 알아야 쓴다. 처음 쓰는 사람은 그 낱말을 모르므로
            훑어볼 목록이 따로 있어야 한다. */}
        <button
          role="tab"
          aria-selected={tab === 'reference'}
          className={tab === 'reference' ? 'tab active' : 'tab'}
          onClick={() => setTab('reference')}
        >
          목록
        </button>
      </div>

      {/* 안내는 탭 밖에 둔다. 목록에서 문서 없는 커맨드를 고르면 파라미터 탭으로
          보내지는데, 안내가 매뉴얼 탭 안에만 있으면 왜 옮겨졌는지 알 수 없다. */}
      {notice && <p className="muted">{notice}</p>}

      {tab === 'reference' && <ReferenceBrowser onSelect={pick} />}

      {tab === 'parameters' && (
        <ParameterTable
          command={pinned ? (picked ?? section?.command ?? null) : command}
        />
      )}

      {tab === 'manual' && (
      <>
      <form onSubmit={runSearch} className="docs-search">
        <input
          type="search"
          aria-label="매뉴얼 검색"
          placeholder="매뉴얼 검색"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <button type="submit">찾기</button>
      </form>

      {hits && (
        <ul className="docs-hits">
          {hits.map((hit) => (
            <li key={hit.id}>
              <button className="link" onClick={() => load(hit.id)}>
                {hit.title}
              </button>
              <p className="muted">{hit.snippet}</p>
            </li>
          ))}
        </ul>
      )}

      {!hits && section && (
        <article>
          <h3>{section.title}</h3>
          <p className="muted">
            매뉴얼 {section.page_start}
            {section.page_end !== section.page_start && `–${section.page_end}`} 쪽
          </p>
          {orderedEntries(section.subsections).map(([name, body]) => (
            <section key={name}>
              <h4>{name}</h4>
              {/* 매뉴얼은 고정폭 조판이다. 그대로 보여야 SYNOPSIS 의 정렬이 산다. */}
              <pre>{body}</pre>
            </section>
          ))}
        </article>
      )}

      {!hits && !section && !notice && (
        <p className="muted">
          편집기에서 커맨드에 커서를 두면 그 문서가 여기 나옵니다.
        </p>
      )}
      </>
      )}
    </aside>
  )
}
