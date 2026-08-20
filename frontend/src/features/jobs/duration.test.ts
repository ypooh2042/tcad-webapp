/**
 * 실행 시간 표기.
 *
 * 초 단위 숫자를 사람이 읽는 문자열로 옮긴다. 반올림하지 않고 버린다 —
 * 1.9초에 "2s" 를 보여주면 시계가 앞서 가는 것처럼 보인다.
 */
import { describe, expect, it } from 'vitest'
import { formatDuration } from './duration'

describe('실행 시간 표기', () => {
  it('1분 미만은 초만 보여준다', () => {
    expect(formatDuration(0)).toBe('0s')
    expect(formatDuration(9)).toBe('9s')
    expect(formatDuration(59)).toBe('59s')
  })

  it('소수점은 버린다', () => {
    expect(formatDuration(1.9)).toBe('1s')
  })

  it('1분이 넘으면 분과 초를 함께 보여준다', () => {
    expect(formatDuration(70)).toBe('1min 10s')
    expect(formatDuration(605)).toBe('10min 5s')
  })

  it('딱 떨어지는 분은 초를 생략한다', () => {
    expect(formatDuration(60)).toBe('1min')
    expect(formatDuration(120)).toBe('2min')
  })

  it('1시간이 넘으면 시간과 분만 보여준다', () => {
    // 이 자리에서 초는 잡음이다. 한 시간을 넘긴 실행에서 3초 차이는
    // 아무도 읽지 않는다.
    expect(formatDuration(3600)).toBe('1h')
    expect(formatDuration(3725)).toBe('1h 2min')
    expect(formatDuration(7200)).toBe('2h')
  })

  it('음수는 0 으로 본다', () => {
    // 서버 시계가 조금 어긋나도 "-3s" 를 세지 않는다.
    expect(formatDuration(-5)).toBe('0s')
  })
})
