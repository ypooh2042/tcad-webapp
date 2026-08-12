/**
 * 탭 이름.
 *
 * 보통은 파일 이름만 보여준다. 하지만 다른 폴더에 같은 이름이 있으면 어느
 * 쪽인지 알 수 없으므로 구분될 만큼만 경로를 붙인다.
 *
 * 사용자가 보는 경로는 작업공간 루트 기준이다 — 서버의 실제 절대경로가 아니다.
 */
import { describe, expect, it } from 'vitest'
import { tabLabels } from './tabLabels'

describe('이름이 겹치지 않을 때', () => {
  it('파일 이름만 보여준다', () => {
    expect(tabLabels(['boron.in', 'semi/arsenic.in'])).toEqual([
      'boron.in',
      'arsenic.in',
    ])
  })

  it('깊은 경로도 이름만 보여준다', () => {
    expect(tabLabels(['a/b/c/deep.in'])).toEqual(['deep.in'])
  })
})

describe('이름이 겹칠 때', () => {
  it('구분되도록 경로를 붙인다', () => {
    expect(tabLabels(['boron.in', 'semi/boron.in'])).toEqual([
      'boron.in',
      'semi/boron.in',
    ])
  })

  it('필요한 만큼만 붙인다', () => {
    // 전체 경로를 다 붙이면 탭이 길어져 이름이 안 보인다.
    expect(tabLabels(['a/x/same.in', 'b/x/same.in'])).toEqual([
      'a/x/same.in',
      'b/x/same.in',
    ])
  })

  it('한 단계로 구분되면 한 단계만 붙인다', () => {
    expect(tabLabels(['deep/a/same.in', 'b/same.in'])).toEqual([
      'a/same.in',
      'b/same.in',
    ])
  })

  it('셋이 겹쳐도 각각 구분된다', () => {
    const labels = tabLabels(['same.in', 'x/same.in', 'y/same.in'])

    expect(new Set(labels).size).toBe(3)
    expect(labels[0]).toBe('same.in')
  })

  it('겹치지 않는 탭은 영향을 받지 않는다', () => {
    const labels = tabLabels(['boron.in', 'semi/boron.in', 'other.in'])

    expect(labels[2]).toBe('other.in')
  })
})

describe('가장자리', () => {
  it('빈 목록은 빈 목록이다', () => {
    expect(tabLabels([])).toEqual([])
  })

  it('같은 경로가 두 번 들어와도 터지지 않는다', () => {
    // 열려 있는 파일을 또 열면 생길 수 있다.
    expect(tabLabels(['a.in', 'a.in'])).toEqual(['a.in', 'a.in'])
  })

  it('입력 순서를 지킨다', () => {
    // 탭 순서는 사용자가 연 순서다. 정렬하면 탭이 제멋대로 움직인다.
    expect(tabLabels(['z.in', 'a.in'])).toEqual(['z.in', 'a.in'])
  })
})
