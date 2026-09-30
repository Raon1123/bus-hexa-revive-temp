---
status: fixed
postmortem_id: PM-017
severity: low
discovered: 2026-09-30
phase: /ktx 중간역 시각 작업 중 발견
component: bushexa.services.rail_timetable.refresh_trains
related: [PM-008, ADR-013, docs/guide/api-usage.md]
auditor_status: pending
fix: 2026-09-30 feat/ktx-connection-table
---

# PM-017 — 정차역 후보 조회 하나가 타임아웃되면 그 날짜의 알던 정차역이 전부 "모름"으로 덮임

> 부검(postmortem)은 **비난이 아니라 재발 방지**를 위한 기록이다.

## 1. 요약 (3줄)

- **증상:** `crawl-rail` 재실행 뒤 울산→서울 2026-10-03 열차 41편의 `stops` 가 모두 `null` 이 되어 `/ktx` 중간역이 빈 칸, `/seoul` 안내판 정차역 띠가 사라졌다.
- **근본 원인:** `_fetch_stop_map` 은 후보역 조회가 하나라도 실패하면(TAGO `Read timed out`) 그 날짜 전체를 `None`(모름)으로 돌려주고, `refresh_trains` 는 새 열차 목록을 저장하면서 기존 날짜 항목의 `stops` 를 그대로 버렸다. "실패 결과로 좋은 캐시를 덮지 않는다"(PM-008) 가 열차 목록에는 적용됐지만 정차역에는 빠져 있었다.
- **재발 방지:** 새 행의 `stops` 가 모름(`None`·키 없음)이면 기존 항목의 같은 출발시각 열차 정차역을 옮겨 싣는다(`_carry_old_stops`). `/ktx` 는 추가로 같은 요일구분 다른 날짜의 같은 번호·시각 열차에서 정차역을 빌린다(`ktx_connections.borrow_stops`).

## 2. 영향

- 표시만 영향(정차역을 "통과"로 잘못 보이지는 않음 — 모름은 빈 칸/띠 없음). 다음 성공 수집에서 회복되지만, TAGO 타임아웃이 잦은 날에는 며칠 동안 정차역이 비어 있을 수 있었다.

## 3. 회귀 테스트

- `tests/services/test_rail_timetable.py::test_failed_stop_lookup_keeps_previously_known_stops` — 조회 실패(None)·키 없음 행은 기존 정차역을 유지하고, 새로 안 값은 우선한다.
- `tests/services/test_ktx_connections.py::test_borrow_stops_matches_number_and_times_only`

## 4. 교훈

- "실패로 좋은 캐시를 덮지 않는다"는 레코드 단위가 아니라 **필드 단위**로도 점검한다. 부분 조회(후보역 N개)의 실패가 상위 레코드를 새로 쓸 때 함께 사라지는지 본다.
