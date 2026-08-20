/**
 * 실행 시간 표기.
 *
 * 반올림하지 않고 버린다. 1.9초에 "2s" 를 보여주면 시계가 실제보다 앞서 가는
 * 것처럼 보이고, 끝난 잡의 총 시간이 실제보다 길게 남는다.
 */

const MINUTE = 60
const HOUR = 3600

/** 초를 "1h 2min" / "1min 10s" / "9s" 로 옮긴다. */
export function formatDuration(seconds: number): string {
  // 서버와 워커의 시계가 조금 어긋나면 음수가 올 수 있다.
  const total = Math.max(0, Math.floor(seconds))

  if (total >= HOUR) {
    const hours = Math.floor(total / HOUR)
    const minutes = Math.floor((total % HOUR) / MINUTE)
    // 한 시간을 넘긴 실행에서 초는 아무도 읽지 않는다.
    return minutes === 0 ? `${hours}h` : `${hours}h ${minutes}min`
  }

  if (total >= MINUTE) {
    const minutes = Math.floor(total / MINUTE)
    const rest = total % MINUTE
    return rest === 0 ? `${minutes}min` : `${minutes}min ${rest}s`
  }

  return `${total}s`
}
