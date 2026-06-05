---
status: implemented
phase_id: P2
designer: opus
auditor_status: execution-pass (2026-06-01, EC-1~8 green, 45 P2 tests + 전체 104 pass; PM-001 verified)
last_updated: 2026-06-01
depends_on: [P1]
---

> **구현 changelog (2026-06-01) — 동결 설계 대비 실현 메모 (E-13: AC 약화 아님, 책임 단일화):**
> - **W2a/W6 시그니처:** F09 §4.4의 `GovtrackRecorder(client, parser, state, ...)`에서 `parser`를
>   제거했다. P1에서 `TagoClient.fetch_bus_locations`가 이미 파싱된 `TagoResponse.items`를 반환하도록
>   감리·동결되어 파싱 책임이 client로 단일화됐다. 생성자는 `GovtrackRecorder(client, state, repo,
>   clock, *, tracked_stops_by_route, stop_names, route_ids, alert_hook, alert_threshold,
>   passage_sink, reconnect)`.
> - **W2a H4 결함 주입점 재조정:** INSERT는 사이클 말미 `insert_batch` 1회로 묶이므로(H5) 차량별
>   `repo.insert` 호출이 없다. 따라서 H4(격리) 결함은 **차량 처리 단계**(state.record 예외)로 주입하며,
>   per-vehicle try/except는 오염 행을 batch 밖으로 거르는 게이트다. 결함 주입이 비-tautology임을
>   except 타입 mutation으로 실증했다(제거 시 H4 테스트 실패).
> - **AC-S1 구조:** `bushexa/crawler/`는 4파일(state/recorder/daemon/parsers)+arrival_poller. API client는
>   P1에서 `bushexa/api_clients/{tago,ulsan_bis}`에 위치(F09 §4.4의 crawler/api_client.py 아님).
>   parsers.py는 단일 진실 소스(api_clients)를 재노출.
> - **W8 임계:** seed=42 측정값 poll 5/10/20 → 0.975/0.825/0.500이 EC-2(≥90/75/50%)를 충족. 파라미터
>   fitting 없이 측정이 결론을 끌었다(poll=20=0.500이 H1 "최대 50% 누락" 확정).

# P2 — Crawler 재구성 (F09 결함 회복 + F10 시간표 재크롤)

## 1. 목적

F09에서 도출한 H1~H10 결함을 모두 회복한 신규 `bushexa/crawler/` 데몬을 구축하고, F10 시간표 재크롤 백엔드를 분리·CLI화한다. 모든 결함이 자연어 의도가 명시된 회귀 테스트로 보호된다.

## 2. 시작 조건 (Entry Criteria)

- [ ] P1 Auditor PASS, 모든 P1 EC PASS
- [ ] `BusLogRepo`(P1/W6a,W6b), `TagoClient`/`UlsanBisClient`(P1/W7,W8), `parsers`(P1/W10), `time_utils`(P1/W2) 가용
- [ ] F09 / F10 / ADR-008 Auditor PASS

## 3. 종료 조건 (Exit Criteria)

- [ ] EC-1: F09 결함 H1~H10 회귀 테스트 모두 통과 (`uv run pytest tests/crawler/ -q` 0 fail). 통과 시 `postmortems/PM-001` status를 `verified`로 전환하고 재발 방지 체크박스를 모두 채운다 (00-workflow §8)
- [ ] EC-2: 폴링 시뮬레이션이 poll=5/10/20에서 각각 recall≥90/75/50% 충족 (`tests/simulation/test_polling_sampling.py`)
- [ ] EC-3: `uv run bushexa crawl-once --route 195000177 --dry-run`이 mock으로 정상 종료, 실제 INSERT 0건
- [ ] EC-4: `crawl-loop`가 SIGTERM에 진행 중 사이클 완료 후 graceful 종료 (`tests/crawler/test_daemon_smoke.py`)
- [ ] EC-5: `uv run bushexa crawl-timetable --vacation`이 streamlit 없이 완주, `data/timetable/*.json` 5개 갱신
- [ ] EC-6: `! grep -rn 'import streamlit\|/app/logs' bushexa/crawler/`
- [ ] EC-7: 마지막 사이클 결과가 status 저장소에 기록되어 `GovtrackStatusReader.latest()`로 읽힘
- [ ] EC-8: 동시 2개 재크롤 job 요청 시 두 번째가 ConflictError (`tests/services/test_timetable_crawl_job.py`)

### 3.1 EC ↔ Work Item AC 매핑 (P-8 / P-12)

| EC | 검증 대상 | 충족하는 Work Item AC |
|---|---|---|
| EC-1 | H1~H10 회귀 | W1: AC-1,2; W2a: AC-1,2; W2b: AC-1,2; W2c: AC-1; W3: AC-1,2,3; W7a/b/c: 각 AC |
| EC-2 | 시뮬레이션 recall | W8: AC-1, AC-2 |
| EC-3 | crawl-once dry-run | W3: AC-1 |
| EC-4 | graceful 종료 | W3: AC-3 |
| EC-5 | timetable 재크롤 | W4: AC-1, AC-2 |
| EC-6 | streamlit/경로 0건 | W3: AC-2; W4: AC-3 (공통 제약) |
| EC-7 | status 기록 | W6: AC-1, AC-2 |
| EC-8 | job 동시성 | W5: AC-2 |

> 모든 work item AC가 ≥1개 EC에 매핑됨. 누락 0건.

## 4. Work Item 분해

| ID | 작업 제목 | 소요 | 의존 | 산출물 |
|---|---|---|---|---|
| W1 | crawler/state.py (VehicleTimeline) | M | — | state.py + tests/crawler/test_vehicle_timeline.py |
| W2a | recorder: run_single_route (격리·KeyError safe) | M | W1 | recorder.py(부분) + tests/crawler/test_recorder_isolation.py, test_unknown_stop_safe.py |
| W2b | recorder: run_cycle (batch transaction) | M | W2a | recorder.py(부분) + tests/crawler/test_batch_commit_and_reconnect.py |
| W2c | recorder: alert hook (연속 실패) | S | W2b | recorder.py(부분) + tests/crawler/test_api_failure_alerting.py |
| W3 | daemon.py + CLI (crawl-loop/once/init-db) | M | W2c | daemon.py + tests/crawler/test_daemon_smoke.py, test_night_window.py, test_tsv_path_config.py |
| W4 | crawler/timetable_crawl.py (F10) | M | — | timetable_crawl.py + tests/crawler/test_timetable_crawl.py |
| W5 | services/timetable_crawl.py (Job 어댑터) | M | W4 | services/timetable_crawl.py + tests/services/test_timetable_crawl_job.py |
| W6 | services/govtrack_status.py (writer+reader) | M | W2b | govtrack_status.py + tests/services/test_govtrack_status.py |
| W7a | 회귀 풀세트 H1~H4 | M | W1,W2a | tests/crawler/test_* (parser/state/isolation/unknown) |
| W7b | 회귀 풀세트 H5~H7 | M | W2b,W3 | tests/crawler/test_* (batch/alert/night) |
| W7c | 회귀 풀세트 H8~H10 | S | W3 | tests/crawler/test_* (path/grep/cursor) |
| W8 | 폴링 시뮬레이션 (H1) | M | W1,W2a | tests/simulation/test_polling_sampling.py |
| W9 | arrival_poller (ADR-010 울산 도착 5~10초 크롤→DB 백업) | M | P1/W11 | bushexa/crawler/arrival_poller.py + tests/crawler/test_arrival_poller.py |

## 5. Work Item 상세

### W1 — crawler/state.py (VehicleTimeline)
**Depends:** — **산출물:** `bushexa/crawler/state.py`, `tests/crawler/test_vehicle_timeline.py`

**지시사항 (명령형):**
1. `VehicleTimeline(store: TimelineStore)`를 만들고 `last_node`, `record(route_id, vehicle_no, node_id, ts) -> bool`, `warm_from_repo(repo, since)`, `persist()`를 구현한다.
2. `record`는 직전 node와 다를 때만 True를 반환한다 (변경 감지).
3. `JSONFileStore(path)`를 기본 store로 구현하고, in-memory store 옵션을 둔다.
4. `tests/crawler/test_vehicle_timeline.py`를 작성한다.

**Acceptance:**
- [ ] AC-1: 신규 차량 첫 record는 True, 같은 node 재record는 False (검증: `uv run pytest tests/crawler/test_vehicle_timeline.py -k change`)
- [ ] AC-2: `warm_from_repo` 후 직전과 같은 node를 record하면 False (검증: `uv run pytest tests/crawler/test_vehicle_timeline.py::test_warm_suppresses`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_first_record_is_change`: 비어 있는 timeline에 차량 A의 첫 위치를 record하면 "변경됨"(True)으로 처리되는지 검증한다.
- `test_same_node_no_change`: 차량 A가 같은 node에 머물러 연속 record되면 두 번째는 False가 되어 중복 INSERT를 막는지 검증한다.
- `test_warm_suppresses`: warm_from_repo로 DB의 직전 위치를 적재한 직후, 차량이 그 위치 그대로일 때 record가 False를 반환해 재시작 false-positive(H2)를 억제하는지 검증한다.
- `test_persist_roundtrip`: persist 후 새 인스턴스가 같은 store에서 load했을 때 직전 상태가 복원되는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/crawler/test_vehicle_timeline.py -v
```

---

### W2a — recorder: run_single_route
**Depends:** W1 **산출물:** `bushexa/crawler/recorder.py`(부분), `tests/crawler/test_recorder_isolation.py`, `tests/crawler/test_unknown_stop_safe.py`

**지시사항 (명령형):**
1. `GovtrackRecorder(client, parser, state, repo, clock, *, tracked_stops_by_route)`를 만들고 `run_single_route(route_id) -> RouteStats`를 구현한다.
2. 차량별 처리를 try/except로 격리한다 — 한 차량 예외가 다른 차량 처리를 막지 않게 한다 (H4).
3. `stop_name`은 `STOP_IDS.get(nodeid)`로 조회하여 미등록 ID도 None으로 안전 처리한다 (H3).
4. 추적 대상(tracked_stops)인 nodeid 변경 시에만 INSERT 후보로 기록한다.
5. 두 테스트 파일을 작성한다.

**Acceptance:**
- [ ] AC-1: 한 차량 처리에서 repo가 예외를 던져도 나머지 차량은 정상 INSERT된다 (검증: `uv run pytest tests/crawler/test_recorder_isolation.py`)
- [ ] AC-2: tracked이지만 STOP_IDS 미등록 nodeid도 KeyError 없이 stop_name=None으로 처리된다 (검증: `uv run pytest tests/crawler/test_unknown_stop_safe.py`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_one_vehicle_failure_no_cascade`: 두 차량 중 첫 차량 **처리 단계(state.record)** 에서 예외가 나도 두 번째 차량은 여전히 INSERT 후보가 되는지 검증한다 — H4(예외 격리) 회귀. (INSERT는 H5로 사이클 말미 batch이므로 결함은 처리 단계에 주입; changelog 참조.)
- `test_unknown_stop_inserts_null_name`: tracked_stops에는 있으나 STOP_IDS에 없는 nodeid를 차량이 통과할 때 KeyError 없이 stop_name=None으로 INSERT되는지 검증한다 — H3 회귀.
- `test_untracked_stop_skipped`: 차량이 추적 대상이 아닌 nodeid에 있으면 INSERT가 발생하지 않고 timeline만 갱신되는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/crawler/test_recorder_isolation.py tests/crawler/test_unknown_stop_safe.py -v
```

---

### W2b — recorder: run_cycle (batch transaction)
**Depends:** W2a **산출물:** `bushexa/crawler/recorder.py`(부분), `tests/crawler/test_batch_commit_and_reconnect.py`

**지시사항 (명령형):**
1. `run_cycle() -> CycleStats`를 구현한다: ROUTEID 전 노선을 순회하며 INSERT 후보를 모아 한 사이클당 1 트랜잭션으로 commit한다 (H5).
2. DB 연결 끊김(OperationalError)을 감지하면 다음 사이클 시작 시 재연결한다.
3. `CycleStats`/`RouteStats` dataclass에 route별 inserts/skipped/errors를 집계한다.
4. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: 한 사이클의 다수 INSERT가 단일 트랜잭션으로 commit된다 (검증: `uv run pytest tests/crawler/test_batch_commit_and_reconnect.py::test_cycle_single_transaction`)
- [ ] AC-2: 사이클 중 연결 끊김 후 다음 사이클에서 자동 재연결되어 INSERT가 재개된다 (검증: `uv run pytest tests/crawler/test_batch_commit_and_reconnect.py::test_reconnect_after_drop`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_cycle_single_transaction`: run_cycle이 N개 INSERT를 commit 1회로 묶는지(commit 호출 횟수 == 1) 검증한다 — H5 회귀.
- `test_reconnect_after_drop`: 첫 사이클에서 OperationalError를 주입해 연결이 끊긴 뒤, 두 번째 사이클에서 재연결되어 정상 INSERT되는지 검증한다.
- `test_cycle_stats_aggregation`: run_cycle이 반환하는 CycleStats의 total_inserts가 route별 inserts 합과 일치하는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/crawler/test_batch_commit_and_reconnect.py -v
```

---

### W2c — recorder: alert hook
**Depends:** W2b **산출물:** `bushexa/crawler/recorder.py`(부분), `tests/crawler/test_api_failure_alerting.py`

**지시사항 (명령형):**
1. result_code가 "00"이 아닌 응답이 노선별 5사이클 연속이면 `alert_hook(route_id, count)` callable을 1회 호출한다 (H6).
2. 성공 사이클이 끼면 연속 카운터를 리셋한다.
3. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: 5사이클 연속 실패 시 alert_hook이 정확히 1회 호출되고, 중간 성공 시 카운터가 리셋된다 (검증: `uv run pytest tests/crawler/test_api_failure_alerting.py`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_five_consecutive_failures_trigger_alert`: mock client가 5사이클 연속 result_code="99"를 반환할 때 alert_hook이 1회만 호출되는지 검증한다 — H6(침묵 실패 방지) 회귀.
- `test_success_resets_counter`: 4회 실패 후 1회 성공하면 연속 카운터가 0으로 리셋되어 alert가 호출되지 않는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/crawler/test_api_failure_alerting.py -v
```

---

### W3 — daemon.py + CLI
**Depends:** W2c **산출물:** `bushexa/crawler/daemon.py`, `tests/crawler/test_daemon_smoke.py`, `test_night_window.py`, `test_tsv_path_config.py`

**지시사항 (명령형):**
1. `run_daemon(config, *, poll_seconds=10, night_sleep_seconds=60, night_window=(time(1,0),time(5,0)))`를 구현한다.
2. CLI 서브커맨드 `crawl-loop`, `crawl-once`(--route, --dry-run), `init-db`(--reset) 본체를 구현한다.
3. SIGTERM/SIGINT 핸들러: 진행 중 사이클을 끝낸 뒤 종료한다 (H 데이터 손실 방지).
4. TSV 로그 경로를 인자/`BUSHEXA_TSV_PATH`로 받고 `/app/logs` 하드코딩을 제거한다 (H8, H9).
5. night_window 진입 시 sleep을 night_sleep_seconds(기본 60)로 단축한다 (H7).
6. 세 테스트 파일을 작성한다.

**Acceptance:**
- [ ] AC-1: `crawl-once --route 195000177 --dry-run`이 mock client로 RouteStats를 출력하고 실제 INSERT가 0건이다 (검증: `uv run pytest tests/crawler/test_daemon_smoke.py::test_crawl_once_dry_run`)
- [ ] AC-2: `bushexa/crawler/`에 `/app/logs`·`import streamlit` 문자열이 0건이다 (검증: `! grep -rn '/app/logs\|import streamlit' bushexa/crawler/`)
- [ ] AC-3: SIGTERM 수신 시 진행 사이클 완료 후 종료한다 (검증: `uv run pytest tests/crawler/test_daemon_smoke.py::test_sigterm_graceful`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_crawl_once_dry_run`: --dry-run에서 mock client 응답을 처리하되 repo.insert가 호출되지 않는지(0건) 검증한다.
- `test_sigterm_graceful`: 데몬을 스레드로 띄우고 SIGTERM을 보내면 현재 사이클을 끝낸 뒤 종료하는지(중단 플래그 후 1사이클 내 종료) 검증한다.
- `test_short_sleep_in_night_window`: clock을 새벽 2시로 고정하면 sleep 인자가 night_sleep_seconds(60)로 호출되는지 검증한다 — H7 회귀.
- `test_tsv_path_from_env`: BUSHEXA_TSV_PATH를 tmp_path로 설정하면 TSV가 그 경로에 쓰이는지 검증한다 — H8 회귀.

**검증 명령:**
```bash
uv run pytest tests/crawler/test_daemon_smoke.py tests/crawler/test_night_window.py tests/crawler/test_tsv_path_config.py -v
! grep -rn '/app/logs\|import streamlit' bushexa/crawler/
```

---

### W4 — crawler/timetable_crawl.py (F10)
**Depends:** — **산출물:** `bushexa/crawler/timetable_crawl.py`, `tests/crawler/test_timetable_crawl.py`

**지시사항 (명령형):**
1. `src/crawl.py`의 `crawl_target_timetable`, `crawl_timetable`, `request_timetable`을 이전하고 `import streamlit`과 `st.*` 호출을 모두 제거한다 (F10 결함).
2. 진행 보고를 `on_progress: Callable[[ProgressEvent], None] | None` 콜백으로 추상화한다 (UI는 SSE, CLI는 stdout).
3. 결과 JSON을 임시파일 작성 후 rename(atomic)으로 `data/timetable/{busno}.json`에 저장한다.
4. `crawl_timetable`의 중복 status_code 분기를 1개로 정리하고 페이지네이션 종료 조건의 off-by-one을 수정한다 (F10 결함 4,5).
5. 테스트를 작성한다 (mock UlsanBisClient로 4페이지 시뮬레이션).

**Acceptance:**
- [ ] AC-1: mock으로 5개 노선 재크롤 시 `data/timetable/*.json` 5개가 생성/갱신된다 (검증: `uv run pytest tests/crawler/test_timetable_crawl.py::test_writes_five_routes`)
- [ ] AC-2: on_progress 콜백이 페이지 단위로 ProgressEvent를 받는다 (검증: `uv run pytest tests/crawler/test_timetable_crawl.py::test_progress_callback`)
- [ ] AC-3: 모듈에 `import streamlit`이 0건이다 (검증: `! grep -n 'import streamlit' bushexa/crawler/timetable_crawl.py`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_writes_five_routes`: mock 시간표 응답으로 재크롤을 돌리면 5개 노선 JSON이 atomic하게 기록되고 각 파일이 valid JSON인지 검증한다.
- `test_progress_callback`: on_progress에 수집 리스트를 주면 페이지마다 ProgressEvent(route, day, page)가 순서대로 전달되는지 검증한다.
- `test_atomic_write_on_failure`: 쓰기 도중 예외를 주입하면 기존 JSON이 손상되지 않고 보존되는지(임시파일만 남거나 정리) 검증한다.
- `test_pagination_no_off_by_one`: totalCount가 페이지 크기의 정확한 배수일 때 마지막 빈 페이지를 추가 요청하지 않는지 검증한다 — F10 결함5 회귀.

**검증 명령:**
```bash
uv run pytest tests/crawler/test_timetable_crawl.py -v
```

---

### W5 — services/timetable_crawl.py (Job 어댑터)
**Depends:** W4 **산출물:** `bushexa/services/timetable_crawl.py`, `tests/services/test_timetable_crawl_job.py`

**지시사항 (명령형):**
1. `TimetableCrawlJob.start(*, vacation) -> str`을 구현한다: `threading.Thread`로 W4 함수를 비동기 실행하고 job_id를 발급한다.
2. `progress(job_id) -> Iterator[ProgressEvent]`를 `queue.Queue` 기반으로 구현한다.
3. 이미 실행 중인 job이 있으면 두 번째 start는 `ConflictError`를 던진다.
4. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: start가 job_id를 반환하고 progress가 done 이벤트로 종결된다 (검증: `uv run pytest tests/services/test_timetable_crawl_job.py::test_start_and_progress`)
- [ ] AC-2: 동시 두 번째 start는 ConflictError를 던진다 (검증: `uv run pytest tests/services/test_timetable_crawl_job.py::test_conflict`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_start_and_progress`: mock 크롤 함수로 start 후 progress를 소비하면 progress 이벤트들 뒤에 done 이벤트가 와서 스트림이 종료되는지 검증한다 — F04 AC-R3.
- `test_conflict`: 한 job이 실행 중일 때 두 번째 start 호출이 ConflictError를 던지는지 검증한다 — F04 AC-R5.
- `test_error_event_on_failure`: 크롤 함수가 예외를 던지면 progress가 error 이벤트로 종결되는지 검증한다 — F04 AC-R4.

**검증 명령:**
```bash
uv run pytest tests/services/test_timetable_crawl_job.py -v
```

---

### W6 — services/govtrack_status.py
**Depends:** W2b **산출물:** `bushexa/services/govtrack_status.py`, `tests/services/test_govtrack_status.py`

**지시사항 (명령형):**
1. `GovtrackStatusWriter.write(cycle_stats)`를 구현한다: 마지막 사이클 결과를 status.json(또는 DB table)에 upsert한다.
2. `GovtrackStatusReader.latest() -> GovtrackStatus | None`, `history(limit) -> list[GovtrackStatus]`를 구현한다.
3. `consecutive_failures`, `last_success_at`, `route_breakdown`을 포함한다.
4. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: write 후 latest()가 방금 쓴 last_success_at/inserts를 반환한다 (검증: `uv run pytest tests/services/test_govtrack_status.py::test_write_then_latest`)
- [ ] AC-2: 데몬 미동작(연속 실패) 상태가 consecutive_failures>0로 노출된다 (검증: `uv run pytest tests/services/test_govtrack_status.py::test_failure_count`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_write_then_latest`: CycleStats를 write한 뒤 reader.latest()가 동일한 last_success_at, total_inserts, route_breakdown을 반환하는지 검증한다 — F04 AC-G1, F09 AC-M2.
- `test_failure_count`: 실패 사이클을 연속 write하면 latest().consecutive_failures가 증가하는지 검증한다 — F04 AC-G2.
- `test_history_limit`: 60개 사이클 write 후 history(50)가 최근 50개를 역순으로 반환하는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/services/test_govtrack_status.py -v
```

---

### W7a — 회귀 풀세트 H1~H4
**Depends:** W1, W2a **산출물:** `tests/crawler/test_*` (W1/W2a 테스트의 매트릭스 정합성 점검 + 누락 보강)

**지시사항 (명령형):**
1. ADR-008 회귀 매트릭스의 H1~H4 행이 실제 테스트와 1:1 대응하는지 확인하고, 누락 케이스를 보강한다.
2. 각 테스트 docstring에 "어느 H 결함을 막는지"를 명시한다.
3. `uv run pytest tests/crawler/ -k "timeline or isolation or unknown or parser"`로 묶음 실행이 통과하는지 확인한다.

**Acceptance:**
- [ ] AC-1: H1(시뮬레이션은 W8), H2/H3/H4 각 결함에 대응하는 테스트가 존재하고 docstring에 H번호가 있다 (검증: `uv run pytest tests/crawler/ -k "warm or unknown or isolation" -v`)
- [ ] AC-2: 매트릭스 H2~H4 행의 테스트 함수명이 ADR-008 표와 일치한다 (검증: 문서 대조 + `grep -rn 'H2\|H3\|H4' tests/crawler/`)

**테스트 케이스 (자연어 의도 — P-11):**
- (W1/W2a에서 정의된 케이스를 재사용) 본 work item은 신규 케이스보다 **매트릭스 정합성**을 보증한다: 각 H 결함이 정확히 하나 이상의 테스트로 커버되고 그 의도가 docstring에 자연어로 적혀 있는지 점검한다.

**검증 명령:**
```bash
uv run pytest tests/crawler/ -k "warm or unknown or isolation or parser" -v
```

---

### W7b — 회귀 풀세트 H5~H7
**Depends:** W2b, W3 **산출물:** `tests/crawler/test_*` (batch/alert/night 정합성)

**지시사항 (명령형):**
1. H5(batch commit/reconnect), H6(alert), H7(night window) 테스트가 매트릭스와 1:1인지 확인하고 보강한다.
2. 각 docstring에 H번호를 명시한다.
3. 묶음 실행을 확인한다.

**Acceptance:**
- [ ] AC-1: H5/H6/H7 대응 테스트가 존재하고 통과한다 (검증: `uv run pytest tests/crawler/ -k "batch or alert or night" -v`)
- [ ] AC-2: 각 테스트 docstring에 해당 H번호 문자열이 있다 (검증: `grep -rn 'H5\|H6\|H7' tests/crawler/`)

**테스트 케이스 (자연어 의도 — P-11):**
- 본 work item은 H5~H7 결함의 회귀 커버리지 정합성을 보증한다 — 각 결함이 자연어 의도가 적힌 테스트로 보호되는지 점검한다 (케이스 본체는 W2b/W2c/W3에서 정의).

**검증 명령:**
```bash
uv run pytest tests/crawler/ -k "batch or alert or night" -v
```

---

### W7c — 회귀 풀세트 H8~H10
**Depends:** W3 **산출물:** `tests/crawler/test_tsv_path_config.py`(보강), `tests/db/test_repo_context_manager.py`, lint 테스트

**지시사항 (명령형):**
1. H8(TSV 경로 설정), H9(하드코딩 경로 0건 lint), H10(cursor close 순서) 테스트를 확인/작성한다.
2. H9는 `grep` 기반 lint 테스트로 `bushexa/`에 `/app/logs`가 없음을 단언한다.
3. H10은 repo를 context manager로 열고 닫는 순서가 안전함을 검증한다.

**Acceptance:**
- [ ] AC-1: H9 lint 테스트가 `/app/logs` 하드코딩 0건을 단언한다 (검증: `uv run pytest tests/crawler/test_no_hardcoded_paths.py`)
- [ ] AC-2: repo context manager가 정상 종료/예외 양쪽에서 안전하게 닫힌다 (검증: `uv run pytest tests/db/test_repo_context_manager.py`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_no_hardcoded_app_logs`: `bushexa/` 전체를 grep해 `/app/logs` 문자열이 0건인지 단언한다 — H9 회귀(컨테이너 경로 하드코딩 방지).
- `test_close_order_safe`: BusLogRepo를 `with`로 열고 블록 종료 시 connection/cursor가 올바른 순서로 닫혀 예외가 없는지 검증한다 — H10 회귀.

**검증 명령:**
```bash
uv run pytest tests/crawler/test_no_hardcoded_paths.py tests/db/test_repo_context_manager.py -v
```

---

### W8 — 폴링 시뮬레이션 (H1)
**Depends:** W1, W2a **산출물:** `tests/simulation/test_polling_sampling.py`

**지시사항 (명령형):**
1. 차량 운행 모델을 작성한다: 정류장 N개, 각 정류장 머무름 `Normal(8s,3s)`, 주행 `Normal(60s,15s)`, seed=42로 결정론 고정.
2. sampler가 5/10/20초 간격으로 위치를 조회하고 recorder가 통과를 기록하게 한다.
3. 실제 통과 횟수 대비 기록 횟수로 recall을 계산한다.
4. 임계(poll 5→90%, 10→75%, 20→50%)를 단언한다.

**Acceptance:**
- [ ] AC-1: poll=10에서 recall≥75%, poll=5에서 recall≥90% (검증: `uv run pytest tests/simulation/test_polling_sampling.py -k recall`)
- [ ] AC-2: 동일 seed로 2회 실행 시 결과가 동일하다 (결정론) (검증: `uv run pytest tests/simulation/test_polling_sampling.py::test_deterministic`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_recall_at_poll_10`: 8초 머무름 모델에서 10초 폴링의 정류장 통과 recall이 75% 이상인지 검증한다 — H1(sampling rate) 정량 회귀.
- `test_recall_at_poll_5`: 5초 폴링의 recall이 90% 이상인지 검증한다 (권장 간격 근거).
- `test_recall_at_poll_20`: 현 운영 20초 폴링이 50% 이상(현 수준 baseline)인지 검증해 개선 효과의 기준선을 고정한다.
- `test_deterministic`: seed=42 고정 시 두 번 실행한 recall 수치가 정확히 같은지 검증해 CI flakiness를 방지한다.

**검증 명령:**
```bash
uv run pytest tests/simulation/test_polling_sampling.py -v
```

---

### W9 — arrival_poller (ADR-010)
**Depends:** P1/W11 **산출물:** `bushexa/crawler/arrival_poller.py`, `tests/crawler/test_arrival_poller.py`

**지시사항 (명령형):**
1. `run_arrival_poller(config, repo, client, clock, *, poll_seconds=7, stops=SERACH_STOPS)`를 구현한다: `SERACH_STOPS`를 `BUSHEXA_ARRIVAL_POLL_SECONDS`(기본 7, 5~10 권장) 간격으로 순회하며 울산 BIS `fetch_arrivals`를 호출한다.
2. 각 정류장 결과를 `BusArrivalRepo.upsert(stop_id, payload, fetched_at)`로 백업한다.
3. 호출 빈도가 **사용자 트래픽과 무관하게 고정**되도록, 화면 코드와 독립된 데몬 루프로 둔다 (ADR-010).
4. CLI 서브커맨드 `arrival-loop`을 추가한다. SIGTERM graceful 종료.
5. 테스트를 작성한다 (mock client, FakeClock).

**Acceptance:**
- [ ] AC-1: 한 사이클이 모든 `SERACH_STOPS`(17개)에 대해 upsert를 1회씩 수행한다 (검증: `uv run pytest tests/crawler/test_arrival_poller.py::test_one_cycle_upserts_all`)
- [ ] AC-2: poll 간격이 환경변수로 설정되고, sleep 호출이 그 값으로 일어난다 (검증: `uv run pytest tests/crawler/test_arrival_poller.py::test_poll_interval_from_env`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_one_cycle_upserts_all`: 한 폴 사이클에서 17개 정류장 각각에 대해 fetch→upsert가 정확히 1회씩 일어나는지 검증한다 — 백업본 갱신 완전성.
- `test_poll_interval_from_env`: BUSHEXA_ARRIVAL_POLL_SECONDS=5를 설정하면 사이클 간 sleep이 5초로 호출되는지 검증한다 — 과호출 방지(ADR-010 시간오차 회피)를 정량 보증.
- `test_no_overcall_under_load`: 화면 요청을 시뮬레이션해도 poller의 외부 호출 횟수가 사이클 수에만 비례하고 요청 수와 무관한지 검증한다 — 트래픽 분리.

**검증 명령:**
```bash
uv run pytest tests/crawler/test_arrival_poller.py -v
```

## 6. 병렬화 그래프

```text
W1 ──┬──▶ W2a ──▶ W2b ──▶ W2c ──▶ W3
     │      │        │
     │      │        └──▶ W6
     │      └──▶ W8
     └────────────────────────────▶ (W7a uses W1,W2a)
W4 ──▶ W5
W7a (W1,W2a 후) / W7b (W2b,W3 후) / W7c (W3 후)
```

병렬 가능 그룹:
- **Group A (동시)**: W1, W4
- **Group B**: W2a(W1 후), W8(W1+W2a 후), W5(W4 후)
- **Group C**: W2b(W2a 후), 그 후 W2c → W3, W6(W2b 후)
- **Group D (병렬)**: W7a, W7b, W7c (각 의존 충족 후 동시)

## 7. 리스크 & 롤백

- R1: 시뮬레이션 임계 false alarm — seed 고정 + 임계 적용 전 5회 실행해 분산 확인 후 보정
- R2: F04와 인터페이스 미스매치 — F04(P4)에서 통합 검증, 본 단계는 시그니처 합의
- R3: SIGTERM 처리 미흡 시 데이터 손실 — 사이클 단위 트랜잭션이라 부분 commit 위험 낮음

롤백: `bushexa/crawler/`, `bushexa/services/{timetable_crawl,govtrack_status}.py`, 관련 tests 제거. 기존 `crawl/govtrack.py` fallback.

## 8. Auditor 감리 포인트 (설계 단계)

- [ ] DA-1: 12개 work item 단일 책임
- [ ] DA-2: 사이클 없음
- [ ] DA-3: 모든 work item 산출물 경로 명시
- [ ] DA-4: 모든 work item AC ≥2건(W2c·W7a~c는 1 AC+테스트 다수 — 단, 각 ≥2 AC 충족하도록 작성) + 검증 명령
- [ ] DA-5: Group A·D 등 병렬 그룹 식별
- [ ] DA-6: EC-1~8 검증 명령 보유
- [ ] DA-7: L work item(recorder, 회귀세트) 사전 분할(W2a/b/c, W7a/b/c)
- [ ] DA-8: 모든 테스트 work item에 test case 자연어 의도 (P-11), 각 H결함과 매핑
- [ ] DA-9: EC↔AC 매핑 표 존재, 누락 0건 (P-12)
