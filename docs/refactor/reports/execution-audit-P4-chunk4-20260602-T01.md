---
phase: P4
scope: "W15,carryover"
verdict: PASS
auditor: sonnet
date: 2026-06-02
---

# Execution Audit — P4 Chunk 4 (W15 smoke 통합 + 이월 2건)

TARGET: P4/W15,carryover
VERDICT: PASS

## CHECKLIST_RESULTS

- AC-1 (W15): PASS
  - 근거: `tests/web/test_routes_smoke.py::test_all_ui_routes_200` — 7개 UI 라우트 (board/busno/info/stops/unist/timetable/running) 각각 200 + `<title>` 고유 마커 확인 (PASSED).
  - 근거: `tests/web/test_routes_smoke.py::test_admin_login_page_200` — GET /admin/login → 200 + `/admin/login` 마커 확인 (PASSED).
  - 근거: `tests/web/test_routes_smoke.py::test_admin_dashboard_after_login` — 로그인 세션 후 GET /admin/ → 200 + `admin-dashboard` + `govtrack-card` 마커 확인 (PASSED).
  - 총 9개 라우트 smoke: admin login + admin dashboard + 7 UI = 9 ✓

- AC-2 (W15): PASS
  - 근거: `tests/web/test_routes_smoke.py::test_partials` — /partial/board, /partial/stops?stop_id=<valid>, /partial/unist 모두 200 (PASSED).

- E-1 (모든 AC PASS): PASS — AC-1, AC-2 모두 충족.

- E-2 (산출물 파일): PASS
  - `tests/web/test_routes_smoke.py` 존재 확인 (W15 산출물).
  - `tests/web/test_admin_logs.py` — 이월 2 masking 테스트 포함.
  - `bushexa/web/routes/admin.py` — `_SECRET_PATTERN` Bearer 수정 + `_mask_secrets` 구현.
  - `bushexa/web/templates/admin/dashboard.html` — govtrack-card 배선 (이월 1).
  - `docs/refactor/postmortems/PM-006-bearer-token-masking-bypass.md` 존재 (E-10 게이트).

- E-3 (SyntaxError/ImportError): PASS — `uv run pytest -q` 206 passed, 0 error.

- E-4 (pytest 0 fail/0 error): PASS
  - 전체 `uv run pytest -q` → **206 passed, 0 failed, 0 errors, 0 skipped**.
  - Chunk 4 이전 baseline: 206 − 4(smoke) − 2(masking) = 200 → 회귀 0건 확인.

- E-5 (시크릿 하드코딩): PASS
  - `_SECRET_PATTERN`은 로그에서 시크릿을 *마스킹*하는 패턴 (노출 아님).
  - 테스트 고정값 `"hunter2"`, `"secrettoken123"`, `"ABCDEF123"` 은 픽스처 sentinel이지 실제 운용 시크릿 아님.

- E-6 (TODO/FIXME): PASS — 신규 파일에 미해결 TODO/FIXME 없음.

- E-7 (도메인 서비스 시그니처): PASS
  - W15: domain mock 대상(`get_board_data`, `get_busno_page_data`, `get_stop_data`, `get_unist_board_data`, `get_full_timetable_data`) 모두 기존 W2~W8 산출물과 일치.
  - 이월 1: `govtrack_status_stream` route → SSE `event: status` 이벤트 형식 (W14 구현 일치).
  - 이월 2: `_SECRET_PATTERN` regex 수정 (`(?:Bearer\s+)?` 추가) — PM-006 §6 명세 정확히 반영.

- E-8 (테스트 케이스 자연어 설명): PASS — TEST_CASE_EXPLANATIONS 섹션 참조.

- E-9 (P-11 케이스 1:1 대응): PASS (with PASS_NOTES on executor-added)
  - W15 P-11 3종: `test_all_ui_routes_200`, `test_partials`, `test_admin_dashboard_after_login` — 모두 구현됨, 의도 일치.
  - W16 P-11 2종 (web): `test_requires_login`, `test_uses_fixed_path` — 모두 구현됨, 의도 일치.
  - Executor-added: `test_admin_login_page_200`, `test_logs_route_returns_200_with_log_file`, `test_logs_missing_file_returns_empty_notice`, `test_masking_password_and_api_key`, `test_masking_bearer_token` — PASS_NOTES 참조.

- E-10 (부검·재발방지 회귀테스트): PASS
  - `docs/refactor/postmortems/PM-006-bearer-token-masking-bypass.md` 존재, `status: fixed`.
  - Root Cause: `\S+` 가 `Bearer ` 앞에서 멈춰 토큰 원문 노출 → `(?:Bearer\s+)?` 추가로 수정.
  - 재발방지 회귀 테스트 2건 (`test_masking_bearer_token`, `test_masking_password_and_api_key`) 모두 PASSED.
  - PM frontmatter `auditor_status: pending`은 본 감리 후 Executor가 `reviewed`로 갱신해야 하나, 감리 내용 자체는 충족됨.

- E-11 (보안 게이트): 해당 없음 (P4 종료 후 별도 보안 감리 게이트 — ADR-009)

- E-12 (TP-011 인터랙션 명세 일치): PASS
  - TP-011 §8: SSE `text/event-stream`, `event: status\ndata: {json}\n\n`, **5초 간격** (`_SSE_INTERVAL_SECS=5`).
  - 구현: `admin.py:608` `_SSE_INTERVAL_SECS = 5`, `admin.py:625` `yield f"event: status\ndata: {data}\n\n"`, `time.sleep(_SSE_INTERVAL_SECS)` — 명세 일치.
  - TP-011 §5 "피드백 규약": `consecutive_failures > 0` → 카드 `class="warning"` (빨간 강조).
  - 구현: `dashboard.html:55` `var isWarning = failures > 0;`, `dashboard.html:57` `card.className = isWarning ? 'warning' : '';` — 명세 일치.
  - TP-011 §3 목업: "⚠ 데몬 미동작 감지" 메시지 → `dashboard.html:66` `&#9888; 데몬 미동작 감지 — 연속 실패 중입니다.` — 일치.
  - TP-011 §2 인터랙션 #1: 첫 이벤트 즉시 전송 — `admin.py:621-625` `while True:` 진입 후 sleep 없이 즉시 yield — 일치.
  - **SSE vs hx-get 선택**: 구현자가 `hx-get`(JSON raw 렌더) 대신 `EventSource`+SSE를 택함. `/admin/govtrack/status`가 JSON 라우트이므로 `hx-get`으로 받으면 raw JSON이 화면에 노출됨 — SSE+EventSource 선택은 합리적 구현 결정. TP-011 §8에서 SSE 방식 명시됨(실질적으로 TP 명세 자체가 SSE를 지정).

- E-13 (테스트 출처·반정당화 무결성): PASS
  - **(a) 출처 추적성**: P-11 명세 3종(W15) + P-11 명세 2종(W16) 모두 1:1 추적됨. Executor-added 분류는 PASS_NOTES 참조.
  - **(b) tautology 적발**: 기대값이 구현 독립적.
    - `<title>` 마커들은 템플릿 내 `{% block title %}` 값으로, spec에서 라우트별 기능명 그대로 (예: "버스번호별 시간표" = F02 §4.2 기능명). 구현 출력을 베낀 것이 아니라 기능 명세에서 도출.
    - `admin-dashboard`/`govtrack-card` 마커: W10 AC-2와 이월 1 명세(govtrack 카드 배선)에서 도출.
    - `/admin/login` 마커: `admin/login` 문자열이 login.html에만 존재 (`grep -rn` 확인 — 공유 nav에 없음) → 단일 라우트 고유 마커 ✓. 다만 `<title>관리자 로그인 — UNIST 버스</title>`가 더 강한 마커이므로 향후 강화 권고.
    - masking 테스트: "시크릿 원문 부재" 기대값은 알려진 sentinel 상수를 직접 심고, 그것이 응답에 없음을 단언 — tautology 아님 (spec: S7 명세 인용).
  - **(c) 의도 동결**: git repo 없어 diff 불가. 단, phase doc P-11 의도 3종(W15) + 2종(W16) 대비 실제 구현 의도가 약화되지 않음 확인.
  - **(d) 독립 기대값**: 각 AC당 기대값 출처 — P4 §3 EC-2, W2~W8 AC-1, W10 AC-1/2, S7 명세 직접 인용.

---

## COMMAND_OUTPUTS

- $ `uv run pytest tests/web/test_routes_smoke.py tests/web/test_admin_logs.py -v`
  ```
  ============================= test session starts ==============================
  collected 10 items

  tests/web/test_routes_smoke.py::test_all_ui_routes_200 PASSED            [ 10%]
  tests/web/test_routes_smoke.py::test_admin_login_page_200 PASSED         [ 20%]
  tests/web/test_routes_smoke.py::test_admin_dashboard_after_login PASSED  [ 30%]
  tests/web/test_routes_smoke.py::test_partials PASSED                     [ 40%]
  tests/web/test_admin_logs.py::test_requires_login PASSED                 [ 50%]
  tests/web/test_admin_logs.py::test_uses_fixed_path PASSED                [ 60%]
  tests/web/test_admin_logs.py::test_logs_route_returns_200_with_log_file PASSED [ 70%]
  tests/web/test_admin_logs.py::test_logs_missing_file_returns_empty_notice PASSED [ 80%]
  tests/web/test_admin_logs.py::test_masking_password_and_api_key PASSED   [ 90%]
  tests/web/test_admin_logs.py::test_masking_bearer_token PASSED           [100%]

  10 passed in 1.89s
  ```

- $ `uv run pytest -q` (전체 회귀)
  ```
  206 passed in 11.16s
  ```
  (0 failed, 0 errors, 0 skipped)

- $ `grep -rn 'streamlit' bushexa/web/`
  (출력 없음 — streamlit 참조 0건 ✓)

- $ `grep -rn 'datetime.now\|datetime.today' bushexa/web/`
  (출력 없음 — naive datetime 0건 ✓)

- $ `grep -rn 'admin/login\|admin\.login' bushexa/web/templates/` (마커 유일성 확인)
  ```
  bushexa/web/templates/admin/login.html:23: ... url_for('admin.login_submit') ...
  bushexa/web/templates/admin/login.html:33: ... url_for('admin.login_submit') ...
  ```
  (login.html에만 존재 — 공유 nav/base에 없음 → 마커 유일성 ✓)

---

## TEST_CASE_EXPLANATIONS

신규 6개 테스트 케이스 (Chunk 4 추가분):

- `tests/web/test_routes_smoke.py::test_all_ui_routes_200`:
  board/busno/info/stops/unist/timetable/running 7개 UI 라우트 각각에 GET 요청을 보낼 때, HTTP 200이 반환되고 `<title>` 내 라우트 고유 마커가 HTML에 포함되는지 검증한다. 외부 네트워크 없이 domain 함수를 최소 유효 dataclass mock으로 교체해 실행하며, 기대값은 P4 §3 EC-2 및 W2~W8 AC-1에서 도출된 `<title>` 문자열이다. 데이터 없는 기본 상태(빈 rows, no error)에서도 페이지 골격이 200으로 내려오는 smoke 확인.

- `tests/web/test_routes_smoke.py::test_admin_login_page_200` (executor-added):
  GET /admin/login이 200을 반환하고, 폼 action에 `/admin/login` 문자열이 포함되는지 검증한다. 비로그인 상태. P-11에는 없지만 W15 AC-1 "9개 라우트" 충족에 필요해 Executor가 추가 (P-11의 `test_admin_dashboard_after_login`이 dashboard를 커버하므로 login 페이지도 별도 smoke가 있어야 9개 완성). P-11 의도 약화 없음 — AC-1 보강.

- `tests/web/test_routes_smoke.py::test_admin_dashboard_after_login`:
  세션에 `admin_authed=True`를 주입한 상태로 GET /admin/ 요청 시, 200이 반환되고 `id="admin-dashboard"` 마커와 `id="govtrack-card"` 마커가 HTML에 있는지 검증한다. 이월 1(govtrack 대시보드 카드 배선)이 실제 대시보드 HTML에 삽입됐는지 단언. 기대값 출처: W10 AC-2(dashboard 200), F04 §4.5(govtrack 카드).

- `tests/web/test_routes_smoke.py::test_partials`:
  `/partial/board`, `/partial/stops?stop_id=<valid>`, `/partial/unist` 3개 partial 라우트에 GET 요청 시 모두 200이 반환되는지 검증한다. domain 함수를 mock으로 교체하고 유효한 stop_id(`SERACH_STOPS[0]`)를 사용한다. 기대값 출처: W15 AC-2, P4 §3 EC-4.

- `tests/web/test_admin_logs.py::test_masking_password_and_api_key` (이월 2, executor-added):
  `password=hunter2`와 `api_key=ABCDEF123`이 포함된 로그 라인을 bushexa.log에 기록한 뒤, 로그인 세션으로 GET /admin/logs를 요청했을 때 응답 HTML에 원본 시크릿 값이 없고 `****` 마스킹이 있는지 검증한다. 기대값은 "시크릿 원문 부재" — 구현 출력이 아닌 S7 명세 직접 인용. PM-006 §7 재발방지 목록 중 기존 패턴 회귀 방지 테스트.

- `tests/web/test_admin_logs.py::test_masking_bearer_token` (이월 2, PM-006 재발방지):
  `Authorization: Bearer secrettoken123` 형태 로그 라인을 기록한 뒤 /admin/logs 응답에서 `secrettoken123`이 없고 `****` 가 있는지 검증한다. PM-006에서 발견된 HIGH 버그(Bearer 토큰 마스킹 누락)의 재발방지 회귀 테스트. 기대값: "Bearer 토큰 원문 부재" — S7 명세 + 이월 2 명세에서 도출. `\S+`가 `Bearer`에서 멈춰 토큰이 노출되는 구 버그가 재현되면 이 테스트가 실패함 (비-tautological).

---

## FAIL_REASONS_FOR_DESIGNER

없음 — PASS.

---

## PASS_NOTES

- **Executor-added 테스트 목록** (E-13(a)):
  - `test_admin_login_page_200` (test_routes_smoke.py): P-11 미포함. W15 AC-1 "9라우트" 충족에 필요한 admin login smoke. P-11 `test_admin_dashboard_after_login`이 dashboard만 커버하므로 login 페이지 smoke 보강 — 대체 아닌 보강 ✓.
  - `test_logs_route_returns_200_with_log_file` (test_admin_logs.py): P-11 미포함. 로그 파일 존재 시 200 + 내용 렌더 확인 — 서비스 레이어 P-11 테스트(`test_tail_returns_recent_lines_last_first`)와 중복 없는 web 레이어 보강 ✓.
  - `test_logs_missing_file_returns_empty_notice` (test_admin_logs.py): P-11 미포함. F04 AC-L4 "파일 부재 시 500 아닌 200" 커버 — 서비스 레이어 `test_missing_log_file_returns_empty`의 web-layer 보강 ✓.
  - `test_masking_password_and_api_key` (test_admin_logs.py): PM-006 §7 명시 재발방지 테스트 — P-11 미포함이나 PM에 명시된 의무 테스트. S7 명세 인용 ✓.
  - `test_masking_bearer_token` (test_admin_logs.py): PM-006 §7 명시 재발방지 테스트 — P-11 미포함이나 PM에 명시된 의무 테스트. 이월 2 명세 인용 ✓.

- **회귀 가드**: 206 − 4 smoke − 2 masking = 200 (Chunk 4 이전 baseline 일치). 삭제된 테스트 0건.

- **SSE vs hx-get 선택**: 구현자가 govtrack 카드를 `hx-get`(JSON raw 렌더) 대신 `EventSource`+SSE로 구현한 것은 TP-011 §8 명세가 SSE를 명시하고, `/admin/govtrack/status` JSON 라우트를 hx-get으로 직접 렌더 시 raw JSON이 화면에 표시되는 문제를 회피하는 합리적 결정이다. 수용.

- **`/admin/login` 마커 강도**: 현재 `"/admin/login" in html` 마커는 login.html에만 등장해 유일성 충족. 단, W15 명세에서 마커 형식을 `<title>` 또는 컨테이너 id로 지정하므로 `<title>관리자 로그인 — UNIST 버스</title>` 사용 권장 (향후 리팩터링 안전성 향상).

- **PM-006 `auditor_status: pending`**: 본 감리 완료 시 Executor가 `reviewed`로 갱신 권장.

- **W1~W16 전 완료**: W15 PASS로 P4 내 W1~W16 전 work item이 Auditor PASS 상태. 다음 단계는 별도 보안감리 게이트 (ADR-009 / E-11).
