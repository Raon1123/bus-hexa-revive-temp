---
status: implemented
phase_id: P3
designer: opus
auditor_status: execution-pass (2026-06-02, EC-1~5 green, 29 P3 tests + 전체 133 pass; report execution-audit-P3-20260602-T01)
last_updated: 2026-06-02
depends_on: [P1]
---

# P3 — Domain Services (UI 무관 비즈니스 로직)

## 1. 목적

각 UI feature(F01, F02, F05, F06, F07, F08)의 핵심 로직을 `bushexa/domain/`에 순수 함수/서비스로 추출한다. Flask·Streamlit 없이 호출·테스트 가능하며, 모든 시간 의존은 `Clock` 주입으로 결정론 테스트가 가능하다.

## 2. 시작 조건 (Entry Criteria)

- [x] P1 Auditor PASS, 모든 P1 EC PASS (data/db/api_clients/time_utils 가용) — P1 execution-pass (51 P1 tests), 전체 104 pass
- [x] F01/F02/F05/F06/F07/F08 feature doc Auditor PASS — F01/F06/F07 clean PASS(T01), F02/F05/F08 F-9 fixed(T02), 잔여 C-3는 design-audit FROZEN 면제

## 3. 종료 조건 (Exit Criteria)

- [ ] EC-1: `uv run python -c "import bushexa.domain.board, bushexa.domain.stops, bushexa.domain.unist_board, bushexa.domain.unist_timetable, bushexa.domain.running, bushexa.domain.busno"` 무오류
- [ ] EC-2: `uv run pytest tests/domain/ -q` → 0 fail / 0 error
- [ ] EC-3: 모든 domain 함수가 `Clock` 주입을 받아 freezegun 고정 시각으로 테스트된다 (`tests/domain/` 내 freezegun 사용 ≥1/모듈)
- [ ] EC-4: `! grep -rn 'flask\|streamlit\|jinja\|render_template' bushexa/domain/`
- [ ] EC-5: domain 모듈이 P1 인터페이스(`TagoClient`/`UlsanBisClient`/`BusLogRepo`/`get_timetable`/`time_utils`)만 의존 (`! grep -rn 'from bushexa.web' bushexa/domain/`)

### 3.1 EC ↔ Work Item AC 매핑 (P-8 / P-12)

| EC | 검증 대상 | 충족하는 Work Item AC |
|---|---|---|
| EC-1 | 6 모듈 import | W1a: AC-1; W2: AC-1; W3: AC-1; W4: AC-1; W5a: AC-1; W6: AC-1 |
| EC-2 | pytest domain | W1a/W1b/W2/W3/W4/W5a/W5b/W6 각 AC |
| EC-3 | Clock freezegun | W1a: AC-2; W2: AC-2; W3: AC-2; W4: AC-2; W6: AC-2 |
| EC-4 | no flask/streamlit | 전 work item 공통 제약 |
| EC-5 | P1 의존만 | 전 work item 공통 제약 |

> 모든 work item AC가 ≥1개 EC에 매핑됨. 누락 0건.

## 4. Work Item 분해

| ID | 작업 제목 | 소요 | 의존 | 산출물 |
|---|---|---|---|---|
| W1a | board: get_board_data (live+timetable merge) | M | — | domain/board.py(부분) + tests/domain/test_board.py |
| W1b | board: merge_live_rows (FIRST/SECOND 마킹) | M | W1a | domain/board.py(부분) + tests/domain/test_board_merge.py |
| W2 | stops: get_stop_data + filter/gap | M | — | domain/stops.py + tests/domain/test_stops.py |
| W3 | unist_board: get_unist_board_data | M | — | domain/unist_board.py + tests/domain/test_unist_board.py |
| W4 | unist_timetable: get_full_timetable_data | M | — | domain/unist_timetable.py + tests/domain/test_unist_timetable.py |
| W5a | running: parse_runs (vehicle trip 재구성) | M | — | domain/running.py(부분) + tests/domain/test_running_parse.py |
| W5b | running: build_running_grid | M | W5a | domain/running.py(부분) + tests/domain/test_running_grid.py |
| W6 | busno: get_busno_page_data | S | — | domain/busno.py + tests/domain/test_busno.py |

## 5. Work Item 상세

### W1a — board: get_board_data
**Depends:** — **산출물:** `bushexa/domain/board.py`(부분), `tests/domain/test_board.py`

**지시사항 (명령형):**
1. `get_board_data(stop_id, clock, *, client, timetable_provider) -> BoardSnapshot`을 구현한다 (F01 §4.4).
2. 라이브 도착(`client`)과 시간표(`timetable_provider`)를 읽어 도착 예정 목록을 합성한다.
3. 모든 시각 비교는 `clock.now()` 기준 KST로 한다 (직접 `datetime.now()` 호출 금지).
4. 외부 호출은 주입된 client mock으로 대체 가능하게 한다.
5. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: mock client+timetable로 호출 시 도착 시각 오름차순 `BoardSnapshot.rows`를 반환한다 (검증: `uv run pytest tests/domain/test_board.py::test_rows_sorted`)
- [ ] AC-2: `clock`을 08:30으로 고정하면 그 시각 기준으로 다음 도착이 계산된다 (검증: `uv run pytest tests/domain/test_board.py::test_uses_injected_clock`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_rows_sorted`: 라이브 2건·시간표 3건을 합성하면 결과 rows가 도착 시각 오름차순으로 정렬되는지 검증한다.
- `test_uses_injected_clock`: FakeClock(08:30)을 주입하면 그 시각 이전 시간표 항목은 제외되고 이후만 남는지 검증한다 — 직접 now() 호출 금지 보증.
- `test_live_overrides_timetable`: 같은 버스에 라이브 도착이 있으면 시간표 추정 대신 라이브 값을 source="live"로 표시하는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/domain/test_board.py -v
```

---

### W1b — board: merge_live_rows (FIRST/SECOND)
**Depends:** W1a **산출물:** `bushexa/domain/board.py`(부분), `tests/domain/test_board_merge.py`

**지시사항 (명령형):**
1. `merge_live_rows(rows) -> list[BoardRow]`을 구현한다: 가장 이른 2건을 각각 FIRST/SECOND로 마킹한다 (F01 색상 로직).
2. 동률 시각의 tie-break 규칙(버스번호 오름차순)을 정한다.
3. 빈 입력 시 빈 리스트를 반환한다.
4. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: 3건 이상 입력 시 가장 이른 2건이 FIRST/SECOND로 마킹된다 (검증: `uv run pytest tests/domain/test_board_merge.py::test_first_second`)
- [ ] AC-2: 빈 입력은 빈 리스트, 1건 입력은 FIRST만 (검증: `uv run pytest tests/domain/test_board_merge.py::test_edge_counts`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_first_second`: 도착 시각이 다른 3건 입력에서 가장 이른 것이 FIRST, 두 번째가 SECOND, 나머지는 무표시인지 검증한다.
- `test_edge_counts`: 0건이면 빈 리스트, 1건이면 FIRST만 표시되고 SECOND가 없는지 검증한다.
- `test_tie_break_by_busno`: 동일 도착 시각 2건에서 버스번호 오름차순으로 FIRST/SECOND가 결정되는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/domain/test_board_merge.py -v
```

---

### W2 — stops: get_stop_data
**Depends:** — **산출물:** `bushexa/domain/stops.py`, `tests/domain/test_stops.py`

**지시사항 (명령형):**
1. `get_stop_data(stop_id, clock, *, client) -> StopSnapshot`을 구현한다 (F06 §4.4). 캐시는 service 책임이므로 domain은 매번 fresh.
2. 도착 목록을 도착 시각 오름차순 정렬한다.
3. 연속 버스 간 간격이 30분 초과면 `long_gap=True` 플래그를 단다.
4. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: mock client 응답을 정렬된 StopSnapshot으로 반환한다 (검증: `uv run pytest tests/domain/test_stops.py::test_sorted`)
- [ ] AC-2: 30분 초과 간격에서 long_gap 경고 플래그가 켜진다 (검증: `uv run pytest tests/domain/test_stops.py::test_long_gap`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_sorted`: mock 도착 3건(역순)을 주면 결과가 도착 시각 오름차순으로 정렬되는지 검증한다.
- `test_long_gap`: 첫 버스와 둘째 버스 도착 간격이 35분일 때 long_gap 플래그가 True가 되는지 검증한다 — 사용자에게 배차 공백 경고.
- `test_no_bus_empty_snapshot`: 도착이 없을 때 빈 rows와 "운행 없음" 상태를 반환하는지 검증한다.
- `test_uses_injected_clock`: FakeClock 기준으로 도착까지 남은 시간이 계산되는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/domain/test_stops.py -v
```

---

### W3 — unist_board: get_unist_board_data
**Depends:** — **산출물:** `bushexa/domain/unist_board.py`, `tests/domain/test_unist_board.py`

**지시사항 (명령형):**
1. `get_unist_board_data(clock, *, client, timetable_provider) -> UnistBoardSnapshot`을 구현한다 (F07 §4.4). 6 카드(via 2 + from 4 — 513 양방향 2 + UNIST 출발 4개 713/743/753/1115). <!-- Designer 사후 정정(2026-06-02, execution-audit-P3-T01): "via 1 + from 5"는 ROUTEID 사실 오류. F07 §2.3 기준 via 2 + from 4 = 6. -->
2. via 노선(513)은 라이브, UNIST 출발 노선(713/743/753/1115)은 시간표 기반으로 다음 2건을 채운다.
3. 카드 루프 안에서 API를 중복 호출하지 않도록, 라이브 데이터를 한 번만 fetch해 재사용한다 (F07 결함).
4. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: 6개 카드를 반환하고 각 카드에 다음 2건이 채워진다 (검증: `uv run pytest tests/domain/test_unist_board.py::test_six_cards`)
- [ ] AC-2: 라이브 fetch가 1회만 발생한다(카드 수만큼 호출 안 함) (검증: `uv run pytest tests/domain/test_unist_board.py::test_single_fetch`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_six_cards`: 결과 UnistBoardSnapshot에 via 2 + from 4 = 6개 카드(513 양방향 + UNIST 출발 4개)가 있고 각 카드에 최대 2건의 다음 출발이 채워지는지 검증한다.
- `test_single_fetch`: mock client의 호출 횟수를 세어, 카드가 6개여도 라이브 fetch가 정확히 1회만 일어나는지 검증한다 — F07 중복 호출 결함 회귀.
- `test_from_card_index_safe`: 시간표가 1건뿐인 노선에서 "다음 2건" 접근이 IndexError 없이 1건만 채우는지 검증한다 — F07 IndexError 결함 회귀.

**검증 명령:**
```bash
uv run pytest tests/domain/test_unist_board.py -v
```

---

### W4 — unist_timetable: get_full_timetable_data
**Depends:** — **산출물:** `bushexa/domain/unist_timetable.py`, `tests/domain/test_unist_timetable.py`

**지시사항 (명령형):**
1. `get_full_timetable_data(weekday, clock, *, timetable_provider) -> FullTimetableSnapshot`을 구현한다 (F08 §4.4).
2. 시(hour)별로 버스번호·분(minute)을 모아 정렬한다. 색상은 view(CSS) 책임이므로 domain은 버스번호만 부여.
3. weekday가 0/1/2 밖이면 0으로 보정한다.
4. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: 시간별 그룹화 결과가 hour 오름차순, 각 hour 내 minute 오름차순이다 (검증: `uv run pytest tests/domain/test_unist_timetable.py::test_grouped_sorted`)
- [ ] AC-2: weekday=5 입력이 0으로 보정된다 (검증: `uv run pytest tests/domain/test_unist_timetable.py::test_weekday_clamp`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_grouped_sorted`: 여러 노선 시간표를 합치면 hour 오름차순으로 그룹화되고 각 시간대 내 분이 오름차순인지 검증한다.
- `test_weekday_clamp`: 범위를 벗어난 weekday=5를 주면 0(평일)으로 보정되어 처리되는지 검증한다.
- `test_empty_when_no_data`: 모든 노선 시간표가 비면 빈 그리드와 "데이터 없음" 상태를 반환하는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/domain/test_unist_timetable.py -v
```

---

### W5a — running: parse_runs
**Depends:** — **산출물:** `bushexa/domain/running.py`(부분), `tests/domain/test_running_parse.py`

**지시사항 (명령형):**
1. `parse_runs(timelog_rows, route_id) -> list[VehicleRun]`을 구현한다: 차량별로 그룹화하고 시간 간격으로 개별 운행(trip)을 분리한다 (F05 §6.1). <!-- Designer 사후 정정(2026-06-02, execution-audit-P3-T01): route_id 인자 누락이었음. AC-2(미등록 stop 제외)에 ROUTEID[route_id] stop 목록이 필요. -->
2. **마지막 운행 회차 유실 버그를 수정한다**: 루프 종료 후 누적된 마지막 run을 결과에 반드시 추가한다 (F05 결함).
3. `stop_id`가 노선 정류장 목록에 없으면 해당 로그를 건너뛴다.
4. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: 2회 운행한 차량 로그에서 정확히 2개 VehicleRun이 나온다 (마지막 회차 포함) (검증: `uv run pytest tests/domain/test_running_parse.py::test_last_run_included`)
- [ ] AC-2: 미등록 stop_id 로그는 조용히 제외된다 (검증: `uv run pytest tests/domain/test_running_parse.py::test_skip_unknown_stop`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_last_run_included`: 한 차량이 정류장 순회를 2번 완료한 로그에서 parse_runs가 2개의 run을 반환하는지(루프 종료 후 마지막 run 누락 없이) 검증한다 — F05 "마지막 회차 유실" 결함 회귀.
- `test_skip_unknown_stop`: 노선 stop_ids에 없는 stop_id를 가진 로그 행이 결과에서 제외되고 예외가 없는지 검증한다.
- `test_split_by_time_gap`: 같은 차량이라도 큰 시간 간격으로 떨어진 로그가 별개 run으로 분리되는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/domain/test_running_parse.py -v
```

---

### W5b — running: build_running_grid
**Depends:** W5a **산출물:** `bushexa/domain/running.py`(부분), `tests/domain/test_running_grid.py`

**지시사항 (명령형):**
1. `build_running_grid(runs, stops_order) -> RunningGrid`을 구현한다: 행=정류장, 열=운행 회차, 셀=통과 시각.
2. 미통과 정류장 셀은 일관된 마커("레" 또는 빈칸)로 채운다.
3. 모든 열의 정류장 수를 맞춰 DataFrame/렌더 호환이 깨지지 않게 한다 (F05 결함).
4. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: 정류장 N개 × 운행 M회 그리드의 모든 열이 N행을 가진다 (검증: `uv run pytest tests/domain/test_running_grid.py::test_uniform_rows`)
- [ ] AC-2: 미통과 셀이 마커로 채워진다 (검증: `uv run pytest tests/domain/test_running_grid.py::test_missing_cell_marker`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_uniform_rows`: 통과 정류장 수가 다른 두 run을 그리드로 만들 때 모든 열이 동일하게 stops_order 길이만큼의 행을 갖는지 검증한다 — F05 "key-value 길이 불일치" 결함 회귀.
- `test_missing_cell_marker`: 어떤 run이 특정 정류장을 통과하지 않았을 때 그 셀이 일관된 마커로 채워지는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/domain/test_running_grid.py -v
```

---

### W6 — busno: get_busno_page_data
**Depends:** — **산출물:** `bushexa/domain/busno.py`, `tests/domain/test_busno.py`

**지시사항 (명령형):**
1. `get_busno_page_data(bus, day, dep, clock, *, timetable_provider) -> BusnoTimetable`을 구현한다 (F02 §4.4).
2. bus/day/dep가 None이거나 유효하지 않으면 기본값(busnos[0], 현재 요일, 첫 출발지)으로 보정하고 warning을 채운다.
3. 시간표를 Hour/Minute 2열 구조로 가공한다.
4. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: 유효한 bus/day/dep로 Hour/Minute 행을 반환한다 (검증: `uv run pytest tests/domain/test_busno.py::test_valid_selection`)
- [ ] AC-2: 잘못된 dep는 첫 출발지로 폴백하고 warning을 채운다 (검증: `uv run pytest tests/domain/test_busno.py::test_invalid_dep_fallback`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_valid_selection`: bus="713", day=0, dep="UNIST"로 호출하면 그 노선의 시간표가 Hour/Minute 행으로 반환되는지 검증한다.
- `test_invalid_dep_fallback`: 존재하지 않는 dep를 주면 첫 출발지로 폴백하고 warning 메시지가 채워지는지 검증한다.
- `test_day_clamp`: day=9 같은 범위 밖 입력이 0으로 보정되는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/domain/test_busno.py -v
```

## 6. 병렬화 그래프

```text
W1a ──▶ W1b
W2  ── (독립)
W3  ── (독립)
W4  ── (독립)
W5a ──▶ W5b
W6  ── (독립)
```

병렬 가능 그룹:
- **Group A (동시 6개)**: W1a, W2, W3, W4, W5a, W6
- **Group B (동시 2개)**: W1b(W1a 후), W5b(W5a 후)

## 7. 리스크 & 롤백

- R1: domain이 암묵적 `now()`에 의존하면 freezegun 우회 — 모든 시간은 `Clock` 주입만 사용 (EC-3로 가드)
- R2: API client 응답 형식 변동 시 domain 테스트 깨짐 — fixture를 P1과 공유, 버전 명시
- R3: F05 grid 호환성 — build_running_grid가 열 길이를 강제 통일 (W5b)

롤백: `bushexa/domain/`, `tests/domain/` 제거.

## 8. Auditor 감리 포인트 (설계 단계)

- [ ] DA-1: 8개 work item 단일 책임
- [ ] DA-2: 사이클 없음 (W1a→W1b, W5a→W5b, 나머지 독립)
- [ ] DA-3: 모든 work item 산출물 + 테스트 경로 명시
- [ ] DA-4: 모든 work item AC ≥2건 + 검증 명령
- [ ] DA-5: Group A 6개 동시 식별
- [ ] DA-6: EC-1~5 검증 명령 보유
- [ ] DA-7: L work item 없음 (board/running 사전 분할)
- [ ] DA-8: 모든 테스트 work item에 test case 자연어 의도 (P-11), F05/F07 결함과 매핑
- [ ] DA-9: EC↔AC 매핑 표 존재, 누락 0건 (P-12)
