/**
 * 파일 브라우저.
 *
 * 사용자에게는 자기 작업공간이 파일시스템 전부다. 서버가 보내는 경로는 모두
 * 루트 기준이라, 화면 어디에도 서버의 실제 절대경로가 나오지 않는다.
 *
 * **폴더와 `.in` 파일만** 보인다. 서버도 같은 규칙으로 거르지만, 화면이 규칙을
 * 알고 있어야 새 파일 이름에 `.in` 을 붙여 줄 수 있다.
 *
 * 파일을 고르면 알리기만 하고 탭은 건드리지 않는다 — 무엇이 열려 있는지는
 * 작업 화면이 안다.
 *
 * **끌어서 옮길 수 있다.** 서버에서는 이름 바꾸기와 옮기기가 같은 연산이라
 * 새 엔드포인트가 필요 없다. 폴더 위에 떨어뜨리면 그 안으로, 파일 위에
 * 떨어뜨리면 그 파일이 있는 폴더로 들어간다 — 파일은 무언가를 담을 수 없으니
 * 그렇게 읽는 것이 자연스럽다.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError } from '../../api/client'
import { files } from '../../api/endpoints'
import type { FileEntry, FileUsage } from '../../api/types'

/** 새 파일에 넣어 둘 뼈대. 빈 파일로 시작하면 무엇을 쓸지 막막하다. */
const STARTER = `mode one.dim
line x loc = 0    spacing = 0.05 tag = top
line x loc = 1.0  spacing = 0.10 tag = bottom
region silicon xlo = top xhi = bottom
bound exposed xlo = top xhi = top
init boron conc = 1e15
structure outfile = result.str
`

interface Props {
  onOpen: (path: string) => void
  onClose: () => void
}

function megabytes(bytes: number): string {
  return `${(bytes / 1_048_576).toFixed(1)}MB`
}

/** 부모 폴더 경로. 루트 바로 아래면 빈 문자열. */
function parentOf(path: string): string {
  const cut = path.lastIndexOf('/')
  return cut < 0 ? '' : path.slice(0, cut)
}

function join(folder: string, name: string): string {
  return folder ? `${folder}/${name}` : name
}

export function FileBrowser({ onOpen, onClose }: Props) {
  const [entries, setEntries] = useState<FileEntry[]>([])
  const [usage, setUsage] = useState<FileUsage | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  //: 지금 끌고 있는 것 위에 올라와 있는 대상. 어디에 떨어질지 보여준다.
  const [dropTarget, setDropTarget] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [tree, used] = await Promise.all([files.tree(), files.usage()])
      setEntries(tree.entries)
      setUsage(used)
      setError(null)
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : '목록을 불러오지 못했습니다',
      )
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  /** 접힌 폴더 안은 감춘다. 다 펴 놓으면 파일이 많아질수록 안 보인다. */
  const visible = useMemo(
    () =>
      entries.filter((entry) => {
        const parent = parentOf(entry.path)
        if (!parent) return true
        // 조상이 하나라도 접혀 있으면 보이지 않는다.
        const parts = parent.split('/')
        return parts.every((_, index) =>
          expanded.has(parts.slice(0, index + 1).join('/')),
        )
      }),
    [entries, expanded],
  )

  async function guard(action: () => Promise<unknown>) {
    try {
      await action()
      await load()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : '처리하지 못했습니다')
    }
  }

  function toggle(path: string) {
    setExpanded((current) => {
      const next = new Set(current)
      if (!next.delete(path)) next.add(path)
      return next
    })
  }

  function createFile() {
    const name = window.prompt('새 파일 이름')
    if (!name) return
    // 확장자를 빼먹으면 서버가 거절한다. 사용자가 규칙을 외울 이유가 없다.
    const filename = name.toLowerCase().endsWith('.in') ? name : `${name}.in`
    void guard(() => files.write(filename, STARTER))
  }

  function createFolder() {
    const name = window.prompt('새 폴더 이름')
    if (!name) return
    void guard(() => files.makeFolder(name))
  }

  function rename(entry: FileEntry) {
    // 이름만 묻는다. 경로째 물으면 사용자가 폴더 구조를 손으로 써야 한다.
    const name = window.prompt('새 이름', entry.name)
    if (!name || name === entry.name) return
    void guard(() =>
      files.rename(entry.path, join(parentOf(entry.path), name)),
    )
  }

  /** 떨어뜨린 지점이 뜻하는 폴더. 파일 위면 그 파일이 든 폴더다. */
  function folderOf(entry: FileEntry): string {
    return entry.is_dir ? entry.path : parentOf(entry.path)
  }

  function moveInto(sourcePath: string, target: FileEntry) {
    const source = entries.find((entry) => entry.path === sourcePath)
    if (!source || source.path === target.path) return

    const folder = folderOf(target)
    // 이미 그 폴더에 있으면 할 일이 없다.
    if (parentOf(source.path) === folder) return
    // 폴더를 자기 안으로 넣으면 트리가 끊겨 되돌릴 수 없다. 서버도 막지만
    // 화면에서 먼저 막아야 실패 메시지를 볼 일이 없다.
    if (source.is_dir && (folder === source.path || folder.startsWith(`${source.path}/`))) {
      return
    }

    void guard(() => files.rename(source.path, join(folder, source.name)))
  }

  function remove(entry: FileEntry) {
    const warning = entry.is_dir
      ? `'${entry.name}' 폴더를 지웁니다.\n안의 파일도 모두 사라지며 되돌릴 수 없습니다.`
      : `'${entry.name}' 을(를) 지웁니다. 되돌릴 수 없습니다.`
    if (!window.confirm(warning)) return
    void guard(() => files.remove(entry.path))
  }

  return (
    <div className="file-browser" role="dialog" aria-label="내 파일">
      <header>
        <h2>내 파일</h2>
        <button onClick={createFile}>새 파일</button>
        <button onClick={createFolder}>새 폴더</button>
        <div className="spacer" />
        {usage && (
          <span className="muted">
            {megabytes(usage.used_bytes)} / {megabytes(usage.quota_bytes)}
          </span>
        )}
        <button className="link" onClick={onClose}>
          닫기
        </button>
      </header>

      {error && <p className="error">{error}</p>}

      {entries.length === 0 && !error && (
        <p className="muted">파일이 없습니다. 새 파일을 만들어 보세요.</p>
      )}

      <ul className="file-tree">
        {visible.map((entry) => (
          <li
            key={entry.path}
            className={dropTarget === entry.path ? 'drop-target' : undefined}
            style={
              { '--depth': entry.path.split('/').length - 1 } as React.CSSProperties
            }
            draggable
            onDragStart={(event) => {
              event.dataTransfer.setData('text/plain', entry.path)
              event.dataTransfer.effectAllowed = 'move'
            }}
            onDragOver={(event) => {
              // preventDefault 를 하지 않으면 브라우저가 드롭을 받지 않는다.
              event.preventDefault()
              event.dataTransfer.dropEffect = 'move'
              setDropTarget(entry.path)
            }}
            onDragLeave={() =>
              setDropTarget((current) => (current === entry.path ? null : current))
            }
            onDrop={(event) => {
              event.preventDefault()
              setDropTarget(null)
              moveInto(event.dataTransfer.getData('text/plain'), entry)
            }}
            onDragEnd={() => setDropTarget(null)}
          >
            <button
              className="link name"
              onClick={() => (entry.is_dir ? toggle(entry.path) : onOpen(entry.path))}
            >
              <span aria-hidden="true">
                {entry.is_dir ? (expanded.has(entry.path) ? '▾' : '▸') : '·'}
              </span>{' '}
              {entry.name}
            </button>
            {!entry.is_dir && (
              <span className="muted size">{entry.size_bytes}B</span>
            )}
            <button className="link" onClick={() => rename(entry)}>
              이름 바꾸기
            </button>
            <button className="link danger" onClick={() => remove(entry)}>
              삭제
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
