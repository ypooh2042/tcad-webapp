# 시뮬레이터 코드맵

**마지막 갱신:** 2026-08-22
**진입점:** `docker/suprem/Containerfile` (이미지), `backend/app/runner/sandbox.py` (실행 계약)

SUPREM-IV.GS 는 스탠퍼드/플로리다대에서 만든 1993년 실리콘·GaAs 2D 공정
시뮬레이터다. 이 저장소는 그 상류 소스를 담고, 컨테이너 안에서 빌드해,
격리된 컨테이너로 사용자 입력을 실행한다.

---

## 1. 먼저 알아야 할 것: `.in` 은 셸 스크립트다

SUPREM4GS 인터프리터는 **인식하지 못한 첫 단어를 `/bin/bash` 로 넘긴다.**
즉 사용자가 제출하는 `.in` 파일은 시뮬레이션 스크립트인 동시에 임의 셸
스크립트다. 실측으로 확인했다 — `.in` 에 `id` 한 줄만 넣고 돌리면 실행 유저의
uid/gid 와 소속 그룹이 그대로 출력된다.

이 사실이 이 저장소의 여러 결정을 지배한다:

| 결정 | 이유 |
|---|---|
| podman 루트리스 컨테이너 | 격리가 편의가 아니라 보안의 본체다 |
| 사용자 입력이 argv 에 절대 안 들어감 | 고정 파일명(`job.in`)으로만 전달 |
| 로그의 `/bin/bash:` 접두사를 오류로 판정 | 셸 fall-through 를 잡는 유일한 단서 |
| 에디터가 미인식 첫 단어를 경고 | 오타가 오류 없이 셸로 넘어가 조용히 지나간다 |
| 초대 없이는 가입 불가 | 모르는 사람이 서버에서 코드를 돌리게 둘 수 없다 |

메시지 본문(`command not found`)은 로케일에 따라 번역되므로, 오류 탐지는
번역되지 않는 `/bin/bash:` 접두사로 한다.

---

## 2. 저장소 안에서의 구성

```
SUPREM4GS/
├── upstream/               ★ 상류 원본. 손대지 않는다.
│   ├── src/  Makefile  LICENSE  README.upstream.md
│   └── PROVENANCE.md       출처·커밋·라이선스·우리가 고친 것
├── data/                   물성 데이터와 커맨드 정의
│   ├── suprem.key            ← 백엔드 카탈로그가 파싱 (메타데이터: 설명·단위·제약)
│   ├── suprem.uk             ← 시뮬레이터가 실행 중 읽음 (이름 11자로 잘림)
│   ├── modelrc               도펀트 역할(donor/acceptor) 등 모델 정의
│   └── sup4gs.imp            implant 통계
├── examples/               상류 예제 데크 (exam1~17, mosfet, gaas)
├── Suprem-IV GS Manual.pdf ← tools/docs 가 매뉴얼 JSON 으로 추출
├── STR_FILE_FORMAT.md      ★ .str 포맷 분석 (파서의 근거 문서)
├── COMMAND_REFERENCE.md    커맨드 레퍼런스
├── postmini                공식 후처리 툴 (포맷 검증에 사용한 대조군)
└── suprem4gs               상류 실행 래퍼 스크립트 (컨테이너에서는 쓰지 않는다)

docker/
├── suprem/
│   ├── Containerfile       2단계 빌드: 소스 컴파일 → 최소 실행 이미지
│   └── patches/            0001~0011. 상류 코드 수정은 전부 여기 diff 로만 있다
├── remesh/Containerfile    gmsh. 소자 해석 전에 메시를 다시 짠다
└── devsim/                 DevSim + 해석 스크립트(run.py, 이미지에 구워 넣는다)
```

이미지가 셋인 이유는 **최소 구성 원칙**이다. suprem 이미지의 동적 의존성은
`libc`/`libm` 뿐인데 거기에 gmsh 나 파이썬 런타임을 얹으면 그 원칙이 깨진다.
gmsh 는 GPL 이라 우리 코드에 링크하지 않고 별도 프로세스로만 부르는 이유도
있다. 셋 다 **같은 샌드박스 플래그**로 돌고(`app/runner/sandbox.py` 의 argv 를
그대로 재사용) 실행 유저 uid 도 10001 로 맞춰 둔다 — `--userns keep-id` 아래에서
작업디렉토리 소유권이 세 컨테이너에 같게 보여야 하기 때문이다.

**`upstream/` 과 `patches/` 를 섞지 않는 것이 요점이다.** 상류 트리는 원본
그대로 두고 우리 수정은 전부 diff 로 남긴다. 그래야 "무엇이 상류이고 무엇이 우리
것인지"가 분명해지고, 상류를 갱신할 때 무엇을 다시 맞춰야 하는지 보인다.

패치는 이 문서가 하나(0001)만 자세히 다룬다. 나머지는 각 `.patch` 파일 머리의
주석과 그것을 넣은 커밋 메시지에 근거가 있다.

출처: `rafael1193/suprem4gs` 커밋 `33e9043`. 원저작권 Stanford University (1994)
및 University of Florida. 라이선스는 상업적 재판매를 제외한 사용·복사·수정·배포를
허용한다 (`SUPREM4GS/upstream/LICENSE`).

`data/` 를 상류 것이 아니라 기존 배포본 것을 그대로 쓰는 이유: 내용은 같고
줄바꿈만 다른데, 바꾸면 결과가 달라지는지 다시 검증해야 해서 이번 전환에 함께
건드리지 않았다.

---

## 3. 소스에서 빌드하기 (`Containerfile` 1단계)

예전에는 출처를 설명할 수 없는 바이너리를 그대로 실었다. 지금은 debian:bookworm
빌더에서 컴파일한다.

1993년 코드를 요즘 툴체인에 맞추기 위한 조정이 필요하다. **동작을 바꾸는 수정이
아니며** 코드 변경은 patches/ 에만 있다:

| 조정 | 이유 |
|---|---|
| `g77` → `gfortran -std=legacy` | 30년 전 포트란 컴파일러가 없다 |
| `-std=gnu89` | K&R 함수 정의와 암묵적 int 를 쓴다 |
| `-fcommon` | gcc 10 부터 `-fno-common` 이 기본이라 tentative definition 이 중복 심볼로 링크에서 터진다 |
| `-no-pie` | **없으면 시작하자마자 죽는다.** 여섯 군데가 포인터를 int 로 받는다(1993년엔 같은 크기였다). PIE 로 빌드하면 힙이 2GB 위로 올라가 잘린 주소가 음수가 된다 |

패치 적용이 실패하면 빌드를 멈춘다. 조용히 안 고쳐진 채 나가면 격자를 조금만
키워도 죽는 바이너리가 배포된다.

### 패치 0001 — `min_fill` 포인터 안정화

`src/math/min_fill.c` 의 `min_ia_fill` 이 링크 풀을 `realloc` 으로 두 배씩
키우면서, **키우기 전에 나눠 준 포인터를 계속 썼다.** `nbrs[]` 와 소거 루프의
지역변수들이 전부 옛 블록을 가리키게 되어 해제된 메모리를 따라가다 죽는다.
격자를 조금만 촘촘히 깔면 재현된다.

1993년 malloc 은 대개 제자리에서 늘려 줘 드러나지 않았지만, 현대 glibc 는 큰
블록을 mmap 으로 잡고 늘릴 때 주소를 옮긴다.

수정은 풀을 옮기지 않고 **새 덩어리를 잡아 목록에 이어 붙이는** 것이다. 기존
포인터가 그대로 유효하고 총 할당량은 같다. 늘리는 개수를 원본과 똑같이 맞춘 것이
중요한데, 개수가 어긋나면 freelist 재활용 순서가 달라지고 그것이 최소차수 정렬의
tie-break 를 바꿔 결과가 반올림 수준에서 흔들린다(CMOS 예제에서 실제로 겪었다).

이미지에 `MALLOC_MMAP_THRESHOLD_=1073741824` 도 걸어 둔다. 이 패치로 근본 원인은
고쳤지만, 같은 종류의 `realloc` 성장 자료구조가 코드베이스에 더 있고(예:
`dbase/list.c` 의 `add_list`) 전부 확인하지는 못했다. 제자리 확장을 유도해 잠복
버그의 발동 확률을 낮춘다. 결과에는 영향이 없다 — 켠 것과 끈 것의 `.str` 이
바이트 단위로 같았다.

---

## 4. 실행 이미지 (`Containerfile` 2단계)

debian:bookworm-slim. `suprem` 의 동적 링크 의존성은 `libc.so.6` / `libm.so.6`
뿐이라 추가 패키지를 깔지 않는다 — 안 깔면 공격 표면도 그만큼 준다. 빌드 도구는
여기 오지 않는다.

- 전용 시스템 유저 `suprem`(uid 10001), 홈 없음, 로그인 셸 없음.
- 바이너리와 물성 데이터는 root 소유 + 쓰기 불가(`0555`, `a-w`). 실행 유저가 자기
  실행 환경을 고쳐 쓰지 못하게 한다.
- 상류 래퍼 스크립트(`suprem4gs`)를 쓰지 않는다. 그 스크립트는 `SUPREM4_HOME` 을
  `$(pwd)` 로 잡아 실행 위치에 종속적이고 결과가 cwd 에 떨어져 동시 실행 시 서로
  덮어쓴다. 대신 `SUP4KEYFILE`/`SUP4MODELRC`/`SUP4IMPDATA`/`SUP4MANDIR` 네 변수를
  절대경로로 직접 지정한다.
- `WORKDIR /work` — 잡별 스크래치 디렉토리가 여기 rw 로 마운트된다. 컨테이너 안에서
  쓰기가 허용되는 유일한 경로.
- ENTRYPOINT 가 `stdbuf -oL -eL` 로 감싸져 있다. **줄 단위로 흘려보내지 않으면
  시뮬레이터가 신호로 죽을 때 버퍼가 통째로 사라져 로그가 완전히 빈 채로 남는다**
  (exit 139, log='' 로 실측). `--tty` 로 해결하지 않는 이유는 제어문자가 섞여
  로그 파싱이 깨지기 때문이다.

`SUP4MANDIR` 이 가리키는 `help/` 는 이 배포판에 존재하지 않는다. `man` 커맨드가
동작하지 않을 뿐 시뮬레이션에는 영향이 없다. 문서 기능은 매뉴얼 PDF 에서 따로
만든다(→ [backend.md](backend.md) 의 `app/docs`).

---

## 5. 실행 계약 (`app/runner/sandbox.py`)

호출 한 번의 생애:

```
1. workdir 준비        jobs_root/job-<uuid>/          이름은 서버가 정한다
2. 소스 기록           workdir/job.in                 CRLF→LF, 끝 개행 보장
3. podman run
     --rm --name tcad-job-<uuid> --interactive
     --network none --cap-drop ALL --security-opt no-new-privileges --read-only
     --userns keep-id:uid=10001,gid=10001  --user 10001:10001
     --tmpfs /tmp:rw,noexec,nosuid,size=64m
     --cpus 1.0 --memory 2048m --pids-limit 128 --timeout 600
     --volume <workdir>:/work:rw --workdir /work
     tcad/suprem:latest
4. stdin              "source job.in\nquit\n"          ★ 고정 문자열
5. 실행 중            워치독이 1초마다 /work 크기 확인
6. 종료 후            로그 절단 → 오류 문구 탐색 → 크기 재확인
                      → .str 수집(소스 순서) → 그 외 파일 전부 삭제
```

옵션마다 이유가 있다. 성능이나 편의를 위해 완화해서는 안 된다:

- `--interactive` 없으면 `source job.in` 이 전달되지 않아 배너만 찍고 조용히
  종료된다(exit 0).
- `--userns keep-id` 가 필요한 이유: 루트리스 podman 은 기본적으로 호스트 유저를
  컨테이너 uid 0 에 매핑하고 나머지는 서브uid 로 보낸다. 그 상태로 `--user 10001`
  을 쓰면 컨테이너가 스크래치 디렉토리를 읽지도 쓰지도 못한다(실측). keep-id 로
  호스트 유저를 컨테이너의 10001 에 직접 매핑하면 컨테이너 안에서는 전용 비특권
  uid 로 보이고 호스트에는 워커 소유로 파일이 떨어진다.
- `--timeout` 은 conmon 이 직접 컨테이너를 죽인다. 클라이언트 프로세스만
  타임아웃시키면 컨테이너가 살아남아 CPU 를 계속 문다. 클라이언트 쪽 타임아웃은
  30초 여유를 더 둬서 **항상 컨테이너가 먼저 끝나게** 한다.
- `--name` 은 밖에서 확실히 죽이기 위해 필요하다. 이름이 `workdir` 이름에서
  결정론적으로 나오므로(`container_name` = `tcad-<workdir 이름>`) 워커가 아닌
  API 프로세스도 DB 의 workdir 만 있으면 `podman kill` 할 수 있다 — 중단 버튼이
  이렇게 동작한다. 뒤집어 말하면 **잡이 띄우는 컨테이너는 모두 그 잡의
  작업디렉토리에서 돌아야 한다.** 소자 해석의 재메시가 한동안 임시 디렉토리에서
  돌아 이름이 `tcad-remesh-…` 였고, 그 구간에서는 중단이 먹지 않았다. 지금은
  `remesh()` 가 잡 작업디렉토리를 건네받는다.
- `/work` 크기는 컨테이너 옵션으로 못 묶는다(bind mount). tmpfs 로 만들면 산출물이
  컨테이너와 함께 사라진다. 그래서 밖에서 감시한다. 실측된 문제다 — 잡 하나가
  몇 초 만에 호스트 디스크에 200MB 를 썼고, 400MB `dd` 는 폴링 주기보다 빨리
  끝나 워치독을 통째로 빠져나갔다(그래서 실행 직후 재검사가 따로 있다).

이 계약에는 적혀 있지 않은 **바깥 전제가 하나** 있다: 루트리스 podman 의 pause
프로세스(`catatonit -P`)가 살아 있어야 한다. 그것이 user namespace 를 붙들고
있고 위 `podman run` 은 거기 합류할 뿐이다. 합류에는 아무 특권도 필요 없지만
**새로 만들 때는** setuid 인 `newuidmap` 이 필요하고, 워커 유닛은
`NoNewPrivileges=true` 로 돌아 그것을 쓸 수 없다. 그래서 만드는 일만 NNP 밖의
별도 유닛(`deploy/systemd/tcad-podman.service`)이 맡는다. pause 가 죽은 채로
있으면 모든 실행이 `newuidmap: write to uid_map failed` 로 죽는다 — 실제로 그렇게
멈춘 적이 있다. 되살리는 쪽은 → [backend.md](backend.md) 의 `app/runner`.

---

## 6. 산출물: `.str`

`structure out=<이름>` 을 만날 때마다 그 시점 구조가 파일로 떨어진다. 산출물
하나가 공정 한 단계이므로, 순번을 훑으면 공정 진행을 그대로 볼 수 있다.

포맷은 라인 접두 문자로 종류가 갈리는 텍스트다:

| 접두 | 뜻 |
|---|---|
| `v` | 버전 헤더 |
| `D` | `D <mode> <nvrt> <nedg>` — **`t` 라인의 필드 배치를 정한다** |
| `c` | 좌표 (1D 는 x 가 깊이, 2D 는 x·y) |
| `r` | region → material 매핑 |
| `t` | 요소 연결성 (정점 + 이웃, 이웃이 음수면 경계 조건 코드) |
| `M` | 온도(K) |
| `s` | **이 파일의 species 코드 나열 — `n` 라인 컬럼 순서를 정한다** |
| `n` | 노드별 물성값 (`<0-based 좌표 인덱스> <material_id> <값들>`) |
| `I` | 인터페이스 레코드 (현재 사용처 없음, 보존만) |

분석 근거와 검증 방법은 `SUPREM4GS/STR_FILE_FORMAT.md` 에 있다. 요약하면:
`exam1/boron.in` 과 `mosfet/CMOS.in` 을 실행해 나온 `.str` 을 공식 후처리 툴
`postmini` 의 `Line` 명령 출력과 1:1 대조했고, 메시 라인 구조(`D`/`t`/경계 조건
sentinel)는 `suprem` 바이너리의 `ig2_write`/`ig2_read`/`ChosenBC` 를 역어셈블해
확정했다. material id 매핑은 CMOS 공정 단계별 `.str` 을 순서대로 대조해
"물질이 하나 추가될 때 새 id 가 정확히 그 시점에 나타나는지"로 검증했다.

파싱은 백엔드가 한다 → [backend.md](backend.md) 의 `app/str_parser`.

---

## 7. 알려진 한계

**영역당 약 10,900점.** `geom.h` 의 `struct list_str` 이 개수를 `short` 로 세기
때문에 영역 하나의 변 개수가 32,767 을 넘으면 죽는다. 삼각형 격자에서 변은 점의
약 3배다. 한계는 **영역별**이라 층이 여러 개면 전체 점수는 더 커도 된다.

고치지 않은 이유는 실패가 조용하지 않고(즉시 죽는다) 격자만 보면 미리 계산되기
때문이다. 대신 실행 결과에 안내가 붙는다 — `app/runner/results.py` 의
`describe_abnormal_exit` 이 로그의 마지막 `Points = N` 을 읽어, 격자가 컸다면
그 숫자를 근거로 원인을 짚고 작았다면 짐작하지 않는다.

**종료 코드가 성공을 뜻하지 않는다.** 커맨드 오류가 있어도 exit 0 으로 끝난다.
`exam1/boron.in` 의 잘못된 `option plot.out=` 줄이 "errors detected on command
input" 을 출력하고도 종료 코드는 0이었다.

**마지막 줄에 개행이 없으면 그 줄이 실행되지 않는다.** CMOS 예제를 끝 개행 없이
돌리면 마지막 `structure out=` 이 빠져 산출물이 14개만 나오고, 이어지는 `quit` 이
미완성 줄에 붙어 "illegal input" 이 난다. 브라우저 편집기에서 마지막 줄 끝에
Enter 를 치지 않는 것은 아주 흔해서 `runner.normalise_source` 가 보정한다.

**이름 해석 규칙이 특이하다.** 접두사 해석 + 정확 일치 우선 규칙 없음 +
대소문자 구분 + 런타임 이름 11자 절단. 자세한 것은 [backend.md](backend.md) 의
`app/catalog` 절.

---

## 8. 개발용 도구

`tools/` 는 **개발 시점에 한 번 돌리고 결과를 커밋하는** 스크립트다. 앱 런타임에
쓰이지 않는다.

| 스크립트 | 하는 일 |
|---|---|
| `tools/docs/extract_docs.py` | 매뉴얼 PDF → 섹션 단위 JSON |
| `tools/docs/build_reference.py` | 매뉴얼 + `suprem.key` → `app/docs/data/reference.json` |
| `tools/docs/lookup_demo.py` | 추출 결과 점검 — 커서 아래 토큰 → 섹션, 검색어 → 순위 |
| `tools/catalog/parse_key.py` | 초기 탐색용 `suprem.key` 파서 (앱은 쓰지 않는다) |
| `tools/catalog/gen_monaco.py` | 초기 탐색용 Monaco 자산 생성기 (앱은 쓰지 않는다) |
| `tools/catalog/smoke.mjs` | 위 자산으로 접두사 해석·자동완성을 훑어보는 스크립트 |
| `tools/catalog/coverage.py` | `examples/` 데크가 카탈로그로 얼마나 커버되는지 점검 |

추출에 `pdftotext` 가 필요하므로 배포 시점이 아니라 개발 시점에 돌린다.
`tools/catalog/parse_key.py` 는 이름을 `suprem.key` 에 적힌 그대로 내놓으므로
그 출력을 자동완성에 먹이면 **실행되지 않는 코드**가 나온다 — 앱은
`backend/app/catalog/` 쪽을 쓴다.

---

## 관련 문서

- [backend.md](backend.md) — 이 컨테이너를 띄우는 쪽과 산출물을 읽는 쪽
- `SUPREM4GS/STR_FILE_FORMAT.md` — `.str` 포맷 분석 원본
- `SUPREM4GS/upstream/PROVENANCE.md` — 출처·라이선스·패치 목록
