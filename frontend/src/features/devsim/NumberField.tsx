/**
 * 숫자 입력칸.
 *
 * **치는 도중의 글자를 그대로 둔다.** 값을 매번 다시 문자열로 만들어 넣으면
 * `"0."` 이 `Number("0.") = 0` 을 거쳐 `"0"` 으로 되돌아가고, 소수점을 아예
 * 칠 수 없게 된다(게이트 단계 전압이 정수로만 들어가던 것이 이것이었다).
 * 그래서 글자는 이 칸이 들고 있고, 숫자로 읽히는 동안에만 바깥에 알린다.
 *
 * `type="number"` 를 쓰지 않는 이유도 같다. 브라우저마다 중간 상태
 * (`"-"`, `"1e"`, `"0."`)를 다르게 다루고, React 가 값을 되돌려 넣는 순간
 * 그 글자가 사라진다. `inputMode="decimal"` 로 모바일 자판만 숫자로 맞춘다.
 */
import { useEffect, useRef, useState } from 'react'

/** 쉼표로 나눈 숫자들. 아직 숫자가 아닌 조각은 버린다. */
export function parseNumberList(text: string): number[] {
  return text
    .split(',')
    .map((part) => part.trim())
    .filter((part) => part !== '')
    .map((part) => Number(part))
    .filter((value) => Number.isFinite(value))
}

export function formatNumberList(values: number[]): string {
  return values.join(', ')
}

/**
 * 바깥에서 값이 바뀌었을 때만 글자를 다시 맞춘다.
 *
 * 내가 친 글자가 그대로 돌아온 것인지(그러면 두어야 한다) 다른 곳에서 값이
 * 바뀐 것인지(그러면 따라가야 한다)를, **내 글자를 읽은 결과**와 비교해 가른다.
 * `"0."` 을 쳤으면 읽은 결과가 `0` 이고 바깥 값도 `0` 이니 글자를 안 건드린다.
 */
function useDraft<T>(
  value: T,
  format: (value: T) => string,
  read: (text: string) => T | null,
  same: (a: T, b: T) => boolean,
): [string, (text: string) => void] {
  const [draft, setDraft] = useState(() => format(value))
  const typed = useRef(draft)

  useEffect(() => {
    const mine = read(typed.current)
    if (mine !== null && same(mine, value)) return
    const next = format(value)
    typed.current = next
    setDraft(next)
    // format/read/same 은 이 훅을 쓰는 쪽에서 상수로 넘긴다. 목록에 넣으면
    // 매 렌더마다 새 함수라 글자가 계속 되돌아간다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  return [
    draft,
    (text: string) => {
      typed.current = text
      setDraft(text)
    },
  ]
}

interface ListProps {
  label: string
  values: number[]
  onChange: (values: number[]) => void
}

export function NumberListField({ label, values, onChange }: ListProps) {
  const [draft, setDraft] = useDraft(
    values,
    formatNumberList,
    parseNumberList,
    (a, b) => a.length === b.length && a.every((one, at) => one === b[at]),
  )

  return (
    <label className="field">
      {label}
      <input
        inputMode="decimal"
        value={draft}
        aria-label={label}
        onChange={(event) => {
          setDraft(event.target.value)
          onChange(parseNumberList(event.target.value))
        }}
      />
    </label>
  )
}

interface Props {
  label: string
  value: number
  onChange: (value: number) => void
}

/** 한 칸에 숫자 하나. 숫자로 읽히는 동안에만 바깥에 알린다. */
export function NumberField({ label, value, onChange }: Props) {
  const [draft, setDraft] = useDraft(
    value,
    (one) => String(one),
    (text) => {
      const trimmed = text.trim()
      if (trimmed === '') return null
      const read = Number(trimmed)
      return Number.isFinite(read) ? read : null
    },
    (a, b) => a === b,
  )

  return (
    <label className="field">
      {label}
      <input
        inputMode="decimal"
        value={draft}
        aria-label={label}
        onChange={(event) => {
          const text = event.target.value
          setDraft(text)
          const read = Number(text.trim())
          // 빈칸이나 `"-"` 같은 중간 상태에서는 알리지 않는다. 알리면 0 이
          // 되돌아와 지우고 다시 칠 수가 없다.
          if (text.trim() !== '' && Number.isFinite(read)) onChange(read)
        }}
      />
    </label>
  )
}
