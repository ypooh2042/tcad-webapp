/**
 * 이름 입력칸.
 *
 * **치는 동안에는 바깥을 건드리지 않는다.** 한 글자마다 이름을 바꾸면 그 이름을
 * 열쇠로 쓰는 곳이 전부 따라 움직이고, 목록 항목이 새로 만들어지면서 입력칸이
 * 포커스를 잃는다 — 전극 이름이 실제로 그래서 한 글자밖에 못 쳐졌다.
 *
 * 다 치고 칸에서 벗어날 때(또는 Enter) 한 번만 알린다. 바깥이 받아들이지 않으면
 * (겹치는 이름 같은 것) 값이 그대로 돌아오므로 칸도 원래대로 되돌아간다.
 */
import { useEffect, useState } from 'react'

interface Props {
  /** 화면에 읽히는 이름. `aria-label` 로 붙는다. */
  label: string
  value: string
  /** 다 치고 난 뒤 한 번 불린다. 빈 이름은 바깥에서 거절하면 된다. */
  onCommit: (name: string) => void
  className?: string
}

export function NameField({ label, value, onCommit, className }: Props) {
  const [draft, setDraft] = useState(value)

  // 바깥에서 값이 바뀌면 따라간다. 받아들여졌을 때와, 다른 곳에서 바뀌었을 때
  // 둘 다 여기로 온다.
  useEffect(() => {
    setDraft(value)
  }, [value])

  function commit() {
    const trimmed = draft.trim()
    // 되돌려 놓고 알린다. 바깥이 받아들이면 위 effect 가 새 값으로 다시 맞추고,
    // 거절하면 이 자리 그대로 남아 원래 이름이 보인다.
    setDraft(value)
    if (trimmed && trimmed !== value) onCommit(trimmed)
  }

  return (
    <input
      className={className}
      value={draft}
      aria-label={label}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === 'Enter') event.currentTarget.blur()
        if (event.key === 'Escape') setDraft(value)
      }}
    />
  )
}
