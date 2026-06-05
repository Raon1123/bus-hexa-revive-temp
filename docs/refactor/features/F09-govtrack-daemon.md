---
status: designed
designer: opus
auditor_status: pending
last_updated: 2026-06-01
feature_id: F09
---

# F09 — Govtrack 데몬 (버스 통과 로그 수집)

> 본 doc은 사용자가 보고한 **"버스가 지나간 기록이 제대로 안 남는다"** 결함을 1순위 대상으로 한 deep-dive 문서다.
> 가설별 진단 → 재설계 → pytest 회귀 보호 까지 한 문서에서 처리한다.

## 0. 한 줄 요약

- **As-is:** `python -m crawl.govtrack`이 20초 주기로 10개 노선의 국토부 버스위치 API를 폴링하여 `bus_timelog` 테이블에 통과 이벤트를 적재. 누락·중복·재시작 false-positive 등의 결함이 누적되어 신뢰할 수 없는 상태.
- **To-be:** `bushexa.crawler.govtrack`에 책임 분리된 (a) API client, (b) parser, (c) 상태머신 (벡터 시계 in-memory + 지속화), (d) repository writer로 재구성. 실패 격리, 재시작 안전성, KeyError 방어, pytest로 회귀 보호.

## 1. 사용자 시나리오

- **누가/의도:** 관리자(또는 자동 데몬). 운행 중인 버스의 정류장 통과 시각을 실시간으로 누적 기록하여 `running_table` (F05) 및 분석에 활용.
- **Happy path:**
  1. 데몬 시작 (`uv run bushexa crawl-loop` 또는 podman-compose 워커 서비스)
  2. ROUTEID에 정의된 10개 route_id 각각에 대해 국토부 BusLcInfoInqireService API 호출
  3. 응답에서 (nodeid, nodenm, vehicleno) 추출
  4. 차량별 이전 위치와 비교, 변경이 발생했고 신규 nodeid가 노선의 추적 stop 집합에 속하면 DB에 1행 INSERT 및 TSV append
  5. 20초 sleep 후 반복
  6. KST 01:00-05:00 구간은 600초 sleep (운행 없음 가정)
- **엣지 케이스:**
  - **E1**: API quota exhausted → resultCode != 00 → 전 사이클 skip (현재) → **데이터 영구 손실 가능**
  - **E2**: API 응답이 totalCount=0 → `parse_busloc`이 [] 반환 → 정상 skip
  - **E3**: API 응답에 신규 nodeid (STOP_IDS 미등록) → 현재 KeyError 발생 (DB insert 직전 `STOP_IDS[nodeid]` 조회). 전체 사이클 폭사 위험
  - **E4**: 데몬 재시작 직후 → `bus_timeline` 빈 dict로 시작 → 첫 poll에서 모든 차량이 "신규" 처리되어 현재 위치가 추적 stop이면 한꺼번에 INSERT → **시간상 부정확한 false-positive 폭주**
  - **E5**: 20초 사이에 차량이 정류장 A → B (둘 다 추적 대상) → C로 이동 → poll N에서 A, poll N+1에서 C → **B 누락**
  - **E6**: DB 연결 끊김 → `psycopg2.OperationalError` 비격리 전파 → while-True 루프 폭사 → 데몬 죽음
  - **E7**: 새벽 1-5시에 차량이 막차로 운행 중 → 600초 sleep → 막차 정보 누락
  - **E8**: 응답 totalCount=1일 때 `items.item`이 dict인지 list인지 일관되지 않음 (현재 코드는 dict 가정하여 list로 wrap)

## 2. 현재 구현 분석 (As-Is)

### 2.1 진입점 / 파일 / 라인 참조
- 데몬 엔트리: `crawl/govtrack.py:77-104` (`if __name__ == "__main__"`)
- 핵심 처리: `crawl/govtrack.py:13-66` (`busloc_status`)
- API 호출: `src/crawl.py:175-212` (`crawl_loc`)
- 파싱: `src/crawl.py:215-242` (`parse_busloc`)
- 저장소: `crawl/db.py:80-88` (`BUS_TIMELOG.insert_log`)
- 상수: `src/constants.py:13-34` (`ROUTEID`), `src/constants.py:75-134` (`STOP_IDS`)

### 2.2 사용된 Streamlit API 전수 목록

본 feature는 UI 미보유 (백그라운드 데몬, `python -m crawl.govtrack` 실행). 따라서 Streamlit API 사용 **해당 없음**.

| API | 위치 | 용도 |
|---|---|---|
| 해당 없음 | — | govtrack 데몬은 Streamlit 미사용. UI 매핑 비대상 |

### 2.3 데이터 흐름

```text
crawl_loc(route_id)
  → http://apis.data.go.kr/1613000/BusLcInfoInqireService/getRouteAcctoBusLcList
  → JSON (response.body.items.item[])
parse_busloc(json)
  → list[(nodeid_no_prefix, nodenm, vehicle_no)]
busloc_status(db, route_id, bus_timeline_for_route)
  → for each busloc:
      if vehicle 신규 → bus_timeline[veh] = ''
      if nodeid 변경 AND nodeid ∈ ROUTEID[route_id][3]:
          - TSV append (/app/logs/logs.tsv)
          - db.insert_log((timestamp, nodeid, route_id, vehicle_no))
      bus_timeline[veh] = nodeid
```

`bus_timeline`은 process-local in-memory dict, route_id별 sub-dict, vehicle_no → last nodeid.

### 2.4 의존 모듈 그래프

```text
crawl/govtrack.py
  ├── src.constants.ROUTEID
  ├── src.constants.STOP_IDS
  ├── src.crawl.crawl_loc           # requests + JSON
  ├── src.crawl.parse_busloc        # JSON 파싱, USB prefix strip
  ├── src.tools.get_now             # KST datetime
  └── crawl.db.BUS_TIMELOG          # psycopg2
```

### 2.5 관찰된 결함·악취 (가설별 분리)

> **★ 본 섹션이 본 doc의 가장 중요한 출력이다.**

#### H1 — 폴링 sampling rate 부족 (20초)
- 도시 일반 버스가 정류장에 머무는 시간 평균 5-10초.
- 20초 폴링은 정류장 통과 이벤트의 약 30-50% 누락 가능 (가속/정차 시간 가정).
- 증거: 시뮬레이션 필요 (pytest로 검증, 8.1 참조).
- **수정안 우선:** API 호출량 ↑ 부담은 있으나 5-10초 폴링 또는 차량별 next-stop 추정으로 보상.

#### H2 — In-memory state 휘발성 → 재시작 false-positive 폭주
- `bus_timeline = {}` (govtrack.py:78) → 데몬 재시작 시 모든 차량 신규로 인식
- 첫 poll에서 차량의 현재 위치가 추적 stop이면 **즉시 INSERT** → 통과시각이 아닌 "처음 본 시각" 기록 → 데이터 부정확
- **수정안:** 데몬 시작 시 DB에서 차량별 최근 nodeid 조회하여 hot-warm. 또는 별도 state 파일 (`data/govtrack_state.json`) 사용

#### H3 — `STOP_IDS[nodeid]` KeyError 가능성
- `govtrack.py:62`에서 `STOP_IDS[nodeid]` 직접 조회
- `ROUTEID[route_id][3]`에 신규 정류장 ID가 추가되었으나 `STOP_IDS`에 누락된 경우 KeyError → 함수 전체 중단
- 증거: `ROUTEID['194000107']` (1115 꽃바위방면) 의 `'999000209'`, `'195030615'`는 `STOP_IDS`에 존재. 다행히 현재는 안전. 그러나 향후 데이터 추가 시 위험.
- **수정안:** `STOP_IDS.get(nodeid, nodeid)` 또는 사전 검증 단계에서 누락 경고

#### H4 — 예외 격리 부재
- `busloc_status` 내 for-loop (54-66) 어떤 차량 처리에서 예외 발생 시 → 함수 전체 abort → 같은 사이클 내 후속 차량 손실
- `insert_query` 안의 `db.insert_log` 예외 시 → 함수 전체 abort
- `__main__`의 while True 루프 자체에 try/except 없음 → 한 예외로 데몬 죽음
- **수정안:** 차량별 try/except 격리, 데몬 루프에 catch-all + 로그 + sleep + 계속

#### H5 — DB commit 정책 비효율
- `BUS_TIMELOG.insert_log` 각 호출마다 commit (`db.py:87-88`)
- 10개 노선 × N 대 차량 = 사이클당 수십 commit. 정상에서는 부담 적지만, 연결 끊김 시 부분 commit으로 상태 모호
- **수정안:** 사이클 단위 batch commit (transaction). 또는 SQLite의 경우 더더욱 단위 트랜잭션 필요

#### H6 — `crawl_loc` 응답 검증 약함
- `parse_busloc`이 `totalCount == 1`일 때 `item`을 list로 wrap (line 229-230) 하지만 실제 API는 `totalCount==1`이어도 list로 반환할 수 있음 (수동 확인 필요, BR 응답 가변성)
- 동시에 API 키 만료/quota 초과 시 `resultCode != "00"`만 출력 후 None 반환. 데몬은 정상 정도로 처리하고 사이클 진행 → 침묵 실패
- **수정안:** resultCode 별 분기 처리, 일정 횟수 연속 실패 시 데몬 alert (log level ERROR + 외부 알림 hook)

#### H7 — 새벽 1-5시 절대 skip
- `govtrack.py:90-92`의 `if 1 ≤ hour < 5: sleep(600)` → 막차/첫차 시점 데이터 공백
- **수정안:** 운행 종료/시작 시각을 timetable 기준 동적 결정. 또는 sleep을 600→60으로 단축하여 위험 구간 좁히기.

#### H8 — `logging_file` 모듈 스코프 의존
- `govtrack.py:82`에서만 정의된 `logging_file`을 `busloc_status:63`에서 module-global로 참조
- `python -m crawl.govtrack` 외 import 경로로 호출 불가 (NameError)
- **수정안:** `logging_file`을 함수 인자 또는 설정값으로

#### H9 — `/app/logs/` 하드코딩
- 컨테이너 내부 경로 가정. 로컬 실행 시 fail
- **수정안:** `BUSHEXA_LOG_DIR` env var, 기본값 `./logs`

#### H10 — `BUS_TIMELOG.__del__`에서 cursor 닫기 순서
- `db.py:58-60`에서 `self.db.close(); self.curser.close()` — 연결 닫은 후 cursor 닫기 시도 → 예외 가능
- 또한 `__del__`은 GC 타이밍 의존 → 명시적 close 컨텍스트 매니저로 대체 권장

## 3. 외부 의존성

### 3.1 외부 API
- **국토부 TAGO 버스위치정보** (`api-manual/오픈API활용가이드_국토교통부(TAGO)_버스위치정보v1.0.docx` 참조)
- Endpoint: `http://apis.data.go.kr/1613000/BusLcInfoInqireService/getRouteAcctoBusLcList`
- 메서드: GET
- 파라미터: `serviceKey` (encoded), `pageNo=1`, `numOfRows=70`, `_type=json`, `cityCode=26` (울산), `routeId=USB{route_id}` (USB prefix 필수)
- 응답 형식: JSON, `response.body.items.item[]`
- 응답 필드: `nodeid` (USB prefix 포함), `nodenm`, `nodeord`, `routenm`, `routetp`, `vehicleno`
- 실패: `resultCode != "00"` 헤더, 또는 HTTP 비-200
- Rate limit: 공공데이터포털 보통 일 10000건 (운영 기준 1일 약 432,000 호출 = 10노선 × 4320 cycle × 1page → 키 분할 또는 시간 분산 필요할 수 있음. 검증 대상)

### 3.2 데이터베이스
- 테이블 `bus_timelog` (`crawl/db.py:41-50`)
- 컬럼: `idx` (timestamp str), `stop_id`, `route_id`, `route_nm` (현재 미사용), `vehicle_number`, `stop_name` (현재 미사용)
- 인덱스: 없음 (성능 문제 시 `(route_id, idx)`, `(stop_id, idx)`, `(vehicle_number, idx)` 추가 권장)
- 쓰기: govtrack daemon 단일 writer
- 읽기: F05 `running_table.py`, F04 admin 데이터 브라우저

### 3.3 정적 파일
- `secret/key.txt` — API 키
- `/app/logs/logs.tsv` — TSV append (디버그 용)
- `/app/logs/error_{route_id}_{timestamp}.json` — 파싱 실패 응답 덤프

## 4. 새 구현 매핑 (To-Be)

### 4.1 URL & HTTP 메서드

본 feature는 백그라운드 데몬으로 HTTP를 직접 노출하지 않는다. 노출은 **F04 관리자** (`GET /admin/govtrack/status`, `GET /admin/govtrack/status/stream`)에 위임한다.

#### CLI 서브커맨드 (본 feature의 진입점)
- `uv run bushexa crawl-loop [--poll SECONDS] [--night-sleep SECONDS]`
  - 무한 루프 데몬. 기본 poll=10, night-sleep=60.
  - 예시: `uv run bushexa crawl-loop --poll 10`
- `uv run bushexa crawl-once --route ROUTE_ID [--dry-run]`
  - 단일 노선 1회 폴링 (디버그/검증용).
  - 예시: `uv run bushexa crawl-once --route 195000177 --dry-run`
- `uv run bushexa init-db [--reset]`
  - 스키마 + 인덱스 생성. `--reset` 시 `bus_timelog` 비우기.

### 4.2 Flask 라우트 / 핸들러 시그니처

본 feature는 HTTP 라우트를 자체 정의하지 않는다. **해당 없음** — 데몬 상태 노출 라우트(`/admin/govtrack/status*`)는 F04에서 정의·구현한다.

### 4.3 템플릿 & 정적 자원

**해당 없음** — 데이터 표출 템플릿은 F04 (`bushexa/web/templates/admin/govtrack_status.html`)에서 정의한다.

### 4.4 도메인 서비스 호출

신규 모듈 구조:

```text
bushexa/crawler/
├── __init__.py
├── api_client.py    # TagoClient (BusLcInfo, BusRouteInfo)
├── parsers.py       # parse_busloc, parse_route, parse_busstop
├── state.py         # VehicleTimeline (load/save, mutate)
├── recorder.py      # 비즈니스 로직: busloc → repo insert decision
└── daemon.py        # CLI entry, scheduler, while-loop
```

핵심 시그니처:

```python
# bushexa/crawler/api_client.py
class TagoClient:
    def __init__(self, api_key: str, *, base_url: str = "...", timeout: float = 10.0): ...
    def fetch_bus_locations(self, route_id: str, *, page: int = 1, rows: int = 70) -> TagoResponse: ...

@dataclass(frozen=True)
class TagoResponse:
    result_code: str
    total_count: int
    items: list[BusLocation]

@dataclass(frozen=True)
class BusLocation:
    node_id: str       # USB prefix 제거됨
    node_name: str
    vehicle_no: str
    node_ord: int | None = None
```

```python
# bushexa/crawler/state.py
class VehicleTimeline:
    """차량별 최근 노드 추적. JSON 또는 DB 영속."""
    def __init__(self, store: TimelineStore): ...
    def last_node(self, route_id: str, vehicle_no: str) -> str | None: ...
    def record(self, route_id: str, vehicle_no: str, node_id: str, ts: datetime) -> bool:
        """True if changed (warrant a check), False if same."""
    def warm_from_repo(self, repo: BusLogRepo, since: datetime) -> int:
        """데몬 시작 시 최근 기록으로 워밍, 워밍된 차량 수 반환."""
    def persist(self) -> None: ...
```

```python
# bushexa/crawler/recorder.py
class GovtrackRecorder:
    def __init__(self, client: TagoClient, parser, state: VehicleTimeline,
                 repo: BusLogRepo, clock: Clock, *,
                 tracked_stops_by_route: dict[str, set[str]]): ...
    def run_cycle(self) -> CycleStats: ...
    def run_single_route(self, route_id: str) -> RouteStats: ...

@dataclass
class CycleStats:
    cycle_started_at: datetime
    route_results: dict[str, RouteStats]
    total_inserts: int
    total_errors: int

@dataclass
class RouteStats:
    route_id: str
    api_ok: bool
    api_error: str | None
    parsed_count: int
    inserts: int
    skipped_unchanged: int
    skipped_unknown_stop: int
```

```python
# bushexa/db/repo.py
class BusLogRepo:
    def __init__(self, conn): ...
    def insert_log(self, *, idx: str, stop_id: str, route_id: str, vehicle_no: str, stop_name: str | None = None) -> None: ...
    def insert_batch(self, rows: Iterable[LogRow]) -> int: ...
    def latest_node_per_vehicle(self, *, since: datetime) -> dict[tuple[str,str], str]:
        """반환 키: (route_id, vehicle_no), 값: 최근 nodeid. warm_from_repo가 사용."""
    def get_by_route(self, route_id: str, *, day: date | None = None) -> list[LogRow]: ...
```

```python
# bushexa/crawler/daemon.py
def run_daemon(config: AppConfig, *, poll_seconds: int = 10, night_sleep_seconds: int = 60,
               night_window: tuple[time, time] = (time(1,0), time(5,0))) -> None: ...
```

### 4.5 HTMX/SSE 동작
N/A (백그라운드). 단, 관리자 status SSE는 F04 참조.

## 5. 데이터 모델 변경

- 신규 INSERT 시 `stop_name`도 채움 (`STOP_IDS.get(nodeid)`, 미존재 시 NULL)
- 인덱스 추가:
  ```sql
  CREATE INDEX IF NOT EXISTS ix_bus_timelog_route_idx ON bus_timelog (route_id, idx);
  CREATE INDEX IF NOT EXISTS ix_bus_timelog_stop_idx ON bus_timelog (stop_id, idx);
  CREATE INDEX IF NOT EXISTS ix_bus_timelog_vehicle ON bus_timelog (vehicle_number, idx);
  ```
- 마이그레이션: 신규 컬럼 없음, 인덱스만 추가 → 무중단 적용 가능

## 6. 인터페이스 계약

(4.4 참조)

추가:

```python
@dataclass(frozen=True)
class LogRow:
    idx: str            # "%Y%m%d_%H:%M:%S"
    stop_id: str
    route_id: str
    vehicle_no: str
    stop_name: str | None
```

```python
class Clock(Protocol):
    def now(self) -> datetime: ...  # KST aware
```

```python
class TimelineStore(Protocol):
    def load(self) -> dict[tuple[str,str], str]: ...
    def save(self, snapshot: dict[tuple[str,str], str]) -> None: ...
```

## 7. Acceptance Checklist

### 결함 수정 (가설 → 회귀 보호)
- [ ] AC-H1: 폴링 간격 환경변수화 (`BUSHEXA_POLL_SECONDS`, default 10), 시뮬레이션 테스트로 누락률 측정 (검증: `uv run pytest tests/crawler/test_sampling_simulation.py`)
- [ ] AC-H2: 데몬 시작 시 `warm_from_repo`로 차량별 최근 위치 로드. 재시작 후 첫 사이클 INSERT 수가 워밍 적용 전 대비 ≥90% 감소 (검증: `uv run pytest tests/crawler/test_restart_no_falsepositive.py`)
- [ ] AC-H3: 신규/미등록 nodeid에 대해 KeyError 미발생, stop_name=None으로 기록 (검증: `uv run pytest tests/crawler/test_unknown_stop_safe.py`)
- [ ] AC-H4: 차량별 try/except 격리, 1개 차량 처리 실패가 다른 차량 처리에 영향 없음 (검증: `uv run pytest tests/crawler/test_recorder_isolation.py`)
- [ ] AC-H5: 사이클당 1 transaction batch commit. DB 연결 끊김 시 다음 사이클부터 자동 재연결 (검증: `uv run pytest tests/crawler/test_batch_commit_and_reconnect.py`)
- [ ] AC-H6: `result_code != "00"` 응답이 5사이클 연속이면 ERROR 로그 + alert hook 호출 (검증: `uv run pytest tests/crawler/test_api_failure_alerting.py`)
- [ ] AC-H7: night_window 진입 시 sleep을 600→60초로 단축 (설정 가능), 5시 정각에 첫 사이클 (검증: `uv run pytest tests/crawler/test_night_window.py`)
- [ ] AC-H8: `logging_file` (TSV) 경로가 함수 인자로 전달, 환경변수 `BUSHEXA_TSV_PATH`로 오버라이드 (검증: code review + `tests/crawler/test_tsv_path_config.py`)
- [ ] AC-H9: 컨테이너 외부 경로 하드코딩 0건 (검증: `! grep -rn '/app/logs' bushexa/`)
- [ ] AC-H10: BUS_TIMELOG 대체 신규 BusLogRepo는 context manager 사용, `__del__` 의존 없음 (검증: `grep -n '__del__' bushexa/db/repo.py`로 0건)

### 구조·재현성
- [ ] AC-S1: `bushexa/crawler/` 디렉토리 구조가 4.4와 일치 (5개 파일)
- [ ] AC-S2: 신규 코드에 `import streamlit` 0건 (검증: `! grep -rn 'import streamlit' bushexa/crawler/`)
- [ ] AC-S3: `uv run bushexa crawl-once --route 195000177 --dry-run` 동작 (API 키 없이 mock으로)
- [ ] AC-S4: SQLite 백엔드에서 정상 INSERT (검증: pytest in-memory sqlite)
- [ ] AC-S5: Postgres 백엔드에서 정상 INSERT (검증: pytest with testcontainers 또는 docker compose)

### 메트릭
- [ ] AC-M1: `CycleStats` 가 매 사이클마다 로그에 INFO 레벨로 한 줄 요약 (route별 inserts)
- [ ] AC-M2: 마지막 사이클 결과를 `/admin/govtrack/status`로 노출 (F04와 연계)

## 8. 테스트 계획

### 8.1 단위 테스트 (pytest)

`tests/crawler/`:

1. **`test_parser_bus_location.py`**
   - `test_parses_normal_response`: 표본 JSON (3 items) 정상 파싱
   - `test_handles_total_count_zero`: 빈 응답 → []
   - `test_handles_total_count_one_dict_form`: item이 dict일 때 list로 정상 wrap
   - `test_handles_total_count_one_list_form`: item이 list일 때도 정상 처리
   - `test_strips_usb_prefix`: nodeid의 `USB` 접두사 제거 확인
   - `test_missing_field_raises`: 필수 필드 누락시 ParseError

2. **`test_vehicle_timeline.py`**
   - `test_first_record_is_change`: 신규 차량 첫 record → True
   - `test_same_node_no_change`: 같은 node 재기록 → False
   - `test_different_node_change`: node 변경 → True
   - `test_warm_from_repo_suppresses_false_positive`: warm 후 첫 record가 같은 node면 False
   - `test_persist_and_restore_roundtrip`: save → load 라운드트립

3. **`test_recorder_isolation.py`** (AC-H4)
   - 두 차량 중 한 차량 처리에서 mock repo가 예외 던지도록 → 다른 차량 INSERT 정상

4. **`test_unknown_stop_safe.py`** (AC-H3)
   - tracked_stops에 있지만 STOP_IDS에 없는 nodeid → stop_name=None으로 INSERT 성공

5. **`test_recorder_unchanged_skipped.py`**
   - 같은 nodeid 연속 2사이클 → 두번째 사이클 INSERT 없음

6. **`test_recorder_untracked_stop_skipped.py`**
   - 차량이 tracked_stops 외 nodeid에 있을 때 INSERT 없음, state는 업데이트

7. **`test_api_failure_alerting.py`** (AC-H6)
   - mock client가 5사이클 연속 result_code="99" 반환 → alert_hook 호출 1회

8. **`test_batch_commit_and_reconnect.py`** (AC-H5)
   - 사이클 중간에 OperationalError → 다음 사이클 시작 시 재연결 성공
   - 한 사이클 내 N개 INSERT가 단일 transaction commit

9. **`test_restart_no_falsepositive.py`** (AC-H2)
   - 시나리오: 초기 상태 (DB에 차량 A가 stop X 기록) → 새 데몬 인스턴스 시작 → 첫 API 응답에 A가 X에 있음 → INSERT **0건** 확인

10. **`test_sampling_simulation.py`** (AC-H1)
    - 시뮬레이션: 차량이 정류장 A→B→C를 평균 8초씩 머무름.
    - 폴링 간격 5, 10, 20초 각각에서 누락률 측정.
    - 10초 폴링에서 누락률 < 25%, 5초에서 < 10% 검증.

### 8.2 통합 테스트

`tests/integration/`:

11. **`test_daemon_smoke.py`**
    - 가짜 TagoClient (고정 응답 2 사이클), in-memory SQLite, run_daemon을 별도 스레드에서 2.5초 실행 후 종료. DB에 예상 행 수 확인.

12. **`test_dual_backend_compat.py`**
    - 동일 시나리오를 SQLite 및 Postgres(testcontainers) 양쪽에서 실행 → 동일 결과 확인.

### 8.3 수동 검증 시나리오

1. `uv run bushexa crawl-once --route 195000177` 실행 → stdout에 RouteStats 1줄 요약 출력
2. `uv run bushexa crawl-loop --poll 10 &` 시작
3. 30초 후 SQLite 파일에 새 row가 있는지 `sqlite3 data/bushexa.db 'SELECT count(*) FROM bus_timelog;'`
4. 데몬 죽인 후 다시 시작 → 첫 사이클 INSERT 수가 평소 사이클 대비 비정상 폭증하지 않음 확인
5. API 키를 잘못된 값으로 바꾸고 5사이클 진행 → 로그에 ERROR alert 출력 + DB INSERT 0건

## 9. 변경 영향 범위

- 영향 받는 다른 feature doc: **F04** (관리자 데몬 status 표출), **F05** (running_table은 신규 stop_name 활용 가능)
- Breaking change: **Yes**
  - `crawl/govtrack.py`, `crawl/db.py` 제거 → `bushexa/crawler/`, `bushexa/db/repo.py`로 대체
  - 신규 인덱스 추가 (down-time 거의 없음)
  - 새 환경변수 도입 (`.env.example` 갱신)

## 10. 미해결 질문

- Q1: 국토부 API의 일일 호출 한도 정확값 확인 필요 (`api-manual/오픈API활용가이드_국토교통부(TAGO)_버스위치정보v1.0.docx`)
- Q2: night_window 동작 — vacation 모드 (대학 방학)에는 막차/첫차 시각이 다름. 별도 검토.
- Q3: `tracked_stops_by_route`를 동적으로 (DB·설정) 관리할지, `ROUTEID` 상수에 정적 유지할지. 본 doc은 정적 가정.
- Q4: H1 (폴링 간격) 시뮬레이션에서 사용할 정류장 머무름 시간 분포의 표본을 어디서 얻을지 — 현재 가짜 데이터로 회귀만 보호. 실측 보강은 후속 작업.
