---
status: implemented
touchpoint_id: TP-004
actor: 일반 사용자
surface: web
location: "GET /unist, GET /partial/unist"
related_feature: F07
auditor_status: pending
last_updated: 2026-06-02
implemented_by: P4/W6 (Executor, 2026-06-02)
---

# TP-004 — UNIST 출발 버스 카드 보드를 열어두면 자동갱신된다

> 전사 출처: F07 §4.2 + P4/W6 상세. 새 UX 발명 없음.

## 1. 맥락

- **누가 (actor):** 일반 사용자(버스 이용자)
- **언제·왜:** UNIST에서 출발하는 버스(513 경유·713/743/753/1115 출발) 전체 현황을 한눈에 파악하려 할 때.
- **위치 (surface/location):** `GET /unist` (전체), `GET /partial/unist` (HTMX 폴링)
- **사전 상태 (precondition):** 로그인 불필요.

## 2. 인터랙션 흐름 (Happy Path)

| # | 사람의 행동 | 시스템의 정확한 반응 | 화면/상태 변화 |
|---|---|---|---|
| 1 | `/unist`로 진입 | 200 + 6개 카드 그리드 렌더링. `id="unist-grid"` 컨테이너에 `hx-trigger="every 30s"` | 6카드 즉시 표시 |
| 2 | (아무 것도 안 함, 페이지 유지) | 30초마다 HTMX가 `/partial/unist`를 GET → `id="unist-grid"` 전체 교체 | 카드 내용 조용히 갱신 |

## 3. 화면/상태 목업 (ASCII)

```text
┌─────────────────────────────────────────────────┐
│  UNIST 출발 버스 현황             (30초마다 자동) │
│  id="unist-grid"                                 │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐   │
│  │ 513 삼남   │ │ 513 덕하   │ │ 713 명촌   │   │
│  │ 10:30 예정 │ │ live 5분   │ │ 08:40 예정 │   │
│  └────────────┘ └────────────┘ └────────────┘   │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐   │
│  │ 743 명촌   │ │ 753 명촌   │ │1115 꽃바위 │   │
│  └────────────┘ └────────────┘ └────────────┘   │
└─────────────────────────────────────────────────┘
6개 카드 = 513 양방향(2) + UNIST 출발 4개(713/743/753/1115)
```

## 4. 입력 사양

| 입력 | 형식/제약 | 필수 | 기본값 | 검증 시점 |
|---|---|---|---|---|
| (없음 — GET 폴링) | — | N | — | — |

## 5. 피드백 규약

- **로딩:** 첫 로드는 서버 렌더링으로 즉시 데이터 표시.
- **성공:** 6개 카드가 최신 정보로 갱신.
- **에러:** BIS API 실패 시 `bis_error` 배너 + 시간표 기반 카드. 폴링 계속.
- **빈 상태(카드별):** 운행 종료 → `last-bus` 클래스 카드.

## 6. 분기 (성공/실패/엣지)

| 조건 | 시스템 반응 | 사용자에게 보이는 것 |
|---|---|---|
| 정상 | 200 + 6카드 | 실시간/시간표 혼합 데이터 |
| BIS API 실패 | 200 + 에러 배너 + 시간표만 | 배너 + 시간표 카드 |
| 운행 종료(카드별) | is_last_bus=True | "운행 종료 또는 정보 없음" |

## 7. 접근성·키보드

- 카드는 `<div>` 구조. 자동 갱신이 키보드 포커스를 빼앗지 않음 (`outerHTML` swap).

## 8. 자동 갱신/실시간

- **트리거:** HTMX `hx-trigger="every 30s"` (F07 §4.5, W6 지시사항).
- `hx-get="/partial/unist"`, `hx-swap="outerHTML"`, target=`id="unist-grid"`.
- partial은 `<html>` 없는 `id="unist-grid"` 조각만 반환.

## 9. Acceptance (W6 AC 재인용 — 새 기준 만들지 않음)

- [ ] AC-1: `GET /unist` → 200 + 정확히 6개 `class="bus-card"` (검증: `tests/web/test_unist_board_route.py::test_six_cards`)
- [ ] AC-2: `GET /partial/unist` → 200, `id="unist-grid"` 조각만 (`<html>` 없음) (검증: `tests/web/test_unist_board_route.py::test_partial`)

## 10. 관련 touch point / feature

- feature: F07
- 인접 TP: [[TP-001]] (출발 게시판 15초), [[TP-003]] (정류장 10초)
