---
status: fixed
postmortem_id: PM-007
severity: medium
discovered: 2026-06-02
phase: P4 / 보안 감리
component: bushexa.web.routes.admin
related: [security-audit-P4-20260602-T01.md S1/OPEN-REDIRECT, W10, P4, tests/web/test_admin_auth_flow.py::test_login_next_rejects_open_redirect]
auditor_status: pending
---

# PM-007 — 관리자 로그인 next 파라미터 open-redirect (백슬래시 우회)

> 부검(postmortem)은 **비난이 아니라 재발 방지**를 위한 기록이다. 사람이 아니라 시스템·프로세스의 결함을 본다.

## 1. 요약 (3줄)

- **증상:** 로그인 성공 후 `?next=/\evil.com` 형태의 URL로 접근하면 응답 Location 헤더가 `/\evil.com`으로 설정되어 브라우저가 `http://evil.com`으로 이동한다.
- **근본 원인:** `next` 파라미터 가드가 `startswith("//")` 만 막고, 백슬래시(`/\`) 우회 및 절대 URL(`http://`, `https://`) 형태를 검증하지 않았다.
- **재발 방지:** `_safe_next()` 헬퍼가 제어문자 제거·백슬래시 거부·`urlparse` netloc/scheme 이중 검증을 통해 내부 상대경로만 허용하며, 회귀 테스트 `test_login_next_rejects_open_redirect`가 6종 악성 페이로드를 자동 검증한다.

## 2. 영향 (Impact)

- **영향 받은 기능**: 관리자 로그인 후 `next` 파라미터 redirect (W10, `login_submit()`).
- **영향 받은 사용자**: 관리자 계정 소지자 — 공격자가 조작한 로그인 URL로 유도된 경우.
- **공격 시나리오**: 공격자가 `https://bushexa-admin/admin/login?next=/\evil.com`을 관리자에게 전달 → 관리자가 올바른 비밀번호 입력 → 로그인 성공 직후 외부 도메인(`evil.com`)으로 이동 (피싱 보조).
- **지속 기간**: P4 구현 이후 — 정확한 시작 시점은 `login_submit()` 초기 구현 시점.
- **데이터 손실·오염**: 없음. 세션 탈취 아님; redirect 경로 조작만 가능.

## 3. 타임라인 (발견 경위)

- 2026-06-02: P4 보안 감리 (`security-audit-P4-20260602-T01.md`) 中 S1/OPEN-REDIRECT 항목으로 발견.
- 감리 도구: 코드 직접 열람 (`admin.py:208`) + 브라우저 정규화 지식 교차 적용.
- 핵심 재현 입력: `GET /admin/login?next=/\evil.com` → 올바른 비밀번호 POST → `Location: /\evil.com`.

## 4. 근본 원인 분석 (Root Cause)

**인과 사슬**:

1. `login_submit()` (admin.py:206~210)은 로그인 성공 후 `request.args.get("next", "")`를 읽는다.
2. 가드 조건: `next_url.startswith("/") and not next_url.startswith("//")`.
3. `/\evil.com`은 `"/"` 로 시작하고 `"//"` 로 시작하지 않으므로 가드를 **통과**한다.
4. 브라우저(Chrome, Firefox, Safari)는 HTTP `Location: /\evil.com` 헤더를 `//evil.com`으로 정규화하여 외부 도메인으로 이동시킨다.

**추가 미처리 케이스**:
- `http://evil.com`, `https://evil.com` — `"/"` 로 시작하지 않아 가드에서 걸리지만, 절대 URL 명시적 차단 없음.
- 탭·CR 등 제어문자 삽입 후 정규화: `/\t/evil.com` → 제거 후 `//evil.com`.

**왜 기존 테스트가 못 잡았는가**: 기존 `test_admin_auth_flow.py`에 `next` 파라미터 검증 케이스가 없었다. 또한 가드 조건 자체를 단독 테스트하는 유닛 테스트도 없었다.

**코드 위치**: `bushexa/web/routes/admin.py:208` (수정 전).

## 5. 재현 (Reproduction)

```python
# 수정 전 코드 재현
from bushexa.web.routes.admin import _safe_next  # 수정 전엔 이 함수 없음

# 수정 전 가드 로직 (인라인)
next_url = "/\\evil.com"
if next_url and next_url.startswith("/") and not next_url.startswith("//"):
    # → 이 분기 진입 → redirect("/\evil.com") 발생
    print("VULNERABLE: redirect to", next_url)
```

- **기대 동작**: `/admin/`(대시보드)로 redirect.
- **실제 동작(수정 전)**: `Location: /\evil.com` → 브라우저가 `http://evil.com`으로 이동.

## 6. 해결 (Resolution)

**수정 내용** (`bushexa/web/routes/admin.py`):

1. `urllib.parse.urlparse` import 추가 (line 29).
2. `_safe_next(next_url: str) -> str` 헬퍼 함수 추가 (lockout 헬퍼 섹션 다음):
   - 제어문자·공백 제거 (`re.sub(r"[\x00-\x1f\x7f\s]", "", next_url)`).
   - 단일 `"/"` 시작 여부 확인.
   - `"//"` 또는 `"/\\"` 시작 거부.
   - `"\\"` 문자 포함 거부.
   - `urlparse(cleaned).netloc == "" and scheme == ""` 이중 검증.
   - 위 조건 미충족 시 `"/admin/"` 반환.
3. `login_submit()` redirect 로직을 `redirect(_safe_next(next_url))`로 교체 (기존 인라인 if-else 제거).

**대안 검토**:
- 허용리스트 방식(known admin paths만 수락): 과도하게 제한적, 새 라우트 추가 시 유지보수 부담.
- `re.match(r'^/[^/\\\\]', next_url)` (감리 보고서 제안): 제어문자 우회를 막지 못함. 채택 않음.
- 선택한 방식: 다층 방어(제어문자 정리 → 시작문자 검사 → 백슬래시 검사 → urlparse 검증).

## 7. 재발 방지 (Prevention) — **필수**

- [x] **회귀 테스트**: `tests/web/test_admin_auth_flow.py::test_login_next_rejects_open_redirect` — 로그인 성공 후 `next` 파라미터에 외부 호스트·프로토콜 상대 URL·백슬래시 우회 등 6종 악성 페이로드를 주입했을 때 Location이 `/admin/`로 폴백하고 `evil.com`이 포함되지 않음을 단언하며, 정상 케이스(`/admin/timetable`)는 그대로 통과함도 검증한다.
- [x] **코드 가드**: `_safe_next()` 헬퍼가 모든 `next` 처리를 단일 진입점에서 검증 — `login_submit()` 외부에서도 재사용 가능.
- [ ] **프로세스**: 향후 redirect를 사용하는 신규 기능은 `_safe_next()` 패턴 또는 동등한 다층 검증을 적용할 것 (코드 리뷰 체크리스트 항목으로 추가 권고).

## 8. 교훈 (Lessons)

- **브라우저 정규화 우회**: HTTP `Location` 헤더의 `/\` 경로는 브라우저가 `//`로 정규화한다. 서버 측 문자열 검사만으로는 부족하며 `urlparse` + 명시적 백슬래시 검사를 병행해야 한다.
- **제어문자 삽입**: `/\t/evil.com` → tab 제거 후 `//evil.com`. 검증 전 정규화(제어문자 제거) 단계가 필수.
- **단층 가드의 한계**: `not startswith("//")` 같은 단일 조건 가드는 변형 입력에 취약. 다층 방어가 안전하다.
- **관련 결함**: PM-005 (lockout 가드 우회), PM-006 (마스킹 우회) — 모두 "단일 조건 가드"에 의존한 보안 결함. 동일 패턴.

## 9. 상태

- 수정 PR/커밋: (local, git 미등록 프로젝트)
- 회귀 테스트 통과 확인: ✅ `uv run pytest -q` → 207 passed, 0 failed, 0 errors
- Auditor 확인: pending
