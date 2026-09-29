# bushexa — UNIST 버스 정보 시스템

울산과학기술원(UNIST)을 경유하는 시내버스의 **실시간 도착 정보·시간표·운행 현황**을 제공하는 웹 서비스입니다.
기존 Streamlit + Conda 스택을 **Flask 3 + [uv](https://docs.astral.sh/uv/)** 기반 헥사고날 아키텍처로 재구축했습니다.

- **대상 노선**: 513 · 713 · 743 · 753 · 1115 (UNIST 경유)
- **데이터 소스**: 울산광역시 BIS / 국토교통부 TAGO 공용 API
- **스택**: Python 3.12 · Flask 3 · HTMX · SQLite (단일 백엔드) · 단일 컨테이너(supervisord)
- **상태**: 백엔드·웹·크롤러·배포자산 구현 완료 (2026-09-29 기준 테스트 573 passed)

---

## 목차

- [기능](#기능)
- [화면·API 예시](#화면api-예시)
- [사전 요구사항 (Prerequisites)](#사전-요구사항-prerequisites)
- [빠른 시작 (Quick Start)](#빠른-시작-quick-start)
- [설정 (Configuration)](#설정-configuration)
- [실행 방법](#실행-방법)
- [Docker 배포](#docker-배포)
- [프로젝트 구조](#프로젝트-구조)
- [테스트](#테스트)
- [문제 해결 (Troubleshooting)](#문제-해결-troubleshooting)

---

## 기능

### 사용자 화면

| 페이지 | 경로 | 설명 |
|---|---|---|
| 출발 게시판 | `/board` | UNIST 정류장 **실시간 버스 도착 정보** (HTMX 15초 자동 갱신) |
| 출발 게시판 (Lite) | `/lite` | FASTER 모드 — 웹폰트·JS·CSS 0의 순수 HTML 표. `<meta refresh>` 만으로 갱신, 저사양·느린망에서 즉시 렌더 |
| 버스번호별 시간표 | `/busno` | 노선 번호로 조회하는 시간표 |
| 정류소별 도착 정보 | `/stops` | 정류장 단위 도착 예정 버스 (HTMX 자동 갱신) |
| UNIST 버스 카드 | `/unist` | UNIST 경유 노선 요약 카드 (HTMX 30초 갱신) |
| 전체 시간표 그리드 | `/timetable` | 노선별 색상 구분 컬러 시간표 |
| 운행 재구성 테이블 | `/running` | 통과 로그 기반 실제 운행 현황 재구성 |
| 정보 페이지 | `/info` | 서비스 안내 |
| 부산 가는 길 | `/busan` | 부산역(513→울산역→KTX)·노포(743·753→1224, 준비 중)·벡스코/부전(버스→태화강역→동해선) 연결 안내 |
| 서울 가는 길 | `/seoul` | 513→울산역→KTX 서울역·수서역. 열차 목록은 표(기본)·발차 안내판(`?view=board`, 정차역 띠) 선택 |

> 루트(`/`) 접속 시 `/board` 로 리다이렉트됩니다.

### 관리자 패널 (`/admin`)

| 기능 | 경로 | 설명 |
|---|---|---|
| 로그인 / 로그아웃 | `/admin/login`, `/admin/logout` | Argon2id 해시 인증(legacy PBKDF2/평문 검증 호환 + 로그인 시 자동 재해시) + 로그인 잠금(lockout) |
| 대시보드 | `/admin/` | govtrack 수집 상태 카드 (SSE 실시간) |
| 비밀번호 변경 | `/admin/password` | 관리자 비밀번호 변경 |
| 데이터 브라우저 | `/admin/data`, `/admin/data.csv` | 통과 로그 조회 + CSV 내보내기 |
| 시간표 편집 | `/admin/timetable`, `/admin/timetable/<노선>` | 시간표 JSON 편집·검증·백업 |
| 시간표 재크롤 | `/admin/timetable/recrawl` | 외부 소스 재크롤 (SSE 진행률) |
| govtrack 상태 | `/admin/govtrack/status` | 수집 사이클 통계 (SSE 스트림) |
| 로그 뷰어 | `/admin/logs` | 애플리케이션 로그 (시크릿 자동 마스킹) |

### 백그라운드 작업 (CLI 데몬)

| 작업 | 명령 | 설명 |
|---|---|---|
| govtrack 데몬 | `bushexa crawl-loop` | 버스 위치를 폴링해 통과 로그를 DB에 적재 (기본 10초) |
| 도착정보 폴러 | `bushexa arrival-loop` | 울산 BIS 도착정보를 캐시에 적재 (기본 7초) |
| 시간표 크롤 | `bushexa crawl-timetable` | 외부 소스에서 시간표 갱신 |

---

## 화면·API 예시

웹 서버 기동 후 브라우저로 접속합니다.

```text
http://localhost:8000/board       # 실시간 도착 게시판
http://localhost:8000/timetable   # 컬러 시간표 그리드
http://localhost:8000/admin/      # 관리자 (로그인 필요)
```

`curl` 로 동작 확인:

```bash
# 출발 게시판 (HTTP 200)
curl -sf http://localhost:8000/board

# HTMX 부분 갱신 엔드포인트 (테이블 조각만 반환)
curl -s http://localhost:8000/partial/board

# 비로그인 관리자 접근은 로그인으로 리다이렉트(302)
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/admin/
```

CLI 사용 예:

```bash
# 단발성 1회 크롤 (디버깅용, INSERT 없이 결과만)
uv run bushexa crawl-once --route 195000177 --dry-run

# 크롤 폴링 간격을 5초로 조정해 데몬 실행
uv run bushexa crawl-loop --poll 5

# 웹 서버를 외부 노출 포트로 기동
uv run bushexa serve --host 0.0.0.0 --port 8000
```

---

## 사전 요구사항 (Prerequisites)

| 항목 | 필요 | 비고 |
|---|---|---|
| **Python 3.12** | 필수 | `>=3.12,<3.13`. uv가 자동 설치 가능 |
| **[uv](https://docs.astral.sh/uv/)** | 필수 | 패키지·가상환경 관리자 |
| **울산 BIS / TAGO API 키** | 실데이터 수집 시 필수 | `BUSHEXA_API_KEY` |
| **Docker / Podman** | 운영 배포 시 | 단일 컨테이너(supervisord) compose 배포 |

uv 설치 (미설치 시):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## 빠른 시작 (Quick Start)

```bash
# 1) 의존성 설치 (.venv 자동 생성, dev 도구 포함)
uv sync

# 2) 환경변수 파일 준비
cp .env.example .env
#    .env 를 편집하여 최소한 BUSHEXA_API_KEY 입력

# 3) DB 스키마 생성 (개발은 SQLite로 충분)
DATABASE_URL=sqlite:///./data/bushexa.db uv run bushexa init-db

# 4) 웹 서버 기동 (기본 포트 8000)
DATABASE_URL=sqlite:///./data/bushexa.db uv run bushexa serve

# 5) (선택) 별도 터미널에서 크롤러 데몬
uv run bushexa crawl-loop
uv run bushexa arrival-loop
```

접속: <http://localhost:8000/board>

### CLI 서브커맨드 전체

| 명령 | 설명 |
|---|---|
| `bushexa serve` | Flask 웹 서버 (`--host 0.0.0.0 --port 8000`) |
| `bushexa crawl-loop` | govtrack 버스 위치 크롤 데몬 (`--poll 10`) |
| `bushexa arrival-loop` | 울산 도착정보 캐시 폴러 (`--poll 7`) |
| `bushexa crawl-once` | 수동 1회 크롤 (`--route <ID> [--dry-run]`) |
| `bushexa init-db` | DB 스키마 생성 (`--reset` 시 통과 로그 비우기) |
| `bushexa crawl-timetable` | 시간표 재크롤 (`--vacation` 방학 모드) |

---

## 설정 (Configuration)

설정은 **환경변수 우선, 없으면 `secret/` 파일 fallback** 순으로 해석됩니다(ADR-005).
`.env.example` 을 복사해 편집하세요.

```bash
cp .env.example .env
```

| 환경변수 | 필수 | 설명 |
|---|---|---|
| `BUSHEXA_API_KEY` | **필수** | 울산 BIS / 국토부 TAGO API 키 (또는 `secret/key.txt`) |
| `DATABASE_URL` | **필수** | `sqlite:///./data/bushexa.db` (운영·개발 공통). psycopg2를 직접 설치하면 `postgresql://...` 도 동작하나 기본 배포는 SQLite |
| `BUSHEXA_SESSION_SECRET` | 권장 | Flask 세션 서명 키 (미설정 시 재시작마다 세션 초기화) |
| `BUSHEXA_SESSION_COOKIE_SECURE` | HTTPS 운영 시 `true` | 세션 쿠키 `Secure` 플래그 (기본 `false`) |
| `BUSHEXA_LOG_LEVEL` | — | 로그 레벨 (기본 `INFO`) |
| `BUSHEXA_LOG_DIR` | — | 로그 파일 디렉터리 (기본 `logs/`) |
| `BUSHEXA_ARRIVAL_POLL_SECONDS` | — | arrival 워커의 울산 API 폴링 주기(초, 기본 7) |

> **보안 주의**
> - `.env` 와 `secret/` 는 **git에 커밋하지 마세요** (`.gitignore` 처리됨).
> - `secret/*` 파일은 `chmod 600` 권한을 유지하세요.
> - 운영 DB 비밀번호는 기본/예시 값을 그대로 쓰지 말고 반드시 교체하세요.

---

## 실행 방법

### 로컬 개발 (compose 없이, 가장 빠름)

```bash
uv sync                                                    # 의존성
DATABASE_URL=sqlite:///./data/bushexa.db uv run bushexa init-db
DATABASE_URL=sqlite:///./data/bushexa.db uv run bushexa serve
uv run pytest -q                                           # 테스트
uv lock --upgrade && uv sync                               # 의존성 업데이트
```

### 개발용 compose (소스 bind-mount + DEBUG + SQLite)

```bash
docker compose -f docker/compose.yaml -f docker/compose.dev.yaml up
```

---

## Docker 배포

운영 배포는 **단일 컨테이너**(`app`) 모델입니다. 한 컨테이너 안에서 `supervisord` 가
web + 2개 워커를 함께 구동하고, 저장소는 **SQLite 단일 백엔드**(postgres 제거됨)입니다.
**호스트 포트 8017 → 컨테이너 포트 8000** (bushexa CLI 기본값) 으로 매핑됩니다.

- canonical(podman): 루트의 `compose.podman.yaml`
- docker variant: `docker/compose.yaml` (동일 구성, `../` 상대경로)

### 사전 준비

1. `.env` 작성 (위 [설정](#설정-configuration) 참고 — `BUSHEXA_API_KEY`, `BUSHEXA_SESSION_SECRET`, `DATABASE_URL`)
2. `data/` 디렉터리 쓰기권한 확인 (SQLite DB·시간표·비밀번호 해시가 여기에 저장됨)

### 빌드 및 기동

```bash
# DB 스키마 1회 생성 (SQLite — 기존 스키마 있으면 no-op)
docker compose -f docker/compose.yaml run --rm --entrypoint python app -m bushexa init-db

# 이미지 빌드 + 단일 컨테이너 기동
docker compose -f docker/compose.yaml up -d --build

# 상태 확인 (컨테이너 + supervisord program)
docker compose -f docker/compose.yaml ps
docker compose -f docker/compose.yaml exec app supervisorctl -c /app/docker/supervisord.conf status

# 웹 접속 확인 (호스트 포트 8017) — /lite 가 가장 빠른 헬스 신호
curl -sf http://localhost:8017/lite
curl -sf http://localhost:8017/board

# 통합 로그 (web + 두 워커가 한 컨테이너에)
docker compose -f docker/compose.yaml logs -f app

# 종료
docker compose -f docker/compose.yaml down
```

> `podman-compose` 사용 시 루트의 `compose.podman.yaml` 을 쓰고, `docker compose` → `podman-compose` 로 대체하세요.

### 컨테이너 구성 (단일 `app`, supervisord)

| program | 역할 | 비고 |
|---|---|---|
| `web` | Flask 웹 서버 (gunicorn) | 8017 → 8000 |
| `worker-govtrack` | govtrack 크롤 데몬 (`crawl-loop`) | autorestart |
| `worker-arrival` | 도착정보 폴러 (`arrival-loop`) — 울산 API를 매 N초 폴링해 SQLite `bus_arrival_cache` 에 백업 | autorestart |

> 화면(`/board`·`/lite`·`/stops`·`/unist`)은 울산 API를 직접 호출하지 않고 위 cache 만 읽는다(ADR-010).

### 스모크 테스트

```bash
# HTTP-200 만 확인 (API 키 불필요)
SMOKE_SKIP_FEED=1 bash scripts/smoke_compose.sh

# 전체 확인 (실 API 키 + 네트워크 필요)
bash scripts/smoke_compose.sh
```

운영 전환(cutover) 절차와 롤백은 [`docs/refactor/migration-notes.md`](docs/refactor/migration-notes.md) 를 참고하세요.

---

## 프로젝트 구조

헥사고날 레이어로 외부 어댑터·도메인·웹을 분리했습니다.

```text
bushexa/
├── cli.py           # 진입점 (서브커맨드 dispatch)
├── config.py        # AppConfig.from_env() — 설정 해석
├── api_clients/     # 외부 API 어댑터 (울산 BIS, TAGO, 공휴일)
├── db/              # 포트+어댑터 (SQLite / PostgreSQL 듀얼 백엔드)
├── crawler/         # govtrack 데몬, 도착 폴러, 시간표 크롤
├── domain/          # 순수 비즈니스 로직 (게시판/정류장/운행 재구성 등)
├── services/        # 앱 서비스 (인증, 시간표 편집, 상태 기록)
└── web/             # Flask 팩토리 + 블루프린트 라우트 + 템플릿 + 정적자원

docs/refactor/       # 설계 문서 (워크플로우·ADR·Phase·터치포인트·부검)
docker/              # Dockerfile, compose.yaml, compose.dev.yaml
scripts/             # smoke_compose.sh 등 운영 스크립트
tests/               # pytest (단위·통합·보안)
```

설계 문서:

| 문서 | 내용 |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | AI 세션·기여자 진입점 — 명령, 절대 규칙, 작업 방식, 미해결 문제 |
| [`docs/guide/architecture.md`](docs/guide/architecture.md) | **현행** 아키텍처·데이터 흐름·불변식·ADR 현행성 |
| [`docs/guide/api-usage.md`](docs/guide/api-usage.md) | 국토부 TAGO·울산 BIS·특일정보 API 활용과 호출량 전략 |
| [`docs/guide/ui-design.md`](docs/guide/ui-design.md) | UI 디자인 토큰·컴포넌트·노선도·i18n 규칙 |
| [`docs/guide/pitfalls.md`](docs/guide/pitfalls.md) | 자주 범하는 오류 (부검에서 추린 규칙) |
| [`docs/guide/change-playbooks.md`](docs/guide/change-playbooks.md) | 노선 변경·페이지/API/설정 추가·배포 체크리스트 |
| [`docs/refactor/postmortems/INDEX.md`](docs/refactor/postmortems/INDEX.md) | 부검 보고서 목록 |
| [`docs/refactor/00-workflow.md`](docs/refactor/00-workflow.md) | Designer/Executor/Auditor 3역할 워크플로우 |
| `docs/refactor/architecture/ADR-*.md` | 아키텍처 결정 레코드 |
| `docs/refactor/phases/P0~P5.md` | 단계별 리팩터 계획 |
| [`docs/refactor/migration-notes.md`](docs/refactor/migration-notes.md) | 운영 마이그레이션·cutover·롤백 |

주요 결정: **ADR-002** SQLite↔PostgreSQL 듀얼 백엔드(현재 배포는 SQLite 단독) · **ADR-005** 설정 우선순위(env > secret 파일) · **ADR-006** slim+uv 단일 이미지 · **ADR-010** govtrack/arrival 워커 분리(현재는 단일 컨테이너에서 supervisord로 통합 구동, 오류격리는 program별 autorestart로 보존).

---

## 테스트

```bash
# 전체
uv run pytest -q

# 상세 / 특정 모듈
uv run pytest -v
uv run pytest tests/web/ -v
uv run pytest tests/security/ -v
uv run pytest tests/crawler/ -v

# 통합 테스트 제외 (빠른 단위만)
uv run pytest -m "not integration" -q
```

- `pytest` 등 dev 도구는 `uv sync` 시 자동 설치됩니다(PEP 735 dependency group).
- 보안 회귀 테스트(`tests/security/`)는 평문 비밀번호 부재·관리자 라우트 보호·CSV 수식 인젝션 방어를 검증합니다.
- 관리자 비밀번호는 **Argon2id**(OWASP 권장)로 저장되며, 기존 PBKDF2/평문 자격증명은 검증만 호환되고 로그인 시 자동 재해시됩니다.

---

## 문제 해결 (Troubleshooting)

**govtrack 크롤러가 동작하지 않음**
```bash
docker compose -f docker/compose.yaml logs app --tail 50 | grep CycleStats
uv run bushexa crawl-once --route 195000177   # 로컬 단발 점검
```
`BUSHEXA_API_KEY` 설정 여부와 울산 BIS 접근성을 확인하세요. 로그에 `CycleStats` 가 보이면 정상입니다.

**DB 연결 오류 / `database is locked`**
```bash
# SQLite 파일 존재·권한 확인 (data/ 는 컨테이너에 rw로 bind-mount 되어야 함)
docker compose -f docker/compose.yaml exec app ls -l /app/data/bushexa.db
docker compose -f docker/compose.yaml exec app sqlite3 /app/data/bushexa.db '.tables'
```
세 프로세스가 같은 SQLite 파일을 공유하므로 동시쓰기는 `PRAGMA busy_timeout`(connection.py)으로 흡수됩니다.

**관리자 비밀번호 초기 설정 / 변경**

- 초기 설정: 첫 배포 직후 `/admin/login` 에 접속하면 로그인 대신 "새 비밀번호 / 확인" 폼이 나옵니다. 8자 이상으로 입력하면 저장되고 곧바로 로그인됩니다. 배포 후 바로 설정하세요.
- 변경: 로그인한 뒤 `/admin/password` 에서 현재 비밀번호를 확인하고 바꿉니다.
- 로그인에 5회 실패하면 해당 IP 가 잠시 잠깁니다(HTTP 423). 잠시 뒤 다시 시도하세요.

**울산 BIS 장애 / API quota** — 공공 서비스 특성상 간헐적 다운타임이 있습니다. `crawl-loop` 은 오류 시 재시도하므로 대기하면 자동 복구되며, `BUSHEXA_LOG_LEVEL=DEBUG` 로 상세 로그를 볼 수 있습니다.

**이미지 빌드 실패**
```bash
docker compose -f docker/compose.yaml build --no-cache
uv lock   # uv.lock 재생성이 필요한 경우
```
