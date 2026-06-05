---
status: implemented
touchpoint_id: TP-001
actor: 일반 사용자
surface: web
location: "GET /board, GET /partial/board"
related_feature: F01
auditor_status: pending
last_updated: 2026-06-02
implemented_by: P4/W2 (Executor, 2026-06-02)
---

# TP-001 — 출발 게시판을 열어두면 도착정보가 저절로 갱신된다

> Designer 대표 작성(자동갱신 인터랙션 표준). Executor는 W2 구현 시 이 명세를 그대로 따른다.
> feature: F01 §4.2, phase: P4/W2.

## 1. 맥락

- **누가 (actor):** 일반 사용자(버스 이용자)
- **언제·왜:** 정류장으로 가기 전/대기 중, 다음 버스 도착·출발 현황을 실시간으로 확인하려 한다.
- **위치 (surface/location):** `GET /board` (전체 페이지), `GET /partial/board` (테이블 조각, HTMX 폴링)
- **사전 상태 (precondition):** 로그인 불필요. domain `get_board_data`가 BIS 도착정보(`client.fetch_arrivals`)와 timetable로 데이터를 만들 수 있어야 한다(외부 API 실패는 분기 §6에서 처리).

## 2. 인터랙션 흐름 (Happy Path)

| # | 사람의 행동 | 시스템의 정확한 반응 | 화면/상태 변화 |
|---|---|---|---|
| 1 | `/board`로 진입 | 200 + 전체 페이지 렌더. `<div id="board-table" hx-get="/partial/board" hx-trigger="every 15s" hx-swap="innerHTML">`에 첫 행 데이터가 채워져 있다 | 게시판 테이블 즉시 표시 |
| 2 | (아무 것도 안 함, 페이지 유지) | 15초마다 HTMX가 `/partial/board`를 GET → 테이블 행 조각만 응답 → `#board-table` 내부만 교체 | 행 내용만 갱신, 페이지 리로드 없음 |
| 3 | 새 도착정보 도래 | 다음 폴링 응답에 반영 | 시간/잔여 정류장 수 등 갱신 |

## 3. 화면/상태 목업 (ASCII)

```text
┌──────────────────────────────────────────────┐
│  UNIST 출발 게시판            (15초마다 자동) │
├──────────────────────────────────────────────┤
│ id="board-table"  ← 이 안만 교체됨            │
│ ┌──────┬────────────┬───────────┬───────────┐ │
│ │ 노선 │ 현재 위치  │ 도착 예상 │ 경유      │ │
│ │ 713  │ 3 정류장 전 │ 약 6분    │ ...대학병원│ │
│ │ 743  │ 곧 도착     │ 약 1분    │ ...시청   │ │
│ └──────┴────────────┴───────────┴───────────┘ │
└──────────────────────────────────────────────┘
> 열 = BoardRow 필드(bus_number/present/arrival_time·arrival_minutes/via_string). vehicle_no 필드는 도메인에 없음(Designer 사후 정정 2026-06-02).
```

## 4. 입력 사양

| 입력 | 형식/제약 | 필수 | 기본값 | 검증 시점 |
|---|---|---|---|---|
| (없음 — GET 폴링) | — | N | — | — |

## 5. 피드백 규약

- **로딩:** 첫 로드는 서버 렌더로 즉시 데이터 표시(빈 깜빡임 없음). 폴링 갱신은 무음(조용한 교체); 필요 시 `hx-indicator`로 미세 표시.
- **성공:** 행이 갱신되면 그대로 최신 데이터 노출(별도 토스트 없음 — 백그라운드 갱신).
- **에러:** 외부 API 실패 시 §6대로 직전 데이터 + "실시간 정보를 일시적으로 가져오지 못했습니다" 안내 배너. 폴링은 계속.
- **빈 상태:** 운행 데이터 없음 → "현재 출발 정보가 없습니다" 행.

## 6. 분기 (성공/실패/엣지)

| 조건 | 시스템 반응 | 사용자에게 보이는 것 |
|---|---|---|
| 정상 | 200 + 조각 교체 | 최신 행 |
| 외부 API(BIS) 실패 | partial 200 유지 + 도메인이 error 필드 + 시간표 기반 행 반환, 500 회피 | 안내 배너 + 시간표 표 |
| 데이터 없음 | 200 + 빈 상태 행 | "출발 정보 없음" |
| 네트워크 끊김(클라) | HTMX 폴링 자연 재시도(다음 주기) | 다음 갱신 시 자동 복구 |

## 7. 접근성·키보드

- 테이블은 의미적 `<table><thead><tbody>`. 자동 갱신이 키보드 포커스를 빼앗지 않는다(`#board-table` 내부 교체, 컨테이너 외 포커스 유지).
- 색에만 의존하는 상태 표시 금지(텍스트 라벨 병기).

## 8. 자동 갱신/실시간

- **트리거:** HTMX `hx-trigger="every 15s"` (F01 규정 15초). `hx-get="/partial/board"`, `hx-swap="innerHTML"`, target=`#board-table`.
- **보존:** 컨테이너 내부만 교체하므로 페이지 스크롤/상단 네비 유지. partial은 `<html>` 없는 행 조각만 반환(전체 페이지 금지).
- **연결 끊김:** 다음 주기에 자동 재요청(별도 재연결 로직 불필요).

## 9. Acceptance (W2 AC 재인용 — 새 기준 만들지 않음)

- [ ] AC-1: `GET /board` 200 + `id="board-table"` + `hx-trigger="every 15s"` 포함 (검증: `tests/web/test_board_route.py::test_board_ok`)
- [ ] AC-2: `GET /partial/board`가 `<html>` 없는 행 조각만 반환 (검증: `tests/web/test_board_route.py::test_partial_fragment`)

## 10. 관련 touch point / feature

- feature: F01
- 인접 TP: [[TP-003]] (정류장 자동갱신 10초), [[TP-004]] (UNIST 카드 30초) — 동일 자동갱신 패턴
