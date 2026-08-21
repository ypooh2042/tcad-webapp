/**
 * 머리말 오른쪽의 계정 표시 — 접속 현황, 이메일, 관리자, 로그아웃.
 *
 * **화면마다 하나씩 있어야 한다.** 공정 화면에만 두었더니 소자 해석 화면에서
 * 나갈 방법이 없었다(공정 쪽은 숨겨져 있어 버튼이 눌리지 않는다). 브라우저
 * 시험에서 로그아웃이 조용히 실패해 세션이 정원까지 쌓이는 것으로 드러났다.
 */
import { useAuth } from './AuthContext'
import { occupancyLabel, occupancyTitle, useOccupancy } from './useOccupancy'

interface Props {
  /** 관리자 패널을 여는 신호. 없으면 관리자 버튼을 두지 않는다. */
  onOpenAdmin?: () => void
}

export function AccountBar({ onOpenAdmin }: Props) {
  const { user, logout } = useAuth()
  const occupancy = useOccupancy()

  return (
    <>
      {occupancy && (
        <span
          className={
            occupancy.occupied >= occupancy.capacity
              ? 'muted occupancy full'
              : 'muted occupancy'
          }
          title={occupancyTitle(occupancy)}
        >
          {occupancyLabel(occupancy)}
        </span>
      )}
      <span className="muted">{user?.email}</span>
      {/* 관리자에게만 보인다. 일반 사용자가 눌러 봐야 서버가 403 을 준다. */}
      {user?.role === 'admin' && onOpenAdmin && (
        <button className="link" onClick={onOpenAdmin}>
          관리자
        </button>
      )}
      <button className="link" onClick={() => void logout()}>
        로그아웃
      </button>
    </>
  )
}
