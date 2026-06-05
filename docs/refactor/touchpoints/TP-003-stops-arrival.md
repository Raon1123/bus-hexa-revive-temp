---
status: implemented
touchpoint_id: TP-003
actor: 일반 사용자
surface: web
location: "GET /stops, GET /partial/stops?stop_id="
related_feature: F06
auditor_status: pending
last_updated: 2026-06-02
implemented_by: P4/W5 (Executor, 2026-06-02)
---

# TP-003 — 정류장 도착정보를 선택하고 자동갱신으로 확인한다

> 전사 출처: F06 §4.2 + P4/W5 상세. 새 UX 발명 없음.

## 1. 맥락

- **누가 (actor):** 일반 사용자(버스 이용자)
- **언제·왜:** 특정 정류소에서 버스를 기다리며 실시간 도착 정보를 확인하려 할 때.
- **위치 (surface/location):** `GET /stops` (전체), `GET /partial/stops?stop_id=` (HTMX 폴링)
- **사전 상태 (precondition):** 로그인 불필요. 울산 BIS API 연결 가능 여부와 무관(실패 시 에러 배너).

## 2. 인터랙션 흐름 (Happy Path)

| # | 사람의 행동 | 시스템의 정확한 반응 | 화면/상태 변화 |
|---|---|---|---|
| 1 | `/stops`로 진입 | 200 + 정류소 드롭다운 `<select id="stop-select">` 렌더링 | 정류소 선택 UI 표시 |
| 2 | 드롭다운에서 정류소 선택 | HTMX `hx-trigger="change"`로 `/partial/stops?stop_id={id}` 즉시 GET | `#stops-table` 영역에 도착 테이블 교체 |
| 3 | (아무 것도 안 함) | 10초마다 HTMX `hx-trigger="every 10s"`로 `/partial/stops?stop_id=...` 재요청 | 도착 정보 자동 갱신 |

## 3. 화면/상태 목업 (ASCII)

```text
┌──────────────────────────────────────────────┐
│  정류소별 버스 도착 정보                       │
│  정류소: [울산과학기술원 (경유) ▼]             │
├──────────────────────────────────────────────┤
│  id="stops-table"  ← 10초마다 자동 갱신       │
│  ┌──────┬─────────┬──────────┬──────────────┐ │
│  │ 노선 │ 방향    │ 도착 예상 │ 현재 위치    │ │
│  │ 713  │ 명촌 방면 │ 5분 30초 │ 천상       │ │
│  └──────┴─────────┴──────────┴──────────────┘ │
└──────────────────────────────────────────────┘
```

## 4. 입력 사양

| 입력 | 형식/제약 | 필수 | 기본값 | 검증 시점 |
|---|---|---|---|---|
| stop_id | SERACH_STOPS 목록 내 문자열 | Y (partial) | — | server (없으면 400) |

## 5. 피드백 규약

- **로딩:** 첫 선택은 HTMX change trigger로 즉시 부분 갱신.
- **성공:** 도착 테이블 렌더링.
- **에러:** BIS API 실패 → `error` 배너. 폴링 계속.
- **30분 gap 경고:** 두 번째 버스까지 간격 30분 초과 시 경고 배너.
- **빈 상태:** 도착 버스 없음 → "운행 중인 버스가 없습니다."

## 6. 분기 (성공/실패/엣지)

| 조건 | 시스템 반응 | 사용자에게 보이는 것 |
|---|---|---|
| 정상 | 200 + 도착 테이블 | 노선·도착예상·위치 |
| BIS API 오류 | 200 + error 배너 | 에러 안내 |
| 30분 gap | 200 + warning 배너 | 간격 경고 |
| 버스 없음 | 200 + empty-state | "운행 중인 버스가 없습니다" |
| stop_id 미등록 | 400 | 오류 메시지 |

## 7. 접근성·키보드

- `<select>` 드롭다운: Tab+Enter 선택 가능.
- 자동 갱신이 포커스를 빼앗지 않음 (`outerHTML` swap — 선택 후 포커스는 다른 곳으로 이동된 상태).

## 8. 자동 갱신/실시간

- **트리거:** HTMX `hx-trigger="every 10s"` (F06 §1 UPDATE_THRESHOLD 10초).
- `hx-get="/partial/stops?stop_id={id}"`, `hx-swap="outerHTML"`.
- 서버 캐시(TTL 10초, stop_id별): 동일 stop_id 10초 내 재요청은 domain 호출 없이 캐시 반환.

## 9. Acceptance (W5 AC 재인용 — 새 기준 만들지 않음)

- [ ] AC-1: `GET /stops` → 200 + 정류소 선택 UI (검증: `tests/web/test_stops_route.py::test_stops_ok`)
- [ ] AC-2: 10초 내 재요청 → 캐시 적중, domain 1회만 호출 (검증: `tests/web/test_stops_route.py::test_cache_hit`)
- [ ] (cache_expires): FakeClock 11초 → 캐시 만료 재조회 (검증: `tests/web/test_stops_route.py::test_cache_expires`)

## 10. 관련 touch point / feature

- feature: F06
- 인접 TP: [[TP-001]] (출발 게시판 15초 자동갱신), [[TP-004]] (UNIST 카드 30초)
