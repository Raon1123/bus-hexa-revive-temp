---
status: living
last_verified: 2026-09-29 (HEAD 8dc582e)
audience: 이 저장소에서 작업하는 사람·AI 세션
---

# 아키텍처 설계 (현재 구현 기준)

> `docs/refactor/` 는 리팩터 **당시의 계획**이다. 이 문서는 **지금 코드가 실제로 어떻게 생겼는지**를 적는다.
> 둘이 어긋나면 이 문서와 코드가 우선이며, 어긋난 ADR은 §8 표에 표시한다.
> 코드 구조를 바꾸면 이 문서를 같은 커밋에서 갱신한다.

## 1. 한 장 요약

```text
 울산 BIS API ─┐                        ┌─> bus_arrival_cache (SQLite) ──┐
 국토부 TAGO ──┤  worker-arrival (7s) ──┘                                 │
               │  worker-govtrack (15s) ─> bus_timelog (SQLite) + logs.tsv├─> web (gunicorn) ─> 브라우저
 특일정보 API ─┤  worker-cache-refresh ──> holiday_cache.json,            │     (HTMX 폴링 / /lite)
 울산 시간표 ──┤   (하루 1회 02~03시)      data/timetable/*.json ─────────┤
 TAGO 열차·지하철┘                          rail_timetable.json ───────────┘
                                          관리자 편집 JSON (data/*.json) ─┘
```

- **단일 컨테이너 + supervisord 4 program**, 저장소는 **SQLite 단일 백엔드**.
- 공개 화면은 외부 API를 **직접 부르지 않는다**. 워커가 채운 캐시/파일만 읽는다(ADR-010).
- API 활용 상세는 [api-usage.md](api-usage.md).

## 2. 런타임 토폴로지

| supervisord program | 명령 | 주기 | 쓰는 것 |
|---|---|---|---|
| `web` | `python -m bushexa serve` (gunicorn sync, `BUSHEXA_WEB_WORKERS` 기본 2) | 요청 | 관리자 편집 파일, audit, lockout, recrawl 잡 |
| `worker-govtrack` | `crawl-loop` | 15s, 01~05시 야간 60s | `bus_timelog`, `data/logs.tsv`, `govtrack_state.json`, `govtrack_status.json` |
| `worker-arrival` | `arrival-loop` | 7s | `bus_arrival_cache`, `arrival_status.json` |
| `worker-cache-refresh` | `cache-refresh-loop` | 600s 점검, 02~03시 KST 1회 갱신 (철도는 부팅 시에도 그날 미성공이면) | `holiday_cache.json`, `data/timetable/*.json`, `rail_timetable.json` |

- 설정: [docker/supervisord.conf](../../docker/supervisord.conf), [docker/compose.yaml](../../docker/compose.yaml) (canonical podman 판은 루트 `compose.podman.yaml`).
- 포트 **8017(호스트) → 8000(컨테이너)**, healthcheck 는 `/lite`.
- bind mount: `../bushexa`(ro), `../data`(rw), `../secret`(ro), `../logs`.
  - 반영은 **`down` → `up -d --build`**(운영 podman-compose 는 `CONTAINERS_CONF_OVERRIDE=$PWD/containers.conf` 필수). 코드는 bind mount 라 `--build` 는 캐시로 금방 끝나지만, `restart app` 만으로는 새 코드가 반영되지 않았다(2026-09-30). 절차는 change-playbooks §6.
  - 컨테이너가 root 로 돌기 때문에 `data/` 의 런타임 파일이 **root 소유**로 생긴다(로컬에서 `rm`·편집 시 권한 오류 주의).
- Streamlit 시절 레거시는 `archive/streamlit-legacy/` 로 옮겨졌다(pytest 제외, 참고용). `old-stuff/`, `postgres-data/`, `media/` 도 현행 코드가 아니다. 수정 대상이 아니다.

## 3. 패키지 구조와 의존 방향 (헥사고날)

| 모듈 | 책임 |
|---|---|
| `cli.py`, `__main__.py` | argparse 진입점 (`bushexa = bushexa.cli:main`) |
| `config.py` | `AppConfig.from_env()` — env 우선, `secret/` 파일 fallback |
| `fileio.py` | **유일한 파일 쓰기 경로**: `atomic_write_*`, `read_json`, `locked_update_json` |
| `redact.py` | 시크릿 가림 단일 출처 `redact_secrets()` (serviceKey) |
| `time_utils.py` | `KST`, `Clock`/`KSTClock`, `get_weekday`(0 평일·1 토·2 일/공휴일) |
| `logging_setup.py` | KST 포매터 + 역할별 로테이팅 로그 |
| `api_clients/` | 외부 API 어댑터 — `_http`, `ulsan_bis`, `tago`, `holiday`, `composite_location`, `cached_arrival`, `errors` |
| `db/` | `connection`(SQLite WAL·busy_timeout 5000), `schema`, `repo`(`BusLogRepo`), `repo_arrival` |
| `crawler/` | `daemon`, `recorder`, `state`, `arrival_poller`, `cache_refresh`, `timetable_crawl`, `parsers` |
| `data/` | `constants.py`(정적 노선·정류장 메타), `timetable.py`(시간표 로드·검증·캐시) |
| `domain/` | **순수 뷰모델 빌더** — board, busno, stops, running, unist_board, unist_timetable, busan, seoul, rail_board(발차 안내판·정차역 띠), rail_match(동해선 시각 매칭). client·clock 주입 |
| `services/` | 파일 기반 스토어·에디터 — board_support, holiday_*, special_timetable, via_editor, changelog_editor, crawl_settings, audit_log, auth, backup, recrawl_job, *_status, log_reader, stop_cache, timetable_editor, route_map_ab(노선도 A/B 카운터) |
| `web/` | Flask 팩토리(`app.py`: CSRF·i18n·Server-Timing), `routes/`, `templates/`, `static/`, `i18n.py`, `route_diagram.py`(노선도 SVG·노선 경로 데이터), `route_lines.py`(노선별 목록 뷰모델) |

**의존 규칙 (grep 으로 확인됨, 깨지 말 것)**

- `domain/` 은 `data.constants`, `data.timetable`, `time_utils` 만 import 한다. web·db·services·crawler·api_clients 금지.
- `data/` 는 `fileio` 만, `db/` 는 자기 자신만 import 한다.
- `web` 은 누구도 import 하지 않는다(최상위).
- 알려진 예외 1건: `api_clients/cached_arrival.py` → `db.repo_arrival` (캐시 드롭인 어댑터).

## 4. 저장소

### 4.1 SQLite 테이블 ([db/schema.py](../../bushexa/db/schema.py))

| 테이블 | 용도 | 비고 |
|---|---|---|
| `bus_timelog(idx, stop_id, route_id, route_nm, vehicle_number, stop_name)` | 버스 통과 기록 | `UNIQUE(idx, vehicle_number, stop_id)` + `INSERT OR IGNORE` |
| `bus_arrival_cache(stop_id PK, payload JSON, fetched_at)` | 도착정보 캐시 | arrival 워커 upsert, 웹은 읽기만 |

- `create_schema` 는 **멱등**이다. 웹도 첫 read 연결 때 호출한다(워커 부팅 순서에 의존하지 않기 위해, [PM-009](../refactor/postmortems/PM-009-lite-500-schema-boot-order.md)).
- PostgreSQL 코드(psycopg2 지연 import)는 남아 있지만 **배포는 SQLite 단독**이다.

### 4.2 `data/` 파일

| 파일 | 소유 모듈 | 쓰기 방식 | git |
|---|---|---|---|
| `timetable/<노선>.json` `{"0"/"1"/"2": {출발지: ["HH:MM"]}}` (UNIST 5노선 + 수집 전용 5001·1224) | data/timetable, crawler/timetable_crawl | atomic | **추적** |
| `timetable/special/<edition>/<노선>.json`, `special_timetables.json` | services/special_timetable | atomic | 미추적 |
| `changelog.json` `[{"date","description"}]` (오래된 순) | services/changelog_editor | atomic | **추적** |
| `holidays.json`(관리자 지정) / `holiday_cache.json`(API 캐시) | holiday_editor / holiday_service | atomic | 미추적 |
| `via_overrides.json` | via_editor | atomic | 미추적 |
| `rail_timetable.json` `{"trains": {"pairs": {"<출발>-<도착>": {"dates": {"YYYY-MM-DD": {"trains", "suspect"}}}}}, "metro": {"schedules": {"<역>:<U/D>:<01/02/03>": {"times"}}}}` | services/rail_timetable (cache-refresh·`crawl-rail`) | **locked_update_json** | ignore(런타임) |
| `ktx_leg_profile.json` `{"period", "sources", "legs": {구간: {"by_day": {"0/1/2": {"all", "hours": {H: {n,p10,p50,p90}}}}}}}` (513 구간 소요, /ktx 입력) | services/leg_profile (CLI `build-leg-profile`, `/admin/rail` 후보→적용) | atomic | **추적** |
| `ktx_leg_profile.candidate.json` / `.prev.json` (관리자 재계산 후보·이전 값), `rail_crawl_*`·`ktx_profile_*` 잡 메타·진행 | admin_rail, recrawl_job | atomic / locked | ignore |
| `ktx_settings.json` (연계표 환승 최소 시간 기본값 0~30분) | services/ktx_settings (`/admin/rail`) | atomic | 미추적 |
| `crawl_settings.json` (폴링 주기 3~600s) | services/crawl_settings | atomic | 미추적 |
| `route_map_ab.json` `{"YYYY-MM-DD": {event: count}}` (노선도 A/B 노출·전환) | services/route_map_ab | locked | ignore |
| `notices.json` 기한형 공지 (표시 기간·시행일·대상 화면/노선). 없거나 깨지면 seed `bushexa/data/notices.seed.json` | services/notices, `/admin/notices` | **locked_update_json** | 미추적 |
| `audit_log.json`, `admin_lockout.json`, `timetable_crawl_job.json` | audit_log, admin, recrawl_job | **locked_update_json** | 미추적 |
| `govtrack_state.json`, `govtrack_status.json`, `arrival_status.json` | crawler/state, *_status | atomic | 미추적(런타임) |
| `logs.tsv` | crawler/daemon (FileHandler append) | append | **추적(주의)** |
| `manager_password.txt` (Argon2id 해시) | services/auth | atomic | **ignore — 절대 커밋 금지** |
| `bushexa.db*`, `timetable_backup/`, `debug/`(운영 DB 스냅샷) | db, timetable_editor, debug-running | — | ignore |

- 백업 화이트리스트([services/backup.py](../../bushexa/services/backup.py)): `holidays.json`, `special_timetables.json`, `via_overrides.json`, `crawl_settings.json`, `notices.json`, `ktx_settings.json`, `timetable/special/**`. `notices.json` 은 복구 때 항목 단위까지 검증한다.
- `bushexa/web/static/data/changelog.json` 은 **시드(fallback)** 이며 2025-08 이후 갱신되지 않았다. 변경이력은 `data/changelog.json` 을 고친다.

## 5. 핵심 불변식 (Invariants)

| # | 불변식 | 위치 |
|---|---|---|
| I-1 | 파일 쓰기는 `fileio.atomic_write_*` 만 쓴다(tmp → fsync → `os.replace`, INFO 로그에 경로·크기만). | [fileio.py](../../bushexa/fileio.py) |
| I-2 | 여러 프로세스/워커가 read-modify-write 하는 파일은 `locked_update_json`(fcntl). atomic write 는 **lost update 를 막지 못한다**. | fileio.py `locked_update_json` |
| I-3 | 웹 프로세스 상태(잡, lockout 등)를 `current_app.config`·모듈 전역에 두지 않는다. gunicorn 워커가 2개 이상이다. | review #6, #9 |
| I-4 | 공개 라우트는 외부 API 호출 금지. `board_support.arrival_client`(DB 캐시)만 사용. 예외는 관리자 recrawl·특별시간표 미리보기뿐. | ADR-010 |
| I-5 | 시간표 선택 우선순위는 **특별편 > 공휴일 > 요일**이며 `services/board_support.timetable_provider_for` 하나로만 결정한다. 라우트에서 `get_timetable` 을 직접 부르지 않는다. | board_support.py, review #4·#5 |
| I-6 | 시간대는 `time_utils.KST` 하나. `ZoneInfo("Asia/Seoul")` 리터럴·naive `datetime.now()` 금지. 시간 의존 코드는 `Clock` 주입. | ADR-008 |
| I-7 | 노선·정류장 ID와 문구는 `data/constants.py` 에만 둔다(`UNIST_VIA_STOP_ID`, `ROUTEID`, `EXTRA_TRACKED_ROUTES`·`TRACKED_ROUTES`(수집 전용 노선, UNIST 화면 제외), `VIA_STOPS`, `SERACH_STOPS`, `STOP_IDS`, `clean_stop_name`). `STOP_IDS[...]` 직접 인덱싱 금지, `.get` 사용. | ADR-011, PM-001 H3 |
| I-8 | 데몬 루프는 예외로 죽지 않는다. 격리 단위는 cycle > route > request, 삼킨 예외는 반드시 로그. | ADR-013 |
| I-9 | "비어 있음"과 "오류"를 구분한다. API 오류를 빈 리스트로 돌려주거나, 실패 결과로 좋은 캐시/파일을 덮어쓰지 않는다. | review #1~#3, [PM-008](../refactor/postmortems/PM-008-holiday-silent-empty-and-overwrite.md) |
| I-10 | 설정 우선순위: env > `secret/` 파일. 새 설정은 env 로 추가하고 `.env.example` 에 문서화한다. | ADR-005, config.py |

### 5.1 캐시

- **read 연결 캐시** — `services/board_support.py` 의 `_READ_CONN_CACHE`(URL 키, `SELECT 1` 생존 확인, 첫 연결 시 `create_schema`). 테스트는 autouse 픽스처로 매번 `_reset_read_connections()`([PM-010](../refactor/postmortems/PM-010-read-connection-cache-cold-start-and-test-leak.md)).
- **시간표 캐시** — `data/timetable.py`, (mtime_ns, size) 서명, 원자 교체 시 자동 무효화. 복사본(list)을 반환하므로 호출자가 변형해도 안전.
- **stop_cache** — 정류장 화면용 in-memory 10s TTL.
- **CompositeLocationClient 도착정보 캐시** — 8s, 단일 락(TAGO 동시 장애 시 울산 fallback 쇄도 방지).

### 5.2 크롤러 동시성

- `BUSHEXA_{GOVTRACK,ARRIVAL}_FETCH_WORKERS`(기본 1). 켜면 **fetch 만 병렬**, 상태·알림·DB 쓰기는 메인 스레드에서 고정 순서로 처리(SQLite `check_same_thread`, 노선별 격리 보존).
- 기본값 1은 **라이브 스모크 게이트 대기 중**이다. 4로 올려 상류 오류율이 1일 때보다 나빠지지 않으면 승격한다.
- 폴링 주기는 `data/crawl_settings.json` 을 **매 사이클 재읽기**한다(관리자 화면 `/admin/crawl-settings` 가 CLI 인자보다 우선).

## 6. 보안 설계

- 관리자 인증: Argon2id(argon2-cffi). legacy PBKDF2/평문은 검증만 호환하고 로그인 시 재해시. `MANAGER_PASSWORD` env override 존재.
- 로그인 lockout: IP당 5회 실패 → 10s, `admin_lockout.json` 에 워커 간 공유.
- CSRF: `/admin/*` 비-GET 전체. 폼 `csrf_token` 또는 `X-CSRFToken` 헤더, `hmac.compare_digest`(bytes 비교). 실패 400. 위치 [web/app.py](../../bushexa/web/app.py).
- `next` 파라미터는 `_safe_next` 다층 검증([PM-007](../refactor/postmortems/PM-007-admin-login-open-redirect.md)).
- 로그 뷰어는 시크릿 마스킹(`Bearer` 포함, [PM-006](../refactor/postmortems/PM-006-bearer-token-masking-bypass.md)).
- API 인증키(`serviceKey=`) 가림: `bushexa/redact.py` 를 로그 포매터(`KSTFormatter`), 상태·진행 파일(`arrival_status`, `recrawl_job`), 로그 뷰어에 적용([PM-016](../refactor/postmortems/PM-016-api-key-in-log-files.md)).
- CSV 내보내기는 수식 인젝션 방어(repo sanitize).

## 7. 설정·CLI

환경변수 전체:

| 변수 | 기본 | 비고 |
|---|---|---|
| `BUSHEXA_API_KEY` | 필수(또는 `secret/key.txt`) | data.go.kr 인증키 |
| `DATABASE_URL` | 필수(또는 `secret/db.yaml`) | `sqlite:///./data/bushexa.db` |
| `BUSHEXA_SESSION_SECRET` | 미설정 시 휘발 키 + 경고 | 재시작마다 세션 초기화 |
| `BUSHEXA_SESSION_COOKIE_SECURE` | false | HTTPS 운영 시 true |
| `BUSHEXA_LOG_LEVEL` / `BUSHEXA_LOG_DIR` | INFO / logs | |
| `BUSHEXA_API_TIMEOUT_SECONDS` | 15 | [PM-012](../refactor/postmortems/PM-012-ulsan-api-timeout-10s.md) |
| `BUSHEXA_WEB_WORKERS` | 2 | gunicorn |
| `BUSHEXA_ARRIVAL_POLL_SECONDS` | 7 | **현재 무효** — CLI `--poll` 기본값 7.0 이 항상 이긴다. 주기 변경은 관리자 크롤 설정으로 |
| `BUSHEXA_{GOVTRACK,ARRIVAL}_FETCH_WORKERS` | 1 | §5.2 |
| `BUSHEXA_TSV_PATH` | `data/logs.tsv` | |
| `BUSHEXA_TIMETABLE_DIR` | `data/timetable` | 테스트·실험 시 격리용 |
| `MANAGER_PASSWORD` | 없음 | 관리자 비밀번호 override |

CLI: `serve`, `crawl-once --route RID [--dry-run]`, `crawl-loop`, `arrival-loop`, `cache-refresh-loop`, `init-db [--reset]`, `crawl-timetable [--vacation]`, `debug-running --route --date [--db 스냅샷] [-v]`(운행 재구성 진단, config 불필요 — 운영 DB 스냅샷은 `data/debug/` 에 두며 ignore 됨). 데몬은 SIGTERM/SIGINT 로 정상 종료하고 역할별 로그 파일(`bushexa.log`, `bushexa-crawl.log`, `bushexa-arrival.log`, `bushexa-cache.log`)을 쓴다.

## 8. ADR 현행성

| ADR | 결정 | 현재 코드와 일치? |
|---|---|---|
| 001 | Flask 3 + Jinja2 + HTMX + vanilla JS | 일치 |
| 002 | SQLite 기본 / PostgreSQL 전환 가능 | **부분 불일치** — 배포는 SQLite 단독, postgres extra 제거 |
| 003 | uv + pyproject + Python 3.12 | 일치 |
| 004 | HTMX 폴링 + SSE | 대체로 일치 — SSE 는 관리자(recrawl 진행, govtrack 상태)에만 |
| 005 | env > secret 파일 | **세부 불일치** — 비밀번호는 `data/manager_password.txt`(Argon2id) |
| 006 | web/worker/postgres 분리 컨테이너, 비루트, 포트 5000 | **불일치** — 단일 컨테이너 supervisord 4 program, root, 8000 |
| 007 | 단일 `bushexa/` 패키지 | 일치 |
| 008 | 3층 테스트 + 시뮬레이션 + Postgres testcontainers | 부분 — Postgres·integration 테스트 없음, 매트릭스의 일부 테스트명 오기 |
| 009 | 구현 후 보안 감리 게이트 | 프로세스 |
| 010 | 도착정보 캐시 워커, 화면은 캐시만 | 공개 라우트는 일치(관리자 예외 2건) |
| 011 | 표시 정류장은 constants 가 권위 | 일치 |
| 012 | 모든 파일 쓰기는 fileio 경유 + 감사 로그 | 대체로 — 예외: recrawl 진행 jsonl(raw append), config 비밀번호 1회 이전, TSV |
| 013 | 루프 불사·격리·로그 | 일치 |
| 014 | 다국어 확장: UI 문자열은 코드 사전, 정류소 이름은 관리자 편집 1:1 사전 | **draft — 아직 미구현**. i18n 작업 전 반드시 읽을 것 |

## 9. 테스트 구조

- `tests/{api_clients,config,crawler,data,db,domain,services,web,security,simulation,unit}` + `tests/fixtures/{tago,ulsan,holiday}`(실응답 샘플).
- 주요 픽스처([tests/conftest.py](../../tests/conftest.py)): `FakeClock`/`fake_clock`(2026-06-01 08:30 KST 월요일), `tmp_sqlite_db`, `mock_tago_client`, `app_config_test`, opt-in `no_network`. autouse 는 read 연결 캐시 리셋.
- 실행: `uv run pytest -q` (단위만 `-m "not integration"`). 2026-09-29 기준 573 passed(C.UTF-8·en_US.UTF-8 모두).
  - `Failed to spawn: pytest` 가 나오면 `.venv` 가 다른 경로(`~/Project/...`)에서 만들어진 것이다. `uv sync --reinstall` 하거나 `uv run python -m pytest` 를 쓴다.
- CI: `.github/workflows/ci.yml` — `uv sync --frozen` + pytest(커버리지 측정만) + `docker build -f docker/Dockerfile` (Dockerfile 경로 회귀 감지).
- 규약은 [pitfalls.md §테스트](pitfalls.md#6-테스트) 참고.
