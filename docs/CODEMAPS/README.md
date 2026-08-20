# 코드맵

**마지막 갱신:** 2026-08-19

이 저장소가 어떻게 나뉘어 있고 데이터가 어디로 흐르는지 설명하는 문서다.
파일 목록이 아니라 **책임의 경계**를 적는다 — 어떤 모듈이 무엇을 보증하고,
그 보증이 깨지면 무엇이 무너지는지.

| 문서 | 다루는 범위 |
|---|---|
| [backend.md](backend.md) | FastAPI 앱 (`backend/app/`) 과 워커 프로세스 |
| [frontend.md](frontend.md) | React + Vite 단일 페이지 앱 (`frontend/`) |
| [simulator.md](simulator.md) | SUPREM4GS 시뮬레이터와 샌드박스 이미지 |

## 이 프로젝트가 하는 일

브라우저에서 SUPREM-IV.GS 공정 시뮬레이션 입력(`.in`)을 쓰고, 서버에서 돌리고,
결과 구조(`.str`)를 그림으로 본다. 사용자는 소수(동시 접속 5명)이고 초대 없이는
가입할 수 없다.

## 저장소 최상위 구성

```
backend/       FastAPI API + 잡 워커 (Python)
frontend/      React SPA (TypeScript, Vite)
SUPREM4GS/     시뮬레이터 배포본 + 상류 소스 + 포맷 분석 문서
docker/suprem/ 시뮬레이터를 소스에서 빌드하는 Containerfile 과 패치
tools/         개발 시점에 한 번 돌리는 추출 스크립트 (매뉴얼·카탈로그)
deploy/        nginx / systemd / 배포 스크립트
compose.dev.yml 개발용 Redis + PostgreSQL
```

## 전체 흐름 한 장

```
   브라우저                        API 프로세스                   워커 프로세스
 ┌──────────┐   저장 PUT       ┌──────────────┐            ┌──────────────────┐
 │ Monaco   │ ───────────────▶ │ routes_files │───▶ 작업공간 (호스트 디렉토리)  │
 │ 편집기   │                  └──────────────┘            │                  │
 │          │   실행 POST      ┌──────────────┐  DB        │  JobQueue        │
 │          │ ───────────────▶ │ /files/jobs  │──▶ jobs ──▶│  .claim_next()   │
 │          │                  └──────────────┘  테이블    │        │         │
 │          │                                              │        ▼         │
 │ JobPanel │   1.5초 폴링     ┌──────────────┐            │  run_simulation  │
 │          │ ◀───────────────▶│ GET /jobs/id │            │        │         │
 │          │                  └──────────────┘            │        ▼         │
 │          │                                              │  podman run      │
 │          │                                              │  (격리 컨테이너) │
 │ ResultView│  구조/프로파일/  ┌──────────────┐            │        │         │
 │ SurfaceView│ 단면 GET       │ routes_plot  │◀── .str ───┴────────┘         │
 └──────────┘ ◀───────────────└──────────────┘   파일          (산출물 등록)
                                     │
                                     ▼
                              str_parser + plotting
```

핵심은 **API 프로세스가 시뮬레이터를 직접 실행하지 않는다**는 점이다. API 는 DB
큐에 넣고 끝내고, 별도 워커 프로세스가 집어가 컨테이너를 띄운다. 그래서 잡이
CPU 를 오래 물고 있어도 상태 조회가 막히지 않고, 워커만 따로 재시작할 수 있다.

## 이 코드베이스에서 먼저 알아야 할 사실

1. **사용자의 `.in` 파일은 사실상 임의 셸 스크립트다.**
   SUPREM4GS 인터프리터는 인식하지 못한 첫 단어를 `/bin/bash` 로 넘긴다.
   그래서 podman 격리가 편의가 아니라 보안의 본체다. → [simulator.md](simulator.md)

2. **종료 코드로 성공을 판정할 수 없다.**
   시뮬레이터는 커맨드 오류가 있어도 exit 0 으로 끝난다. 성공 판정은 로그의
   오류 문구를 찾아서 한다. → `backend/app/runner/results.py`

3. **`.str` 산출물은 캐시다.**
   소스는 작업공간에 남아 있으므로 다시 실행하면 되살아난다. 세션이 끝난
   사용자의 산출물은 워커가 주기적으로 비운다. 로그는 지우지 않는다.

4. **`.str` 파서는 자체 구현이다.**
   포맷 분석 근거는 `SUPREM4GS/STR_FILE_FORMAT.md` 에 있다(실행 결과와 공식
   후처리 툴 `postmini` 출력을 1:1 대조해 확정).

## 읽는 순서

- 처음이면 [simulator.md](simulator.md) → [backend.md](backend.md) → [frontend.md](frontend.md).
  무엇을 돌리는지 알아야 백엔드가 왜 그렇게 방어적인지 읽힌다.
- API 만 볼 거면 [backend.md](backend.md) 의 "진입점" 절 하나로 충분하다.

## 이 문서가 다루지 않는 것

- 배포 절차와 운영 값. `deploy/` 아래 파일의 주석을 볼 것.
- 시뮬레이션 물리 모델. 그건 `SUPREM4GS/Suprem-IV GS Manual.pdf` 의 몫이다.
- 커맨드 문법 레퍼런스. `SUPREM4GS/COMMAND_REFERENCE.md` 와 앱의 매뉴얼 패널이 있다.
