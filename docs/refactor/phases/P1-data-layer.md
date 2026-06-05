---
status: implemented
phase_id: P1
designer: opus
auditor_status: execution-pass (2026-06-01, EC-1~10 green, 51 P1 tests pass, 전체 60 pass)
last_updated: 2026-06-01
depends_on: [P0]
---

# P1 — Data Layer + API Clients (UI 무관)

## 1. 목적

constants, timetable JSON 로더, time utils, DB connection + repo, 외부 API client (TAGO/Ulsan/Holiday), parser를 신규 패키지에 이전하여 UI/데몬과 독립된 재사용 가능 도메인 토대를 만든다.

## 2. 시작 조건 (Entry Criteria)

- [ ] P0 Auditor PASS
- [ ] 모든 P0 work item EC-1~8 PASS
- [ ] ADR-002 (Database), ADR-005 (Secrets), ADR-007 (Layout), ADR-008 (Testing) 모두 Auditor PASS
- [ ] ADR-011 (상수 API 완화 — 표출 정류소 고정), ADR-012 (파일 변경 감사 로깅), ADR-013 (오류 로그+계속) 반영

## 3. 종료 조건 (Exit Criteria — Auditor checklist)

- [ ] EC-1: `uv run python -c "from bushexa.data.constants import ROUTEID, STOP_IDS; print(len(ROUTEID))"` → 10
- [ ] EC-2: `uv run python -c "from bushexa.api_clients.tago import TagoClient; print(TagoClient('dummy').base_url)"` 무오류
- [ ] EC-3: `uv run pytest tests/unit/ tests/db/ tests/api_clients/ -q` → 0 fail / 0 error
- [ ] EC-4: SQLite in-memory에서 insert→query 라운드트립 정상 (`tests/db/test_repo_sqlite.py` 통과)
- [ ] EC-5: 9개 fixture(tago 5 / ulsan 3 / holiday 1) 모두 parser로 정상 변환
- [ ] EC-6: `! grep -rn 'import streamlit' bushexa/data/ bushexa/api_clients/ bushexa/db/ bushexa/crawler/parsers.py`
- [ ] EC-7: `BusLogRepo` 공개 메서드가 F09 §4.4 + F04 §4.4 시그니처와 일치 (`uv run python -c "import inspect, bushexa.db.repo as r; print([m for m in dir(r.BusLogRepo) if not m.startswith('_')])"`)
- [ ] EC-8: time_utils가 freezegun으로 평일/토/일/공휴일 분기 검증 통과 (`tests/unit/test_time_utils.py`)
- [ ] EC-9: `bushexa/fileio.py` 헬퍼가 신규 파일은 `created`, 기존 파일은 `modified`로 INFO 로그를 남기고 원자적 쓰기를 한다 (ADR-012, `tests/unit/test_fileio.py`)
- [ ] EC-10: `bushexa/` 내 직접 디스크 쓰기 0건 — `! grep -rn "open(.*['\"]w['\"]\|\.write_text(\|\.write_bytes(\|json\.dump(" bushexa/ --include='*.py' | grep -v fileio.py` 가 빈 결과 (ADR-012 choke-point 강제)

### 3.1 EC ↔ Work Item AC 매핑 (P-8 / P-12 추적성)

| EC | 검증 대상 | 충족하는 Work Item AC |
|---|---|---|
| EC-1 | constants 노출 | W1: AC-1, AC-2 |
| EC-2 | TagoClient 생성 | W7: AC-1 |
| EC-3 | pytest 전체 | W1~W10 각 AC의 검증 pytest 합집합 |
| EC-4 | SQLite CRUD | W6a: AC-1, AC-2; W6b: AC-1 |
| EC-5 | fixture 파싱 | W7: AC-2; W8: AC-1; W9: AC-1; W10: AC-1, AC-2 |
| EC-6 | streamlit 0건 | 전 work item 공통 제약 (W1~W10) |
| EC-7 | repo 시그니처 | W6a: AC-3; W6b: AC-2 |
| EC-8 | time 분기 | W2: AC-1, AC-2 |
| EC-9 | 파일 쓰기 로그 | W12: AC-1, AC-2 |
| EC-10 | 직접 쓰기 0건 | W12: AC-3 (전 work item 공통 제약) |

> 모든 work item AC가 ≥1개 EC에 매핑됨. 누락 0건.

## 4. Work Item 분해

| ID | 작업 제목 | 소요 | 의존 | 산출물 |
|---|---|---|---|---|
| W1 | constants 이전 | S | — | bushexa/data/constants.py + tests/unit/test_constants.py |
| W2 | time_utils (KST/weekday/holiday) | M | W1 | bushexa/time_utils.py + tests/unit/test_time_utils.py |
| W3 | timetable JSON 로더 | M | W1 | bushexa/data/timetable.py + tests/unit/test_timetable_loader.py |
| W4 | db/connection.py | M | — | bushexa/db/connection.py + tests/db/test_connection.py |
| W5 | db/schema.py | S | W4 | bushexa/db/schema.py + tests/db/test_schema.py |
| W6a | db/repo.py Write API | M | W4, W5 | bushexa/db/repo.py(write) + tests/db/test_repo_sqlite.py |
| W6b | db/repo.py Read API | M | W6a | bushexa/db/repo.py(read) + tests/db/test_repo_read.py |
| W7 | api_clients/tago.py | M | — | bushexa/api_clients/tago.py + tests/api_clients/test_tago.py |
| W8 | api_clients/ulsan_bis.py | M | — | bushexa/api_clients/ulsan_bis.py + tests/api_clients/test_ulsan_bis.py |
| W9 | api_clients/holiday.py | S | — | bushexa/api_clients/holiday.py + tests/api_clients/test_holiday.py |
| W10 | crawler/parsers.py | M | W7, W8 | bushexa/crawler/parsers.py + tests/crawler/test_parser_bus_location.py |
| W11 | db: BusArrivalRepo (ADR-010 백업본 upsert/read) | M | W4, W5 | bushexa/db/repo_arrival.py + tests/db/test_arrival_repo.py |
| W12 | fileio 쓰기 choke-point (ADR-012 감사 로깅) | S | — | bushexa/fileio.py + tests/unit/test_fileio.py |

## 5. Work Item 상세

### W1 — constants 이전
**Owner:** unassigned **Depends:** — **산출물:** `bushexa/data/constants.py`, `tests/unit/test_constants.py`

**지시사항 (명령형):**
1. `src/constants.py`를 `bushexa/data/constants.py`로 복사한다. 데이터 값(ROUTEID, STOP_IDS, SERACH_STOPS, VIA_STOPS, UNISTBUS, ULSAN_CITYCODE, ULSAN_PREFIX, WEEKDAY_STR, UNIST_STR)은 한 글자도 변경하지 않는다.
2. 모듈 상단에 docstring 한 줄을 추가한다: `"""정적 노선·정류장 메타데이터. 외부 의존 없음."""`
3. `tests/unit/test_constants.py`를 작성한다 (아래 테스트 케이스 참조).
4. `! grep -n 'import streamlit' bushexa/data/constants.py`로 streamlit 의존이 없음을 확인한다.

**Acceptance:**
- [ ] AC-1: `from bushexa.data.constants import ROUTEID, STOP_IDS, SERACH_STOPS, VIA_STOPS, UNISTBUS, ULSAN_CITYCODE, ULSAN_PREFIX` 가 모두 성공한다 (검증: `uv run pytest tests/unit/test_constants.py::test_all_symbols_importable`)
- [ ] AC-2: `ROUTEID`의 모든 `stop_ids` 항목이 `STOP_IDS` 키에 존재한다 (검증: `uv run pytest tests/unit/test_constants.py::test_routeid_stops_subset_of_stop_ids`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_all_symbols_importable`: constants 모듈에서 7개 공개 심볼을 import 했을 때 ImportError 없이 모두 로드되고 ROUTEID 길이가 정확히 10인지 검증한다.
- `test_routeid_stops_subset_of_stop_ids`: ROUTEID 각 노선의 4번째 요소(stop_ids 리스트)에 든 모든 정류장 ID가 STOP_IDS 딕셔너리 키에 존재하는지 검증한다 — 누락 시 govtrack의 stop_name 조회가 깨지므로 데이터 무결성 보증.
- `test_stop_ids_values_nonempty`: STOP_IDS의 모든 값(정류장 한글명)이 빈 문자열이 아님을 검증한다.

**검증 명령:**
```bash
uv run pytest tests/unit/test_constants.py -v
```

---

### W2 — time_utils
**Owner:** unassigned **Depends:** W1 **산출물:** `bushexa/time_utils.py`, `tests/unit/test_time_utils.py`

**지시사항 (명령형):**
1. `src/tools.py`의 `get_now`, `get_weekday`, `get_time` 함수를 `bushexa/time_utils.py`로 이전한다. `import streamlit`을 제거한다.
2. `Clock` Protocol과 기본 구현 `KSTClock`(`now() -> datetime` KST aware)을 정의한다 (ADR-008).
3. 공휴일 판정을 순수 함수 `is_holiday(d: date, holiday_set: set[str]) -> bool`로 분리한다 (네트워크/파일 의존 제거).
4. `get_weekday`가 공휴일·일요일이면 2, 토요일이면 1, 평일이면 0을 반환하도록 보장한다.
5. `tests/unit/test_time_utils.py`를 작성한다.

**Acceptance:**
- [ ] AC-1: freezegun으로 고정한 4개 날짜(평일/토/일/공휴일)에서 `get_weekday`가 각각 0/1/2/2를 반환한다 (검증: `uv run pytest tests/unit/test_time_utils.py -k weekday`)
- [ ] AC-2: `KSTClock().now()`의 tzinfo가 KST(UTC+9)이다 (검증: `uv run pytest tests/unit/test_time_utils.py::test_kstclock_is_kst`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_weekday_on_plain_weekday`: 2026-06-01(월)을 freeze하고 빈 holiday_set을 줄 때 get_weekday가 0(평일)을 반환하는지 검증한다.
- `test_weekday_on_saturday`: 2026-06-06(토, 단 공휴일 현충일이므로 별도 케이스)와 구분되는 일반 토요일을 freeze하여 1을 반환하는지 검증한다.
- `test_weekday_on_sunday`: 일요일을 freeze하여 2를 반환하는지 검증한다.
- `test_weekday_on_holiday_weekday`: 평일이지만 holiday_set에 포함된 날짜를 freeze하여, 평일임에도 2(일/공휴일 스케줄)를 반환하는지 검증한다 — 공휴일 우선 규칙 보증.
- `test_kstclock_is_kst`: KSTClock().now()가 반환하는 datetime의 utcoffset이 정확히 9시간인지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/unit/test_time_utils.py -v
```

---

### W3 — timetable JSON 로더
**Owner:** unassigned **Depends:** W1 **산출물:** `bushexa/data/timetable.py`, `tests/unit/test_timetable_loader.py`

**지시사항 (명령형):**
1. `src/tools.py`의 `get_timetable`, `get_busroute_info`, `init_timetable`을 `bushexa/data/timetable.py`로 이전하고 streamlit 의존을 제거한다.
2. 시간표 디렉토리 기본값을 `data/timetable/`로 하되 `BUSHEXA_TIMETABLE_DIR` 환경변수로 override 가능하게 한다.
3. `validate_timetable(data) -> list[ValidationIssue]`를 추가한다: weekday 키 ∈ {"0","1","2"}, 시각 형식 `HH:MM`, 0≤HH≤23, 0≤MM≤59, 중복 없음을 검사한다.
4. `tests/unit/test_timetable_loader.py`를 작성한다 (tmp_path에 sample JSON 생성).

**Acceptance:**
- [ ] AC-1: 5개 노선 JSON(513/713/743/753/1115)을 `get_timetable`로 읽으면 빈 리스트가 아닌 "HH:MM" 목록을 반환한다 (검증: `uv run pytest tests/unit/test_timetable_loader.py -k load`)
- [ ] AC-2: 잘못된 형식("25:00", 중복) JSON에 대해 `validate_timetable`이 해당 ValidationIssue를 반환한다 (검증: `uv run pytest tests/unit/test_timetable_loader.py -k validate`)
- [ ] AC-3: `BUSHEXA_TIMETABLE_DIR` 설정 시 그 경로에서 읽는다 (검증: `uv run pytest tests/unit/test_timetable_loader.py::test_env_override`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_load_existing_route`: tmp_path에 713.json(평일 UNIST 출발 3건)을 만들고 get_timetable("713", 0, "UNIST")이 그 3건을 정렬된 순서로 반환하는지 검증한다.
- `test_validate_rejects_out_of_range`: weekday 0의 시각에 "25:00"을 넣은 데이터에 validate_timetable이 code="out_of_range" 이슈를 1건 반환하는지 검증한다.
- `test_validate_rejects_duplicate`: 동일 시각이 2번 든 데이터에 validate가 code="duplicate" 이슈를 반환하는지 검증한다.
- `test_env_override`: BUSHEXA_TIMETABLE_DIR을 tmp_path로 설정하면 기본 경로가 아닌 그 경로의 JSON을 읽는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/unit/test_timetable_loader.py -v
```

> **구현 메모 (Designer 승인 분할, ADR-012 정합):** 런타임 경로(`get_timetable`/`get_busroute_info`/`validate_timetable`)와 **쓰기 경로 `save_timetable`**(fileio 경유 원자적 쓰기+감사 로그)을 구현. legacy `init_timetable`(xlsx→json **1회성 부트스트랩**, openpyxl 의존)은 현재 `timetable/*.json`이 이미 존재하므로 P2 시간표 도구로 이연한다. 그때의 저장도 반드시 `save_timetable`(=fileio)을 거친다. `save_timetable` 회귀: `test_save_timetable_via_fileio`(생성 시 'created' 감사 로그 확인).

---

### W4 — db/connection.py
**Owner:** unassigned **Depends:** — **산출물:** `bushexa/db/connection.py`, `tests/db/test_connection.py`

**지시사항 (명령형):**
1. `create_connection(dsn: str) -> Connection` 팩토리를 작성한다. `sqlite:///path`, `sqlite:///:memory:`, `postgresql://...` 3형식 DSN을 파싱한다.
2. SQLite 연결 시 `PRAGMA journal_mode=WAL`과 `PRAGMA foreign_keys=ON`을 실행한다.
3. psycopg2 미설치 환경에서 `postgresql://` DSN을 받으면 명확한 메시지의 `ImportError`를 던진다 (deferred import).
4. parameter style 차이(`?` vs `%s`)를 흡수하는 `placeholder(dsn) -> str` 헬퍼를 둔다.
5. `tests/db/test_connection.py`를 작성한다.

**Acceptance:**
- [ ] AC-1: `sqlite:///:memory:` DSN으로 connect 후 `SELECT 1` 실행이 1을 반환한다 (검증: `uv run pytest tests/db/test_connection.py::test_sqlite_memory_connect`)
- [ ] AC-2: SQLite 연결의 journal_mode가 wal이다 (검증: `uv run pytest tests/db/test_connection.py::test_wal_enabled`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_sqlite_memory_connect`: `sqlite:///:memory:` DSN을 create_connection에 주면 연결이 생성되고 `SELECT 1`이 1을 돌려주는지 검증한다.
- `test_wal_enabled`: SQLite 연결 후 `PRAGMA journal_mode`를 조회하면 'wal'이 반환되는지 검증한다 — 단일 writer + 다중 reader 동시성 보증.
- `test_postgres_dsn_without_driver_raises`: psycopg2를 monkeypatch로 None 처리한 뒤 postgresql DSN을 주면 안내 메시지를 가진 ImportError가 발생하는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/db/test_connection.py -v
```

---

### W5 — db/schema.py
**Owner:** unassigned **Depends:** W4 **산출물:** `bushexa/db/schema.py`, `tests/db/test_schema.py`

**지시사항 (명령형):**
1. `create_schema(conn) -> None`을 작성한다: `bus_timelog` 테이블(idx, stop_id, route_id, route_nm, vehicle_number, stop_name)을 `CREATE TABLE IF NOT EXISTS`로 만든다.
2. F09 §5의 인덱스 3종(`ix_bus_timelog_route_idx`, `ix_bus_timelog_stop_idx`, `ix_bus_timelog_vehicle`)을 `IF NOT EXISTS`로 추가한다. **추가로 ADR-010의 `bus_arrival_cache`(stop_id TEXT PRIMARY KEY, payload TEXT, fetched_at TEXT) 테이블도 `IF NOT EXISTS`로 생성한다 (울산 도착정보 백업본).**
3. SQLite와 Postgres 양쪽에서 동작하는 공통 DDL을 사용한다 (타입은 VARCHAR/TEXT 공통).
4. `tests/db/test_schema.py`를 작성한다.

**Acceptance:**
- [ ] AC-1: in-memory SQLite에 create_schema 호출 후 `bus_timelog` 테이블이 존재한다 (검증: `uv run pytest tests/db/test_schema.py::test_table_created`)
- [ ] AC-2: create_schema를 2회 연속 호출해도 예외가 없다 (idempotent) (검증: `uv run pytest tests/db/test_schema.py::test_idempotent`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_table_created`: 빈 SQLite에 create_schema 후 sqlite_master를 조회하면 bus_timelog 테이블과 3개 인덱스가 모두 존재하는지 검증한다.
- `test_idempotent`: create_schema를 두 번 호출해도 OperationalError("table already exists") 없이 통과하는지 검증한다 — 컨테이너 재시작 시 안전성 보증.

**검증 명령:**
```bash
uv run pytest tests/db/test_schema.py -v
```

---

### W6a — db/repo.py Write API
**Owner:** unassigned **Depends:** W4, W5 **산출물:** `bushexa/db/repo.py`(write 부분), `tests/db/test_repo_sqlite.py`

**지시사항 (명령형):**
1. `BusLogRepo(conn)` 클래스를 만들고 `insert_log(*, idx, stop_id, route_id, vehicle_no, stop_name=None)`을 구현한다.
2. `insert_batch(rows: Iterable[LogRow]) -> int`를 구현한다: 한 트랜잭션으로 묶고 마지막에 1회 commit, 예외 시 rollback.
3. parameter placeholder는 W4의 `placeholder()` 헬퍼로 백엔드 차이를 흡수한다.
4. `tests/db/test_repo_sqlite.py`에 write 케이스를 작성한다.

**Acceptance:**
- [ ] AC-1: `insert_batch`로 100건 삽입 후 테이블 행 수가 100이다 (검증: `uv run pytest tests/db/test_repo_sqlite.py::test_batch_inserts_100`)
- [ ] AC-2: 배치 도중 예외 발생 시 rollback되어 0건이 남는다 (검증: `uv run pytest tests/db/test_repo_sqlite.py::test_batch_rollback_on_error`)
- [ ] AC-3: `insert_log` 시그니처가 keyword-only(idx, stop_id, route_id, vehicle_no, stop_name)로 F09 §4.4와 일치한다 (검증: `uv run pytest tests/db/test_repo_sqlite.py::test_insert_log_signature`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_batch_inserts_100`: 100개 LogRow를 insert_batch에 주면 단일 트랜잭션으로 커밋되고 `SELECT count(*)`가 100을 반환하는지 검증한다.
- `test_batch_rollback_on_error`: 배치 중간 행에서 의도적으로 무결성 위반을 일으켜 예외가 나면 트랜잭션 전체가 rollback되어 테이블이 비어 있는지 검증한다 — H5(부분 commit 방지) 회귀.
- `test_insert_log_signature`: inspect로 insert_log의 파라미터가 keyword-only이고 이름이 명세와 정확히 일치하는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/db/test_repo_sqlite.py -v
```

---

### W6b — db/repo.py Read API
**Owner:** unassigned **Depends:** W6a **산출물:** `bushexa/db/repo.py`(read 부분), `tests/db/test_repo_read.py`

**지시사항 (명령형):**
1. `query_paged(*, route_id=None, stop_id=None, vehicle_no=None, day=None, page=1, size=100) -> PagedResult[LogRow]`를 구현한다 (day는 `idx LIKE 'YYYYMMDD_%'`).
2. `count(**filters) -> int`, `get_by_route(route_id, day=None) -> list[LogRow]`, `latest_node_per_vehicle(since) -> dict[(route_id,vehicle_no), nodeid]`를 구현한다.
3. `export_csv(**filters, max_rows=10000) -> Iterator[bytes]`를 구현한다 (UTF-8 BOM 선두).
4. `tests/db/test_repo_read.py`를 작성한다 (시드 데이터 fixture 사용).

**Acceptance:**
- [ ] AC-1: route_id+day 필터 결과 행 수가 동일 조건 raw count와 일치한다 (검증: `uv run pytest tests/db/test_repo_read.py::test_filter_matches_count`)
- [ ] AC-2: `query_paged`, `count`, `get_by_route`, `latest_node_per_vehicle`, `export_csv` 5개 메서드가 모두 존재한다 (검증: `uv run pytest tests/db/test_repo_read.py::test_read_api_surface`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_filter_matches_count`: 시드된 로그에서 특정 route_id와 day로 query_paged한 행 수가 같은 조건 count()와 일치하는지 검증한다.
- `test_pagination_boundaries`: size=10으로 25건을 페이지 1/2/3로 나눠 조회하면 각각 10/10/5건이 나오고 total이 25인지 검증한다.
- `test_latest_node_per_vehicle`: 한 차량의 여러 통과 기록 중 가장 최근 nodeid가 반환되는지 검증한다 — H2 warm 기능의 기반.
- `test_export_csv_has_bom`: export_csv 첫 청크가 UTF-8 BOM(\xef\xbb\xbf)으로 시작하는지 검증한다 — 엑셀 한글 깨짐 방지.
- `test_read_api_surface`: dir(BusLogRepo)에 5개 read 메서드가 모두 존재하는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/db/test_repo_read.py -v
```

---

### W7 — api_clients/tago.py
**Owner:** unassigned **Depends:** — **산출물:** `bushexa/api_clients/tago.py`, `tests/api_clients/test_tago.py`

**지시사항 (명령형):**
1. `TagoClient(api_key, *, base_url=DEFAULT, timeout=10.0)`를 만들고 `fetch_bus_locations(route_id, page=1, rows=70)`, `fetch_route_stops(route_id)`를 구현한다.
2. 응답을 `TagoResponse(result_code, total_count, items: list[BusLocation])` dataclass로 변환한다 (USB prefix strip은 parser(W10) 위임 또는 client 내부).
3. `result_code != "00"`이면 `TagoError(result_code)`를 던진다.
4. 네트워크 호출은 `requests`로 하되, 테스트는 `responses` 라이브러리로 mock한다 (실제 호출 0건).
5. `tests/api_clients/test_tago.py`를 작성한다 (fixture: tago/*.json).

**Acceptance:**
- [ ] AC-1: `TagoClient('dummy').base_url`이 국토부 BusLcInfo 엔드포인트를 가리킨다 (검증: `uv run pytest tests/api_clients/test_tago.py::test_base_url`)
- [ ] AC-2: busloc_normal.json mock 응답에서 3개 BusLocation을 파싱한다 (검증: `uv run pytest tests/api_clients/test_tago.py::test_parse_normal`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_base_url`: TagoClient의 base_url이 `getRouteAcctoBusLcList`를 포함하는 국토부 엔드포인트인지 검증한다.
- `test_parse_normal`: responses로 busloc_normal.json을 반환하도록 mock한 뒤 fetch_bus_locations가 total_count=3과 BusLocation 3개를 돌려주는지 검증한다.
- `test_error_code_raises`: busloc_error_99.json(resultCode=99) mock에서 TagoError가 발생하는지 검증한다.
- `test_no_real_network`: 테스트 중 실제 requests.get이 호출되면 실패하도록 가드(responses 미등록 URL은 ConnectionError)되어 있는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/api_clients/test_tago.py -v
```

---

### W8 — api_clients/ulsan_bis.py
**Owner:** unassigned **Depends:** — **산출물:** `bushexa/api_clients/ulsan_bis.py`, `tests/api_clients/test_ulsan_bis.py`

**지시사항 (명령형):**
1. `UlsanBisClient(api_key)`를 만들고 `fetch_arrivals(stop_id)`, `fetch_timetable(route_no, day_of_week, page=1, rows=50)`를 구현한다.
2. XML 응답을 BeautifulSoup로 파싱해 dataclass(`Arrival`, `TimetableRow`)로 변환한다.
3. 네트워크 실패 시 빈 리스트 또는 명확한 예외로 처리하고, 테스트는 fixture XML을 mock한다.
4. `tests/api_clients/test_ulsan_bis.py`를 작성한다 (fixture: ulsan/*.xml).

**Acceptance:**
- [ ] AC-1: arrival_normal.xml mock에서 `<row>` 개수만큼 Arrival을 파싱한다 (검증: `uv run pytest tests/api_clients/test_ulsan_bis.py::test_parse_arrivals`)
- [ ] AC-2: arrival_no_bus.xml(빈 결과)에서 빈 리스트를 반환한다 (검증: `uv run pytest tests/api_clients/test_ulsan_bis.py::test_empty_arrivals`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_parse_arrivals`: arrival_normal.xml을 mock하여 fetch_arrivals가 각 `<row>`의 routeid/presentstopnm/vehicleno/arrivaltime을 담은 Arrival 목록을 반환하는지 검증한다.
- `test_empty_arrivals`: 버스 없음 XML에서 빈 리스트를 반환하고 예외가 없는지 검증한다.
- `test_parse_timetable_rows`: timetable XML에서 time("HHMM"→"HH:MM")과 direction(int)을 가진 TimetableRow 목록을 반환하는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/api_clients/test_ulsan_bis.py -v
```

---

### W9 — api_clients/holiday.py
**Owner:** unassigned **Depends:** — **산출물:** `bushexa/api_clients/holiday.py`, `tests/api_clients/test_holiday.py`

**지시사항 (명령형):**
1. `HolidayClient(api_key).fetch(year, month) -> list[date]`를 구현한다 (stateless, 캐시는 상위 service 책임).
2. XML 응답의 `<locdate>` 태그(YYYYMMDD)를 date로 변환한다.
3. 결과 없음 시 빈 리스트를 반환한다.
4. `tests/api_clients/test_holiday.py`를 작성한다 (fixture: holiday/2026.xml).

**Acceptance:**
- [ ] AC-1: 2026.xml mock에서 locdate 개수만큼 date를 반환한다 (검증: `uv run pytest tests/api_clients/test_holiday.py::test_parse_holidays`)
- [ ] AC-2: locdate가 없는 월 응답에서 빈 리스트를 반환하고 예외가 없다 (검증: `uv run pytest tests/api_clients/test_holiday.py::test_empty_month_returns_empty`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_parse_holidays`: holiday/2026.xml을 mock하여 fetch(2026,1)가 `<locdate>` 값들을 date 객체 목록으로 변환하는지 검증한다.
- `test_empty_month_returns_empty`: locdate가 없는 월 응답에서 빈 리스트를 반환하는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/api_clients/test_holiday.py -v
```

---

### W10 — crawler/parsers.py
**Owner:** unassigned **Depends:** W7, W8 **산출물:** `bushexa/crawler/parsers.py`, `tests/crawler/test_parser_bus_location.py`

**지시사항 (명령형):**
1. `parse_busloc(resp_json) -> list[BusLocation]`을 작성한다: USB prefix를 strip하고, `totalCount==0`은 빈 리스트, `==1`은 dict/list 양쪽 형태를 모두 list로 정규화한다 (F09 H6).
2. `parse_route`, `parse_busstop`을 함께 둔다 (W7/W8 응답용 순수 함수).
3. 필수 필드 누락 시 `ParseError`를 던진다.
4. `tests/crawler/test_parser_bus_location.py`를 작성한다 (fixture 5종 전부 사용).

**Acceptance:**
- [ ] AC-1: busloc_normal/empty/single_dict/single_list 4개 fixture를 모두 정상 파싱한다 (검증: `uv run pytest tests/crawler/test_parser_bus_location.py -k "normal or empty or single"`)
- [ ] AC-2: 모든 BusLocation.node_id에 USB prefix가 없다 (검증: `uv run pytest tests/crawler/test_parser_bus_location.py::test_strips_usb_prefix`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_parses_normal_response`: busloc_normal.json(3 items)을 parse_busloc에 주면 (node_id, node_name, vehicle_no) 3-튜플 3개를 반환하는지 검증한다.
- `test_handles_total_count_zero`: totalCount=0 응답에서 빈 리스트를 반환하는지 검증한다.
- `test_handles_single_dict_form`: totalCount=1이고 items.item이 단일 dict인 응답을 1개짜리 리스트로 정규화하는지 검증한다 — 국토부 API의 단건 응답 가변성(H6) 회귀.
- `test_handles_single_list_form`: totalCount=1이고 items.item이 list인 응답도 동일하게 1개 리스트로 처리하는지 검증한다.
- `test_strips_usb_prefix`: 모든 결과 node_id가 'USB'로 시작하지 않는지(접두사 제거) 검증한다.
- `test_missing_field_raises`: vehicleno 필드가 빠진 item에 대해 ParseError가 발생하는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/crawler/test_parser_bus_location.py -v
```

---

### W11 — db: BusArrivalRepo (ADR-010 백업본)
**Owner:** unassigned **Depends:** W4, W5 **산출물:** `bushexa/db/repo_arrival.py`, `tests/db/test_arrival_repo.py`

**지시사항 (명령형):**
1. `BusArrivalRepo(conn)`를 만들고 `upsert(stop_id, payload, fetched_at)`을 구현한다: `bus_arrival_cache`에 stop_id 기준 upsert(SQLite `INSERT ... ON CONFLICT(stop_id) DO UPDATE`, Postgres 동일 구문).
2. `get(stop_id) -> ArrivalSnapshot | None`과 `get_many(stop_ids) -> dict[str, ArrivalSnapshot]`을 구현한다 (payload 역직렬화 + fetched_at 포함).
3. `payload`는 JSON 문자열(도착 목록 직렬화)로 저장한다.
4. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: 같은 stop_id로 2회 upsert 시 행이 1개로 유지되고 최신 payload·fetched_at으로 갱신된다 (검증: `uv run pytest tests/db/test_arrival_repo.py::test_upsert_replaces`)
- [ ] AC-2: `get`이 payload를 역직렬화하고 fetched_at을 함께 반환한다 (검증: `uv run pytest tests/db/test_arrival_repo.py::test_get_roundtrip`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_upsert_replaces`: 한 정류장에 2번 upsert하면 INSERT가 아니라 갱신이 일어나 행이 1개로 유지되고 fetched_at이 최신값인지 검증한다 — 백업본은 스냅샷(이력 아님)임을 보증.
- `test_get_roundtrip`: 직렬화 저장한 도착 목록을 get으로 읽으면 동일 구조 + fetched_at이 복원되는지 검증한다.
- `test_get_many`: 여러 stop_id를 한 번에 조회해 stop_id→snapshot 매핑이 반환되는지 검증한다 — 화면이 백업본을 일괄 조회.

**검증 명령:**
```bash
uv run pytest tests/db/test_arrival_repo.py -v
```

---

### W12 — fileio 쓰기 choke-point (ADR-012)
**Owner:** unassigned **Depends:** — **산출물:** `bushexa/fileio.py`, `tests/unit/test_fileio.py`

**지시사항 (명령형):**
1. `atomic_write_bytes(path, data: bytes, *, logger=None)`, `atomic_write_text(path, text, *, encoding="utf-8", logger=None)`, `atomic_write_json(path, obj, *, logger=None)`를 작성한다. 셋 다 동일한 원자적·로깅 동작을 공유한다(내부 `_atomic_write` 1개로 통일).
2. 쓰기 **직전** `path.exists()`로 동사를 정한다(`created`/`modified`). 임시파일(`{path}.tmp.{pid}`) → write → `flush`+`os.fsync` → `os.replace`(원자적 rename). 부모 디렉터리 없으면 생성.
3. `logger`가 None이면 `logging.getLogger("bushexa.fileio")`를 쓴다. 성공 후 INFO 한 줄: `file {verb}: {abs_path} ({nbytes}B)`. **파일 내용은 절대 로그하지 않는다**(ADR-012 민감정보 보호).
4. `bushexa/` 내 다른 모든 모듈은 디스크 파일을 쓸 때 이 헬퍼만 사용한다(직접 `open(...,"w")` 금지).
5. `tests/unit/test_fileio.py`를 작성한다(tmp_path + 자체 로그 핸들러로 캡처 — PM-002 T-1: `bushexa.*`는 propagate=False이므로 caplog 금지, 핸들러 직접 부착).

**Acceptance:**
- [ ] AC-1: 존재하지 않던 경로에 `atomic_write_json` 시 INFO 로그에 `file created`가 1회 남고 파일 내용이 일치한다 (검증: `uv run pytest tests/unit/test_fileio.py::test_create_logs_created`)
- [ ] AC-2: 이미 있는 경로에 다시 쓰면 로그가 `file modified`이고 내용이 새 값으로 교체된다 (검증: `uv run pytest tests/unit/test_fileio.py::test_overwrite_logs_modified`)
- [ ] AC-3: `bushexa/` 전체에 fileio.py 외 직접 디스크 쓰기가 없다 (검증: EC-10 grep)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_create_logs_created`: tmp_path의 새 파일에 atomic_write_json을 호출하면 (a) 파일이 생성되고 json 역직렬화가 원본과 같고, (b) bushexa.fileio 로거에 'created' 동사 INFO가 정확히 1줄 남는지 검증한다 — 사용자 "생성" 기록 요구.
- `test_overwrite_logs_modified`: 같은 경로에 두 번째로 쓰면 동사가 'modified'로 바뀌고 파일 내용이 두 번째 값인지 검증한다 — "수정" 기록 요구 + 생성/수정 구분.
- `test_atomic_no_partial_on_failure`: 직렬화가 불가능한 객체(예: set)를 atomic_write_json에 주면 예외가 나고, 기존 파일이 있었다면 그 내용이 손상되지 않고 그대로 남는지(tmp만 버려짐) 검증한다 — 원자성 보증.
- `test_content_not_logged`: 로그 메시지에 파일 내용 문자열이 포함되지 않고 경로·바이트수만 남는지 검증한다 — 시크릿 유출 방지(ADR-012/ADR-009).

**검증 명령:**
```bash
uv run pytest tests/unit/test_fileio.py -v
```

## 6. 병렬화 그래프

```text
W1 ──┬──▶ W2
     └──▶ W3
W4 ──▶ W5 ──▶ W6a ──▶ W6b
W7 ──┬──▶ W10
W8 ──┘
W9 ── (독립)
```

병렬 가능 그룹:
- **Group A (동시 5개)**: W1, W4, W7, W8, W9
- **Group B**: W2(W1 후), W3(W1 후), W5(W4 후), W10(W7+W8 후)
- **Group C**: W6a(W5 후) → W6b(W6a 후)

## 7. 리스크 & 롤백

- R1: psycopg2-binary import 실패 환경 — deferred import + sqlite fallback (W4 step 3)
- R2: api 응답 fixture와 실제 응답 미세 차이 — 운영 표본 1회 추가 캡처해 보강
- R3: `parse_busloc` totalCount==1 list/dict 변동 — 양쪽 분기 명시 처리 + 테스트(W10)
- R4: `export_csv` CSV formula injection(셀 선두 `=`/`+`/`-`/`@`) 미처리 → **P5 보안 게이트(ADR-009)에서 이스케이프** 추가. 현재는 BOM+원값. (repo.py `export_csv` docstring에 NOTE 표기)

> **시그니처 실현 메모 (E-7 divergence, Designer 인지):** F04 §4.4의 `export_csv(self, **filters, max_rows=10000)`은 유효하지 않은 Python 문법이라 실제는 `export_csv(self, *, max_rows=10000, **filters)`로 구현. `query_paged`의 필터 인자는 모두 `= None` 기본(키워드 전용). 또한 `count`/`export_csv`의 `**filters`는 미지의 키(오타)를 조용히 '전체'로 집계하지 않도록 허용 키 검증(TypeError)을 추가했다. 모두 도메인 의미 불변, doc 문법오류·foot-gun 보정.

롤백: `bushexa/{data,db,api_clients,crawler/parsers.py,time_utils.py}`와 `tests/{unit,db,api_clients,crawler}` 제거. 기존 `src/`, `crawl/db.py` 무손상.

## 8. Auditor 감리 포인트 (설계 단계)

- [ ] DA-1: 11개 work item 모두 단일 책임
- [ ] DA-2: 사이클 없음 (W1→{W2,W3}, W4→W5→W6a→W6b, W7+W8→W10, W9 독립)
- [ ] DA-3: 모든 work item에 단일 산출물 + 테스트 경로
- [ ] DA-4: 모든 work item에 AC ≥2건 + 각 검증 명령
- [ ] DA-5: Group A 5개 동시 식별
- [ ] DA-6: EC-1~8 객관적 검증 명령 보유
- [ ] DA-7: L work item 없음 (W6 사전 분할 W6a/W6b)
- [ ] DA-8: 모든 테스트 work item에 test case 자연어 의도 기재 (P-11)
- [ ] DA-9: EC↔AC 매핑 표 존재, 누락 0건 (P-12)
