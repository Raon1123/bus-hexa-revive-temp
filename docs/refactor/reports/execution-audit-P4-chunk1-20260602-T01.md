---
phase: P4
scope: W1,W2
verdict: PASS
auditor: sonnet
date: 2026-06-02
---

# Execution Audit — P4 Chunk 1 (W1 + W2)

```
TARGET: P4/W1,W2
VERDICT: PASS
```

---

## CHECKLIST_RESULTS

### W1 — app factory + base + static

- **AC-1** (root 200/302): PASS
  근거: `test_app_factory.py::test_root_ok` PASSED. `GET /` → 302 to `/board` (Location 헤더에 `/board` 포함). `app.py:65-67`의 `index()` 라우트가 `url_for("board.departure_board")`로 redirect.

- **AC-2** (HttpOnly·SameSite=Lax): PASS
  근거: `test_app_factory.py::test_cookie_flags` PASSED. `app.py:42-43`에서 `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE="Lax"` 정적 설정. `before_request`의 csrf_token 세션 쓰기로 첫 요청에서 Set-Cookie 발생, 쿠키에 `HttpOnly`·`SameSite=Lax` 포함 확인.

### W2 — board route + partial (F01, TP-001)

- **AC-1** (GET /board 200 + id="board-table" + hx-trigger="every 15s"): PASS
  근거: `test_board_route.py::test_board_ok` PASSED. `board.html:21-24`에 `id="board-table"`, `hx-get="/partial/board"`, `hx-trigger="every 15s"`, `hx-swap="innerHTML"` 전체 포함. TP-001 §2 §8 명세와 일치.

- **AC-2** (GET /partial/board 200 + <html> 없는 조각 + hx-trigger 메인에만): PASS
  근거: `test_board_route.py::test_partial_fragment` PASSED. `partial/board_table.html`는 `<html>/<head>/<body>` 미포함, `hx-trigger` 0건 확인(`grep -c 'hx-trigger' partial/board_table.html` → 0). partial은 `<table>` 태그 시작 순수 조각.

---

## COMMAND_OUTPUTS

- $ uv run pytest tests/web/test_app_factory.py tests/web/test_board_route.py -v
  ```
  tests/web/test_app_factory.py::test_root_ok PASSED                    [ 20%]
  tests/web/test_app_factory.py::test_cookie_flags PASSED               [ 40%]
  tests/web/test_board_route.py::test_board_ok PASSED                   [ 60%]
  tests/web/test_board_route.py::test_partial_fragment PASSED           [ 80%]
  tests/web/test_board_route.py::test_board_uses_domain PASSED          [100%]

  5 passed in 0.12s
  ```

- $ uv run pytest -q
  ```
  138 passed in 2.25s
  ```
  (138 = 133 기존 + 5 신규 W1/W2. failed=0, error=0, skip=0.)

- $ grep -rn 'streamlit' bushexa/web/
  (출력 없음 — EC-7 충족)

- $ grep -rn 'datetime.now\|datetime.today' bushexa/web/
  (출력 없음 — Clock 주입 규약 준수)

- $ grep -rni 'password\|secret_key' bushexa/web/
  ```
  bushexa/web/app.py:6:- Uses config.session_secret as SECRET_KEY (S7: no hardcoding).
  bushexa/web/app.py:39:    app.secret_key = config.session_secret   # S7: from config, never hardcoded
  ```
  (하드코딩 없음. config 주입 패턴 — E-5 충족)

- $ uv run --collect-only (선별)
  ```
  138 tests collected
  ```

---

## TEST_CASE_EXPLANATIONS

모든 케이스는 P4-web.md §5 W1/W2 **테스트 케이스(자연어 의도 — P-11)**에 1:1 대응한다.

### W1 테스트

- **test_app_factory.py::test_root_ok**
  - **무엇을:** `create_app(app_config_test)`로 생성한 Flask 앱의 `/` GET 라우트가 정상 응답하는지.
  - **입력·조건:** `app_config_test` fixture(테스트용 session_secret="test-session-secret", api_key="test-api-key"). `client.get("/")`
  - **통과 조건:** `status_code in (200, 302)`. 302일 경우 `Location` 헤더에 `/board` 포함.
  - **독립 출처:** P4 W1 AC-1 설계 명세("/ 는 200 또는 board로의 302"). 구현 출력을 베끼지 않음.

- **test_app_factory.py::test_cookie_flags**
  - **무엇을:** 세션 쿠키의 `HttpOnly`·`SameSite=Lax` 보안 플래그 존재 여부.
  - **입력·조건:** `before_request`에서 `session["csrf_token"]` 쓰기 → Set-Cookie 발생. `resp.headers["Set-Cookie"]`를 소문자 비교.
  - **통과 조건:** Set-Cookie 헤더가 있고, `httponly` + `samesite=lax` 포함.
  - **독립 출처:** P4 §10 S1 보안 명세("HttpOnly·SameSite=Lax"). 플래그 이름은 구현이 아닌 보안 스펙에서 도출. `before_request`의 csrf_token 쓰기는 "Set-Cookie를 발생시키기 위한 수단"이며, **검증 대상(플래그 값)** 자체는 spec에서 독립적으로 정해졌음 → tautology 아님.

### W2 테스트

- **test_board_route.py::test_board_ok**
  - **무엇을:** `GET /board`가 200이고, HTMX 자동갱신 컨테이너 속성이 TP-001 명세와 일치하는지.
  - **입력·조건:** `get_board_data`를 `_MOCK_SNAPSHOT`으로 patch. `client.get("/board")`.
  - **통과 조건:** `status_code==200`, HTML에 `id="board-table"` + `hx-trigger="every 15s"` 포함.
  - **독립 출처:** P4 W2 AC-1 + TP-001 §2 §8("every 15s"는 F01 규정값). 구현 출력 베끼기 없음.

- **test_board_route.py::test_partial_fragment**
  - **무엇을:** `GET /partial/board`가 전체 HTML 페이지가 아닌 순수 조각(fragment)만 반환하는지.
  - **입력·조건:** `get_board_data`를 `_MOCK_SNAPSHOT`으로 patch. `client.get("/partial/board")`.
  - **통과 조건:** `status_code==200`. 응답 HTML에 `<html` 없음, `hx-trigger` 없음(폴링 속성은 메인에만 있어야 함).
  - **독립 출처:** P4 W2 AC-2 + TP-001 §8("partial은 <html> 없는 행 조각만 반환"). 두 조건 모두 spec에서 도출.

- **test_board_route.py::test_board_uses_domain**
  - **무엇을:** mock 도메인이 반환한 알려진 행 데이터가 실제 렌더 HTML에 나타나는지(템플릿 바인딩 정확성).
  - **입력·조건:** 테스트 파일 내 수기 정의 `_KNOWN_ROW`(bus_number="713", arrival_time="09:15", present="구영리 출발"). `get_board_data`를 해당 snapshot으로 patch하고 `/board` GET.
  - **통과 조건:** 렌더된 HTML에 "713", "09:15", "구영리 출발" 포함.
  - **독립 출처:** `_KNOWN_ROW`는 구현 get_board_data를 실행해 얻은 값이 아닌, 테스트 작성자가 수기로 정의한 입력값 — E-13(d) 독립 기대값 요건 충족. tautology 없음.

---

## E-13 출처·반정당화 검증

### (a) 출처 추적성
모든 5개 테스트케이스가 P4-web.md §5 W1/W2 **P-11 자연어 의도**에 1:1 대응한다:
- `test_root_ok` ← W1 P-11 "test_root_ok" 의도
- `test_cookie_flags` ← W1 P-11 "test_cookie_flags" 의도
- `test_board_ok` ← W2 P-11 "test_board_ok" 의도
- `test_partial_fragment` ← W2 P-11 "test_partial_fragment" 의도
- `test_board_uses_domain` ← W2 P-11 "test_board_uses_domain" 의도

**executor-added 테스트 없음** — P-11에 없는 Executor 추가 테스트 0건.

### (b) tautology 적발
- W1: `test_cookie_flags`의 기대값("httponly", "samesite=lax")은 §10 S1 보안 명세에서 독립 도출. 구현 출력 베끼기 아님.
- W2: `test_board_ok`의 "every 15s"는 TP-001 §8 + F01 규정값. `test_board_uses_domain`의 기대 문자열은 수기 정의 `_KNOWN_ROW` 필드 — tautology 없음.

### (c) 의도 동결
P4-web.md §5의 W1/W2 테스트 의도가 수정·약화된 흔적 없음. 설계 문서 P-11 의도와 실제 구현이 일치.

### (d) 독립 기대값
각 AC당 1개 이상 기대값이 구현과 독립된 출처(설계 명세, TP-001, 수기 fixture)에서 도출됨 — 충족.

---

## E-12 TP-001 인터랙션 일치 검증

| TP-001 명세 | 구현 |
|---|---|
| `GET /board` 200 + 전체 페이지 | `board.py:40-44` routes.GET("/board") → render_template("board.html") ✓ |
| `<div id="board-table" hx-get="/partial/board" hx-trigger="every 15s" hx-swap="innerHTML">` | `board.html:21-24` 정확히 일치 ✓ |
| 첫 렌더: 서버 사이드 첫 페인트(빈 깜빡임 없음) | `board.html:25` `{% include "partial/board_table.html" %}` 포함 ✓ |
| `GET /partial/board` → 테이블 조각만, `<html>` 없음 | `board.py:47-51` → render_template("partial/board_table.html"). partial은 `<table>` 시작 — `<html>` 없음 ✓ |
| hx-trigger는 메인 `/board`에만 | `partial/board_table.html`에 `hx-trigger` 0건 ✓ |
| 외부 API 실패 → partial 200 유지 + error 필드 배너 | `board.html:9-13` error banner 구현 + domain `BoardSnapshot.error` 처리 ✓ |
| 데이터 없음 → "출발 정보 없음" 행 | `board_table.html:43-58` else 분기 ✓ |

**TP-001 명세 일치 100%.**

---

## E-7 도메인 시그니처 일치 검증

`bushexa/domain/board.py:119-125` 시그니처:
```python
def get_board_data(
    stop_id: str,
    clock: Clock,
    *,
    client,
    timetable_provider: Callable[[str, int, str], list[str]],
) -> BoardSnapshot:
```

`bushexa/web/routes/board.py:32-37` 호출:
```python
return get_board_data(
    _STOP_ID,     # str
    clock,        # KSTClock (Clock 구현체)
    client=client,
    timetable_provider=get_timetable,
)
```

위치 인수(stop_id, clock) + 키워드 전용(client, timetable_provider) — **정확히 일치.** E-7 PASS.

---

## 산출물 파일 존재 확인 (E-2)

### W1 명시 산출물
| 파일 | 존재 |
|---|---|
| `bushexa/web/app.py` | ✓ |
| `bushexa/web/templates/_base.html` | ✓ |
| `bushexa/web/static/style.css` | ✓ |
| `bushexa/web/static/vendor/htmx.min.js` | ✓ |
| `tests/web/test_app_factory.py` | ✓ |

### W2 명시 산출물
| 파일 | 존재 |
|---|---|
| `bushexa/web/routes/board.py` | ✓ |
| `bushexa/web/templates/board.html` | ✓ |
| `bushexa/web/templates/partial/board_table.html` | ✓ |
| `tests/web/test_board_route.py` | ✓ |

**모든 W1/W2 산출물 파일 존재 확인. E-2 PASS.**

---

## 구현자 자체 결정 2건 독립 판정

### (a) `before_request`에서 `session["csrf_token"]` seed

**판정: 수용 가능 (위반 아님)**

근거:
- P4-web.md §10 S5 "CSRF (★ 명시 결정)"에서 명시적으로 지정: `"create_app에서 stdlib 기반 토큰(세션에 secrets.token_urlsafe 저장 + 폼 hidden + POST 검증 데코레이터/before_request)을 구현하고"` — W1이 토큰 저장 책임을 포함한다는 것이 Designer 설계 문서에 이미 명시됨.
- W1/W2는 GET-only 라우트이므로 POST 검증(enforcement)은 올바르게 W10+으로 연기됨. 현재 구현은 "저장" 절반만 — 설계 의도와 정확히 일치.
- `test_cookie_flags` 테스트가 Set-Cookie를 보기 위해 세션 쓰기가 필요한 것은 구현상의 실제 종속성이며, 검증 대상 플래그 값(HttpOnly, SameSite=Lax)은 S1 spec에서 독립적으로 도출 — tautology 아님.
- **E-13 관점:** 이것은 테스트 기대값 조작이 아닌 구현 설계 결정이므로 E-13 범주 밖.
- **EC-11 관점:** W1 범위에서 POST 검증 없는 것은 EC-11(test_csrf.py)이 W10+에서 커버하므로 Chunk 1 단계에서 미달 아님.

### (b) `SESSION_COOKIE_SECURE=False` 정적

**판정: 수용 가능 (W1/W2 AC 범위 내 위반 아님, 비차단 주의사항 있음)**

근거:
- W1 AC-2의 검증 범위는 `HttpOnly` + `SameSite=Lax`에 한정. `Secure` 플래그는 W1 AC에 없음.
- `security-audit-criteria.md` S1 체크리스트: `"세션 쿠키 HttpOnly·SameSite·(가능 시) Secure"` — "(가능 시)"로 조건부 표현.
- P4-web.md §10 S1: `"Secure(if is_secure)"` — request.is_secure 기반 조건부 설정 의도.

**비차단 주의사항(P4 종료 E-11 보안 게이트 전달사항):** `app.py:49`의 `SESSION_COOKIE_SECURE=False` 정적 설정은 HTTPS 운영 환경에서도 Secure 플래그를 지원하지 않는다. 설계 명세의 `"if is_secure"` 의도는 Flask의 정적 config만으로는 per-request 분기가 불가능하므로, 운영 배포 시 환경 변수 또는 reverse-proxy를 통한 `SESSION_COOKIE_SECURE=True` 재지정이 필요하다. 현재 구현에는 env override 경로가 없음. **P4 종료 보안 감리(E-11 게이트) 시 `medium` 수준 검토 항목으로 전달.**

---

## E-3 Import 무결성

```
uv run python -c "from bushexa.web.app import create_app; print('OK')"  → OK
uv run python -c "from bushexa.web.routes.board import bp; print('OK')" → OK
```

SyntaxError/ImportError 없음. E-3 PASS.

---

## E-5 시크릿 하드코딩

- `grep -rni 'password\|secret_key' bushexa/web/` 결과: `app.py`에서 주석(S7 no hardcoding 언급) + `app.secret_key = config.session_secret` 동적 할당만.
- 실제 secret 값 하드코딩 0건. E-5 PASS.

---

## E-6 TODO/FIXME

W1/W2 신규 파일 전체(app.py, routes/board.py, templates/board.html, templates/partial/board_table.html, templates/_base.html, tests/web/test_app_factory.py, tests/web/test_board_route.py) — TODO/FIXME 0건. E-6 PASS.

---

## E-10 Postmortem

W1/W2 구현 중 에러 보고 없음. 기존 `postmortems/INDEX.md`에 P4 Chunk 1 관련 PM 등재 없음. 구현자가 에러를 별도 보고하지 않았으므로 PM 작성 불필요. E-10 조건(미기록 에러가 있으면 FAIL) — 해당 없음. PASS.

---

## E-11 보안 게이트

P4-web.md §3 EC-10/EC-11은 P4 전체 종료 시 별도 `security-audit-criteria.md` 기반 보안 감리로 커버. Chunk 1(W1/W2)은 GET-only 라우트이므로 admin POST·CSRF 검증 대상 아님. E-11 게이트는 P4 전 work item 완료 후 평가 — 현재 범위 밖. **비차단.**(단, SESSION_COOKIE_SECURE 주의사항 위 항목 참조)

---

## 회귀 검사 (E-4 / E-5 회귀 가드)

```
138 passed in 2.25s (failed=0, error=0, skip=0)
```

기존 133 테스트 전원 유지, 5건 신규 추가. 삭제된 테스트 없음(`--collect-only` 138건 확인). E-4 PASS.

---

## FAIL_REASONS_FOR_DESIGNER

없음.

---

## PASS_NOTES

- **executor-added 테스트 없음**: 5개 테스트 전원 P-11에 명시된 케이스와 1:1 대응.
- **TP-001 완전 준수**: `id="board-table"`, `hx-get`, `hx-trigger="every 15s"`, `hx-swap="innerHTML"` 전체 속성이 spec과 정확히 일치. partial은 `<table>`로 시작하는 순수 조각.
- **도메인 의존성 격리 우수**: `_build_snapshot()`이 네트워크 의존성(UlsanBisClient, KSTClock)을 한 곳에 집중시켜 테스트에서 `get_board_data`만 patch하면 충분 — 테스트 구조 건전.
- **S5 groundwork 포함**: csrf_token before_request seeding이 W10+ 강제적용을 위한 인프라를 이미 준비. 미리 구현한 것이 설계 의도(§10 S5)에 부합하며 회귀 위험 없음.
- **forward flag (비차단)**: `SESSION_COOKIE_SECURE=False` 정적 설정. P4 종료 보안 게이트(E-11)에서 운영 HTTPS 환경의 Secure 플래그 강제 경로 확인 권고.

---

**VERDICT: PASS**

FAIL 사유 없음 — Executor 재작업 불필요, Designer reopen 불필요.
