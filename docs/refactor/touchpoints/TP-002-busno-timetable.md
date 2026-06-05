---
status: implemented
touchpoint_id: TP-002
actor: 일반 사용자
surface: web
location: "GET /busno?bus=&day=&dep="
related_feature: F02
auditor_status: pending
last_updated: 2026-06-02
implemented_by: P4/W3 (Executor, 2026-06-02)
---

# TP-002 — 버스번호별 시간표를 선택해서 확인한다

> 전사 출처: F02 §4.2 + P4/W3 상세. 새 UX 발명 없음.

## 1. 맥락

- **누가 (actor):** 일반 사용자(버스 이용자)
- **언제·왜:** 특정 버스번호로 오늘 또는 다른 요일의 출발 시각을 확인하려 할 때.
- **위치 (surface/location):** `GET /busno` (쿼리스트링: `?bus=&day=&dep=`)
- **사전 상태 (precondition):** 로그인 불필요. `timetable/*.json` 파일 존재.

## 2. 인터랙션 흐름 (Happy Path)

| # | 사람의 행동 | 시스템의 정확한 반응 | 화면/상태 변화 |
|---|---|---|---|
| 1 | `/busno`로 진입 (쿼리 없음) | 200 + 현재 KST 요일 기본값, 버스번호 목록, 요일 선택, 출발지 선택 UI 렌더링 | 버스 선택 화면 표시 |
| 2 | 버스번호 버튼 클릭 (예: 713) | `?bus=713` GET → 해당 버스의 출발지 목록 갱신 | 출발지 셀렉트 갱신 |
| 3 | 요일 버튼 클릭 + 출발지 선택 | `?bus=713&day=0&dep=UNIST` GET → 시간표 테이블(`class="timetable"`) 렌더링 | Hour/Minute 표 표시 |

## 3. 화면/상태 목업 (ASCII)

```text
┌──────────────────────────────────────────────┐
│  버스번호별 시간표            현재: 08:30      │
├──────────────────────────────────────────────┤
│  [513] [713] [743] [753] [1115]  ← 버스 선택 │
│  [Weekday] [Saturday] [Sunday]   ← 요일 선택 │
│  출발지: [UNIST ▼]               ← dep 선택  │
├──────────────────────────────────────────────┤
│  Hour │ Minute                               │
│  07   │ 20, 40                               │
│  08   │ 10, 30                               │
└──────────────────────────────────────────────┘
```

## 4. 입력 사양

| 입력 | 형식/제약 | 필수 | 기본값 | 검증 시점 |
|---|---|---|---|---|
| bus | 버스번호 문자열 (예: "713") | N | busnos[0] | server |
| day | 정수 0·1·2 | N | 현재 KST 요일 | server |
| dep | 출발지 문자열 (예: "UNIST") | N | 해당 버스 첫 출발지 | server |

## 5. 피드백 규약

- **로딩:** GET 폼 제출. 서버 렌더링으로 즉시 표시.
- **성공:** 시간표 테이블 렌더링.
- **에러:** 유효하지 않은 파라미터 → 경고 배너 + 기본값으로 폴백, 200 유지. 500 금지.
- **빈 상태:** 시간표 없음 → "등록된 시간표가 없습니다."

## 6. 분기 (성공/실패/엣지)

| 조건 | 시스템 반응 | 사용자에게 보이는 것 |
|---|---|---|
| 정상 | 200 + 시간표 테이블 | Hour/Minute 행 목록 |
| bus=999 (미등록) | 200 + warning 배너 + 기본버스 | 경고 메시지 + 기본 시간표 |
| day 범위 이탈 | 0으로 보정 | 평일 시간표 |
| dep 미등록 | 첫 출발지로 폴백 + warning | 경고 메시지 |
| timetable JSON 없음 | 200 + warning + 빈 행 | "시간표 파일을 찾을 수 없습니다" |

## 7. 접근성·키보드

- 버스번호는 `<a>` 링크, 요일도 `<a>` 링크 — 키보드 Tab 이동 가능.
- 출발지는 `<select>` + `onchange` JS submit — Tab+Enter 가능.
- 자동 갱신 없음(정적 페이지).

## 8. 자동 갱신/실시간 (해당 시)

해당 없음. F02 §4.5 — 모든 파라미터 변경은 일반 GET 폼 제출로 처리.

## 9. Acceptance (W3 AC 재인용 — 새 기준 만들지 않음)

- [ ] AC-1: `GET /busno?bus=713&day=0&dep=UNIST` → 200 + `class="timetable"` (검증: `tests/web/test_busno_route.py::test_valid`)
- [ ] AC-2: `?bus=999` → 200 + 경고 배너, 500 아님 (검증: `tests/web/test_busno_route.py::test_invalid_bus_warns`)

## 10. 관련 touch point / feature

- feature: F02
- 인접 TP: [[TP-005]] (전체 시간표 — 같은 timetable_provider 사용)
