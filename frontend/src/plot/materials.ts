/**
 * 재질 색.
 *
 * **1D 배경 띠와 2D 단면이 같은 색을 쓴다.** 두 화면을 오갈 때 oxide 가 다른
 * 색이면 같은 층인지 알아보지 못한다.
 *
 * 어둡게 묶여 있어야 1D 에서 위에 그리는 곡선이 묻히지 않는다. 그런데 어두운
 * 색 여럿을 좁은 명도 구간에 넣으면 서로 비슷해진다 — 예전 팔레트는 인접
 * 재질끼리 색차 ΔE 가 3.8 로, 감지 한계(약 2.3) 언저리라 사실상 구분되지
 * 않았다. 채도를 올려 ΔE 7.0 까지 벌렸다.
 */
const FILLS: Record<string, string> = {
  silicon: '#213649',
  oxide: '#472b0a',
  nitride: '#1d0931',
  poly: '#16331e',
  aluminum: '#3e3e3e',
  gaas: '#512633',
  oxynitride: '#10474c',
  photoresist: '#443f22',
}

/** 모르는 재질은 중립 회색. 실제 재질처럼 보이면 안 된다. */
const UNKNOWN = '#2f2f33'

export function fillOf(material: string): string {
  return FILLS[material] ?? UNKNOWN
}

/**
 * 2D 단면에서 쓸 밝은 판. 1D 은 곡선을 얹으므로 어두워야 하지만, 단면은 색이
 * 곧 내용이라 그 톤으로는 층이 뭉개져 보인다.
 */
const SOLIDS: Record<string, string> = {
  silicon: '#3f6f9a',
  oxide: '#c08a2e',
  nitride: '#8b5fb5',
  poly: '#3fa06a',
  aluminum: '#9aa3ad',
  gaas: '#c0566f',
  oxynitride: '#20ccd4',
  photoresist: '#747044',
}

/** 색을 아는 재질. 새 재질을 넣으면 두 팔레트에 모두 넣어야 한다. */
export const MATERIALS = Object.keys(SOLIDS)

const UNKNOWN_SOLID = '#6b7280'

export function solidOf(material: string): string {
  return SOLIDS[material] ?? UNKNOWN_SOLID
}
