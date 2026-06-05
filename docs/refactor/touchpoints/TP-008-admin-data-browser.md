---
status: implemented
touchpoint_id: TP-008
actor: 관리자
surface: admin
location: "GET /admin/data, GET /admin/data.csv"
related_feature: F04
auditor_status: pending
last_updated: 2026-06-02
implemented_by: P4/W12 (Executor, 2026-06-02)
---

# TP-008 — 관리자가 bus_timelog 데이터를 필터링·조회하고 CSV로 내려받는다

> 전사 출처: F04 §4.2(데이터 브라우저) + P4/W12 상세. 새 UX 발명 없음.

## 1. 맥락

- **누가 (actor):** 인증된 관리자
- **언제·왜:** 데이터 정합성 점검, 특정 노선/날짜/차량 로그 확인, 엑셀 분석용 CSV 추출 시.
- **위치 (surface/location):** `GET /admin/data` (브라우저), `GET /admin/data.csv` (CSV 다운로드)
- **사전 상태 (precondition):** `login_required` 통과(비로그인 시 302 → [[TP-007]]).

## 2. 인터랙션 흐름 (Happy Path)

| # | 사람의 행동 | 시스템의 정확한 반응 | 화면/상태 변화 |
|---|---|---|---|
| 1 | `/admin/data` 접근 | 200 + 필터 폼 + (필터 없으면 전체 첫 페이지) | 필터 폼 + 결과 표 |
| 2 | `route_id=195000177&day=20260601` 입력 후 조회 | `BusLogRepo.query_paged(route_id=..., day=...)` → PagedResult | 해당 조건 행만 표시 |
| 3 | "CSV 다운로드" 클릭 | `GET /admin/data.csv?route_id=...&day=...` → UTF-8 BOM + 헤더 + 행 streaming | 파일 다운로드 시작 |
| 4 | 페이지 이동 | `?page=2` → 다음 페이지 결과 | 페이지 이동 |

## 3. 화면/상태 목업 (ASCII)

```text
┌─ /admin/data ────────────────────────────────────────────┐
│  필터: [route_id] [stop_id] [vehicle] [day YYYYMMDD]     │
│        [size=100]                     [ 조회 ]           │
│                                                          │
│  총 3건 (1 / 1페이지)                                    │
│  [CSV 다운로드]                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │ idx         │ stop_id │ route_id │ vehicle_no │  │   │
│  │ 20260601_.. │ S001    │ 195..    │ VH-001    │  │   │
│  └──────────────────────────────────────────────────┘   │
│  ← 이전  다음 →                                          │
└──────────────────────────────────────────────────────────┘
```

## 4. 입력 사양

| 입력 | 형식/제약 | 필수 | 기본값 | 검증 시점 |
|---|---|---|---|---|
| `route_id` | 문자열 | N | None | server |
| `stop_id` | 문자열 | N | None | server |
| `vehicle` | 문자열 | N | None | server |
| `day` | YYYYMMDD 8자리 숫자 | N | None | server (잘못된 형식 → 400) |
| `page` | 양의 정수 | N | 1 | server |
| `size` | 1–500 정수 | N | 100 | server |

## 5. 피드백 규약

- **성공:** `id="total-count"` 엘리먼트에 "총 N건", 결과 표 표시.
- **결과 없음:** "No rows — 조건에 맞는 데이터가 없습니다." (`id="no-rows"`).
- **잘못된 day:** 400 Bad Request.
- **DB 오류:** 결과 없음 상태로 표시(500 금지).
- **CSV:** `Content-Disposition: attachment; filename=bus_data.csv`, UTF-8 BOM 선두, 최대 10000행.

## 6. 분기 (성공/실패/엣지)

| 조건 | 시스템 반응 | 사용자에게 보이는 것 |
|---|---|---|
| 정상 필터 | 200 + PagedResult | 결과 표 |
| 결과 0건 | 200 + no-rows | "No rows" 안내 |
| day 형식 오류 | 400 | 오류 응답 |
| CSV 다운로드 | 200 + BOM + 헤더 + 행 | 파일 다운로드 |
| 비로그인 | 302 login | 로그인 페이지 |

## 7. 접근성·키보드

- 필터 폼 `<label>` 연결. Enter 제출 가능.
- 페이지네이션 `<nav id="pagination">` 링크.

## 8. 자동 갱신/실시간

해당 없음. GET 폼 제출 기반.

## 9. Acceptance (W12 AC 재인용)

- [ ] AC-1: 필터 결과 행 수 = `repo.count()` 독립 검증 (검증: `tests/web/test_admin_data_browser.py::test_filter_count`)
- [ ] AC-2: `/admin/data.csv`가 UTF-8 BOM(`\xef\xbb\xbf`)으로 시작 (검증: `tests/web/test_admin_data_browser.py::test_csv_bom`)
- [ ] AC-3: `?day=abc` → 400 (검증: `tests/web/test_admin_data_browser.py::test_bad_day_400`)

## 10. 관련 touch point / feature

- feature: F04
- 인접 TP: [[TP-007]] (인증 게이트), [[TP-006]] (운행 로그 — 같은 bus_timelog DB 읽기)
