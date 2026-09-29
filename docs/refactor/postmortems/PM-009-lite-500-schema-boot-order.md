---
status: fixed
postmortem_id: PM-009
severity: high
discovered: 2026-06-05
phase: 3차 웨이브 감리 (라이브 스모크)
component: bushexa.services.board_support, bushexa.web.routes.board_lite
related: [ADR-010, review #8, "docker/compose.yaml healthcheck /lite"]
auditor_status: pending (회귀 테스트 없음)
---

# PM-009 — 새 DB에서 `/lite` 가 500 (웹이 arrival 워커의 스키마 생성에 의존)

> 부검(postmortem)은 **비난이 아니라 재발 방지**를 위한 기록이다. 사람이 아니라 시스템·프로세스의 결함을 본다.

## 1. 요약 (3줄)

- **증상:** arrival 워커가 한 번도 돌지 않은 DB에서 `/lite` 가 `no such table: bus_arrival_cache` 로 500.
- **근본 원인:** `create_schema` 를 데몬·CLI 만 호출했고, 웹은 "워커가 먼저 떴을 것"이라는 부팅 순서를 암묵적으로 가정했다.
- **재발 방지:** 웹의 read 연결 생성 시점에 멱등 `create_schema` 를 호출한다. 각 프로세스가 자기 저장소 전제조건을 스스로 세운다.

## 2. 영향 (Impact)

- compose healthcheck 가 `/lite` 를 치므로, 새 배포에서 컨테이너가 unhealthy 로 판정될 수 있었다.
- `/board` 는 `domain/board.py` 가 fetch 예외를 잡아 오류 배너로 처리해 500 이 나지 않았다. `/lite` 의 `_last_fetched_at()` 만 무방비였다.
- 데이터 손실 없음. 배포 전 스모크에서 발견.

## 3. 타임라인 (발견 경위)

- `6114da3` 에서 board_support 팩토리로 라우트를 일원화한 직후, 3차 웨이브 감리의 **라이브 스모크**(실제 서버 기동 + curl)에서 발견.
- 단위 테스트는 통과 중이었다.

## 4. 근본 원인 분석 (Root Cause)

- 스키마 생성 호출 위치: `crawler/daemon.py`, `crawler/arrival_poller.py`, `cli.py init-db` 뿐.
- 웹은 이미 있는 테이블을 읽기만 했다.
- **왜 테스트가 못 잡았나:** `tests/web/test_board_lite.py` 가 `_build_snapshot` 과 `_last_fetched_at` 을 모두 mock 했다. 데이터 접근을 전부 mock 한 라우트 테스트는 "테이블이 없다"를 원리적으로 볼 수 없다.

## 5. 재현 (Reproduction)

```bash
rm -f /tmp/fresh.db
DATABASE_URL=sqlite:////tmp/fresh.db uv run bushexa serve --dev --port 8099 &
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8099/lite   # 수정 전 500, 수정 후 200
```

## 6. 해결 (Resolution)

- `bushexa/services/board_support.py` `get_read_connection` — 새 연결을 만들 때 `create_schema(conn)`(`CREATE ... IF NOT EXISTS`, 멱등) 호출.

## 7. 재발 방지 (Prevention) — **필수**

- [ ] **회귀 테스트**: 미작성. 필요한 테스트 — "스키마가 없는 새 SQLite 파일로 앱을 만들고 mock 없이 `/lite` 가 200 을 반환한다".
- [x] **코드 가드**: 읽기 경로 첫 연결 시 멱등 스키마 생성.
- [x] **프로세스**: 배포 전 라이브 스모크(`scripts/smoke_compose.sh`)를 게이트로 유지. `docs/guide/pitfalls.md` §3.

## 8. 교훈 (Lessons)

- 여러 프로세스가 같은 저장소를 쓰면 **어느 프로세스가 먼저 뜰지 가정하지 않는다.** 전제조건 설정은 멱등으로 만들고 모두가 호출한다.
- mock 이 많은 테스트 스위트는 배선(wiring) 결함을 못 본다. mock 없는 "새 DB 스모크" 1개가 가치가 크다.
- healthcheck 대상 라우트는 가장 단순하고 견고해야 한다.

## 9. 상태

- 수정 커밋: `516c55b`
- 회귀 테스트: 없음(§7 참고)
- Auditor 확인: pending
