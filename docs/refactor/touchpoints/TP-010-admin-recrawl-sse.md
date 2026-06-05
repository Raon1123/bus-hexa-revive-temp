---
status: implemented
touchpoint_id: TP-010
actor: 관리자
surface: admin
location: "POST /admin/timetable/recrawl, GET /admin/timetable/recrawl/<job_id>/stream"
related_feature: F04
auditor_status: pending
last_updated: 2026-06-02
implemented_by: P4/W13b
---

# TP-010 — 관리자가 시간표 재크롤을 실행하고 진행 상황을 실시간으로 본다

> Designer 대표 작성(SSE 진행 스트림 + 동시성 제어). Executor는 W13b 구현 시 이 명세를 그대로 따른다.
> feature: F04 §4.5, phase: P4/W13b (job은 P2/W5 `TimetableCrawlJob` 위임, depends W13a).

## 1. 맥락

- **누가 (actor):** 인증된 관리자
- **언제·왜:** 외부 시간표가 갱신되어 전체를 다시 크롤해 반영하려 할 때.
- **위치 (surface/location):** `POST /admin/timetable/recrawl`(job 시작), `GET /admin/timetable/recrawl/<job_id>/stream`(SSE)
- **사전 상태 (precondition):** `login_required`. 진행 중인 재크롤 job이 없어야 함(동시 1개). 시작 POST는 CSRF 토큰 필요(§10 S5).

## 2. 인터랙션 흐름 (Happy Path)

| # | 사람의 행동 | 시스템의 정확한 반응 | 화면/상태 변화 |
|---|---|---|---|
| 1 | "재크롤" 버튼(POST) | 200 + `job_id` 반환, `TimetableCrawlJob.start(vacation=...)`로 백그라운드 시작 | 진행 영역 표시 |
| 2 | 클라이언트가 `/recrawl/<job_id>/stream` SSE 구독 | `text/event-stream`으로 `event: progress` 데이터(route/day/page)를 ≥1회 송신 | 진행률/현재 노선 갱신 |
| 3 | (대기) | 완료 시 `event: done` 송신 후 스트림 종료 | "완료" 표시, 결과 요약 |

## 3. 화면/상태 목업 (ASCII)

```text
┌─ 시간표 재크롤 ────────────────────────────┐
│ 방학 모드 [ ]      [ 재크롤 시작 ]         │
│ ── 진행 (SSE) ───────────────────────────  │
│  713 day=0 page=2 ...                      │
│  ▓▓▓▓▓▓░░░░  진행 중                       │
│  ✔ 완료 (event: done)                      │
└────────────────────────────────────────────┘
```

## 4. 입력 사양

| 입력 | 형식/제약 | 필수 | 기본값 | 검증 시점 |
|---|---|---|---|---|
| `vacation` (방학모드) | bool | N | false | server |
| `csrf_token` | 세션 토큰과 일치 | Y | — | server (불일치 400/403) |
| `<job_id>` (경로) | 발급된 job만, 미존재 404 | Y | — | server |

## 5. 피드백 규약

- **로딩:** SSE progress 이벤트로 현재 노선/페이지 실시간 표시. 버튼은 진행 중 비활성.
- **성공:** `event: done` 수신 → "재크롤 완료" + 갱신 노선 수.
- **에러:** `event: error` 수신 → 실패 사유 표시, 부분 결과 안내. SSE 브라우저 기본 retry(3초) 자동 재연결.
- **빈 상태:** 진행 중 job 없을 때 시작 버튼만.

## 6. 분기 (성공/실패/엣지)

| 조건 | 시스템 반응 | 사용자에게 보이는 것 |
|---|---|---|
| 정상 | progress ≥1 → done, 스트림 종료 | 진행 → 완료 |
| 진행 중 재시작 시도 | 두 번째 POST는 **409 Conflict**(동시 1개) | "이미 진행 중입니다" |
| 크롤 실패 | `event: error` + 사유 | 실패 배너, 부분 결과 |
| 비로그인 | 302 `/admin/login` | 로그인 페이지 |
| CSRF 누락/불일치 | 400/403, 시작 안 함 | 거부 메시지 |
| 잘못된/만료 job_id 구독 | 404 | "작업을 찾을 수 없음" |

## 7. 접근성·키보드

- 진행 영역은 `aria-live="polite"`로 스크린리더가 갱신을 읽음.
- 버튼 키보드 작동, 진행 중 disabled 상태 명시.

## 8. 자동 갱신/실시간

- **트리거:** SSE `text/event-stream`. 이벤트 종류 `progress`/`done`/`error`. 한 줄당 `event: <type>\ndata: <json>\n\n`.
- **동시성:** 재크롤 동시 1개(두 번째 409). SSE 연결은 sync 워커 1개를 점유하므로 운영은 관리자 단일 접속 가정(R2).
- **연결 끊김:** 브라우저 기본 retry로 재연결; job은 서버에서 계속 진행.

## 9. Acceptance (W13b AC 재인용)

- [ ] AC-1: SSE 스트림이 progress 이벤트 ≥1 후 done으로 종결 (검증: `tests/web/test_admin_recrawl_sse.py::test_stream`)
- [ ] AC-2: 진행 중 두 번째 recrawl POST는 409 (검증: `::test_conflict`)

## 10. 관련 touch point / feature

- feature: F04
- 인접 TP: [[TP-009]] (편집 화면), [[TP-011]] (govtrack status SSE) — 동일 SSE 패턴
