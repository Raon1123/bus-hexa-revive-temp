---
status: fixed
postmortem_id: PM-010
severity: medium
discovered: 2026-06-05
phase: 코드리뷰 #8 → 3차 웨이브 감리
component: bushexa.services.board_support, tests/conftest.py
related: [review #8 E2 E5, "tests/web/test_board_support.py", "tests/conftest.py::_reset_board_support_connections"]
auditor_status: pass (advisor 지적, 504 passed ×5)
---

# PM-010 — `/board` 콜드 18.7초, 그리고 그 수정(연결 캐시)이 만든 테스트 교차 오염

> 부검(postmortem)은 **비난이 아니라 재발 방지**를 위한 기록이다. 사람이 아니라 시스템·프로세스의 결함을 본다.

## 1. 요약 (3줄)

- **증상 1:** `/board` 콜드 응답 18.7초. **증상 2:** 수정 후 테스트가 간헐적으로 실패.
- **근본 원인:** 요청마다 새 SQLite 연결 + PRAGMA 를 실행했고, 크롤러 쓰기와 잠금 경합 시 읽기마다 `busy_timeout`(5초)까지 대기 가능했다(추정, 프로파일로 확정하진 않음). 수정으로 넣은 URL 키 연결 캐시는 테스트들이 공유하는 `sqlite:///:memory:` URL 때문에 하나의 인메모리 DB를 공유시켰다.
- **재발 방지:** 워커 수명 read 연결 캐시(`SELECT 1` 생존 확인, 끊기면 재연결) + 테스트마다 캐시를 비우는 autouse 픽스처.

## 2. 영향 (Impact)

- 사용자 체감 지연(첫 접속·HTMX 폴링). 수정 후 라이브 스모크: cold 153ms → warm 2.9ms.
- 테스트 신뢰도 저하(순서 의존 간헐 실패).

## 3. 타임라인 (발견 경위)

- 2026-06-05 코드리뷰 #8(요청당 연결), E2(`/lite` 요청당 연결 2개) 보고.
- `6114da3` 에서 `get_read_connection` 도입. "504 passed ×5" 로 안정성을 확인했다고 판단.
- 3차 웨이브 감리에서 advisor 가 간헐 실패의 진짜 원인을 캐시 공유로 지목 → `516c55b` 에서 autouse 픽스처 추가.

## 4. 근본 원인 분석 (Root Cause)

- 캐시 키가 `database_url`. `:memory:` 는 연결마다 다른 DB 인데 URL 은 같아서, 캐시가 "같은 DB"로 취급했다.
- 모듈 전역 캐시를 추가하면서 **테스트 리셋 훅을 함께 만들지 않았다.**
- 5회 연속 통과는 순서 의존이 없다는 증거가 아니다(같은 순서로 5번 돌았을 뿐).

## 5. 재현 (Reproduction)

```bash
# tests/conftest.py 의 _reset_board_support_connections 픽스처를 임시로 비활성화한 뒤
uv run python -m pytest tests/web tests/services -q
# 같은 sqlite:///:memory: URL 을 쓰는 테스트끼리 데이터가 섞여 실행 순서에 따라 실패한다
```

## 6. 해결 (Resolution)

- `bushexa/services/board_support.py` — `_READ_CONN_CACHE`, `get_read_connection()`, `_reset_read_connections()`.
- `tests/conftest.py::_reset_board_support_connections`(autouse) — 매 테스트 후 리셋.
- 부수: 시간표 mtime+size 캐시(`data/timetable.py`, E5).

## 7. 재발 방지 (Prevention) — **필수**

- [x] **회귀 테스트**: `tests/web/test_board_support.py::test_get_read_connection_reuse`, `::test_get_read_connection_reconnect_on_broken`, `::test_get_read_connection_different_urls`.
- [x] **코드 가드**: autouse 리셋 픽스처.
- [x] **프로세스**: `docs/guide/pitfalls.md` §6 "모듈 전역 캐시는 리셋 훅과 함께".
- [ ] 지연 회귀 테스트: 없음. 성능 확인은 `Server-Timing` 헤더로 수동.

## 8. 교훈 (Lessons)

- 모듈 전역 캐시·싱글턴을 추가하면 **같은 커밋에서 테스트 리셋 훅**을 추가한다(시간표 캐시의 `_clear_cache` 도 같은 규칙).
- `:memory:` URL 은 식별자가 아니다.
- 성능 수정은 측정(Server-Timing span) 전후를 남긴다. 이 건은 원인이 "추정"으로만 남았다.

## 9. 상태

- 수정 커밋: `6114da3`, `516c55b`
- 회귀 테스트 통과 확인: 2026-09-29 563 passed
