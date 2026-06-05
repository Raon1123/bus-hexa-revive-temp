---
phase: P4
scope: "W10,W12,CSRF,set_initial"
verdict: PASS
auditor: sonnet
date: 2026-06-02
---

# Execution Audit — P4 Chunk 3b (W10 admin login/dashboard/logout/password + W12 data browser/CSV + CSRF infra + AuthService.set_initial)

## TARGET
P4 / W10, W12, EC-11(CSRF), set_initial (F04 §4.4 Designer 추가)

## VERDICT
**PASS**

---

## CHECKLIST_RESULTS

- **AC W10-1**: PASS (`test_redirect` PASS — 비로그인 `/admin/` → 302, Location에 `/admin/login`과 `next=/admin/` 모두 포함 확인: `admin.py:71`, `tests/web/test_admin_auth_flow.py::test_redirect`)
- **AC W10-2**: PASS (`test_login_logout` PASS — 올바른 비밀번호로 로그인 후 대시보드 200, 로그아웃 후 `/admin/` 재접근 302 차단 확인)
- **lockout 5회→6번째 423**: PASS (`test_lockout_after_5_fails` PASS — `admin.py:120-122`, `locked_until: float|None` 구조. 상세는 PASS_NOTES 참조)
- **비번변경 현재 비번 불일치 422 (D8)**: PASS (`test_password_change_current_invalid` PASS — `/admin/password` POST current_invalid → 422, `error-current` 마커 포함)
- **setup 모드 set_initial 성공**: PASS (`test_setup_mode_sets_password` PASS — needs_setup 상태에서 setup 폼 POST → PBKDF2 저장 + 로그인 성공)
- **EC-11/S5 CSRF — 토큰 없는 POST → 400**: PASS (`test_csrf_missing_token_rejected` PASS — `app.py:69-83` `before_request` `/admin/` POST에서 토큰 부재 시 abort(400))
- **EC-11/S5 CSRF — 올바른 토큰 → 통과**: PASS (`test_csrf_correct_token_passes` PASS — 세션 토큰과 form 토큰 일치 시 400/403 아님)
- **EC-11/S5 CSRF — 틀린 토큰 → 400**: PASS (`test_csrf_wrong_token_rejected` PASS — 세션 토큰 불일치 시 400)
- **EC-11/S5 CSRF — 비-admin GET 무영향**: PASS (`test_non_admin_get_unaffected` PASS — `GET /board` 400/403 아님)
- **AC W12-1 필터 count 일치**: PASS (`test_filter_count` PASS — 시드 3건, `repo.count()` 독립 oracle 3건, HTML `총 3건` 일치)
- **AC W12-2 CSV BOM**: PASS (`test_csv_bom` PASS — `resp.data[:3] == b"\xef\xbb\xbf"`, `repo.py:174` `yield b"\xef\xbb\xbf"`)
- **W12 bad day 400**: PASS (`test_bad_day_400` PASS — `/admin/data?day=abc` → 400, `/admin/data.csv?day=abc` → 400)
- **set_initial needs_setup → 성공+0600**: PASS (`test_set_initial_when_needs_setup` PASS — `auth.py:163-177`, PBKDF2 저장, 권한 0600)
- **set_initial already_set → 거부**: PASS (`test_set_initial_refuses_when_already_set` PASS — `auth.py:163-164` `if not self.needs_setup: return Result.error("already_set")`, 파일 불변 확인)
- **set_initial too_short → 거부**: PASS (`test_set_initial_too_short` PASS — 5자 입력 → `error('too_short')`, 파일 미생성)
- **E-1 모든 AC PASS**: PASS (위 15개 항목 전부 PASS)
- **E-2 산출물 파일 존재**: PASS (`bushexa/web/routes/admin.py`, `bushexa/services/auth.py`, `bushexa/web/app.py`, `bushexa/web/templates/admin/{login,dashboard,password,data_browser}.html` 전부 존재)
- **E-3 ImportError 없음**: PASS (`uv run python -c "from bushexa.web.app import create_app"` → OK; `from bushexa.services.auth import AuthService` → OK; `from bushexa.web.routes.admin import bp` → OK)
- **E-4 전체 pytest 0 fail**: PASS (`uv run pytest -q` → 185 passed, 0 fail, 0 error)
- **E-5 시크릿 하드코딩 0**: PASS (상세는 PASS_NOTES 참조)
- **E-6 TODO/FIXME 없음**: PASS (3개 신규 파일에서 grep 결과 없음)
- **E-7 시그니처 일치**: PASS (상세 검증 아래 기술)
- **E-10 PM-005 부검 + 회귀**: PASS (`docs/refactor/postmortems/PM-005-admin-lockout-until-ts-zero.md` 존재, 재발방지 `test_lockout_after_5_fails` 통과)
- **E-12 TP status implemented**: PASS (TP-007/TP-008/TP-012 status: `implemented`, 구현 일치)
- **EC-7 no streamlit**: PASS (`grep -rn 'streamlit' bushexa/web/` → 결과 없음)
- **S2 모든 /admin/* login_required**: PASS (logout/dashboard/password_form/password_change/data_browser/data_csv 전부 `@login_required` 장식, 로그인 폼은 의도적 exempt)

---

## COMMAND_OUTPUTS

- `$ uv run pytest tests/web/test_admin_auth_flow.py tests/web/test_csrf.py tests/web/test_admin_data_browser.py tests/services/test_auth.py -v`
  ```
  collected 24 items

  tests/web/test_admin_auth_flow.py::test_redirect PASSED
  tests/web/test_admin_auth_flow.py::test_login_logout PASSED
  tests/web/test_admin_auth_flow.py::test_lockout_after_5_fails PASSED
  tests/web/test_admin_auth_flow.py::test_password_change_current_invalid PASSED
  tests/web/test_admin_auth_flow.py::test_setup_mode_sets_password PASSED
  tests/web/test_csrf.py::test_csrf_missing_token_rejected PASSED
  tests/web/test_csrf.py::test_csrf_correct_token_passes PASSED
  tests/web/test_csrf.py::test_csrf_wrong_token_rejected PASSED
  tests/web/test_csrf.py::test_non_admin_get_unaffected PASSED
  tests/web/test_admin_data_browser.py::test_filter_count PASSED
  tests/web/test_admin_data_browser.py::test_csv_bom PASSED
  tests/web/test_admin_data_browser.py::test_bad_day_400 PASSED
  tests/services/test_auth.py::test_verify_pbkdf2 PASSED
  tests/services/test_auth.py::test_change_requires_current PASSED
  tests/services/test_auth.py::test_legacy_plain_migrates PASSED
  tests/services/test_auth.py::test_needs_setup PASSED
  tests/services/test_auth.py::test_needs_setup_false_when_file_exists PASSED
  tests/services/test_auth.py::test_needs_setup_false_with_env PASSED
  tests/services/test_auth.py::test_verify_env_password PASSED
  tests/services/test_auth.py::test_change_too_short PASSED
  tests/services/test_auth.py::test_change_sets_0600_permissions PASSED
  tests/services/test_auth.py::test_set_initial_when_needs_setup PASSED
  tests/services/test_auth.py::test_set_initial_refuses_when_already_set PASSED
  tests/services/test_auth.py::test_set_initial_too_short PASSED

  24 passed in 4.45s
  ```

- `$ uv run pytest -q`
  ```
  185 passed in 8.17s
  ```
  기존 170개 + 신규 15개 = 185개. 0 fail / 0 error. 기존 테스트 회귀 없음.

- `$ grep -rn 'streamlit' bushexa/web/`
  (출력 없음 — 0건)

- `$ grep -rn 'datetime.now\|datetime.today' bushexa/web/`
  (출력 없음 — 0건)

- `$ grep -rn '_hash_password' bushexa/web/`
  (출력 없음 — 0건, setup 분기가 `auth.set_initial`을 호출함 확인: `admin.py:164`)

- `$ grep -rn 'secret_key\s*=\s*' bushexa/`
  → `bushexa/web/app.py:39: app.secret_key = config.session_secret  # S7: from config, never hardcoded`
  (구성값에서 주입, 하드코딩 없음)

---

## TEST_CASE_EXPLANATIONS
*(Chunk 3b가 추가·변경한 15개 신규 테스트 케이스)*

### W10 admin auth flow (5개)

- **test_admin_auth_flow.py::test_redirect**: 비로그인 상태에서 GET `/admin/`을 요청하면, `login_required` 데코레이터가 302를 반환하고 Location 헤더에 `/admin/login`과 `next=/admin/`이 동시에 포함되는지 검증한다. 독립 출처: F04 §7 AC-A1, W10 AC-1. 기대값은 spec 명시 경로이므로 tautology 아님.

- **test_admin_auth_flow.py::test_login_logout**: 올바른 비밀번호(legacy 평문 파일에 직접 기록한 알려진 값)로 POST `/admin/login` → 세션 발급 → GET `/admin/` 200(dashboard 마커 존재) → POST `/admin/logout` → GET `/admin/` 302 재차단 흐름 전체를 검증한다. 독립 출처: F04 §7 AC-A1/A2, W10 AC-2.

- **test_admin_auth_flow.py::test_lockout_after_5_fails**: 틀린 비밀번호로 5회 연속 POST 후 6번째 시도가 423(또는 429)으로 차단되는지 검증한다. 1~5번째 각 시도는 401/423/429 중 하나를 허용(spec "5회 실패 후 차단"에서 5번째 이미 423일 수 있음). 6번째는 반드시 423/429. 독립 출처: F04 §7 AC-A2, W10 spec "5회 실패 후 lockout". PM-005 회귀 테스트.

- **test_admin_auth_flow.py::test_password_change_current_invalid**: 로그인 세션 + CSRF 토큰 주입 상태에서 현재 비밀번호를 틀리게 입력해 POST `/admin/password`하면 422 + HTML에 `current_invalid` 오류 마커(`id="error-current"`)가 포함되는지 검증한다. D8 봉인(세션 탈취 시 무단 변경 불가) 회귀. 독립 출처: TP-012 AC-1, F04 D8.

- **test_admin_auth_flow.py::test_setup_mode_sets_password**: 비밀번호 파일과 env가 모두 없는 needs_setup 상태에서 setup 폼 POST(new_password + confirm_password + csrf_token) → `AuthService.set_initial` 경유 → PBKDF2 포맷(`pbkdf2_sha256$` prefix) 파일 생성 → 동일 비밀번호로 새 클라이언트 로그인 성공 → 대시보드 200 접근까지 전체 흐름을 검증한다. 독립 출처: F04 §4.4 set_initial, W10 지시사항 #3.

### CSRF infra (4개)

- **test_csrf.py::test_csrf_missing_token_rejected**: admin POST(`/admin/login`)에 form body에 `csrf_token`을 포함하지 않으면 400/403으로 거부되는지 검증한다. `before_request._csrf_protect`가 `/admin/` POST에서 form/헤더 토큰 부재를 400으로 차단함을 확인. 독립 출처: P4-web §11 S5 spec "토큰 없으면 거부", EC-11.

- **test_csrf.py::test_csrf_correct_token_passes**: 세션에 주입한 토큰과 동일한 값을 form body에 포함하면 CSRF 거부(400/403)가 발생하지 않고 로그인 로직까지 진행되는지 검증한다. 독립 출처: S5 spec "올바른 토큰 포함 시 통과".

- **test_csrf.py::test_csrf_wrong_token_rejected**: 세션 토큰과 다른 값을 form body에 넣어 POST하면 400/403으로 거부되는지 검증한다. 독립 출처: S5 spec "토큰 불일치 시 거부".

- **test_csrf.py::test_non_admin_get_unaffected**: GET `/board` 같은 비-admin, 비-POST 요청은 CSRF 토큰 없이도 400/403이 아닌 정상 응답(또는 도메인 미목업에 의한 500)이 반환되는지 검증한다. CSRF 적용 범위가 admin POST로 한정됨을 확인. 독립 출처: S5 spec — GET 면제, 비-admin 라우트 면제.

### W12 data browser / CSV (3개)

- **test_admin_data_browser.py::test_filter_count**: 4건(같은 날짜 3건 + 다른 날짜 1건)을 시드한 DB에서 `route_id=195000177&day=20260601`으로 필터링 후 HTML의 `id="total-count"` 엘리먼트가 `repo.count(route_id=..., day=...)`의 독립 오라클 값(3건)과 일치하는지 검증한다. 독립 출처: W12 AC-1, 시드에서 직접 센 3건.

- **test_admin_data_browser.py::test_csv_bom**: 동일 필터로 GET `/admin/data.csv` 응답 본문의 첫 3바이트가 `b"\xef\xbb\xbf"`(UTF-8 BOM)인지 검증한다. BOM 값은 Unicode 표준(U+FEFF, UTF-8 인코딩 EF BB BF)에서 독립적으로 정의된 상수로, 구현 출력을 베낀 것이 아님. 독립 출처: W12 AC-2, F04 §7 AC-D3.

- **test_admin_data_browser.py::test_bad_day_400**: `/admin/data?day=abc`(잘못된 YYYYMMDD 형식)에 대해 400이 반환되는지, 그리고 CSV 엔드포인트 `/admin/data.csv?day=abc`도 동일하게 400인지 검증한다. 독립 출처: W12 spec "잘못된 day 형식은 400", F04 §7 AC-D5.

### set_initial (3개)

- **test_auth.py::test_set_initial_when_needs_setup**: 파일 미존재(needs_setup=True) 상태에서 `set_initial("new-initial-pw-123")`을 호출하면 Result.ok()가 반환되고, 파일이 `pbkdf2_sha256$` 포맷으로 생성되며, 권한이 0600이고, 동일 비밀번호로 `verify()`가 True를 반환하는지 검증한다. 독립 출처: F04 §4.4 set_initial 계약, 표준 hashlib prefix.

- **test_auth.py::test_set_initial_refuses_when_already_set**: 이미 PBKDF2 파일이 존재(needs_setup=False)할 때 `set_initial("attacker-new-pw-123")`을 호출하면 `error('already_set')`가 반환되고, 파일 내용이 변하지 않으며, 기존 비밀번호가 여전히 유효한지 검증한다. 인증 없는 비밀번호 재설정 방지(방어심층 S1/S2). 독립 출처: F04 §4.4 "★보안: 이미 비밀번호가 존재하면 error('already_set')로 거부".

- **test_auth.py::test_set_initial_too_short**: needs_setup 상태에서 8자 미만 비밀번호("short", 5자)로 `set_initial`을 호출하면 `error('too_short')`가 반환되고 비밀번호 파일이 생성되지 않는지 검증한다. 독립 출처: F04 §4.4 "too_short".

---

## E-7 시그니처 검증

**F04 §4.2 라우트 시그니처 대조:**
- `login_required(view)` 데코레이터: `admin.py:65` ✓
- `@bp.get("/login")` → `login_form()`: `admin.py:142-145` ✓
- `@bp.post("/login")` → `login_submit()`: `admin.py:148-194` ✓
- `@bp.post("/logout") @login_required` → `logout()`: `admin.py:197-201` ✓
- `@bp.get("/") @login_required` → `dashboard()`: `admin.py:204-207` ✓
- `@bp.get("/data") @login_required` → `data_browser()`: `admin.py:262-306` ✓
- `@bp.get("/data.csv") @login_required` → `data_csv()`: `admin.py:309-340` ✓
- `@bp.get("/password") @login_required` → `password_form()`: `admin.py:210-213` ✓
- `@bp.post("/password") @login_required` → `password_change()`: `admin.py:216-237` ✓

**F04 §4.4 AuthService.set_initial 시그니처 대조:**
- 반환: `Result.ok | Result.error('already_set'|'too_short'|'io_error')` → `auth.py:150-177` ✓
- 이미 설정 시 거부: `if not self.needs_setup: return Result.error("already_set")` → `auth.py:163-164` ✓
- PBKDF2 atomic write + chmod 0600: `fileio.atomic_write_text` + `os.chmod(..., 0o600)` → `auth.py:169-172` ✓
- W10 setup 분기가 `auth.set_initial` 호출: `admin.py:164 result = auth.set_initial(new_pw)` ✓ (`_hash_password` 복제 없음)

---

## E-10 PM-005 검증

- 파일: `docs/refactor/postmortems/PM-005-admin-lockout-until-ts-zero.md` 존재 ✓
- Root Cause: `until_ts=0` sentinel이 `now_ts >= 0`(항상 True)로 평가되어 entry를 삭제 → 실패 카운터 리셋. `admin.py:86-100`에서 `locked_until: float | None` 구조로 수정 ✓
- 재발방지 회귀테스트: `test_lockout_after_5_fails` 실행 PASS ✓
- PM `auditor_status: pending` → 이번 감리로 확인 완료(아래 PASS_NOTES 참조)

---

## E-12 Touch Point 검증

- **TP-007** (admin login/logout): `status: implemented` ✓, 인터랙션 흐름(302→로그인→대시보드→로그아웃→302), CSRF 폼 숨김 필드, lockout, setup 모드 모두 구현과 일치
- **TP-008** (data browser): `status: implemented` ✓, `/admin/data`(필터·페이지네이션), `/admin/data.csv`(BOM), day 형식 오류 400, `id="total-count"`, `id="no-rows"`, `nav id="pagination"` 모두 `data_browser.html`에서 확인
- **TP-012** (password): `status: implemented` ✓, `id="error-current"`, `error='too_short'`, `error='new_mismatch'`, `error='io_error'` 모두 `password.html:22-29`에서 확인

---

## FAIL_REASONS_FOR_DESIGNER
(해당 없음 — 모든 AC PASS)

---

## PASS_NOTES

1. **PM-005 완결**: `auditor_status: pending` → 이번 감리에서 Root Cause(`until_ts=0` sentinel), 구현 수정(`locked_until: float | None`), 회귀테스트(`test_lockout_after_5_fails`) 통과 모두 확인. PM-005를 `auditor_status: pass`로 업데이트 권고(Executor 작업).

2. **lockout 5번째 시도 동작**: `admin.py:120-124`에서 `_record_fail`이 `fails >= _MAX_FAILS(5)` 시점에 즉시 `locked_until` 설정 후 호출 측에서 `if fails >= _MAX_FAILS: abort(423)`을 수행하므로, 5번째 오답 시도에서 이미 423이 반환된다. spec "5회 실패 후 차단"의 보안 속성은 충족되고, `test_lockout_after_5_fails`가 1~5번째에 401/423/429를 모두 허용하므로 AC 위반 없음. 단, PM-005 §5와 P-11 서술("6번째 시도가 423")과 미세한 의미 차이가 있으므로 문서 차원 정합성 개선 권고 수준.

3. **E-13 출처 분류 (executor-added 보강 테스트)**:
   - `test_password_change_current_invalid`: TP-012 AC-1/D8에서 추적 가능한 spec 기반이나 P-11 명시 이름은 없음 → executor-added 보강. spec AC(`test_lockout_after_5_fails` 외에 password change D8) 대체 없음.
   - `test_setup_mode_sets_password`: W10 지시사항 #3(setup 모드 폼) + F04 §4.4에서 추적 가능. P-11 명시 이름 없음 → executor-added 보강.
   - `test_csrf_wrong_token_rejected`, `test_non_admin_get_unaffected`: §11 S5 "토큰 없으면 거부/올바른 토큰 통과" 범위 보강. P-11 명시 이름은 `test_csrf.py` 파일 존재만 기술됨 → executor-added 보강.
   - `test_set_initial_when_needs_setup`, `test_set_initial_refuses_when_already_set`, `test_set_initial_too_short`: F04 §4.4 Designer 계약에서 추적. P-11(`test_needs_setup` 1건만 있음) 미명시 → executor-added 보강.
   - `test_needs_setup_false_when_file_exists`, `test_needs_setup_false_with_env`, `test_verify_env_password`, `test_change_too_short`, `test_change_sets_0600_permissions`: W9 P-11 명시 4개 이외 추가 → executor-added 보강.
   - 위 모든 executor-added는 spec AC를 대체하지 않고 보강하며, tautological(구현 출력 복사) 기대값 없음 확인.

4. **E-5 상세**: `app.secret_key = config.session_secret` — 구성값 주입, 하드코딩 아님. 테스트 파일의 `_CORRECT_PW = "correcthorse"` 등은 테스트 전용 fixture(독립 알려진 값) — 운영 시크릿이 아니므로 E-5 위반 아님.

5. **CSV formula injection 미처리**: `repo.py:170-171` NOTE에 P5 보안 게이트에서 처리 예정 명시. 현 청크 범위 밖이며 P4 §10 S3에서도 P5 추적으로 위임되어 있어 이번 감리에서 FAIL 사유 아님. P5 진입 전 보안 게이트에서 확인 필요.

6. **`test_login_logout`의 302 follow**: Flask test_client 기본값은 redirects 미추적. 로그인 POST 후 `resp.status_code in (200, 302)` 허용 범위는 클라이언트가 follow_redirects 없이 302를 직접 수신하기 때문. 이후 `client.get("/admin/")` 200 검증은 세션 쿠키가 유지된 별도 요청이므로 정확한 검증.
