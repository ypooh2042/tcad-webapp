# TCAD 웹앱

브라우저에서 반도체 공정과 소자를 시뮬레이션한다.

- **공정** — SUPREM-IV.GS 입력(`.in`)을 편집기에서 쓰고, 서버에서 돌리고, 단계마다
  떨어지는 구조(`.str`)를 깊이 프로파일과 2D 단면으로 본다.
- **소자 해석** — 그렇게 나온 구조에 전극을 붙이고 전압을 걸어 DevSim 으로 I-V
  곡선을 뽑고, 저장해 둔 결과끼리 겹쳐 본다.

FastAPI 백엔드 + React/Vite 프런트엔드이고, 시뮬레이터는 **루트리스 podman
컨테이너 안에서만** 돈다. 사용자가 제출하는 `.in` 은 사실상 임의 셸 스크립트라
(SUPREM4GS 인터프리터가 인식하지 못한 첫 단어를 `/bin/bash` 로 넘긴다) 격리가
편의가 아니라 이 프로젝트의 본체다. 그 사정과 구조는 [docs/CODEMAPS](docs/CODEMAPS/)
에 정리해 두었다.

---

## 로컬에서 돌리기

### 준비물

| | |
|---|---|
| Python | 3.11 이상 (`backend/pyproject.toml` 의 `requires-python`) |
| Node | Vite 8 / Vitest 4 가 도는 최신 LTS |
| podman | **루트리스**로 설정된 것. 보조 서비스를 띄우려면 `podman-compose` 도 |

프로세스를 네 개 띄우게 된다 — 보조 서비스(컨테이너), API, 잡 워커, Vite 개발
서버. 아래 순서대로 하면 된다. 명령은 모두 **저장소 루트 기준**이고, 디렉토리를
옮기는 곳은 그때그때 적어 두었다.

### 1. 보조 서비스 (Redis, PostgreSQL)

```bash
podman-compose -f compose.dev.yml up -d
```

호스트 기본 포트와 어긋내 **Redis 6380**, **PostgreSQL 5433** 에 뜬다(같은 상자에
다른 서비스가 돌 때 원인 찾기가 번거로워서다). 둘 다 `127.0.0.1` 에만 묶인다.
백엔드 기본 설정이 이 둘을 그대로 가리키므로 접속 정보를 따로 적을 것이 없다.

내릴 때는 `podman-compose -f compose.dev.yml down`.

### 2. 백엔드 가상환경

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"
```

`[dev]` 에는 pytest 와 **`devsim` 파이썬 패키지**가 들어 있다. 소자 해석은 원래
컨테이너 안에서 도는 것이 정상 경로이고, 이 패키지는 컨테이너를 띄우지 않고
해석 스크립트를 손보기 위한 것이다. 앱만 돌려 볼 거라면 `pip install -e .` 로
충분하다(그 대신 `pytest` 는 못 돌린다).

### 3. 환경 파일

로컬에서는 채워 넣을 것이 사실상 하나뿐이다. `backend/.env` 를 만들고:

```
TCAD_SESSION_COOKIE_SECURE=false
```

세션 쿠키의 `Secure` 플래그는 **기본값이 `true`** 다(운영에서 평문으로 새면 안
된다). `http://localhost` 로 개발할 때 그대로 두면 브라우저가 쿠키를 되돌려
보내지 않아 로그인 직후 다시 로그인 화면이 뜬다.

나머지 값은 전부 기본값이 `compose.dev.yml` 과 짝을 이루므로 건드릴 필요가 없다.
바꾸고 싶다면 `TCAD_` 접두 환경변수나 같은 `.env` 로 덮어쓴다. 무엇이 있는지는
`backend/app/core/config.py` 에 주석과 함께 전부 적혀 있다 — 자주 손대는 것만
꼽으면:

| 이름 | 무엇 |
|---|---|
| `TCAD_DATABASE_URL` | PostgreSQL 접속 URL (`postgresql+asyncpg://…`) |
| `TCAD_REDIS_URL` | 세션 저장소 |
| `TCAD_SESSION_COOKIE_SECURE` | HTTPS 로만 쿠키를 보낼지. **로컬 http 개발에서는 `false`** |
| `TCAD_JOBS_ROOT` | 잡 작업디렉토리의 부모 (기본 `backend/var/jobs`) |
| `TCAD_WORKSPACES_ROOT` | 사용자 소스 루트 (기본 `backend/var/workspaces`) |
| `TCAD_MAX_CONCURRENT_JOBS` | 동시에 돌릴 시뮬레이션 수 |
| `TCAD_JOB_TIMEOUT_SECONDS` | 잡 하나의 제한 시간 |

`.env` 와 `.env.*` 는 `.gitignore` 에 들어 있다. 비밀 값을 커밋할 일은 없다.

### 4. 데이터베이스 마이그레이션

```bash
cd backend
.venv/bin/python -m alembic upgrade head
```

접속 URL 은 `alembic.ini` 가 아니라 앱 설정에서 온다. `alembic.ini` 는 커밋되는
파일이라 거기에 URL 을 적으면 비밀번호가 저장소에 남는다.

### 5. 시뮬레이터 컨테이너 이미지

세 개를 만든다. **빌드 컨텍스트가 저장소 루트**여야 한다(Containerfile 이
`SUPREM4GS/` 와 `docker/` 를 그 기준으로 복사한다).

```bash
podman build -t tcad/suprem:latest -f docker/suprem/Containerfile .
podman build -t tcad/remesh:latest -f docker/remesh/Containerfile .
podman build -t tcad/devsim:latest -f docker/devsim/Containerfile .
```

| 이미지 | 무엇 | 없으면 |
|---|---|---|
| `tcad/suprem` | SUPREM-IV.GS 를 상류 소스에서 빌드한 것 | 공정 실행이 안 된다 |
| `tcad/remesh` | gmsh. 소자 해석 전에 메시를 다시 짠다 | 소자 해석이 첫 단계에서 멈춘다 |
| `tcad/devsim` | DevSim + 해석 스크립트 | 소자 해석이 안 된다 |

`suprem` 빌드는 1993년 코드를 요즘 툴체인으로 컴파일하는 것이라 몇 분 걸린다.
공정 화면만 볼 거라면 첫 번째만 만들어도 된다.

### 6. API 와 워커

두 프로세스다. API 는 큐에 넣기만 하고, 컨테이너를 띄우는 것은 워커다 — 그래서
잡이 CPU 를 오래 물고 있어도 상태 조회가 막히지 않는다.

```bash
# 터미널 A
cd backend
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 터미널 B
cd backend
.venv/bin/python -m app.jobs.main
```

`--reload` 를 붙이면 코드가 바뀔 때 API 가 다시 뜬다. 워커는 Ctrl+C(SIGINT)나
SIGTERM 을 **즉사가 아니라 중지 신호로** 받아들여, 돌던 잡이 끝난 뒤에 내려간다 —
누르고 나서 잠깐 기다릴 수 있다.

### 7. 첫 계정

가입에는 초대 코드가 필요하고 초대는 관리자만 발급할 수 있다. 그 순환을 CLI 로
끊는다. **대화형 터미널에서** 실행해야 한다(비밀번호를 두 번 물어본다).

```bash
cd backend
.venv/bin/python -m app.auth.create_user --email you@example.com --admin
```

만든 뒤 화면에서 로그인하고, 관리자 패널에서 초대 코드를 발급하면 다른 계정도
가입할 수 있다.

### 8. 프런트엔드

```bash
cd frontend
npm install
npm run dev
```

Vite 개발 서버가 뜨고 `/api` 는 `127.0.0.1:8000` 으로 프록시된다(`TCAD_API_URL`
로 바꿀 수 있다). 프록시를 쓰는 이유는 요청이 같은 출처로 나가야 세션 쿠키가
그대로 실리기 때문이다 — CORS 를 열 필요가 없다.

---

## 시험

### 백엔드

```bash
cd backend
.venv/bin/python -m pytest                     # 전부
.venv/bin/python -m pytest -m "not integration" # 외부 의존 없는 것만
```

`integration` 마커가 붙은 것은 개발용 PostgreSQL·Redis 를 쓴다(위 1번). 실제
컨테이너를 띄우는 시험은 `podman` 과 샌드박스 이미지가 없으면 스스로 건너뛴다.

### 프런트엔드

```bash
cd frontend
npm run test       # Vitest (e2e/ 는 제외)
npm run coverage
npm run lint       # oxlint
```

### E2E

```bash
cd frontend
npx playwright install chromium   # 처음 한 번
npm run e2e
```

진짜 브라우저로 진짜 백엔드를 친다. `e2e/global-setup.ts` 가 **임시 PostgreSQL
데이터베이스를 만들어 마이그레이션을 걸고** API 와 워커를 직접 띄우므로, 개발 중인
데이터에 손대지 않는다. 대신 다음이 준비되어 있어야 한다:

- 1번의 보조 서비스가 떠 있을 것 (임시 DB 를 그 PostgreSQL 안에 만든다)
- `backend/.venv` 가 있고 의존성이 설치돼 있을 것 (setup 이 그 파이썬을 쓴다)
- 잡이 실제로 도는 시험을 보려면 컨테이너 이미지가 빌드돼 있을 것

Playwright 는 `workers: 1` 로 돈다 — 동시 접속 정원과 잡 큐를 공유하기 때문에
병렬로 돌리면 서로를 방해한다.

---

## 저장소 구조

| 경로 | 무엇 |
|---|---|
| `backend/` | FastAPI API + 잡 워커 (Python). 도메인 로직은 `app/` 아래 구획별로 |
| `frontend/` | React + TypeScript SPA (Vite). 단위 시험은 `src/`, E2E 는 `e2e/` |
| `docker/` | 샌드박스 이미지 셋 — `suprem`(공정), `remesh`(gmsh), `devsim`(소자 해석) |
| `deploy/` | 배포 스크립트, systemd 사용자 유닛, nginx 설정 |
| `docs/` | [코드맵](docs/CODEMAPS/) — 책임의 경계와 그렇게 만든 이유 |
| `SUPREM4GS/` | 시뮬레이터 상류 소스, 물성 데이터, 예제 데크, `.str` 포맷 분석 문서 |
| `tools/` | 개발 시점에 한 번 돌리고 결과를 커밋하는 추출 스크립트 (매뉴얼·카탈로그) |

먼저 읽을 것: [docs/CODEMAPS/README.md](docs/CODEMAPS/README.md).

---

## 배포

```bash
./deploy/bootstrap.sh       # 처음 한 번만
./deploy/deploy.sh          # 그 뒤로는 이것만
```

`deploy.sh` 는 시험을 돌려 보고, 프런트엔드를 빌드하고, `/srv/tcad` 로 옮기고,
마이그레이션을 걸고, 컨테이너 이미지와 systemd 유닛을 다시 맞추고, 서비스를
재시작한다. 순서에 이유가 있다 — 마이그레이션이 코드보다 **먼저**, 워커는 배포
중에 **멈춰** 있고, 프런트엔드가 **마지막**이다.

**이 스크립트들은 특정 한 서버를 위한 것이다.** 루트리스 podman + systemd
**사용자** 유닛 + `/srv/tcad` + 앞단 nginx 를 전제하고, 도메인·인증서·DNS·첫
관리자 계정은 `bootstrap.sh` 가 끝에 안내하는 대로 손으로 해야 한다. 다른 곳에
올릴 거라면 그대로 쓰지 말고 읽고 옮겨 적는 편이 낫다. 운영 비밀 값은 저장소에
없고 `~/.config/tcad/api.env`(0600)에 있다.
