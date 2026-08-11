/**
 * 관리자 화면: 초대 코드 발급·조회·회수.
 *
 * 평문 코드는 **발급 응답에서만** 볼 수 있다. 서버가 해시만 저장하기 때문에
 * 목록에서는 다시 꺼낼 수 없다. 그래서 발급 직후 화면에 크게 띄우고, 다시 볼
 * 수 없다는 사실을 분명히 말한다 — 모르고 닫으면 재발급밖에 방법이 없다.
 */
import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../../api/client'
import { admin } from '../../api/endpoints'
import type { InviteSummary, IssuedInvite } from '../../api/types'

const MAX_USES_LIMIT = 10
const MAX_VALID_DAYS = 90

function formatDate(value: string): string {
  return new Date(value).toLocaleString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function statusOf(invite: InviteSummary): string {
  if (invite.revoked) return '회수됨'
  if (invite.used_count >= invite.max_uses) return '모두 사용'
  if (new Date(invite.expires_at) <= new Date()) return '기한 지남'
  return '사용 가능'
}

export function AdminPanel({ onClose }: { onClose: () => void }) {
  const [invites, setInvites] = useState<InviteSummary[]>([])
  const [issued, setIssued] = useState<IssuedInvite | null>(null)
  const [maxUses, setMaxUses] = useState(1)
  const [validDays, setValidDays] = useState(7)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)

  const report = useCallback((caught: unknown) => {
    setError(caught instanceof ApiError ? caught.message : '알 수 없는 오류입니다')
  }, [])

  const refresh = useCallback(() => {
    admin.listInvites().then(setInvites).catch(report)
  }, [report])

  useEffect(refresh, [refresh])

  async function issue() {
    setBusy(true)
    setError(null)
    setCopied(false)
    try {
      setIssued(await admin.issueInvite(maxUses, validDays))
      refresh()
    } catch (caught) {
      report(caught)
    } finally {
      setBusy(false)
    }
  }

  async function revoke(inviteId: number) {
    try {
      await admin.revokeInvite(inviteId)
      // 방금 발급한 코드를 회수했다면 화면에서도 지운다. 남겨 두면 이미 못 쓰는
      // 코드를 그대로 전달하게 된다.
      setIssued((current) => (current?.id === inviteId ? null : current))
      refresh()
    } catch (caught) {
      report(caught)
    }
  }

  async function copy(code: string) {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
    } catch {
      // 클립보드 권한이 없을 수 있다. 코드는 화면에 그대로 보이므로 치명적이지
      // 않다.
      setError('클립보드에 복사하지 못했습니다. 직접 선택해 복사해 주세요.')
    }
  }

  return (
    <section className="admin" aria-label="관리자">
      <header>
        <h2>초대 코드</h2>
        <button className="link" onClick={onClose}>
          닫기
        </button>
      </header>

      {error && <p role="alert" className="error">{error}</p>}

      <div className="issue">
        <label htmlFor="max-uses">사용 횟수</label>
        <input
          id="max-uses"
          type="number"
          min={1}
          max={MAX_USES_LIMIT}
          value={maxUses}
          onChange={(event) => setMaxUses(Number(event.target.value))}
        />
        <label htmlFor="valid-days">유효 기간(일)</label>
        <input
          id="valid-days"
          type="number"
          min={1}
          max={MAX_VALID_DAYS}
          value={validDays}
          onChange={(event) => setValidDays(Number(event.target.value))}
        />
        <button className="primary" onClick={() => void issue()} disabled={busy}>
          발급
        </button>
      </div>

      {issued && (
        <div className="issued" role="status">
          <p className="warn">
            지금만 볼 수 있습니다. 서버에는 해시만 저장되어 나중에 다시 확인할 수
            없습니다.
          </p>
          <div className="code-row">
            <code>{issued.code}</code>
            <button onClick={() => void copy(issued.code)}>
              {copied ? '복사됨' : '복사'}
            </button>
          </div>
          <p className="muted">
            {formatDate(issued.expires_at)}까지 · {issued.max_uses}회
          </p>
        </div>
      )}

      {invites.length > 0 && (
        <table className="invites">
          <thead>
            <tr>
              <th>발급</th>
              <th>사용</th>
              <th>만료일</th>
              <th>상태</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {invites.map((invite) => (
              <tr key={invite.id} className={invite.usable ? '' : 'spent'}>
                <td>#{invite.id}</td>
                <td>
                  {invite.used_count}/{invite.max_uses}
                </td>
                <td>{formatDate(invite.expires_at)}</td>
                <td>{statusOf(invite)}</td>
                <td>
                  {!invite.revoked && (
                    <button
                      className="link"
                      onClick={() => void revoke(invite.id)}
                    >
                      회수
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
