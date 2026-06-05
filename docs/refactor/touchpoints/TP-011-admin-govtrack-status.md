---
status: implemented
touchpoint_id: TP-011
actor: 관리자
surface: admin
location: "GET /admin/govtrack/status, GET /admin/govtrack/status/stream"
related_feature: F04
auditor_status: pending
last_updated: 2026-06-02
implemented_by: P4/W14
---

# TP-011 — 관리자가 govtrack 데몬 상태를 실시간으로 모니터링한다

> feature: F04 §4.5, phase: P4/W14 (GovtrackStatusReader 위임, depends W1/W9/P2-W6).

## 1. 맥락

- **누가 (actor):** 인증된 관리자
- **언제·왜:** govtrack 데몬이 정상 동작하는지 확인하거나 이상 여부(연속 실패)를 감지하려 할 때.
- **위치 (surface/location):** `GET /admin/govtrack/status` (JSON), `GET /admin/govtrack/status/stream` (SSE 5초 간격)
- **사전 상태 (precondition):** `login_required`. govtrack 데몬이 `config.data_dir/govtrack_status.json` 에 상태를 기록하고 있어야 함.

## 2. 인터랙션 흐름 (Happy Path)

| # | 사람의 행동 | 시스템의 정확한 반응 | 화면/상태 변화 |
|---|---|---|---|
| 1 | `govtrack_status.html` 페이지 접속 | `EventSource` 로 `/admin/govtrack/status/stream` SSE 구독 | 카드 "로드 중..." 표시 |
| 2 | (자동) | 첫 이벤트 즉시 수신: `event: status\ndata: {…}` | 카드에 last_success_at·consecutive_failures 표시 |
| 3 | (5초마다 자동 갱신) | 최신 GovtrackStatus를 읽어 SSE 이벤트 송신 | 카드 내용 갱신 |

## 3. 화면/상태 목업 (ASCII)

```text
┌─ Govtrack 데몬 상태 ─────────────────────────┐
│  마지막 성공: 2026-06-01T08:00:00+09:00       │
│  연속 실패: 0   (상태: 정상)                  │
│  마지막 삽입: 5건                             │
└──────────────────────────────────────────────┘

(데몬 미동작 시 카드 빨간 강조)
┌─ Govtrack 데몬 상태  [경고 배경] ─────────────┐
│  마지막 성공: 2026-06-01T08:00:00+09:00       │
│  연속 실패: 3   ⚠ 데몬 미동작 감지           │
└──────────────────────────────────────────────┘
```

## 4. 입력 사양

| 입력 | 형식/제약 | 필수 | 기본값 | 검증 시점 |
|---|---|---|---|---|
| — (GET, 파라미터 없음) | — | — | — | — |

## 5. 피드백 규약

- **로딩:** "상태를 로드 중입니다..." 문구 + SSE 첫 이벤트 수신 즉시 교체.
- **성공:** `consecutive_failures == 0` → 정상 상태 표시.
- **에러 (데몬 미동작):** `consecutive_failures > 0` → 카드 빨간 강조 + "⚠ 데몬 미동작 감지" 메시지.
- **빈 상태:** `last_success_at` 없음(데몬 미실행) → "데이터 없음 — 데몬이 아직 실행되지 않았습니다."
- **SSE 연결 오류:** "SSE 연결 오류. 재연결 중..." + 브라우저 기본 retry(3초).

## 6. 분기 (성공/실패/엣지)

| 조건 | 시스템 반응 | 사용자에게 보이는 것 |
|---|---|---|
| 데몬 정상 동작 | consecutive_failures=0, last_success_at 최신 | 정상 카드 (초록 강조 없음) |
| 데몬 미동작 (failures>0) | consecutive_failures>0 | 카드 빨간 강조 + ⚠ 메시지 |
| status 파일 부재 | 빈 dict 반환 (500 아님) | "데이터 없음" 안내 |
| 비로그인 접근 | 302 `/admin/login` | 로그인 페이지 |
| SSE 연결 끊김 | 브라우저 기본 retry 3초 | 오류 메시지 → 자동 재연결 |

## 7. 접근성·키보드

- 페이지 텍스트 기반이므로 스크린리더 자동 읽기 가능.
- SSE 카드 갱신은 `aria-live` 영역으로 표시 가능 (현재 미구현 — MVP 이후).

## 8. 자동 갱신/실시간

- **트리거:** SSE `text/event-stream`. `event: status\ndata: {json}\n\n` 형식. 5초 간격(`_SSE_INTERVAL_SECS=5`).
- **첫 이벤트:** sleep 없이 즉시 전송 (테스트 안정성).
- **연결 끊김:** 브라우저 기본 retry; 서버 쪽은 GeneratorExit/BrokenPipeError로 자연 종료.
- **동시성:** admin 단일 접속 가정 (R2, P4 §7).

## 9. Acceptance (W14 AC 재인용)

- [ ] AC-1: status JSON에 `last_success_at`·`consecutive_failures` 필드가 있다 (검증: `tests/web/test_admin_govtrack_status.py::test_status_json`)
- [ ] AC-2: SSE 스트림이 `text/event-stream`으로 status 이벤트를 송신한다 (검증: `tests/web/test_admin_govtrack_status.py::test_status_sse`)

## 10. 관련 touch point / feature

- feature: F04 §4.5
- 인접 TP: [[TP-010]] (recrawl SSE — 동일 SSE 패턴), [[TP-015]] (로그 뷰어)
- 의존: P2/W6 `GovtrackStatusReader`
