# 백엔드 코드맵

**마지막 갱신:** 2026-08-19
**진입점:** `backend/app/main.py` (API), `backend/app/jobs/main.py` (워커)

FastAPI 앱과 잡 워커. 두 프로세스가 같은 코드베이스를 공유하고 PostgreSQL,
Redis, 호스트 파일시스템을 통해서만 서로를 만난다.

---

## 1. 진입점: 사용자가 "실행"을 누르면

```
브라우저: PUT /api/files/content          (편집 중이면 먼저 저장)
   │
   └─ routes_files.write
        └─ Workspace.write            paths.resolve_in_root 로 경로 검증
                                      .in 만 허용, 쿼터 검사(덮어쓰기는 차이만)

브라우저: POST /api/files/jobs {path}
   │
   ├─ deps.current_session            쿠키 → Redis 세션 조회, 유휴 타이머 갱신
   ├─ Workspace.read(path)            ★ 제출 시점 내용을 그 자리에서 읽는다
   ├─ workdir = jobs_root/job-<uuid>  ★ 경로는 서버가 정한다 (사용자 입력 배제)
   └─ JobQueue.enqueue(...)           jobs 행 하나 INSERT (status=QUEUED,
                                      source 스냅샷 포함)
   ◀── 201 {id, status}

───────── 여기서 HTTP 요청은 끝난다. 아래는 별도 프로세스 ─────────

워커 루프 (app/jobs/worker.py, max_concurrent_jobs 개가 동시에 돈다)
   │
   ├─ JobQueue.claim_next()           조건부 UPDATE 한 번으로 선점
   │                                  (SELECT 후 UPDATE 면 중복 실행된다)
   ├─ asyncio.to_thread(run_simulation, ...)
   │     │
   │     ├─ normalise_source          CRLF→LF, 끝 개행 보장
   │     ├─ workdir/job.in 기록       ★ 소스는 파일로만 전달, argv 에 안 들어간다
   │     ├─ build_sandbox_argv        podman run --network none --cap-drop ALL
   │     │                            --read-only --userns keep-id --volume workdir:/work
   │     ├─ OutputWatchdog            1초마다 /work 크기 감시, 넘으면 podman kill
   │     ├─ subprocess.run(stdin="source job.in\nquit\n")
   │     ├─ extract_errors(log)       ★ 종료 코드가 아니라 로그로 성공 판정
   │     ├─ collect_structure_files   소스의 `structure out=` 등장 순서로 정렬
   │     └─ prune_workdir             .str 만 남기고 전부 삭제
   │
   ├─ Artifact 행 삽입 (sequence = 공정 단계 순서)
   └─ JobQueue.mark_finished          RUNNING 에서만 전이 (중단된 잡 보호)

브라우저: GET /api/jobs/{id} 를 1.5초마다  → 상태·로그·산출물 목록
브라우저: GET /api/jobs/{id}/artifacts/{seq}/structure|profile|surface
   │
   └─ routes_plot → plotting.loader (mtime+size 키 LRU 캐시)
                  → str_parser.parse_structure
                  → plotting.profile / plotting.surface
```

중단 버튼은 이 흐름을 옆에서 끊는다. `POST /api/jobs/{id}/cancel` 이
**먼저 DB 상태를 CANCELLED 로 바꾸고**, 그 다음 `workdir` 이름에서 컨테이너
이름(`tcad-job-<uuid>`)을 유도해 `podman kill` 한다. 순서가 반대면 워커가
컨테이너의 죽음을 먼저 읽고 "실패"로 기록해 버린다. 컨테이너 이름이
결정론적이라 API 와 워커 사이에 신호 채널을 둘 필요가 없다.

---

## 2. 계층

세 층이다. 위층은 아래층을 알고 아래층은 위층을 모른다.

```
app/api/          HTTP 경계. 예외를 상태 코드로 옮기고 Pydantic 으로 검증한다.
                  비즈니스 판단을 하지 않는다.
      │
app/auth  app/workspace  app/jobs  app/runner  app/projects
app/str_parser  app/plotting  app/catalog  app/docs
                  도메인. FastAPI 를 임포트하지 않는다(그래서 CLI·워커에서도 쓴다).
      │
app/db/models.py  app/core/config.py
                  스키마와 설정.
```

의존성은 `app/main.py` 의 `lifespan` 에서 만들어 `app.state` 에 담고,
`app/api/deps.py` 가 요청마다 꺼내 준다. 전역 싱글턴을 쓰지 않는 이유는
테스트에서 메모리 구현으로 갈아끼우기 위해서다. `get_settings()` 를 의존성으로
직접 쓰면 `lru_cache` 된 전역값이 주입된 설정을 무시한다 — `deps.get_app_settings`
가 그래서 따로 있다.

---

## 3. 구획별 책임

### `app/api/` — HTTP 경계

라우터 9개가 `/api` 접두사로 붙는다.

| 라우터 | 접두사 | 인증 | 책임 |
|---|---|---|---|
| `routes_auth` | `/auth` | 부분 | 가입(초대 필수)·로그인·로그아웃·현재 사용자·접속 현황 |
| `routes_admin` | `/admin` | 관리자 | 초대 코드 발급·목록·회수 |
| `routes_files` | `/files` | 필요 | 작업공간 트리·읽기·쓰기·폴더·이름변경·삭제·**실행 제출** |
| `routes_editor` | `/editor` | 필요 | 열어 둔 탭·커서·저장하지 않은 초안 보관 |
| `routes_jobs` | (없음) | 필요 | 잡 상세(실행 시간·공정 진행 포함)·중단·산출물 원문, 예전 프로젝트 기반 제출 |
| `routes_plot` | (없음) | 필요 | `.str` → 요약/프로파일/단면 |
| `routes_projects` | `/projects` | 필요 | 프로젝트·소스 리비전 (예전 모델) |
| `routes_catalog` | `/catalog` | **불필요** | 커맨드 문법 조회·자동완성 |
| `routes_docs` | `/docs` | **불필요** | 매뉴얼 검색·섹션·커맨드 레퍼런스 |

카탈로그와 매뉴얼에 인증을 걸지 않은 것은 의도적이다. 내용이 전부 레포 안
공개 자료에서 나오고 사용자 데이터가 섞이지 않으므로, 로그인 화면에서도 문법을
찾아볼 수 있고 nginx 가 캐시할 수 있다.

`deps.py` 가 보증하는 것:
- `current_session` — 쿠키 → Redis 조회 → 유휴 판정 → **활동 시각 갱신 + 쿠키 재발급**.
  서버 TTL 과 브라우저 쿠키 수명이 같이 움직여야 "쓰고 있는데 끊긴다"가 안 생긴다.
- `owned_job` / `owned_artifact` — 남의 것은 403 이 아니라 **404**. 403 으로
  구분하면 id 를 훑어 남의 잡 존재 여부를 알아낼 수 있고, 잡 로그에는 사용자가
  쓴 코드가 그대로 들어 있다.

`rate_limit.py` 는 슬라이딩 윈도우 카운터(프로세스 메모리), `throttle.py` 가
용도별 한도를 정한다. 눈여겨볼 설계:
- 로그인은 **IP 와 계정 두 축**으로 센다. 연구실 사용자는 같은 NAT 뒤라 IP 가
  하나이므로 IP 한도만으로는 정상 사용자가 먼저 걸린다. 무차별 대입을 실제로
  막는 것은 계정 축(15분 10회)이다.
- 가입은 **실패만** 한도에 쌓는다. 성공한 가입은 유효한 초대를 하나 소진했으므로
  초대의 `max_uses` 가 이미 상한 역할을 한다.
- `client_key` 는 `X-Forwarded-For` 를 **읽지 않는다.** 누구나 붙일 수 있는
  헤더라 믿으면 한도를 무한히 우회할 수 있다. 프록시 뒤에서는 uvicorn 을
  `--proxy-headers --forwarded-allow-ips=127.0.0.1` 로 띄워 서버가 검증한
  `client.host` 를 쓴다.

### `app/auth/` — 세션·정원·초대

정책과 저장소를 분리했다. `policy.py` 는 순수 규칙(동시 5명, 유휴 30분,
관리자 면제)이고 시각을 인자로 받는다 — 안에서 `now()` 를 부르면 시간 규칙을
sleep 없이 테스트할 방법이 없다. `store.py` 가 Protocol 이고 운영에서는
`redis_store.py`, 테스트에서는 메모리 구현이 들어간다.

- 세션은 Redis 키 하나(`session:<id>`)에 JSON + TTL. Redis 가 스스로 만료시키므로
  정리 작업이 없고 프로세스가 죽어도 세션이 남지 않는다. 관리자 세션은 TTL 없음.
- 정원 계산은 SCAN. 활성 세션이 십여 개(정원 + 관리자)라 인덱스를 따로 두는
  것보다 TTL 과 어긋날 위험이 없는 쪽이 낫다.
- 로그인 판정과 현황 표시(`occupancy`)가 `_occupants()` **하나를 공유한다.** 각자
  세면 언젠가 어긋나고, 그때 화면은 자리가 있다고 말하는데 서버는 거절한다.
- **1인 1세션.** 재로그인하면 이전 세션을 무효화한다.
- `cookies.py` 가 쿠키를 심는 유일한 지점이다. 로그인 때와 요청마다 갱신할 때가
  다른 규칙이면 "가끔 로그아웃된다"는 형태로만 드러나 원인을 못 찾는다.
- `service.py` 는 **사용자 열거 방지**가 주된 관심사다. 없는 계정에도 더미 해시로
  검증을 수행해 응답 시간을 맞춘다.
- `invites.py` 는 코드를 SHA-256 으로 저장한다. argon2 는 솔트 때문에 해시로 행을
  찾을 수 없어 가입 시도마다 전수 검증이 되고, 그 자체가 DoS 벡터다. 코드가
  256비트 무작위라 느린 해시가 필요 없다. 사용 처리는 조건부 UPDATE 한 줄 —
  두 사람이 같은 1회용 코드를 동시에 내밀어도 한쪽만 통과한다.
- `create_user.py` 는 첫 관리자를 만드는 CLI. 초대가 있어야 가입하고 관리자가
  있어야 초대를 발급하는 순환을 끊는다. 이메일 검증기를 API 와 **같은 것**을
  쓴다 — 다르면 만들어졌는데 로그인은 안 되는 계정이 생긴다.

### `app/workspace/` — 사용자 파일시스템

사용자에게는 자기 루트가 파일시스템 전부다. 루트 이름에는 사용자 **id 만** 쓴다
(이메일을 쓰면 서버 디렉토리 목록에 신원이 남는다).

`paths.py` 가 이 구획의 위험을 혼자 감당한다. 뚫리면 서버 파일시스템 전체가
열린다. 방어는 두 단계다: 문자열 단계에서 `..`·절대경로·널바이트를 걸러내고,
심볼릭 링크는 문자열 검사를 그냥 통과하므로 **실제로 따라가 본 뒤** 루트 안인지
확인한다. 루트 밖 시도는 이유를 나누지 않고 전부 같은 문구로 거절한다.

`service.py` 는 **폴더와 `.in` 파일만** 다룬다. `.str` 은 목록에도 안 나오고
용량 셈에도 안 들어간다 — 산출물을 쿼터에 넣으면 실행할수록 소스 저장이 막히는
이상한 일이 생긴다. 서버 절대경로는 응답에도 오류 메시지에도 나가지 않는다.

`starter.py` 가 **새 작업공간에만** 예제(`nmos.in`)를 넣는다. 처음 들어온
사람에게 빈 화면을 주면 무엇부터 해야 할지 알 수 없다. 판정 기준은 "루트를
방금 만들었는가"다 — `mkdir` 이 성공했다는 것이 곧 그 뜻이고, 있을 때마다
채워 넣으면 사용자가 지운 예제가 되살아나 지울 방법이 없어진다. 예제는
`app/workspace/examples/` 안에 **패키지 데이터로** 들어 있다. 레포의
`SUPREM4GS/examples/` 를 런타임에 읽으면 그 트리가 없는 설치에서 조용히
아무것도 넣지 않는다. 두 벌이 갈라지지 않는 것은 시험이 바이트 단위로 본다.

### `app/jobs/` — 큐·워커·청소

**DB 를 큐로 쓴다.** 별도 브로커가 없는 이유는 규모가 작고(동시 실행 4, 접속 정원 5)
잡 상태를 어차피 DB 에 남겨야 하기 때문이다. 브로커를 두면 "브로커엔 있는데
DB 엔 없는" 어긋난 상태를 따로 다뤄야 한다.

- `queue.py` — 선점·완료·중단·복구가 전부 **조건부 UPDATE 의 WHERE 절**로
  경합을 해결한다. `claim_next` 는 `status=QUEUED` 조건을 UPDATE 에 그대로 넣어
  먼저 도착한 워커만 성공시키고, `mark_finished` 는 `status=RUNNING` 가드를 두어
  사용자가 중단한 잡을 워커가 "실패"로 덮어쓰지 못하게 한다.
  `requeue_stale` 은 죽은 워커가 남긴 RUNNING 잡을 되돌린다 — 없으면 재시작할
  때마다 동시 실행 슬롯이 하나씩 사라지다 큐 전체가 멈춘다.
- `worker.py` — 큐와 runner 를 잇는 얇은 층. 핵심 책임은 **한 잡이 실패해도
  루프가 멈추지 않는 것**이다. 시뮬레이션은 동기·CPU 바운드라 `asyncio.to_thread`
  로 내보낸다. 돌릴 소스는 파일을 다시 읽지 않고 **제출 시점 스냅샷**을 쓴다.
- `progress.py` — 도는 잡이 어디까지 갔는지. **로그로는 알 수 없다** — stdout 을
  파이프로 모아 끝난 뒤 한 번에 기록하므로 도는 동안 DB 의 로그는 비어 있다.
  대신 작업디렉토리에 떨어진 `.str` 을 소스의 `structure out=` 순서와 맞춰
  "몇 번째 단계까지 끝났는가"를 낸다. 같은 이름을 두 번 쓰는 소스는 중복을
  접는다 — 그러지 않으면 파일 하나가 생긴 순간 진행이 두 칸 뛴다.
- `main.py` — 워커 프로세스 진입점(`python -m app.jobs.main`). 동시 실행 상한을
  지키는 주체는 이 프로세스가 아니라 DB 이므로, 루프를 몇 개 돌리든 워커를 몇 대
  띄우든 전체 동시 실행 수는 설정값을 넘지 않는다. SIGTERM 은 즉사가 아니라
  중지 이벤트로 옮겨 돌던 잡이 끝난 뒤 내려가게 한다.
- `sweeper.py` / `cache.py` — 산출물 청소. 한 주기에 **세 갈래**를 돈다.
  - **유휴 사용자**: 로그아웃은 눌러야 일어나는데 브라우저를 그냥 닫으면 아무
    일도 없다. 그래서 "지금 화면을 보고 있지 않은" 사용자의 `.str` 을 비운다.
    **관리자의 유휴 면제를 여기까지 끌고 오지 않는다** — 그러면 관리자
    산출물이 영영 정리되지 않는다.
  - **총량 상한**(`storage_quota_mb`): 위 갈래는 접속 중인 사용자를 건드리지
    않으므로, 한 사람이 접속한 채 계속 실행하면 아무도 치우지 않는다. 잡 하나가
    최대 256MB 라 그 경로로 디스크가 찬다. 넘으면 **오래된 잡부터** 버리되
    **가장 최근 잡 하나는 남긴다** — 방금 돌린 결과가 사라지면 사용자는 왜
    결과가 없는지 알 수 없다.
  - **고아 디렉토리**: 사용자를 지우면 잡 행은 CASCADE 로 사라지지만 디스크의
    디렉토리는 남아 아무도 다시 찾지 않는다. 갓 만들어진 것은 한 시간 봐준다 —
    작업 디렉토리는 잡 행보다 나중에 생긴다.

  세 갈래 모두 로그는 지우지 않고, 아직 끝나지 않은 잡의 디렉토리도 건드리지
  않는다.

### `app/runner/` — 샌드박스 실행

이 구획의 규칙은 하나다: **사용자 입력은 실행 인자에 절대 들어가지 않는다.**
소스는 스크래치 디렉토리 안 고정 파일명(`job.in`)으로 기록되고 컨테이너에는
그 고정 이름만 전달된다. `build_sandbox_argv` 의 반환값은 사용자 입력에 전혀
의존하지 않는다.

| 모듈 | 책임 |
|---|---|
| `sandbox.py` | podman argv 조립, 자원 상한(`SandboxLimits`), 컨테이너 이름 규칙 |
| `runner.py` | 소스 정규화·기록, 실행, 로그 절단, 크기 재검사, 산출물 수집 |
| `results.py` | 로그 해석 — 오류 문구 탐지, 비정상 종료 설명, 산출물 순서 |
| `workdir.py` | 디렉토리 크기 계산, 산출물 외 파일 정리 |
| `watchdog.py` | 실행 중 크기 감시 스레드 |
| `control.py` | 바깥에서 `podman kill` |

주의할 점 몇 가지:
- **출력 크기는 두 겹으로 막는다.** `/work` 는 호스트 bind mount 라 컨테이너
  옵션으로 크기를 묶을 수 없다(tmpfs 로 만들면 산출물이 컨테이너와 함께 사라진다).
  워치독이 1초마다 재고, 그것만으로는 폴링 주기보다 빨리 끝나는 쓰기를 놓치므로
  러너가 실행 직후 한 번 더 잰다. 완전한 차단은 파일시스템 쿼터로만 가능하다.
- **stderr 를 분리하지 않는다.** 시뮬레이터의 커맨드 오류도, 셸 fall-through 로
  실행된 명령의 오류도 전부 stderr 로 나간다. 따로 버리면 사용자는 빈 로그만 본다.
- **오류 문구 목록은 바이너리의 문자열 테이블에서 뽑았다**(`strings -n 6 suprem`).
  추측으로 채우면 빠뜨리는 것이 생기고, 빠뜨린 문구 하나가 "아무것도 만들지
  못한 실행"을 성공으로 기록한다.
- **산출물 순서는 소스의 `structure out=` 등장 순서**다. 파일 mtime 으로 정렬하면
  안 된다 — 1초 안에 끝나는 시뮬레이션에서 여러 파일의 `st_mtime_ns` 가 정확히
  같은 값이 되어 공정 순서가 뒤집힌다.
- 세그폴트가 나면 로그가 통째로 빈다. `describe_abnormal_exit` 이 그때 무슨 일이
  일어났는지 대신 적어 주고, 격자가 컸다면 영역당 점 수 한계를 근거로 짚는다.

### `app/str_parser/` — `.str` 파싱

공개 API 는 `parse_structure` 하나. 결과 모델은 전부 frozen 이다(플롯 API 등
여러 곳이 공유한다). 라인 접두 문자로 종류가 갈리는 텍스트 포맷이며 근거는
`SUPREM4GS/STR_FILE_FORMAT.md` 에 있다.

이 파서가 지키는 불변식 중 놓치기 쉬운 것:
- **컬럼 위치는 파일마다 다르다.** `s` 라인이 선언한 species 코드 나열 순서가
  `n` 라인 값의 순서를 정한다. 위치 상수를 쓰면 반드시 깨지므로 코드→이름
  조회(`species.py` 의 `SpeciesTable`)만이 안전하다.
- **계면 점은 물질마다 값이 다르다.** `(coordinate_index, material_id)` 조합이
  유일 키다. 물질 없이 조회하면 어느 쪽 값인지 알 수 없어 계면에서 값이 튄다.
- **net doping 컬럼은 파일에 없다.** 활성 도너 − 활성 억셉터로 계산한다.
  (코드 24 를 net doping 으로 읽던 시절이 있었는데 상류 `impurity.h` 는 그것을
  폴리실리콘 결정립 크기로 정의한다.)
- 모르는 코드·물질은 버리지 않고 `unknown_<코드>` 로 보존한다. 조용히 다른 것으로
  표시하는 것보다 모른다고 드러내는 편이 안전하다. 경고는 `Structure.warnings`
  에 실려 화면까지 올라간다.
- 포맷 불변식을 어기면 `StructureFormatError` 로 즉시 실패한다. 컬럼 개수가
  어긋난 채 통과하면 엉뚱한 quantity 로 그래프가 그려진다.

`mesh.py` 는 삼각형·경계 변 기하를 계산한다(현재 API 응답에는 쓰이지 않고
검증·분석용).

### `app/plotting/` — 그림용 변환

`.str` 원문을 그대로 화면에 주면 파서를 프론트에도 한 벌 유지해야 한다.
그래서 서버가 그릴 수 있는 형태로 바꿔 보낸다.

- `loader.py` — 파싱 결과 LRU 캐시. 키에 **경로 + mtime_ns + 크기**를 넣는다.
  경로만 쓰면 같은 잡을 다시 돌려 파일이 바뀌어도 옛 내용을 계속 보여준다.
- `quantities.py` — 그릴 수 있는 물리량 목록. `net_doping` 만 계산으로 존재한다.
- `profile.py` — 깊이 프로파일. **1D 는 x 가 깊이, 2D 는 y 가 깊이**다. 2D 는
  세로선과 만나는 삼각형 변을 선형 보간해 뽑는다(노드 값만 모으면 격자선이
  아닌 위치에서 프로파일이 빈다). 같은 깊이에 여러 재질이 있을 때는 **앞 구간을
  잇는 재질을 먼저** 놓는다 — 이름순으로 놓으면 층이 끊겨 선이 안 그려진다.
- `surface.py` — 2D 컨투어용 삼각형. **값을 정점이 아니라 삼각형마다** 싣는다.
  계면 정점은 물질에 따라 값이 다르기 때문이다. `quantity=None` 이면 재질만
  내려주고 이때는 요소를 하나도 버리지 않는다(층이 빠지면 그림이 거짓말을 한다).

### `app/catalog/` + `app/docs/` — 문법과 산문

역할이 다르고 둘 다 필요하다.

```
catalog  = 문법.  이름·타입·기본값·제약.  출처: SUPREM4GS/data/suprem.key
docs     = 산문.  무엇을 하는 커맨드인가.  출처: 매뉴얼 PDF (320쪽)
```

카탈로그만 있으면 `dose` 가 float 이라는 것만 알고 뜻을 모르고, 매뉴얼만 있으면
이름이 11자로 잘린다는 사실을 모른다.

카탈로그가 재현하는 SUPREM 의 이름 해석 규칙 두 가지 — 둘 다 실제 시뮬레이터로
확인한 것이고, 여기서 규칙을 "고치면" 카탈로그가 시뮬레이터와 다르게 동작한다:
1. **정확 일치 우선 규칙이 없다.** 다른 이름의 진접두사인 이름은 어떤 입력으로도
   지목할 수 없다(`backside` 는 `backside.y` 때문에 ambiguous). 그런 파라미터는
   `unreachable` 로 표시하고 자동완성 후보에서 뺀다.
2. **런타임 이름은 11자로 잘린다.** 메타데이터는 `suprem.key` 에 있지만 실행 중
   읽는 파일은 `suprem.uk` 이고 거기서 이름이 잘려 저장된다. 해석이 접두사
   방식이라 잘린 이름보다 **긴** 토큰은 어디에도 걸리지 않는다. 매뉴얼대로 치면
   거절되는 파라미터가 있어서 호버 문서가 그 사실을 경고한다.

`keywords.py` 는 `suprem.key` 에 없는 인터프리터 키워드(`source`, `foreach` 등)를
따로 담는다. 목록은 실제 시뮬레이터에서 확인했다 — 인식되지 않은 단어는
`/bin/bash` 로 넘어가므로 그 접두사로 판정했고, bash 내장과 겹치는 단어는
존재하지 않는 경로를 인자로 붙여 걸러냈다.

매뉴얼 JSON(`app/docs/data/manual.json`, `reference.json`)은 `tools/docs/` 의
스크립트가 PDF 에서 뽑아 **레포에 커밋해 둔** 결과물이다. 추출에 `pdftotext` 가
필요하므로 배포 시점이 아니라 개발 시점에 한 번 돌린다.

### `app/db/` — 스키마

| 테이블 | 용도 | 알아둘 점 |
|---|---|---|
| `users` | 계정 | argon2id 해시, `role` 은 CHECK 제약, 가입에 쓴 초대를 참조 |
| `invite_codes` | 초대 | SHA-256 해시, 회수는 행 삭제가 아니라 `revoked_at` |
| `projects` / `source_revisions` | 예전 모델 | 리비전은 만들어진 뒤 수정하지 않는다 |
| `jobs` | 실행 한 건 | 소스 **스냅샷**, workdir, 로그, 상태 |
| `artifacts` | `.str` 하나 | 내용은 파일시스템, DB 엔 경로·크기·`sequence` |

`jobs.source_revision_id` 와 `jobs.source_path`/`source` 가 둘 다 nullable 인 것은
프로젝트 기반 모델에서 파일 기반 모델로 옮겨 온 흔적이다. 파일로 돌린 잡은
리비전이 비어 있다.

`users` 와 `invite_codes` 는 서로를 참조하므로 FK 하나에 `use_alter=True` 를 걸어
테이블 생성 뒤에 제약을 건다. 마이그레이션은 `backend/alembic/` (현재 3개).
접속 URL 은 `alembic.ini` 가 아니라 앱 설정에서 가져온다 — ini 는 커밋되는
파일이라 여기에 URL 을 적으면 비밀번호가 레포에 남는다.

### `app/core/config.py` — 설정

전부 `TCAD_` 접두 환경변수나 `.env` 로 덮어쓸 수 있다. 기본값은 개발 편의를 위한
것이고 `compose.dev.yml` 과 짝을 이룬다. 운영 값은 배포 설정이 주입하며,
**코드가 그것을 강제하지 않는다.**

주요 값: `max_concurrent_jobs`(동시 시뮬레이션 수, 로그인 정원과 별개),
`job_timeout_seconds`, `jobs_root`, `workspaces_root`, `workspace_quota_mb`,
`storage_quota_mb`, `artifact_sweep_seconds`, `session_cookie_secure`, `sandbox_image`.

---

## 4. 상태가 사는 곳

| 저장소 | 무엇 | 잃으면 |
|---|---|---|
| PostgreSQL | 계정·초대·잡·산출물 메타·프로젝트 | 전부 잃는다 |
| Redis | 세션 | 전원 로그아웃 (의도된 동작, 영속화하지 않는다) |
| `jobs_root/job-<uuid>/` | `.str` 산출물 | 다시 실행하면 되살아난다 (캐시) |
| `workspaces_root/user-<id>/` | 사용자 소스 | 되살아나지 않는다 |
| 프로세스 메모리 | 빈도 제한 카운터, 카탈로그·매뉴얼·구조 캐시 | 재시작하면 초기화 (허용) |

빈도 제한을 Redis 로 옮기면 여러 워커가 한도를 공유하겠지만, 이 규모(API 프로세스
1개)에서는 이득보다 복잡도가 크다는 판단이다.

---

## 5. 테스트

```
backend/tests/unit/         도메인 로직. 외부 의존 없음.
backend/tests/integration/  DB·Redis·실제 컨테이너를 쓰는 것.
backend/tests/fixtures/     실제 실행으로 만든 .str 과 .in 샘플
```

`pyproject.toml` 에 `integration` 마커가 정의돼 있고 `conftest.py` 가 테스트마다
빈도 제한을 초기화한다(프로세스 전역 상태라 격리가 필요하다). 커버리지 설정에
`concurrency = ["greenlet", "thread"]` 가 있는데, 없으면 SQLAlchemy 의 async 브리지
이후 프레임이 추적되지 않아 실제로 실행된 코드가 미커버로 잘못 보고된다.

---

## 관련 문서

- [simulator.md](simulator.md) — runner 가 무엇을 실행하는지, 왜 그렇게 가두는지
- [frontend.md](frontend.md) — 이 API 를 누가 어떻게 부르는지
