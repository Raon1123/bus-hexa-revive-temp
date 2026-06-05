---
status: done
phase_id: P4
designer: opus
auditor_status: execution-pass + security-gate-pass (2026-06-02) — W1~W16 7청크 전부 실행감리 PASS(207 tests); 보안게이트 security-audit-P4-20260602-T01 PASS(high/critical 0, deps 0취약). PM-005/006 verified, PM-007 fixed. 잔여 medium/low는 P5 W1에 등록.
last_updated: 2026-06-02
depends_on: [P2, P3]
---

# P4 — Web Layer (Flask routes + templates + admin)

## 1. 목적

`bushexa/web/`에 Flask app factory, blueprint 8개, Jinja2 템플릿, 정적 자원, HTMX 부분 갱신, 관리자 SSE를 구현한다. 종료 시 사용자 대면 기능이 모두 신규 스택으로 동작한다.

## 2. 시작 조건 (Entry Criteria)

- [x] P2 Auditor PASS (crawler & status reader 가용), P3 Auditor PASS (domain 가용) — P3 execution-audit-P3-20260602-T01 PASS
- [x] F01~F08 feature doc Auditor PASS (재제출분 포함) — F01/F06/F07 clean PASS(T01), F02/F03/F04/F05/F08 실질결함 수정 후 잔여 C-3만 남았고 design-audit-criteria FROZEN으로 면제 → 전원 design-pass (2026-06-02 확인)

## 3. 종료 조건 (Exit Criteria)

- [ ] EC-1: `uv run bushexa serve` 후 `curl -sf localhost:8000/` → HTTP 200 (포트는 cli.py serve 기본 8000; Designer 사후 정정 — 기존 "5000"은 cli 실제값과 불일치였음)
- [ ] EC-2: 7개 UI 라우트(board/busno/info/stops/unist/timetable/running) smoke 통과 (`tests/web/test_routes_smoke.py`)
- [ ] EC-3: 비로그인 `/admin/` 접근이 `/admin/login`으로 302, 로그인 후 도달 (`tests/web/test_admin_auth_flow.py`)
- [ ] EC-4: board/stops/unist partial이 `hx-trigger="every Ns"` 속성을 가지고 partial GET이 200 (`tests/web/test_htmx_partials.py`)
- [ ] EC-5: SSE 스트림(`/admin/govtrack/status/stream`, recrawl stream)이 `text/event-stream`으로 이벤트 송신 (`tests/web/test_sse.py`)
- [ ] EC-6: 시간표 편집 저장 시 백업 생성 + atomic write (`tests/web/test_admin_timetable_edit.py`)
- [ ] EC-7: `! grep -rn 'streamlit' bushexa/web/`
- [ ] EC-8: 전체 `uv run pytest -q` → 0 fail / 0 error
- [ ] EC-9: 관리자 로그 뷰어 — 비로그인 `/admin/logs` 302 + `LogTailReader.tail`(최신순/level 필터/≤2000/파일부재 빈목록) (`tests/web/test_admin_logs.py`, `tests/services/test_log_reader.py`)
- [ ] EC-10: 모든 사람 touch point에 대응 `touchpoints/TP-*.md`가 존재하고 status `implemented`(구현이 인터랙션 명세와 일치) — §10 매핑표의 TP-001~TP-012, TP-015 (E-12 게이트)
- [ ] EC-11: 상태 변경 admin POST(login/password/timetable save/recrawl)에 CSRF 방어가 적용되고 누락 0건 — §11 보안 build-to S5 (검증: `tests/web/test_csrf.py`)

### 3.1 EC ↔ Work Item AC 매핑 (P-8 / P-12)

| EC | 검증 대상 | 충족하는 Work Item AC |
|---|---|---|
| EC-1 | serve 200 | W1: AC-1 |
| EC-2 | UI smoke | W2~W8: 각 AC-1; W15: AC-1 |
| EC-3 | admin 인증 | W9: AC-1,2; W10: AC-1,2 |
| EC-4 | HTMX partial | W2: AC-2; W5: AC-2; W6: AC-2 |
| EC-5 | SSE | W13b: AC-1; W14: AC-1 |
| EC-6 | 시간표 편집 | W11: AC-1,2; W13a: AC-1 |
| EC-7 | no streamlit | 전 work item 공통 제약 |
| EC-8 | pytest 전체 | 전 work item AC 합집합 + W15 |
| EC-9 | 관리자 로그 뷰어 | W16: AC-1, AC-2 |
| EC-10 | TP 문서 일치 | 전 web/admin work item 공통 (§10) |
| EC-11 | CSRF 방어 | W10·W11·W13a·W13b 공통 (§11 S5) |

> 모든 work item AC가 ≥1개 EC에 매핑됨. 누락 0건.

## 4. Work Item 분해

| ID | 작업 제목 | 소요 | 의존 | 산출물 |
|---|---|---|---|---|
| W1 | app factory + base.html + static 부트 | M | — | web/app.py, templates/_base.html, static/{style.css,vendor/htmx.min.js} + tests/web/test_app_factory.py |
| W2 | board route + partial (F01, HTMX 15s) | M | W1 | routes/board.py, templates/board.html, partial/board_table.html + tests |
| W3 | busno route (F02) | S | W1 | routes/busno.py, templates/busno.html + tests |
| W4 | info route + changelog.json (F03) | S | W1 | routes/info.py, templates/info.html, static/data/changelog.json + tests |
| W5 | stops route + partial + cache (F06, HTMX 10s) | M | W1 | routes/stops.py, templates/stops*.html, services/stop_cache.py + tests |
| W6 | unist_board route + partial (F07, HTMX 30s) | M | W1 | routes/unist_board.py, templates/unist*.html + tests |
| W7 | unist_timetable route + timetable.css (F08) | M | W1 | routes/unist_timetable.py, templates/unist_timetable.html, static/css/timetable.css + tests |
| W8 | running route (F05) | M | W1 | routes/running.py, templates/running.html + tests |
| W9 | services/auth.py (F04 인증) | M | — | services/auth.py + tests/services/test_auth.py |
| W10 | admin login/dashboard/logout/password (F04) | M | W1, W9 | routes/admin.py(부분), templates/admin/* + tests |
| W11 | services/timetable_editor.py (F04) | M | — | services/timetable_editor.py + tests |
| W12 | admin data browser + CSV (F04) | M | W1, W9 | routes/admin.py(확장), templates/admin/data_browser.html + tests |
| W13a | admin timetable editor (F04) | M | W1, W9, W11 | routes/admin.py(확장), templates/admin/timetable_*.html + tests |
| W13b | admin recrawl SSE (F04) | M | W13a, P2/W5 | routes/admin.py(확장) + tests/web/test_admin_recrawl_sse.py |
| W14 | admin govtrack status + SSE (F04) | M | W1, W9, P2/W6 | routes/admin.py(확장), templates/admin/govtrack_status.html + tests |
| W15 | 라우트 smoke tests 통합 | M | W2~W14 | tests/web/test_routes_smoke.py |
| W16 | 관리자 애플리케이션 로그 뷰어 (TP-015) | M | W1, W9 | services/log_reader.py, config.py(log_dir), web/app.py(setup_logging), routes/admin.py(확장), templates/admin/logs.html, tests/{services/test_log_reader.py, web/test_admin_logs.py} |

## 5. Work Item 상세

### W1 — app factory + base + static
**Depends:** — **산출물:** `bushexa/web/app.py`, `templates/_base.html`, `static/style.css`, `static/vendor/htmx.min.js`, `tests/web/test_app_factory.py`

**지시사항 (명령형):**
1. `create_app(config: AppConfig) -> Flask` 팩토리를 작성하고 blueprint 등록 지점을 둔다.
2. 세션 쿠키를 httponly·samesite=Lax·secure(if request.is_secure)로 설정한다.
3. `_base.html`에 네비게이션·footer·HTMX 부트 스크립트·flash 영역을 둔다.
4. HTMX를 `static/vendor/`에 둔다 (CDN 비의존).
5. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: `create_app(test_config).test_client().get('/')`가 200 또는 board로의 302 (검증: `uv run pytest tests/web/test_app_factory.py::test_root_ok`)
- [ ] AC-2: 세션 쿠키가 HttpOnly·SameSite=Lax로 설정된다 (검증: `uv run pytest tests/web/test_app_factory.py::test_cookie_flags`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_root_ok`: 앱 팩토리로 만든 test_client로 `/`를 GET하면 200(또는 기본 페이지로 302)이 반환되는지 검증한다.
- `test_cookie_flags`: 세션을 발생시키는 응답의 Set-Cookie에 HttpOnly와 SameSite=Lax가 포함되는지 검증한다 — 세션 탈취 완화.

**검증 명령:**
```bash
uv run pytest tests/web/test_app_factory.py -v
```

---

### W2 — board route + partial (F01)
**Depends:** W1 **산출물:** `routes/board.py`, `templates/board.html`, `templates/partial/board_table.html`, `tests/web/test_board_route.py`

**지시사항 (명령형):**
1. `GET /board`와 `GET /partial/board`를 구현한다 (F01 §4.2). domain `get_board_data` 호출.
2. `board.html`에 `<div id="board-table" hx-get="/partial/board" hx-trigger="every 15s" hx-swap="innerHTML">`를 둔다.
3. partial 라우트는 `board_table.html` 조각만 렌더한다.
4. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: `GET /board` → 200, 응답에 `id="board-table"` 포함 (검증: `uv run pytest tests/web/test_board_route.py::test_board_ok`)
- [ ] AC-2: `GET /partial/board` → 200, `hx-trigger`는 메인에만, partial은 `<tr>` 조각 (검증: `uv run pytest tests/web/test_board_route.py::test_partial_fragment`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_board_ok`: `/board` GET이 200이고 HTML에 자동 갱신 컨테이너 `id="board-table"`와 `hx-trigger="every 15s"`가 있는지 검증한다.
- `test_partial_fragment`: `/partial/board`가 전체 페이지가 아닌 테이블 행 조각만 반환하는지(<html> 태그 없음) 검증한다 — 부분 갱신 정확성.
- `test_board_uses_domain`: mock domain.get_board_data가 주는 행이 렌더 HTML에 반영되는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/web/test_board_route.py -v
```

---

### W3 — busno route (F02)
**Depends:** W1 **산출물:** `routes/busno.py`, `templates/busno.html`, `tests/web/test_busno_route.py`

**지시사항 (명령형):**
1. `GET /busno`를 구현한다 (쿼리 `?bus=&day=&dep=`, F02 §4.2). domain `get_busno_page_data` 호출.
2. `busno.html`에 버스/요일/출발지 선택 UI와 Hour/Minute 테이블을 둔다.
3. 잘못된 파라미터는 경고 배너로 표시한다.
4. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: `GET /busno?bus=713&day=0&dep=UNIST` → 200, 시간표 테이블 포함 (검증: `uv run pytest tests/web/test_busno_route.py::test_valid`)
- [ ] AC-2: 잘못된 `?bus=999` → 200 + 경고 배너 (검증: `uv run pytest tests/web/test_busno_route.py::test_invalid_bus_warns`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_valid`: 유효한 쿼리로 `/busno`가 200이고 HTML에 시간표 테이블(`class="timetable"`)이 있는지 검증한다.
- `test_invalid_bus_warns`: 존재하지 않는 버스번호를 주면 500이 아니라 200 + 경고 메시지로 처리되는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/web/test_busno_route.py -v
```

---

### W4 — info route + changelog (F03)
**Depends:** W1 **산출물:** `routes/info.py`, `templates/info.html`, `static/data/changelog.json`, `tests/web/test_info_route.py`

**지시사항 (명령형):**
1. `GET /info`를 구현한다 (F03 §4.2). 정적 콘텐츠 + changelog.json 로드.
2. `?hexa=6` 카운팅 unlock을 **제거**한다 (관리자는 `/admin`).
3. 노선 이미지를 `url_for('static', filename='media/graphisnotmap.png')`로 참조한다.
4. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: `GET /info` → 200, 노선번호 513/713/743/753/1115 모두 포함 (검증: `uv run pytest tests/web/test_info_route.py::test_routes_listed`)
- [ ] AC-2: `GET /info?hexa=6` 응답에 관리자 마커(`/admin`, `__mgr_auth__`)가 없다 (검증: `uv run pytest tests/web/test_info_route.py::test_hexa_no_admin`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_routes_listed`: `/info` HTML에 5개 노선번호가 모두 표시되는지 검증한다.
- `test_hexa_no_admin`: `?hexa=6`을 줘도 관리자 UI가 노출되지 않는지(숨김 진입 제거) 검증한다 — F03 결함 회귀.
- `test_changelog_missing_ok`: changelog.json이 없을 때 500 없이 200 + 빈 변경이력으로 렌더되는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/web/test_info_route.py -v
```

---

### W5 — stops route + partial + cache (F06)
**Depends:** W1 **산출물:** `routes/stops.py`, `templates/stops.html`, `templates/stops_partial.html`, `services/stop_cache.py`, `tests/web/test_stops_route.py`

**지시사항 (명령형):**
1. `GET /stops`와 `GET /partial/stops?stop_id=`를 구현한다 (F06 §4.2). domain `get_stop_data` 호출.
2. `services/stop_cache.py`에 stop_id별 10초 서버 캐시(in-process dict + lock)를 둔다 (구 session_state 대체).
3. partial에 `hx-trigger="every 10s"`를 둔다.
4. 30분 gap 경고를 표시한다.
5. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: `GET /stops` → 200 + stop 선택 UI (검증: `uv run pytest tests/web/test_stops_route.py::test_stops_ok`)
- [ ] AC-2: `GET /partial/stops?stop_id=196040234` → 200, 10초 내 재요청은 캐시 사용 (검증: `uv run pytest tests/web/test_stops_route.py::test_cache_hit`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_stops_ok`: `/stops` GET이 200이고 정류장 선택 셀렉터가 있는지 검증한다.
- `test_cache_hit`: 같은 stop_id로 10초 내 두 번 partial 요청 시 domain/client가 1회만 호출되는지(캐시 적중) 검증한다 — 구 session_state 10초 캐시 동작 이전.
- `test_cache_expires`: FakeClock으로 11초 경과시키면 캐시가 만료되어 재조회하는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/web/test_stops_route.py -v
```

---

### W6 — unist_board route + partial (F07)
**Depends:** W1 **산출물:** `routes/unist_board.py`, `templates/unist_board.html`, `templates/unist_partial.html`, `tests/web/test_unist_board_route.py`

**지시사항 (명령형):**
1. `GET /unist`와 `GET /partial/unist`를 구현한다 (F07 §4.2). domain `get_unist_board_data` 호출.
2. 6 카드 그리드와 `hx-trigger="every 30s"` partial을 둔다.
3. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: `GET /unist` → 200 + 6개 카드 (검증: `uv run pytest tests/web/test_unist_board_route.py::test_six_cards`)
- [ ] AC-2: `GET /partial/unist` → 200, 카드 그리드 조각만 (검증: `uv run pytest tests/web/test_unist_board_route.py::test_partial`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_six_cards`: `/unist` HTML에 정확히 6개 카드(`class="bus-card"`)가 렌더되는지 검증한다.
- `test_partial`: `/partial/unist`가 `id="unist-grid"` 조각만 반환하는지(전체 페이지 아님) 검증한다.

**검증 명령:**
```bash
uv run pytest tests/web/test_unist_board_route.py -v
```

---

### W7 — unist_timetable route + css (F08)
**Depends:** W1 **산출물:** `routes/unist_timetable.py`, `templates/unist_timetable.html`, `static/css/timetable.css`, `tests/web/test_unist_timetable_route.py`

**지시사항 (명령형):**
1. `GET /timetable?day=`를 구현한다 (F08 §4.2). domain `get_full_timetable_data` 호출.
2. `BUS_COLORS`를 `.bus-{N}` CSS 클래스로 전환해 `timetable.css`에 둔다 (인라인 style 제거).
3. 요일 전환은 일반 GET 링크로 처리한다.
4. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: `GET /timetable?day=0` → 200 + 시간표 그리드 (검증: `uv run pytest tests/web/test_unist_timetable_route.py::test_grid`)
- [ ] AC-2: 버스 배지에 `class="bus-713"` 형태 CSS 클래스가 쓰이고 인라인 color style이 없다 (검증: `uv run pytest tests/web/test_unist_timetable_route.py::test_css_class_not_inline`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_grid`: `/timetable?day=0` HTML에 시간표 테이블과 시간대 행이 있는지 검증한다.
- `test_css_class_not_inline`: 버스 색상이 `class="bus-713"`로 표현되고 `style="color:`인라인이 응답에 없는지 검증한다 — F08 인라인 스타일 제거 회귀.

**검증 명령:**
```bash
uv run pytest tests/web/test_unist_timetable_route.py -v
```

---

### W8 — running route (F05)
**Depends:** W1 **산출물:** `routes/running.py`, `templates/running.html`, `tests/web/test_running_route.py`

**지시사항 (명령형):**
1. `GET /running?route_id=&date=`를 구현한다 (F05 §4.2). repo + domain `parse_runs`/`build_running_grid` 호출.
2. DB 연결 실패를 사용자 친화 메시지로 처리한다 (500 회피).
3. 잘못된 date 형식을 검증한다.
4. 테스트를 작성한다 (in-memory SQLite 시드).

**Acceptance:**
- [ ] AC-1: 시드된 로그로 `GET /running?route_id=...&date=...` → 200 + 운행 그리드 (검증: `uv run pytest tests/web/test_running_route.py::test_grid_rendered`)
- [ ] AC-2: 로그 없음 → 200 + "검색된 버스가 없습니다" (검증: `uv run pytest tests/web/test_running_route.py::test_no_data`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_grid_rendered`: in-memory SQLite에 운행 로그를 시드하고 `/running` 호출 시 정류장×회차 그리드가 HTML에 렌더되는지 검증한다.
- `test_no_data`: 해당 날짜·노선에 로그가 없을 때 500이 아니라 200 + 안내 메시지가 나오는지 검증한다.
- `test_bad_date_handled`: `?date=abc` 같은 잘못된 형식이 400 또는 기본값 폴백 + 경고로 처리되는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/web/test_running_route.py -v
```

---

### W9 — services/auth.py (F04 인증)
**Depends:** — **산출물:** `bushexa/services/auth.py`, `tests/services/test_auth.py`

**지시사항 (명령형):**
1. `AuthService(secret_path, env_password)`를 구현한다: `verify`, `change_password`, `needs_setup` (F04 §4.4).
2. PBKDF2-SHA256 해시 검증 + legacy 평문 호환 + 변경 시 자동 PBKDF2 마이그레이션.
3. `change_password`는 현재 비밀번호 검증을 요구한다 (F04 결함 D8).
4. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: PBKDF2 해시 검증이 정답/오답을 정확히 구분한다 (검증: `uv run pytest tests/services/test_auth.py -k verify`)
- [ ] AC-2: `change_password`가 현재 비밀번호 불일치 시 실패를 반환한다 (검증: `uv run pytest tests/services/test_auth.py::test_change_requires_current`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_verify_pbkdf2`: 저장된 PBKDF2 해시에 대해 올바른 비밀번호는 True, 틀린 것은 False를 반환하는지 검증한다.
- `test_change_requires_current`: 현재 비밀번호를 틀리게 주면 change_password가 error('current_invalid')를 반환하는지 검증한다 — F04 D8(세션 탈취 시 무단 변경) 회귀.
- `test_legacy_plain_migrates`: legacy 평문으로 인증 후 비밀번호 변경 시 파일이 PBKDF2 포맷으로 바뀌는지 검증한다.
- `test_needs_setup`: 비밀번호 파일·env가 모두 없으면 needs_setup이 True인지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/services/test_auth.py -v
```

---

### W10 — admin login/dashboard/logout/password (F04)
**Depends:** W1, W9 **산출물:** `routes/admin.py`(부분), `templates/admin/{login,dashboard,password}.html`, `tests/web/test_admin_auth_flow.py`

**지시사항 (명령형):**
1. `login_required` 데코레이터와 `/admin/login`(GET/POST), `/admin/logout`, `/admin/`, `/admin/password`(GET/POST)를 구현한다.
2. 로그인 5회 연속 실패 시 10초 lockout (in-memory).
3. setup 모드(needs_setup)면 비밀번호 강제 설정 폼을 노출한다.
4. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: 비로그인 `/admin/` → 302 `/admin/login?next=/admin/` (검증: `uv run pytest tests/web/test_admin_auth_flow.py::test_redirect`)
- [ ] AC-2: 로그인 후 `/admin/` 도달, 로그아웃 후 재차단 (검증: `uv run pytest tests/web/test_admin_auth_flow.py::test_login_logout`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_redirect`: 비로그인 상태로 보호 라우트에 접근하면 next 파라미터를 단 로그인 페이지로 302되는지 검증한다.
- `test_login_logout`: 올바른 비밀번호로 로그인 후 대시보드 200, 로그아웃 후 다시 보호 라우트가 302되는지 검증한다.
- `test_lockout_after_5_fails`: 5회 연속 오답 후 다음 시도가 일시 차단(423/429)되는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/web/test_admin_auth_flow.py -v
```

---

### W11 — services/timetable_editor.py (F04)
**Depends:** — **산출물:** `bushexa/services/timetable_editor.py`, `tests/services/test_timetable_editor.py`

**지시사항 (명령형):**
1. `TimetableEditor(dir, backup_dir)`를 구현한다: `list_routes`, `load`, `save`, `validate` (F04 §4.4).
2. `save`는 검증 → 백업 → tmp write → fsync → rename(atomic) 순서로 한다.
3. `validate`는 HH:MM 형식·범위·중복을 검사한다.
4. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: save 호출 시 `backup_dir`에 타임스탬프 백업이 생성된다 (검증: `uv run pytest tests/services/test_timetable_editor.py::test_save_backup`)
- [ ] AC-2: 잘못된 형식 저장 시 ValidationError로 원본이 보존된다 (검증: `uv run pytest tests/services/test_timetable_editor.py::test_invalid_preserves_original`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_save_backup`: 기존 713.json을 편집·저장하면 backup_dir에 `713.{timestamp}.json` 백업이 생기는지 검증한다.
- `test_invalid_preserves_original`: "25:00" 같은 잘못된 시각으로 저장 시도 시 ValidationError가 나고 디스크의 원본이 변경되지 않는지 검증한다 — 데이터 보호.
- `test_atomic_rename`: 저장 중 rename 실패를 주입해도 원본 파일이 손상되지 않는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/services/test_timetable_editor.py -v
```

---

### W12 — admin data browser + CSV (F04)
**Depends:** W1, W9 **산출물:** `routes/admin.py`(확장), `templates/admin/data_browser.html`, `tests/web/test_admin_data_browser.py`

**지시사항 (명령형):**
1. `GET /admin/data`(필터+페이지네이션)와 `GET /admin/data.csv`를 구현한다 (F04 §4.2). repo `query_paged`/`export_csv` 호출.
2. CSV는 UTF-8 BOM, 최대 10000행.
3. 잘못된 day 형식은 400.
4. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: 필터 결과 행 수가 repo count와 일치한다 (검증: `uv run pytest tests/web/test_admin_data_browser.py::test_filter_count`)
- [ ] AC-2: `/admin/data.csv`가 UTF-8 BOM으로 시작한다 (검증: `uv run pytest tests/web/test_admin_data_browser.py::test_csv_bom`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_filter_count`: 시드 DB에서 route_id+day 필터로 본 행 수가 같은 조건 count와 일치하는지 검증한다.
- `test_csv_bom`: `/admin/data.csv` 응답 본문이 UTF-8 BOM으로 시작해 엑셀에서 한글이 깨지지 않는지 검증한다.
- `test_bad_day_400`: `?day=abc`가 400을 반환하는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/web/test_admin_data_browser.py -v
```

---

### W13a — admin timetable editor (F04)
**Depends:** W1, W9, W11 **산출물:** `routes/admin.py`(확장), `templates/admin/timetable_index.html`, `timetable_edit.html`, `tests/web/test_admin_timetable_edit.py`

**지시사항 (명령형):**
1. `/admin/timetable`(목록), `/admin/timetable/<busno>`(GET 편집, POST 저장)를 구현한다.
2. 편집 화면은 weekday 탭 + departure별 시간 목록. 시간 추가/삭제는 HTMX partial.
3. 저장은 W11 `TimetableEditor.save`로 위임한다.
4. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: `GET /admin/timetable/713` → 200 + 3개 weekday 탭 (검증: `uv run pytest tests/web/test_admin_timetable_edit.py::test_edit_view`)
- [ ] AC-2: POST 저장 후 파일 변경 + 백업 생성 (검증: `uv run pytest tests/web/test_admin_timetable_edit.py::test_save`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_edit_view`: 로그인 상태로 `/admin/timetable/713`을 열면 평일/토/일 탭과 시간 목록이 렌더되는지 검증한다.
- `test_save`: 시간 1건을 수정해 POST하면 200 + 디스크 JSON 갱신 + 백업 생성이 일어나는지 검증한다 — F04 AC-T2/T3.
- `test_invalid_save_422`: 잘못된 weekday 키로 저장 시 422가 반환되는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/web/test_admin_timetable_edit.py -v
```

---

### W13b — admin recrawl SSE (F04)
**Depends:** W13a, P2/W5 **산출물:** `routes/admin.py`(확장), `tests/web/test_admin_recrawl_sse.py`

**지시사항 (명령형):**
1. `POST /admin/timetable/recrawl`(job 시작)과 `GET /admin/timetable/recrawl/<job_id>/stream`(SSE)을 구현한다.
2. SSE는 `text/event-stream`으로 progress/done/error 이벤트를 송신한다.
3. 동시 2개 재크롤은 409.
4. 테스트를 작성한다 (mock TimetableCrawlJob).

**Acceptance:**
- [ ] AC-1: SSE 스트림이 progress 이벤트 ≥1 후 done으로 종결한다 (검증: `uv run pytest tests/web/test_admin_recrawl_sse.py::test_stream`)
- [ ] AC-2: 진행 중 두 번째 recrawl POST는 409 (검증: `uv run pytest tests/web/test_admin_recrawl_sse.py::test_conflict`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_stream`: mock job으로 recrawl을 시작하고 SSE를 소비하면 progress 이벤트가 1건 이상 온 뒤 done 이벤트로 스트림이 끝나는지 검증한다.
- `test_conflict`: 한 job이 진행 중일 때 두 번째 recrawl 시작 요청이 409를 받는지 검증한다 — F04 AC-R5.

**검증 명령:**
```bash
uv run pytest tests/web/test_admin_recrawl_sse.py -v
```

---

### W14 — admin govtrack status + SSE (F04)
**Depends:** W1, W9, P2/W6 **산출물:** `routes/admin.py`(확장), `templates/admin/govtrack_status.html`, `tests/web/test_admin_govtrack_status.py`

**지시사항 (명령형):**
1. `GET /admin/govtrack/status`(JSON)와 `GET /admin/govtrack/status/stream`(SSE 5초)을 구현한다. `GovtrackStatusReader` 사용.
2. 데몬 미동작(consecutive_failures>0) 시 카드 강조.
3. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: status JSON에 `last_success_at`·`consecutive_failures` 필드가 있다 (검증: `uv run pytest tests/web/test_admin_govtrack_status.py::test_status_json`)
- [ ] AC-2: SSE 스트림이 `text/event-stream`으로 status 이벤트를 송신한다 (검증: `uv run pytest tests/web/test_admin_govtrack_status.py::test_status_sse`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_status_json`: status writer가 기록한 사이클을 reader가 읽어 JSON 응답에 last_success_at과 consecutive_failures가 담기는지 검증한다.
- `test_status_sse`: status stream 응답 Content-Type이 text/event-stream이고 첫 이벤트에 status 데이터가 오는지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/web/test_admin_govtrack_status.py -v
```

---

### W15 — 라우트 smoke tests 통합
**Depends:** W2~W14 **산출물:** `tests/web/test_routes_smoke.py`

**지시사항 (명령형):**
1. 7개 UI 라우트 + admin 대시보드(로그인 후)의 GET smoke 테스트를 한 파일에 모은다.
2. 각 응답 200 + 페이지 고유 마커(`<title>` 또는 컨테이너 id)를 단언한다.
3. partial 라우트도 200을 단언한다.

**Acceptance:**
- [ ] AC-1: 9개 라우트(7 UI + admin login + admin dashboard) smoke가 모두 통과한다 (검증: `uv run pytest tests/web/test_routes_smoke.py -v`)
- [ ] AC-2: partial 라우트 3종(board/stops/unist)이 200이다 (검증: `uv run pytest tests/web/test_routes_smoke.py::test_partials`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_all_ui_routes_200`: board/busno/info/stops/unist/timetable/running 7개 라우트가 각각 200이고 고유 마커를 포함하는지 한 번에 검증한다.
- `test_partials`: 3개 partial 라우트가 조각 HTML 200을 반환하는지 검증한다.
- `test_admin_dashboard_after_login`: 로그인 세션으로 `/admin/`이 200인지 검증한다.

**검증 명령:**
```bash
uv run pytest tests/web/test_routes_smoke.py -v
```

---

### W16 — 관리자 애플리케이션 로그 뷰어 (F04 §4.6, TP-015)
**Depends:** W1, W9 **산출물:** `bushexa/services/log_reader.py`, `bushexa/config.py`(log_dir 추가), `bushexa/web/app.py`(setup_logging 연결), `routes/admin.py`(확장), `templates/admin/logs.html`, `tests/services/test_log_reader.py`, `tests/web/test_admin_logs.py`

**지시사항 (명령형):**
1. `AppConfig`에 `log_dir: Path`(기본 `./logs`, env `BUSHEXA_LOG_DIR`) 필드를 추가한다.
2. `create_app`에서 `setup_logging(level=config.log_level, log_dir=config.log_dir)`를 호출해 `logs/bushexa.log`를 적재한다.
3. `services/log_reader.py`에 `LogLine`/`LogTailReader`를 구현한다(F04 §4.6): 파일 끝에서 N줄을 최신 우선으로 읽고, `level` 이상만 필터, `lines`는 2000 상한, 파일 부재 시 빈 리스트.
4. `GET /admin/logs`(login_required)와 `admin/logs.html`을 구현한다. 쿼리 `?level=&lines=`는 검증하고 **경로 파라미터는 받지 않는다**(고정 경로). `/admin/logs/stream` SSE는 선택.
5. 표출 전 알려진 시크릿 패턴은 마스킹한다.
6. 테스트를 작성한다.

**Acceptance:**
- [ ] AC-1: 비로그인 `GET /admin/logs` → 302 `/admin/login` (검증: `uv run pytest tests/web/test_admin_logs.py::test_requires_login`)
- [ ] AC-2: `LogTailReader.tail`이 최신순·level 필터·`lines`≤2000·파일부재 빈목록을 만족한다 (검증: `uv run pytest tests/services/test_log_reader.py -v`)

**테스트 케이스 (자연어 의도 — P-11):**
- `test_tail_returns_recent_lines_last_first`: 임시 로그 파일에 10줄을 기록한 뒤 `tail(lines=5)`가 마지막 5줄을 최신순(가장 최근이 먼저)으로 반환하는지 검증한다.
- `test_tail_filters_by_level`: INFO/ERROR가 섞인 파일에서 `level="ERROR"`가 ERROR 이상 라인만 남기는지 검증한다.
- `test_tail_caps_lines_at_2000`: `lines=10**6`을 요청해도 반환 길이가 2000 이하인지 검증한다 — 메모리/DoS 상한.
- `test_missing_log_file_returns_empty`: 로그 파일이 아직 없을 때 예외 없이 빈 리스트를 반환하는지 검증한다.
- `test_requires_login`: 비로그인 상태의 `GET /admin/logs`가 로그인 페이지로 302되는지 검증한다 — AC-A1 게이트 재사용.
- `test_uses_fixed_path`: `?file=../../secret/key.txt` 같은 경로 주입을 줘도 설정된 고정 경로(`config.log_dir/bushexa.log`)만 읽는지 검증한다 — path traversal 차단.

**검증 명령:**
```bash
uv run pytest tests/services/test_log_reader.py tests/web/test_admin_logs.py -v
```

## 6. 병렬화 그래프

```text
W1 ──┬──▶ W2,W3,W4,W5,W6,W7,W8 (UI 라우트, 동시)
     └──▶ W10,W12,W13a,W14 (W9 필요)
W9  ── (독립) ──▶ W10,W12,W13a,W14,W16
W11 ── (독립) ──▶ W13a
W13a ──▶ W13b
W2~W14 ──▶ W15
```

병렬 가능 그룹:
- **Group A (W1 후, 동시 9개)**: W2, W3, W4, W5, W6, W7, W8, W9, W11
- **Group B (W9 후, 동시 5개)**: W10, W12, W13a, W14, W16 (W13a는 W11도 필요)
- **Group C**: W13b (W13a 후)
- **Group D**: W15 (전부 후)

## 7. 리스크 & 롤백

- R1: HTMX selector mismatch — partial은 `<div id>` 래핑 필수, smoke로 검증
- R2: SSE 연결이 sync 워커 1개 점유 — dev에서 별도 워커, 운영은 admin 단일 접속 가정
- R3: 시간표 편집 동시성 — 마지막 저장 승리 + 백업 복구 (W11)
- R4: 구현 중 발견 에러는 `postmortems/`에 PM 작성 (00-workflow §8)

롤백: `bushexa/web/`, 관련 tests 제거. 기존 Streamlit `app.py` 작동 유지.

## 8. Auditor 감리 포인트 (설계 단계)

- [ ] DA-1: 17개 work item 단일 책임
- [ ] DA-2: 사이클 없음
- [ ] DA-3: 모든 work item 산출물 + 테스트 경로 명시
- [ ] DA-4: 모든 work item AC ≥2건 + 검증 명령
- [ ] DA-5: Group A 9개 병렬 식별
- [ ] DA-6: EC-1~8 검증 명령 보유
- [ ] DA-7: L work item(admin timetable) 사전 분할 W13a/W13b
- [ ] DA-8: 모든 테스트 work item에 test case 자연어 의도 (P-11)
- [ ] DA-9: EC↔AC 매핑 표 존재, 누락 0건 (P-12)

---

## 9. Touch Point 산출물 매핑 (00-workflow §9 / E-12)

> P4는 사람 대면 화면·액션을 신규 구현하므로, 각 web/admin work item은 대응 `touchpoints/TP-{NNN}.md`를 **산출물에 포함**한다. 인터랙션 자체는 이미 feature §4.2/§4.5와 본 매뉴얼에서 설계·감리되었으므로, Executor는 **새 UX를 발명하지 말고** 그 명세를 `templates/touchpoint-template.md` 양식으로 **전사(transcribe)**한다. 완료 시 해당 TP frontmatter status를 `implemented`로, INDEX.md status를 갱신한다.

| TP | work item | 전사 출처 (이미 감리됨) | 비고 |
|---|---|---|---|
| TP-001 | W2 | **Designer 사전 작성** (본 phase, 자동갱신 대표) | 그대로 따른다 |
| TP-002 | W3 | F02 §4.2 + 본 W3 | 선택 캐스케이드·경고배너 |
| TP-003 | W5 | F06 §4.2 + 본 W5 | 10초 캐시·gap 경고 |
| TP-004 | W6 | F07 §4.2 + 본 W6 | 6카드·30초 갱신 |
| TP-005 | W7 | F08 §4.2 + 본 W7 | 요일 GET 전환 |
| TP-006 | W8 | F05 §4.2 + 본 W8 | 날짜·노선·빈상태 |
| TP-007 | W10 | F04 §4.2 + 본 W10 | 로그인·lockout·setup |
| TP-008 | W12 | F04 §4.2 + 본 W12 | 필터·페이지·CSV |
| TP-009 | W13a | **Designer 사전 작성** (본 phase, 편집 대표) | 그대로 따른다 |
| TP-010 | W13b | **Designer 사전 작성** (본 phase, SSE 대표) | 그대로 따른다 |
| TP-011 | W14 | F04 §4.5 + 본 W14 | govtrack status SSE 5초 |
| TP-012 | W10 | F04 §4.2(비밀번호) + 본 W10 | 현재 비밀번호 검증(D8) |
| TP-015 | W16 | F04 §4.6 + 본 W16 | 로그 뷰어·고정경로 |

> TP-013/TP-014(CLI)는 P4 범위 아님(F09/F10·CLI). Designer가 TP-001/009/010을 대표 작성해 두었으니, 나머지는 동일 양식으로 전사한다. 각 TP의 §9 Acceptance는 대응 work item의 AC/테스트를 재인용한다(새 기준 만들지 말 것).

## 10. 보안 Build-to (ADR-009 / security-audit-criteria S1~S10 / E-11)

> P4 종료 후 **보안 게이트**(high/critical 0건)를 통과해야 P5로 간다. Executor는 아래를 **구현 시점부터** 충족하도록 짓는다(사후 보강은 감리 루프 유발). Auditor는 P4 종료 시 `security-audit-criteria.md`로 별도 감리한다.

- **S1 인증·세션:** PBKDF2 해시(평문비교 0), 비밀번호 변경 시 현재 비번 검증(D8), 세션 쿠키 HttpOnly·SameSite=Lax·Secure(if is_secure), 로그인 lockout(W10), `?hexa=6` 숨김진입 제거(W4).
- **S2 권한:** 모든 `/admin/*`에 `login_required`. 직접 URL 우회 불가.
- **S3 인젝션:** SQL 파라미터 바인딩만(문자열 포매팅 0). 시간표 `<busno>`·로그경로 traversal 차단(`..` 거부, 고정경로). subprocess에 사용자입력 0.
- **S4 XSS:** Jinja 자동이스케이프 유지. `|safe`/`Markup` 사용처는 전수 안전 확인. HTMX partial 응답에 미이스케이프 사용자입력 0.
- **S5 CSRF (★ 명시 결정):** 상태 변경 admin POST(로그인·비밀번호변경·시간표저장·재크롤 시작)에 **CSRF 토큰**을 적용한다 — `create_app`에서 stdlib 기반 토큰(세션에 `secrets.token_urlsafe` 저장 + 폼 hidden + POST 검증 데코레이터/before_request)을 구현하고, 모든 admin POST 폼/HTMX 요청이 토큰을 싣는다. (Flask-WTF 도입 대신 stdlib로 충분; 의존 최소화 ADR 일관.) SameSite=Lax는 보조 방어로 병기하되 단독 의존하지 않는다. `tests/web/test_csrf.py`: 토큰 없는 admin POST는 400/403, 올바른 토큰은 통과.
- **S6 SSRF:** 외부 API URL은 고정 base + 화이트리스트 파라미터(P1 client 재사용). 타임아웃 설정 유지.
- **S7 시크릿:** 세션 SECRET_KEY·비밀번호 해시·API키 평문 하드코딩 0. 로그/에러 응답에 시크릿·내부경로 누출 0(W16 로그 뷰어는 표출 전 마스킹).
- **S8 안전기본값:** 사용자 대면 에러에 stack trace/내부경로 노출 0(500 핸들러). debug=off 기본. secret 파일 0600.
- **S9 DoS:** CSV max_rows=10000(W12), 로그 tail ≤2000(W16), 재크롤 동시 1개(409, W13b), SSE 연결 가정 단일.
- **S10 의존성:** `uv`/`pip-audit` 스캔 high 0건(P4 종료 감리 시).

> CSRF(S5)는 어느 work item AC에도 없던 누락이므로 **W10·W11·W13a·W13b 구현 시 공통 적용**하고 EC-11로 검증한다. 보안 결함 발견 시 `postmortems/`에 PM 등재 + 보안 회귀 테스트(00-workflow §8·§10).
