---
status: implemented
touchpoint_id: TP-005
actor: 일반 사용자
surface: web
location: "GET /timetable?day="
related_feature: F08
auditor_status: pending
last_updated: 2026-06-02
implemented_by: P4/W7 (Executor, 2026-06-02)
---

# TP-005 — 전체 시간표를 요일별로 전환하여 확인한다

> 전사 출처: F08 §4.2 + P4/W7 상세. 새 UX 발명 없음.

## 1. 맥락

- **누가 (actor):** 일반 사용자(버스 이용자)
- **언제·왜:** 모든 노선의 시간표를 시(hour)별로 한눈에 파악하려 할 때. 요일별 시간표 차이 확인.
- **위치 (surface/location):** `GET /timetable?day=0` (0=평일, 1=토, 2=일/공휴일)
- **사전 상태 (precondition):** 로그인 불필요. `timetable/*.json` 파일 존재.

## 2. 인터랙션 흐름 (Happy Path)

| # | 사람의 행동 | 시스템의 정확한 반응 | 화면/상태 변화 |
|---|---|---|---|
| 1 | `/timetable`로 진입 | 200 + 기본 day=0 (평일) 시간표 그리드 렌더링 | 전체 시간표 테이블 표시 |
| 2 | [Saturday] 링크 클릭 | `GET /timetable?day=1` → 토요일 시간표 렌더링 | 테이블 내용 교체 |
| 3 | [Sunday/Holiday] 링크 클릭 | `GET /timetable?day=2` → 일/공휴일 시간표 | 테이블 내용 교체 |

## 3. 화면/상태 목업 (ASCII)

```text
┌──────────────────────────────────────────────┐
│  전체 시간표                현재: 08:30 평일  │
│  [Weekday] [Saturday] [Sunday/Holiday]        │
│  버스 범례: [513] [713] [743] [753] [1115]    │
├──────────────────────────────────────────────┤
│  시(Hour) │ 분·노선 (Minutes)                │
│  06       │ ◉ 30 (713)  ◉ 45 (1115)          │
│  07       │ ◉ 10 (513)  ◉ 20 (743)           │
└──────────────────────────────────────────────┘
◉ = .bus-{N} CSS 클래스로 색상 표시 (인라인 style 없음)
```

## 4. 입력 사양

| 입력 | 형식/제약 | 필수 | 기본값 | 검증 시점 |
|---|---|---|---|---|
| day | 정수 0·1·2 | N | 0 | server (범위 밖 → 0 보정) |

## 5. 피드백 규약

- **로딩:** GET 링크 클릭 → 전체 페이지 재렌더.
- **성공:** 시간표 그리드 표시.
- **빈 상태:** 시간표 없음 → "등록된 시간표가 없습니다."

## 6. 분기 (성공/실패/엣지)

| 조건 | 시스템 반응 | 사용자에게 보이는 것 |
|---|---|---|
| 정상 | 200 + 그리드 | Hour/노선별 색상 배지 |
| day 범위 이탈 | 0으로 보정 | 평일 시간표 |
| 시간표 JSON 없음 | 해당 버스 건너뜀 | 나머지 버스만 표시 |

## 7. 접근성·키보드

- 요일 선택은 `<a>` 링크 — 키보드 Tab 이동 가능.
- 버스 배지 색상: `.bus-{N}` CSS 클래스로 구분, 텍스트(버스번호)도 병기하여 색에만 의존하지 않음.

## 8. 자동 갱신/실시간 (해당 시)

해당 없음. F08 §4.5 — 정적 결과 페이지, HTMX 불필요.

## 9. Acceptance (W7 AC 재인용 — 새 기준 만들지 않음)

- [ ] AC-1: `GET /timetable?day=0` → 200 + 시간표 그리드 (검증: `tests/web/test_unist_timetable_route.py::test_grid`)
- [ ] AC-2: `class="bus-713"` 형태 CSS 클래스 사용, `style="color:"` 인라인 없음 (검증: `tests/web/test_unist_timetable_route.py::test_css_class_not_inline`)

## 10. 관련 touch point / feature

- feature: F08
- 인접 TP: [[TP-002]] (버스번호별 시간표 — 같은 timetable_provider 공유)
