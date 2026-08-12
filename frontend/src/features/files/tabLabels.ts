/**
 * 탭 이름 짓기.
 *
 * 보통은 파일 이름만 보여준다. 다른 폴더에 같은 이름이 있을 때만 **구분될
 * 만큼만** 경로를 앞에 붙인다 — 전체 경로를 늘 붙이면 탭이 길어져 정작 이름이
 * 안 보인다.
 *
 * 경로는 작업공간 루트 기준이다. 서버의 실제 절대경로는 화면에 나오지 않는다.
 */

/** 뒤에서부터 `depth` 조각. depth=1 이면 파일 이름만. */
function tail(path: string, depth: number): string {
  return path.split('/').slice(-depth).join('/')
}

export function tabLabels(paths: readonly string[]): string[] {
  return paths.map((path) => {
    const depth = path.split('/').length

    for (let take = 1; take <= depth; take += 1) {
      const label = tail(path, take)
      // 같은 이름이 되는 **다른** 경로가 없으면 이만큼이면 충분하다.
      const collides = paths.some(
        (other) => other !== path && tail(other, take) === label,
      )
      if (!collides) return label
    }

    return path
  })
}
