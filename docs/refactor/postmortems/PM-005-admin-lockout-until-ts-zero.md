---
status: verified
postmortem_id: PM-005
severity: medium
discovered: 2026-06-02
phase: P4 / W10 구현
component: bushexa.web.routes.admin
related: [F04, P4, "tests/web/test_admin_auth_flow.py::test_lockout_after_5_fails"]
auditor_status: verified (execution-audit-P4-chunk3b-20260602-T01 — 회귀테스트 test_lockout_after_5_fails 통과 확인)
---

# PM-005 — 로그인 lockout이 발동하지 않음 (until_ts=0 sentinel 오평가)

> 부검(postmortem)은 **비난이 아니라 재발 방지**를 위한 기록이다. 사람이 아니라 시스템·프로세스의 결함을 본다.

## 1. 요약 (3줄)

- **증상:** 5회 연속 로그인 실패 후에도 lockout이 발동하지 않고 6번째 시도가 423이 아닌 401을 반환.
- **근본 원인:** lockout entry를 `(until_ts, fails)`로 저장하면서 "아직 미잠금"을 `until_ts=0`으로 표현했는데, `_is_locked`가 `now_ts >= until_ts`(= `now >= 0`, 항상 True)를 만료로 해석해 매 요청마다 entry를 삭제 → 실패 카운터가 0으로 리셋.
- **재발 방지:** entry 구조를 `(locked_until: float | None, fails)`로 변경해 None(미잠금)과 만료된 잠금을 명확히 구분 + 회귀 테스트 `test_lockout_after_5_fails`로 5회 후 차단을 고정.

## 2. 영향 (Impact)

- 영향 받은 기능: 관리자 로그인 lockout(F04 §7 AC-A2, S1 brute-force 완화).
- 지속 기간: W10 구현 초기 ~ 동일 세션 내 발견·수정(미배포). 운영 노출 없음.
- 데이터 손실·오염: 없음. 보안 방어 기능이 비활성 상태였던 잠재 위험만 존재.

## 3. 타임라인 (발견 경위)

- W10 admin 라우트 구현 직후 `test_lockout_after_5_fails` 최초 실행에서 6번째 시도가 401(예상 423)로 FAIL.
- 재현 명령: `uv run pytest tests/web/test_admin_auth_flow.py::test_lockout_after_5_fails`.
- 디버깅: `_record_fail`이 매번 fails=1로 시작함을 확인 → `_is_locked`가 entry를 선삭제하는 것으로 추적.

## 4. 근본 원인 분석 (Root Cause)

- 초기 구조: `state[key] = (until_ts, fails)`. 미잠금 상태를 `until_ts=0`으로 표기.
- `_is_locked`:
  ```python
  until_ts, _ = entry
  if now_ts >= until_ts:   # until_ts=0 → now_ts >= 0 → 항상 True
      del state[key]       # entry 삭제
      return False
  ```
  → 미잠금 entry(`until_ts=0`)를 "만료된 잠금"으로 오인해 삭제.
- `_record_fail`은 매 호출 시 삭제된 entry를 보고 fails=1부터 다시 시작 → 카운터가 누적되지 않음.
- 5 Whys: lockout 미발동 ← 카운터 리셋 ← entry 삭제 ← `now>=0` True ← `until_ts=0`을 "만료"로 해석 ← "미잠금"과 "만료된 잠금"을 같은 sentinel(0)로 표현(타입/의미 분리 실패).
- 기존 테스트가 못 잡은 이유: 테스트 자체는 처음부터 lockout 시나리오를 검증하도록 설계되어 **실제로 잡았다**. 구현이 테스트를 통과하지 못해 결함이 드러난 케이스(TDD 게이트가 정상 작동).

## 5. 재현 (Reproduction)

```bash
uv run pytest tests/web/test_admin_auth_flow.py::test_lockout_after_5_fails
```

- 기대 동작: 5회 오답 후 6번째 시도 → 423 Locked.
- (수정 전) 실제 동작: 6번째 시도 → 401 Unauthorized (lockout 미발동).

## 6. 해결 (Resolution)

- `bushexa/web/routes/admin.py` `_is_locked`/`_record_fail`: entry 구조를
  `(locked_until: float | None, fails: int)`로 변경.
  - `locked_until is None` → 미잠금(실패 카운트만 누적), `_is_locked`는 False.
  - `locked_until`이 float이고 `now >= locked_until` → 만료, entry 삭제.
  - `fails >= _MAX_FAILS(5)`일 때만 `locked_until = now + _LOCKOUT_SECS(10)` 설정.
- 대안 검토: 별도 `locked: bool` 필드 추가도 가능했으나, `None | float` 단일 필드가 "미잠금/잠금시각"을 동시 표현해 더 간결.

## 7. 재발 방지 (Prevention) — **필수**

- [x] **회귀 테스트**: `tests/web/test_admin_auth_flow.py::test_lockout_after_5_fails` — "5회 연속 오답 후 6번째 로그인 시도가 423/429로 차단되는지 검증한다" (ADR-008 P-11 자연어 의도).
- [x] **코드 가드**: sentinel을 `None`으로 명시해 "0=미잠금"과 "0=만료시각" 의미 충돌 제거.
- [ ] **프로세스**: 별도 변경 없음(기존 TDD 게이트가 결함을 포착함).
- [ ] **회귀 매트릭스 갱신**: 해당 없음(P4 web 신규 기능).

## 8. 교훈 (Lessons)

- 시간 기반 sentinel에 `0`을 "없음/미설정"으로 재사용하면 비교 연산(`>=`)에서 "과거=만료"로 오인되기 쉽다. "없음"은 `None`으로 타입 수준에서 분리하라.
- 상태를 (시각, 카운트) 튜플로 압축할 때 각 필드의 "특수값" 의미가 비교 로직과 충돌하지 않는지 점검.

## 9. 상태

- 수정 커밋: P4 Chunk 3b (W10) 구현 내 수정.
- 회귀 테스트 통과 확인: `test_lockout_after_5_fails` PASS (전체 185 passed).
- Auditor 확인: pending.
