"""suprem.key 에 없는 인터프리터 키워드.

suprem.key 는 "카드"(공정 커맨드)만 정의한다. 흐름 제어나 변수 같은 인터프리터
자체의 단어는 그 파일에 없어서, 카탈로그가 카드만 내놓으면 사용자는 `source`,
`foreach` 같은 기본 단어를 자동완성에서 찾지 못한다.

목록은 실제 시뮬레이터에서 확인했다. 인식하지 못한 첫 단어는 /bin/bash 로
넘어가므로, 넘어갔는지를 `/bin/bash:` 접두사로 판정했다.

**bash 내장과 겹치는 단어는 인자 없이 부르면 조용히 성공해 구분이 안 된다.**
그래서 존재하지 않는 경로를 인자로 붙여, bash 라면 반드시 오류를 내게 했다.
이 방법으로 걸러낸 결과 `read` `alias` `unalias` `history` 는 인터프리터 단어가
아니라 bash 내장이었고, `prompt` 는 아예 인식되지 않았다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Keyword:
    name: str
    description: str


#: 인터프리터가 직접 처리하는 단어들. 카드가 아니므로 파라미터가 없다.
INTERPRETER_KEYWORDS: tuple[Keyword, ...] = (
    Keyword("source", "파일에 든 명령을 읽어 실행한다"),
    Keyword("foreach", "값 목록을 돌며 반복한다"),
    Keyword("end", "foreach 블록을 닫는다"),
    Keyword("set", "변수를 설정한다"),
    Keyword("unset", "변수를 지운다"),
    Keyword("define", "매크로를 정의한다"),
    Keyword("undef", "매크로 정의를 지운다"),
    Keyword("printenv", "설정된 변수를 출력한다"),
    Keyword("write", "구조를 파일로 쓴다"),
    Keyword("cd", "작업 디렉토리를 옮긴다"),
    Keyword("sh", "셸 명령을 실행한다"),
    Keyword("help", "도움말을 출력한다"),
    Keyword("quit", "시뮬레이터를 끝낸다"),
    Keyword("exit", "시뮬레이터를 끝낸다"),
    Keyword("logout", "시뮬레이터를 끝낸다"),
)

KEYWORD_NAMES: tuple[str, ...] = tuple(k.name for k in INTERPRETER_KEYWORDS)
