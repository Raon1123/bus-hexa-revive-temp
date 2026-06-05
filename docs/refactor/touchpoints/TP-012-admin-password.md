---
status: implemented
touchpoint_id: TP-012
actor: 관리자
surface: admin
location: "GET /admin/password, POST /admin/password"
related_feature: F04
auditor_status: pending
last_updated: 2026-06-02
implemented_by: P4/W10 (Executor, 2026-06-02)
---

# TP-012 — 관리자가 현재 비밀번호를 확인하고 새 비밀번호로 변경한다

> 전사 출처: F04 §4.2(비밀번호 재설정) + P4/W10 상세 + D8 보안 결함 봉인. 새 UX 발명 없음.

## 1. 맥락

- **누가 (actor):** 인증된 관리자
- **언제·왜:** 비밀번호를 교체하거나 legacy 평문을 PBKDF2로 업그레이드하려 할 때.
- **위치 (surface/location):** `GET /admin/password` (폼), `POST /admin/password` (처리)
- **사전 상태 (precondition):** `login_required` 통과(비로그인 시 302 → [[TP-007]]).

## 2. 인터랙션 흐름 (Happy Path)

| # | 사람의 행동 | 시스템의 정확한 반응 | 화면/상태 변화 |
|---|---|---|---|
| 1 | `/admin/password` 접근 | 200 + 비밀번호 변경 폼 | 폼 표시 |
| 2 | 현재·신규·확인 비밀번호 입력 + 제출 | `AuthService.change_password(current, new)` 호출 | — |
| 3 | 검증 성공 | `secret/manager_password.txt` 갱신(PBKDF2), 302 대시보드 | flash "변경됨" |

## 3. 화면/상태 목업 (ASCII)

```text
┌─ /admin/password ───────────────────────────────────┐
│  비밀번호 변경                                        │
│  현재 비밀번호:          [____________________]      │
│  새 비밀번호 (8자 이상): [____________________]      │
│  새 비밀번호 확인:       [____________________]      │
│  <input hidden name=csrf_token value=...>            │
│                                      [ 변경 ]        │
│                                                      │
│  [오류 시] "현재 비밀번호가 올바르지 않습니다. (D8)" │
└──────────────────────────────────────────────────────┘
```

## 4. 입력 사양

| 입력 | 형식/제약 | 필수 | 기본값 | 검증 시점 |
|---|---|---|---|---|
| `current` | 현재 비밀번호 평문 | Y | — | server (`AuthService.change_password`) |
| `new` | ≥8자 | Y | — | server |
| `confirm` | `new`와 일치 | Y | — | server |
| `csrf_token` | 세션 토큰과 일치 | Y | — | server (before_request, 불일치 400) |

## 5. 피드백 규약

- **성공:** flash "비밀번호가 변경되었습니다." + 302 대시보드.
- **현재 비번 불일치 (D8 봉인):** 422 + "현재 비밀번호가 올바르지 않습니다." 오류 메시지 (`error-current`).
- **8자 미만:** 422 + "새 비밀번호는 8자 이상이어야 합니다."
- **confirm 불일치:** 422 + "새 비밀번호와 확인이 일치하지 않습니다."
- **I/O 오류:** 500 + "저장 중 오류".

## 6. 분기 (성공/실패/엣지)

| 조건 | 시스템 반응 | 사용자에게 보이는 것 |
|---|---|---|
| 정상 변경 | 302 대시보드 | flash 성공 |
| 현재 비번 오류 | 422 + error='current_invalid' | D8 오류 메시지 |
| 신규 8자 미만 | 422 + error='too_short' | 길이 오류 |
| confirm 불일치 | 422 + error='new_mismatch' | 불일치 오류 |
| 비로그인 | 302 login | 로그인 페이지 |
| CSRF 누락 | 400 | 요청 거부 |

## 7. 접근성·키보드

- 세 필드 모두 `<label for>` 연결. Tab 순서 자연스럽게.
- 오류 메시지는 인라인(`#error-current` 등).

## 8. 자동 갱신/실시간

해당 없음. 폼 제출 기반.

## 9. Acceptance (W10 AC/D8 재인용)

- [ ] AC-1: 현재 비밀번호 불일치 → 422 + error='current_invalid' 표시 (검증: `tests/web/test_admin_auth_flow.py::test_password_change_current_invalid`)
- [ ] AC-2: 올바른 비밀번호로 변경 → 302 대시보드 + flash (검증: 수동 시나리오 — F04 §8.3 step 9)
- [ ] D8 봉인: 현재 비밀번호 없이 변경 불가 — 세션 탈취 시 즉시 비밀번호 변경 차단

## 10. 관련 touch point / feature

- feature: F04
- 인접 TP: [[TP-007]] (로그인 — 진입 조건)
