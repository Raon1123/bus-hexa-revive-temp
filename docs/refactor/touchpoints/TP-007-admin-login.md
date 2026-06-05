---
status: implemented
touchpoint_id: TP-007
actor: 관리자
surface: admin
location: "GET /admin/login, POST /admin/login, POST /admin/logout, GET /admin/"
related_feature: F04
auditor_status: pending
last_updated: 2026-06-02
implemented_by: P4/W10 (Executor, 2026-06-02)
---

# TP-007 — 관리자가 로그인하고 세션을 유지·종료한다

> 전사 출처: F04 §4.2 + P4/W10 상세. 새 UX 발명 없음.

## 1. 맥락

- **누가 (actor):** 관리자
- **언제·왜:** 관리자 대시보드·데이터 브라우저·시간표 편집 등 보호 라우트에 접근하려 할 때.
- **위치 (surface/location):** `GET /admin/login` (폼), `POST /admin/login` (처리), `POST /admin/logout`, `GET /admin/` (대시보드)
- **사전 상태 (precondition):** 비밀번호 파일(`secret/manager_password.txt`) 또는 `MANAGER_PASSWORD` env 중 하나 이상 설정(또는 needs_setup 모드).

## 2. 인터랙션 흐름 (Happy Path)

| # | 사람의 행동 | 시스템의 정확한 반응 | 화면/상태 변화 |
|---|---|---|---|
| 1 | 비인증 상태로 `/admin/`에 접근 | 302 → `/admin/login?next=/admin/` | 로그인 폼 표시 |
| 2 | 올바른 비밀번호 입력 + 제출 | AuthService.verify 검증 성공 → `session['admin_authed']=True` → 302 next URL | 대시보드로 이동 |
| 3 | 대시보드 탐색 | login_required 통과, 200 + 대시보드 HTML | 대시보드 표시 |
| 4 | 로그아웃 클릭 | POST /admin/logout → `session['admin_authed']` 제거 → 302 로그인 | 로그인 폼으로 이동 |
| 5 | 로그아웃 후 `/admin/` 재접근 | login_required → 302 → `/admin/login?next=/admin/` | 다시 로그인 요구 |

## 3. 화면/상태 목업 (ASCII)

```text
┌─ GET /admin/login ──────────────────────────┐
│  관리자 로그인                               │
│  비밀번호: [__________________]             │
│  <input hidden name=csrf_token value=...>   │
│                          [ 로그인 ]         │
└─────────────────────────────────────────────┘

┌─ needs_setup 모드 ──────────────────────────┐
│  관리자 초기 설정                            │
│  새 비밀번호 (8자 이상): [______________]   │
│  비밀번호 확인:          [______________]   │
│  <input hidden name=csrf_token>             │
│                          [ 설정 완료 ]      │
└─────────────────────────────────────────────┘
```

## 4. 입력 사양

| 입력 | 형식/제약 | 필수 | 기본값 | 검증 시점 |
|---|---|---|---|---|
| `password` | 평문 문자열 | Y (일반 모드) | — | server (AuthService.verify) |
| `new_password` / `confirm_password` | ≥8자 일치 | Y (setup 모드) | — | server |
| `csrf_token` | 세션 토큰과 일치 | Y | — | server (before_request, 불일치 400) |
| `next` (GET param) | 단일 슬래시로 시작하는 경로 | N | `/admin/` | server (open-redirect 방지) |

## 5. 피드백 규약

- **로그인 실패:** flash "비밀번호가 올바르지 않습니다." + 401 폼 재표시.
- **lockout:** 5회 연속 실패 후 10초간 423 응답.
- **setup 모드:** 비밀번호 미설정 시 설정 폼 자동 노출(현재 비밀번호 칸 없음).
- **성공:** 302 → 원래 next URL 또는 대시보드.
- **로그아웃 성공:** 302 → 로그인 폼.

## 6. 분기 (성공/실패/엣지)

| 조건 | 시스템 반응 | 사용자에게 보이는 것 |
|---|---|---|
| 비인증 접근 | 302 `/admin/login?next=...` | 로그인 폼 |
| 올바른 비밀번호 | session 발급, 302 next | 대시보드 |
| 틀린 비밀번호 | 401 + flash 오류 | 오류 메시지 |
| 5회 연속 실패 | 423 Locked | 일시 차단 |
| CSRF 토큰 누락/불일치 | 400 | 요청 거부 |
| needs_setup | setup 폼 | 비밀번호 강제 설정 |

## 7. 접근성·키보드

- 비밀번호 입력 → Enter → 제출 가능.
- `<label for>` 연결, `autocomplete="current-password"`.

## 8. 자동 갱신/실시간

해당 없음. 로그인 폼은 정적.

## 9. Acceptance (W10 AC 재인용)

- [ ] AC-1: 비로그인 `/admin/` → 302 `/admin/login?next=/admin/` (검증: `tests/web/test_admin_auth_flow.py::test_redirect`)
- [ ] AC-2: 로그인 후 `/admin/` 200, 로그아웃 후 재차단 302 (검증: `tests/web/test_admin_auth_flow.py::test_login_logout`)
- [ ] AC-3: 5회 오답 후 6번째 423/429 (검증: `tests/web/test_admin_auth_flow.py::test_lockout_after_5_fails`)

## 10. 관련 touch point / feature

- feature: F04
- 인접 TP: [[TP-012]] (비밀번호 변경 — 로그인 후 접근), [[TP-008]] (데이터 브라우저 — 로그인 후 접근)
