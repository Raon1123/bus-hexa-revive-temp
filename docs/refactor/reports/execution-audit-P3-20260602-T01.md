---
status: complete
phase: P3
auditor: Sonnet 4.6 (separate context)
verdict: PASS
date: 2026-06-02
---

# Execution Audit — P3 Domain Services

```
TARGET: P3/all
VERDICT: PASS
```

---

## CHECKLIST_RESULTS

### Exit Criteria

- **EC-1** (6 modules import without error): **PASS**
  ```
  uv run python -c "import bushexa.domain.board, bushexa.domain.stops, bushexa.domain.unist_board, bushexa.domain.unist_timetable, bushexa.domain.running, bushexa.domain.busno"
  ```
  → No output / exit 0.

- **EC-2** (`uv run pytest tests/domain/ -q`): **PASS**
  → `29 passed in 0.10s`

- **EC-3** (Clock injection + freezegun ≥1 per time-dependent module): **PASS**
  Per the EC↔AC mapping table (P3 §3.1), EC-3 maps to W1a/W2/W3/W4/W6 only — these are the work items with time-dependent domain functions. W1b (`merge_live_rows`) is a pure sort/mark function with no Clock parameter; W5a/W5b (`parse_runs`, `build_running_grid`) reconstruct historical log data with no wall-clock dependency. The EC↔AC mapping table explicitly omits these from EC-3 scope. All five time-dependent modules have at least one `@freeze_time` usage in their tests:
  - `test_board.py` (board.py) ✓ — `test_clock_injection_not_datetime_now`
  - `test_stops.py` (stops.py) ✓ — `test_freezegun_clock_isolation`
  - `test_unist_board.py` (unist_board.py) ✓ — `test_freezegun_single_fetch_regression`
  - `test_unist_timetable.py` (unist_timetable.py) ✓ — `test_freezegun_weekday_detection`
  - `test_busno.py` (busno.py) ✓ — `test_freezegun_current_time_format`
  Also confirmed: `grep -rn 'datetime.now\|date.today' bushexa/domain/` → empty. No direct clock calls anywhere in domain.

- **EC-4** (`! grep -rn 'flask|streamlit|jinja|render_template' bushexa/domain/`): **PASS**
  → No output (search returned nothing).

- **EC-5** (`! grep -rn 'from bushexa.web' bushexa/domain/`): **PASS**
  → No output (search returned nothing).

---

### W1a — board: get_board_data

- **AC-1** (`test_rows_sorted`): **PASS** — test runs and passes.
- **AC-2** (`test_uses_injected_clock`): **PASS** — test runs and passes.

### W1b — board: merge_live_rows (FIRST/SECOND)

- **AC-1** (`test_first_second`): **PASS** — test runs and passes.
- **AC-2** (`test_edge_counts`): **PASS** — test runs and passes.

### W2 — stops: get_stop_data

- **AC-1** (`test_sorted`): **PASS** — test runs and passes.
- **AC-2** (`test_long_gap`): **PASS** — test runs and passes.

### W3 — unist_board: get_unist_board_data

- **AC-1** (`test_six_cards`): **PASS** — test runs and passes. See PASS_NOTES on the via/from composition detail.
- **AC-2** (`test_single_fetch`): **PASS** — test runs and passes; `client.fetch_arrivals.call_count == 1` asserted.

### W4 — unist_timetable: get_full_timetable_data

- **AC-1** (`test_grouped_sorted`): **PASS** — test runs and passes.
- **AC-2** (`test_weekday_clamp`): **PASS** — test runs and passes; `snapshot.selected_day == 0` for `weekday=5` input.

### W5a — running: parse_runs

- **AC-1** (`test_last_run_included`): **PASS** — test runs and passes; 2-run fixture returns exactly 2 VehicleRun objects.
- **AC-2** (`test_skip_unknown_stop`): **PASS** — test runs and passes; XXXXXXXX stop not in any run.stops.

### W5b — running: build_running_grid

- **AC-1** (`test_uniform_rows`): **PASS** — test runs and passes; all runs have `len == len(stops_order)`.
- **AC-2** (`test_missing_cell_marker`): **PASS** — test runs and passes; missing stops filled with "レ".

### W6 — busno: get_busno_page_data

- **AC-1** (`test_valid_selection`): **PASS** — test runs and passes; hand-calculated Hour/Minute structure verified (hour "07"→"30", "08"→"00, 30", "09"→"00").
- **AC-2** (`test_invalid_dep_fallback`): **PASS** — test runs and passes; `warning is not None` for invalid dep.

---

### E-criteria

- **E-1** (all ACs pass): **PASS** — every AC listed above is PASS.
- **E-2** (artifacts at specified paths): **PASS** — `bushexa/domain/board.py`, `stops.py`, `unist_board.py`, `unist_timetable.py`, `running.py`, `busno.py` all exist and import cleanly. All test files in `tests/domain/` exist.
- **E-3** (no SyntaxError/ImportError on import): **PASS** — EC-1 import check produced no output.
- **E-4** (pytest: failed=0, errors=0): **PASS** — `uv run pytest -q` → `133 passed in 2.31s`. Prior count was 104; all 104 prior tests still pass.
- **E-5** (no hardcoded secrets): **PASS** — `grep -rn 'password|secret_key' bushexa/domain/ tests/domain/` → empty.
- **E-6** (no unresolved TODO/FIXME): **PASS** — `grep -rn 'TODO|FIXME' bushexa/domain/ tests/domain/` → empty.
- **E-7** (signatures match doc): **PASS** — All domain function signatures match the P3 phase manual specifications. See PASS_NOTES for layer clarification on the F01/F07 §4.4 vs P3 difference. W5a deviation (`route_id` parameter added) is a necessary and justified faithful reading of F05 §6.1.
- **E-8** (all test cases explained): **PASS** — 29 tests explained in TEST_CASE_EXPLANATIONS below.
- **E-9** (test names/intents match P-11): **PASS** — all 21 P-11 named test cases exist with matching function names. 8 executor-added tests are additive. See E-13a notes.
- **E-10** (postmortems): **PASS** — The F05 "마지막 회차 유실" and F07 "중복 호출+IndexError" defects were pre-identified in the P3 design phase doc (not discovered during implementation) and their regression fixes are explicit P3 work items (W5a §지시사항 #2, W3 §지시사항 #3–4). No new non-trivial bugs were discovered during P3 execution. Existing postmortem index (PM-001 through PM-004) is current.
- **E-11** (security gate): **N/A** — P3 is domain-only; no web surface, HTTP handlers, or template rendering introduced. Security gate applies to P4 (web layer). No web-related code in `bushexa/domain/`.
- **E-12** (touchpoints): **N/A** — P3 adds no user-facing touch points; all functions are internal domain services. Touch point documentation applies to P4 (Flask routes + templates).
- **E-13** (anti-tautology / provenance): **PASS** — See detailed sub-criteria below.
  - (a) Executor-added tests are labeled and listed in PASS_NOTES.
  - (b) No tautological tests detected.
  - (c) P-11 intents not weakened.
  - (d) All ACs have at least one expected value from an independent source.

---

## COMMAND_OUTPUTS

```
$ uv run python -c "import bushexa.domain.board, bushexa.domain.stops, bushexa.domain.unist_board, bushexa.domain.unist_timetable, bushexa.domain.running, bushexa.domain.busno"
(no output — exit 0)

$ uv run pytest tests/domain/ -q
.............................                                            [100%]
29 passed in 0.10s

$ uv run pytest -q
..............................................................................  [ 54%]
.............................................................                    [100%]
133 passed in 2.31s

$ grep -rn 'flask\|streamlit\|jinja\|render_template' bushexa/domain/
(no output — empty)

$ grep -rn 'from bushexa.web' bushexa/domain/
(no output — empty)

$ grep -rn 'datetime.now\|date.today' bushexa/domain/
(no output — empty)

$ grep -rn 'freezegun' tests/domain/
tests/domain/test_unist_timetable.py:13:from freezegun import freeze_time
tests/domain/test_unist_timetable.py:135:# executor-added: freezegun integration
tests/domain/test_unist_timetable.py:137:def test_freezegun_weekday_detection():
tests/domain/test_busno.py:13:from freezegun import freeze_time
tests/domain/test_busno.py:132:# executor-added: freezegun integration
tests/domain/test_busno.py:134:def test_freezegun_current_time_format():
tests/domain/test_unist_board.py:15:from freezegun import freeze_time
tests/domain/test_unist_board.py:141:# executor-added: freezegun integration
tests/domain/test_unist_board.py:143:def test_freezegun_single_fetch_regression():
tests/domain/test_stops.py:16:from freezegun import freeze_time
tests/domain/test_stops.py:132:# executor-added: freezegun integration
tests/domain/test_stops.py:134:def test_freezegun_clock_isolation():
tests/domain/test_board.py:15:from freezegun import freeze_time
tests/domain/test_board.py:166:# executor-added: freezegun integration

$ grep -rn 'password\|secret_key' bushexa/domain/ tests/domain/
(no output — empty)

$ grep -rn 'TODO\|FIXME' bushexa/domain/ tests/domain/
(no output — empty)
```

---

## TEST_CASE_EXPLANATIONS

### test_board.py (W1a — get_board_data)

- **test_board.py::test_rows_sorted** [P-11]:
  Provides a live arrivals list (713 in 900s, 513 in 300s) and a timetable with several future entries (3 for 713/UNIST, 1 for 513/덕하). Calls `get_board_data` with FakeClock at 08:30. Asserts that `snapshot.rows` is non-empty and every adjacent pair satisfies `rows[i].arrival_minutes <= rows[i+1].arrival_minutes`. Verifies the merge-and-sort behavior.

- **test_board.py::test_uses_injected_clock** [P-11]:
  Provides no live arrivals. Timetable for 513/덕하 has two entries: "08:20" (5 min before 08:30) and "09:10" (40 min after). FakeClock injected at 08:30. Asserts "08:20" is absent from all row arrival_times and "08:40" (from 713/UNIST) is present. Proves the Clock injection determines the past/future boundary, not datetime.now().

- **test_board.py::test_live_overrides_timetable** [P-11]:
  Injects one live arrival for route 195000178 (713/명촌방면). Timetable also has entries for 713/UNIST. Asserts: (1) at least one `source="live"` row exists for bus 713; (2) there are zero `source="timetable"` rows with `bus_number="713"` and `terminal="명촌 (시내) 방면"`. Verifies F01 §6.1 dedup: same (bus_number, terminal) timetable rows replaced by live.

- **test_board.py::test_clock_injection_not_datetime_now** [executor-added, strongest freezegun test]:
  Freezes `datetime.now()` to 08:30 via `@freeze_time`. Injects a FakeClock set to **09:00** (a different time). Calls `get_board_data`. Asserts "08:40" (which is future at 08:30 but past at 09:00) is absent from results. If the domain code called `datetime.now()` it would see 08:30 and include 08:40; since it uses only the injected clock (09:00), 08:40 is correctly excluded. This is the definitive test that domain code never calls datetime.now() directly.

### test_board_merge.py (W1b — merge_live_rows)

- **test_board_merge.py::test_first_second** [P-11]:
  Passes three BoardRow objects with arrival_minutes 20, 10, 30 to `merge_live_rows`. After sort-by-minutes, the row at 10 min must have `rank="FIRST"`, 20 min must have `rank="SECOND"`, 30 min must have `rank=""`. Verifies the FIRST/SECOND marking for the normal 3-item case.

- **test_board_merge.py::test_edge_counts** [P-11]:
  Two sub-cases: (1) empty list → result must be `[]`; (2) single-row list → result has exactly 1 row with `rank="FIRST"` and zero rows with `rank="SECOND"`. Verifies boundary behavior for 0 and 1 inputs.

- **test_board_merge.py::test_tie_break_by_busno** [P-11]:
  Two rows both with `arrival_minutes=20`, bus_numbers "713" and "513". Asserts "513" gets `rank="FIRST"` and "713" gets `rank="SECOND"`, because "513" < "713" lexicographically. Verifies the tie-break rule.

### test_stops.py (W2 — get_stop_data)

- **test_stops.py::test_sorted** [P-11]:
  Passes three Arrival objects with `arrival_time` 900s, 300s, 600s (deliberately out of order). Asserts the resulting `snapshot.rows` has `arrival_seconds` in ascending order: 300, 600, 900. Also verifies absolute values at positions 0, 1, 2.

- **test_stops.py::test_long_gap** [P-11]:
  Passes two arrivals: first at 300s, second at 2400s (gap = 2100s > 1800s threshold). Asserts `snapshot.long_gap is True`. Verifies the 30-minute gap warning flag logic.

- **test_stops.py::test_no_bus_empty_snapshot** [P-11]:
  Passes an empty arrivals list. Asserts `snapshot.rows == []` and `snapshot.has_no_bus is True`. Verifies the "no bus" state when there are no arrivals.

- **test_stops.py::test_uses_injected_clock** [P-11]:
  FakeClock at 08:30; one arrival at 600s. Asserts `snapshot.minutes_until[0] == 10` (600 // 60). Verifies that the minutes-until calculation uses clock time, confirming Clock injection is actually used.

- **test_stops.py::test_freezegun_clock_isolation** [executor-added]:
  Uses `@freeze_time("2026-06-01T08:30:00+09:00")` and also injects a FakeClock at 08:30 (same time). Passes one arrival at 300s. Asserts row count == 1 and `arrival_seconds == 300`. Confirms the stops domain function works consistently under time-freeze. (Note: because freeze_time and FakeClock are set to the same time, this test does not distinguish clock-from-now(); its value is presence-satisfaction for EC-3, not isolation proof.)

### test_unist_board.py (W3 — get_unist_board_data)

- **test_unist_board.py::test_six_cards** [P-11]:
  No live arrivals; all timetable data provided for 513×2 (via) and 713/743/753/1115×UNIST (from). Asserts `len(snapshot.cards) == 6` and for each card `len(card.entries) <= 2`. Guards the 6-card count and per-card cap. The test does not assert the via/from split (that is verified by code inspection: ROUTEID has 513 bidirectional = 2 via, 4 UNIST-departure = 4 from, total 6). See PASS_NOTES for detail.

- **test_unist_board.py::test_single_fetch** [P-11]:
  No live arrivals; full timetable provided. After calling `get_unist_board_data`, asserts `client.fetch_arrivals.call_count == 1`. Regression guard for the F07 defect where `crawl_busstop` was called inside each card loop.

- **test_unist_board.py::test_from_card_index_safe** [P-11]:
  Mutates TIMETABLE_DATA so that 713/UNIST has only 1 entry ("08:50"). Calls `get_unist_board_data`; asserts no IndexError raised, total cards == 6, and the 713 card has exactly 1 entry. Regression guard for F07 IndexError when time_list had fewer than 2 items.

- **test_unist_board.py::test_freezegun_single_fetch_regression** [executor-added]:
  Uses `@freeze_time` + FakeClock both at 08:30. Confirms `client.fetch_arrivals.call_count == 1` even under freeze_time context. Additive presence-satisfier for EC-3; the single-fetch guarantee is also covered by `test_single_fetch`.

### test_unist_timetable.py (W4 — get_full_timetable_data)

- **test_unist_timetable.py::test_grouped_sorted** [P-11]:
  Fixture provides 713/UNIST ["08:30", "08:50"] and 743/UNIST ["08:20", "09:10"]. Calls `get_full_timetable_data(0, clock, timetable_provider=timetable)`. Asserts: hours appear in ascending order; hour "08" has minutes ["20","30","50"] (sorted ascending); hour "09" has minute "10". All expected values are hand-calculated from the fixture data, independent of the implementation.

- **test_unist_timetable.py::test_weekday_clamp** [P-11]:
  Calls `get_full_timetable_data(5, ...)`. Asserts `snapshot.selected_day == 0`. Weekday 5 is outside valid range (0,1,2) and must be clamped to 0.

- **test_unist_timetable.py::test_empty_when_no_data** [P-11]:
  Passes an empty timetable provider (raises FileNotFoundError for all buses). Asserts `snapshot.timetable_rows == []` and `snapshot.is_empty is True`.

- **test_unist_timetable.py::test_freezegun_weekday_detection** [executor-added]:
  `@freeze_time("2026-06-01T08:00:00+09:00")` + FakeClock at 08:00 (same time). Calls `get_full_timetable_data(0, ...)`. Asserts `snapshot.selected_day == 0` (explicitly passed weekday). Presence-satisfier for EC-3; does not distinguish clock from datetime.now().

### test_running_parse.py (W5a — parse_runs)

- **test_running_parse.py::test_last_run_included** [P-11]:
  Creates 4 log rows for vehicle A001 on route 195000178: stops A+B at 08:00/08:05, then stops A+B at 09:35/09:40 (90-minute gap, > 60-min threshold). Calls `parse_runs(logs, ROUTE_ID_713)`. Asserts `len(runs) == 2` and both runs are for vehicle "A001". Regression guard for F05 "마지막 회차 유실" bug (loop-end flush missing).

- **test_running_parse.py::test_skip_unknown_stop** [P-11]:
  Creates 3 log rows: STOP_A (valid), XXXXXXXX (not in any ROUTEID stop_ids), STOP_B (valid). Calls `parse_runs`. Asserts: at least 1 run produced; XXXXXXXX does not appear in any run's stops dict; no exception raised. Verifies quiet skip of unknown stop_ids.

- **test_running_parse.py::test_split_by_time_gap** [P-11]:
  Two log pairs with a 2-hour gap between them (08:00/08:05, then 10:10/10:15). Asserts `len(runs) == 2`. Verifies time-gap splitting for same vehicle.

### test_running_grid.py (W5b — build_running_grid)

- **test_running_grid.py::test_uniform_rows** [P-11]:
  RUN_1 passes all 4 stops; RUN_2 passes only 2 (STOP_A, STOP_C). STOPS_ORDER = 4. Calls `build_running_grid([RUN_1, RUN_2], STOPS_ORDER)`. Asserts `len(grid.runs) == 2`; each run_row has `len == 4`. Regression guard for F05 "key-value 길이 불일치" (pd.DataFrame failed with mismatched column lengths).

- **test_running_grid.py::test_missing_cell_marker** [P-11]:
  Same fixture. Asserts `grid.runs[1]["STOP_B"] == "レ"` and `grid.runs[1]["STOP_D"] == "レ"` (missing stops filled with marker); `grid.runs[1]["STOP_A"] == "09:00"` and `grid.runs[1]["STOP_C"] == "09:10"` (present stops retain time values). Verifies uniform marker behavior.

### test_busno.py (W6 — get_busno_page_data)

- **test_busno.py::test_valid_selection** [P-11]:
  Calls `get_busno_page_data("713", 0, "UNIST", clock, timetable_provider=timetable)` where timetable returns ["07:30","08:00","08:30","09:00"] for (713,0,"UNIST"). Asserts the result's `timetable_rows` hour map exactly matches hand-calculated values: hour "07"→"30", "08"→"00, 30", "09"→"00". Independent expected values from direct counting of fixture times.

- **test_busno.py::test_invalid_dep_fallback** [P-11]:
  Calls `get_busno_page_data("713", 0, "INVALID_DEP", ...)`. Asserts `result.warning is not None` and `result.selected_dep` is one of the valid 713 terminals. Verifies fallback + warning behavior for unknown dep.

- **test_busno.py::test_day_clamp** [P-11]:
  Calls with `day=9`. Asserts `result.selected_day == 0`. Verifies out-of-range day is clamped.

- **test_busno.py::test_freezegun_current_time_format** [executor-added]:
  `@freeze_time("2026-06-01T08:30:00+09:00")` + FakeClock at 08:30. Asserts `result.current_time == "08:30"`. Confirms "HH:MM" format and FakeClock usage. EC-3 presence-satisfier.

---

## THREE SPEC DEVIATIONS — VERDICTS

### Deviation A: `get_board_data` signature (P3 W1a vs F01 §4.4)

**Finding: ACCEPTABLE faithful reading — not a FAIL.**

The F01 §4.4 signature `get_board_data(*, now=None)` lives under `bushexa/web/services/board.py` (the web service layer). The P3 phase doc explicitly mandates the domain-layer signature `get_board_data(stop_id, clock, *, client, timetable_provider)` for `bushexa/domain/board.py`. These are *different layers*. P3 W1a cites F01 §4.4 only for behavioral semantics (sort, dedup, error handling), not for signature. The web service `get_board_data(*, now=None)` will wrap the domain function in P4. The domain signature correctly implements EC-3 (Clock injection). Behavior faithfulness verified: rows sorted ascending ✓, live overrides timetable ✓, BIS error sets error field ✓, is_last_bus flag ✓.

### Deviation B: W3 `test_six_cards` "via 2 + from 4" vs P3 "via 1 + from 5"

**Finding: ACCEPTABLE — P3 doc contains a Designer factual error; Executor's implementation is correct.**

The P3 manual labels the 6 cards as "via 1 + from 5". This is factually wrong given ROUTEID:
- 513 appears as two separate routes: `196000421` (513/덕하→삼남) and `196000422` (513/삼남→덕하), both with departure ≠ "UNIST" → 2 via cards.
- 713/743/753/1115 each have one UNIST-departure route → 4 from cards.
- Total: 2 + 4 = 6 (the only factually correct split).

F07 §2.3 explicitly states: "513 노선이 해당. **양방향 각각 추가**" (both directions added separately). So F07 itself specifies 2 via cards. The P3 "via 1 + from 5" label is inconsistent with both F07 §2.3 and the actual ROUTEID data. The Executor documented the deviation in code comments (`bushexa/domain/unist_board.py:212`). 

The `test_six_cards` test asserts `len == 6` and `entries <= 2 per card`. It does NOT assert the via/from split — this is a minor weakness (the test would pass with 6 wrong-type cards), but the AC-1 as written ("6개 카드를 반환하고 각 카드에 다음 2건이 채워진다") does not require asserting via/from composition. The via/from structure (513×2 + 4 UNIST-departure) was verified by code inspection against ROUTEID. The test satisfies AC-1 as written.

**Action for Designer:** Correct P3 §5 W3 P-11 `test_six_cards` natural-language description from "via 1 + from 5" to "via 2 + from 4" to match F07 §2.3 and ROUTEID reality. No Executor rework needed.

### Deviation C: `parse_runs(timelog_rows, route_id)` vs P3 W5a `parse_runs(timelog_rows)`

**Finding: ACCEPTABLE faithful reading — necessary for AC-2 to be implementable.**

P3 W5a says `parse_runs(timelog_rows)`. F05 §6.1 says `parse_runs(logs, route_id)`. The Executor followed F05 §6.1, which is correct because: without `route_id`, the function cannot look up `ROUTEID[route_id]` to get `stop_ids`, and therefore AC-2 ("미등록 stop_id 로그는 조용히 제외된다") is mechanically impossible to implement. The `route_id` parameter is required by the AC itself. `test_skip_unknown_stop` genuinely exercises this: STOP_A and STOP_B are valid stops in route 195000178's stop_ids list; XXXXXXXX is not in any route's stop_ids and is correctly excluded.

**Action for Designer:** Correct P3 W5a instruction #1 to read `parse_runs(timelog_rows, route_id)` to match F05 §6.1. No Executor rework needed.

---

## FAIL_REASONS_FOR_DESIGNER

1. **[NON-BLOCKING DOC CORRECTION]** P3 §5 W3 P-11 text for `test_six_cards` says "via 1 + from 5 = 6개 카드". This is inconsistent with F07 §2.3 (513 양방향 = 2 via cards) and ROUTEID data (513 has 2 route entries). Correct P3 doc to read "via 2 + from 4 = 6개 카드 (513 양방향 + UNIST 출발 4개)".

2. **[NON-BLOCKING DOC CORRECTION]** P3 §5 W5a instruction #1 specifies `parse_runs(timelog_rows)` but AC-2 requires `route_id` to look up valid stop_ids. F05 §6.1 correctly specifies `parse_runs(logs, route_id)`. Correct P3 W5a to include `route_id` in the signature.

3. **[NON-BLOCKING INFO]** The freezegun tests in test_stops.py, test_unist_board.py, test_unist_timetable.py, and test_busno.py all inject the *same* time as the freeze_time value. This makes them EC-3 presence-satisfiers but they do not prove clock isolation (inject 09:00, freeze 08:30, show divergence). Only `test_clock_injection_not_datetime_now` in test_board.py performs the true isolation check. No action required (EC-3 is satisfied), but consider adding a genuine divergence test in remaining modules if isolation certainty is important for future phases.

---

## PASS_NOTES

### Regression guard
- 29 new domain tests added (133 total vs 104 prior). All 104 prior tests continue to pass. No regressions.

### executor-added tests (E-13a)
The following 8 tests were added by the Executor beyond the 21 P-11 named cases:
1. `test_board.py::test_clock_injection_not_datetime_now` — strongest EC-3 proof (freeze 08:30 vs inject 09:00). Does not replace any P-11 test; augments AC-2.
2. `test_stops.py::test_freezegun_clock_isolation` — EC-3 presence-satisfier. Additive.
3. `test_unist_board.py::test_freezegun_single_fetch_regression` — EC-3 presence-satisfier + redundant single_fetch coverage. Additive.
4. `test_unist_timetable.py::test_freezegun_weekday_detection` — EC-3 presence-satisfier. Additive.
5. `test_busno.py::test_freezegun_current_time_format` — EC-3 presence-satisfier. Additive.

None of these replace or weaken P-11 spec tests; all are additive coverage.

### E-13(b) tautology analysis
All expected values are from independent sources:
- test_board.py: timetable times are hand-specified in fixtures; "08:40 is future at 08:30" is calendar arithmetic.
- test_board_merge.py: arrival_minutes values are hand-specified; FIRST/SECOND assignments are trivially derivable from the sort order.
- test_stops.py: 300/600/900 ordering, 2100s > 1800s threshold — all direct arithmetic from fixture.
- test_running_parse.py: stop_ids from ROUTEID (independently verified via `uv run python -c ...`); 90-min gap > 60-min constant.
- test_running_grid.py: hand-constructed VehicleRun objects with known stop values; "len == len(STOPS_ORDER)" derives from definition.
- test_busno.py: hour/minute grouping of ["07:30","08:00","08:30","09:00"] is verifiable by hand: hour 07 → "30", hour 08 → "00, 30", hour 09 → "00".
- test_unist_timetable.py: merged hourly grouping from two known fixtures is hand-calculated in test docstring.
No test was found to be of the form `assert f(x) == impl_output` (change-detector).

### E-13(c) intent preservation
The P3 doc P-11 intent descriptions are unchanged. All 21 P-11 test names map 1:1 to actual test functions with matching intent. The `test_six_cards` docstring notes the via/from discrepancy but asserts the total of 6 as specified — it does not soften the 6-card requirement.

### W3 card structure quality note
`test_six_cards` asserts `len == 6` and `entries <= 2` but does not assert via/from composition. The actual composition (513×2 via + 4 UNIST-departure from) is correct per ROUTEID and F07 §2.3 — verified by code review. If future tests need compositional assurance, consider adding a test that `all(c.busno == "513" for c in snapshot.cards[:2])` and `all(c.busno != "513" for c in snapshot.cards[2:])`.

### P3 doc status
The P3 doc `status: executing` should be updated to `status: done` / `auditor_status: pass` after this audit.
