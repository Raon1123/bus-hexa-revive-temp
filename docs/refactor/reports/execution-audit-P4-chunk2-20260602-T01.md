---
phase: P4
scope: W3-W8
verdict: PASS
auditor: sonnet
date: 2026-06-02
---

# Execution Audit — P4 Chunk 2 (W3~W8, UI 라우트 6개)

TARGET: P4/W3-W8 (busno, info, stops, unist_board, unist_timetable, running)

VERDICT: **PASS**

---

## CHECKLIST_RESULTS

### W3 — busno route (F02, TP-002)
- AC-1: **PASS** — `GET /busno?bus=713&day=0&dep=UNIST` → 200 + `class="timetable"`.
  근거: `tests/web/test_busno_route.py::test_valid` PASS; `templates/busno.html:53` `<table class="timetable">`.
- AC-2: **PASS** — `?bus=999` → 500 아님, 200 + 경고 배너.
  근거: `test_invalid_bus_warns` PASS (`assert resp.status_code == 200`, `warning-banner` + "유효하지 않은 버스번호" 단언); `templates/busno.html:9-13` warning-banner 블록.

### W4 — info route (F03) — TP 없음 (P4-web §9 매핑표에 W4 미등재, 정상)
- AC-1: **PASS** — `GET /info` → 200 + 5노선(513/713/743/753/1115).
  근거: `tests/web/test_info_route.py::test_routes_listed` PASS; `templates/info.html:55-59` 5노선 행.
- AC-2: **PASS** — `?hexa=6` 응답에 관리자 마커(`/admin`, `__mgr_auth__`) 없음.
  근거: `test_hexa_no_admin` PASS; `routes/info.py`에 hexa unlock 로직 부재(info_page는 쿼리 무시); `info.html`에 `/admin`·`__mgr_auth__` 0건.
- (보강) `test_changelog_missing_ok`: **PASS** — changelog.json 부재 시 500 없이 200 + 노선 유지.
  근거: `routes/info.py:25-33` `_load_changelog`가 FileNotFoundError/JSONDecodeError를 빈 리스트로 처리.

### W5 — stops route + cache (F06, TP-003)
- AC-1: **PASS** — `GET /stops` → 200 + 선택 UI.
  근거: `test_stops_ok` PASS; `templates/stops.html:10` `<select id="stop-select">`.
- AC-2: **PASS** — `/partial/stops?stop_id=196040234` → 200, 10초 내 재요청 캐시 적중(domain 1회 호출).
  근거: `test_cache_hit` PASS (`call_count == 1`); `test_cache_expires` PASS (FakeClock 11초 경과 후 `call_count == 2`).
  산출물 `services/stop_cache.py` 존재(TTL 10초, Clock 주입, threading.Lock).

### W6 — unist_board route + partial (F07, TP-004)
- AC-1: **PASS** — `GET /unist` → 200 + 정확히 6개 `class="bus-card"`.
  근거: `test_six_cards` PASS (regex `<div class="bus-card...">` 매칭 == 6); 6카드 출처 = F07 명세(513 양방향 2 + UNIST 출발 713/743/753/1115 4 = 6).
- AC-2: **PASS** — `/partial/unist` `id="unist-grid"` 조각만(`<html>` 없음).
  근거: `test_partial` PASS (`"<html" not in html`, `'id="unist-grid"' in html`); `templates/unist_partial.html`에 `<html>` 태그 없음.

### W7 — unist_timetable route + css (F08, TP-005)
- AC-1: **PASS** — `GET /timetable?day=0` → 200 + 그리드.
  근거: `test_grid` PASS (`timetable-grid` + 시간대 행 '07'/'08'); `templates/unist_timetable.html:33` `<table class="timetable-grid">`.
- AC-2: **PASS** — `class="bus-713"` 형태 CSS 클래스 + 인라인 `style="color:` 없음(렌더 출력 기준).
  근거: `test_css_class_not_inline` PASS (`'bus-713' in html`, `'style="color:' not in html`).
  산출물 `static/css/timetable.css` 존재. BUS_COLORS 출처 = legacy `infopages/unist_timetable.py:12-18`와 값 일치(아래 PASS_NOTES 참조).

### W8 — running route (F05, TP-006)
- AC-1: **PASS** — 시드 로그로 `/running?route_id=&date=` → 200 + 운행 그리드.
  근거: `test_grid_rendered` PASS (file-based SQLite 시드 → `running-table` + 통과시각 '08:30'); `templates/running.html:39` `<table class="running-table">`.
- AC-2: **PASS** — 로그 없음 → 200 + "검색된 버스가 없습니다".
  근거: `test_no_data` PASS; `test_bad_date_handled` PASS (`?date=abc` → 200/400, 500 아님; `routes/running.py:33-43` `_parse_date`가 실패 시 어제 날짜 폴백 + 경고).

---

## COMMAND_OUTPUTS

```
$ uv run pytest tests/web/test_busno_route.py tests/web/test_info_route.py \
    tests/web/test_stops_route.py tests/web/test_unist_board_route.py \
    tests/web/test_unist_timetable_route.py tests/web/test_running_route.py -v
  15 passed in 1.88s
  (test_valid, test_invalid_bus_warns, test_routes_listed, test_hexa_no_admin,
   test_changelog_missing_ok, test_stops_ok, test_cache_hit, test_cache_expires,
   test_six_cards, test_partial, test_grid, test_css_class_not_inline,
   test_grid_rendered, test_no_data, test_bad_date_handled) — 전부 PASSED
```

```
$ uv run pytest -q
  153 passed in 4.20s        # 기대 153 충족 (Chunk1 138 + 신규 15). 0 fail / 0 error.

$ uv run pytest --collect-only -q | tail
  153 tests collected        # 회귀 테스트 삭제 없음
```

```
$ grep -rn 'streamlit' bushexa/web/ bushexa/services/stop_cache.py
  (출력 없음 — 0건)

$ grep -rn 'datetime.now|datetime.today' bushexa/web/
  (출력 없음 — 0건; 모든 라우트가 KSTClock 주입 사용. stop_cache도 clock.now() 사용)
```

```
$ grep -rn 'style="color' bushexa/web/templates/unist_timetable.html
  unist_timetable.html:46:  {# .bus-{N} 클래스 사용 — 인라인 style="color:" 없음 (W7 AC-2) #}
  → 1 hit, 그러나 Jinja {# ... #} 주석이라 렌더 출력에 미포함.
    권위 있는 검증은 test_css_class_not_inline (렌더 HTML에 'style="color:' 부재 단언) → PASS.
    소스 grep 비-0 (주석만) / 렌더 출력 0 → W7 AC-2 충족.
```

```
$ grep -rn 'hexa' bushexa/web/routes/info.py bushexa/web/templates/info.html
  routes/info.py:6:   ?hexa=6 관리자 unlock 완전 제거 (S1: 숨김 진입 없음).   # 모듈 docstring
  routes/info.py:18:  log = logging.getLogger("bushexa.web.routes.info")       # 'bushexa' substring 오탐
  routes/info.py:38:  """노선 정보 페이지. ?hexa=6 등 어떤 쿼리도 ..."""        # 함수 docstring
  info.html: 0 hits
  → 3 hits 모두 docstring/substring 오탐. hexa unlock 로직 없음. W4 AC-2 충족.
```

```
$ grep BUS_COLORS infopages/unist_timetable.py (legacy)
  513:#D32F2F, 713:#388E3C, 743:#1976D2, 753:#7B1FA2, 1115:#F57C00
$ static/css/timetable.css
  .bus-513 #D32F2F / .bus-713 #388E3C / .bus-743 #1976D2 / .bus-753 #7B1FA2 / .bus-1115 #F57C00
  → 색상값 5개 모두 legacy와 일치. 임의 생성값 아님 (E-13 출처 확인).
```

---

## TEST_CASE_EXPLANATIONS

- `test_busno_route.py::test_valid`: 도메인 `get_busno_page_data`를 hand-built `BusnoTimetable`(07/08시 행 포함)로 patch한 뒤 `/busno?bus=713&day=0&dep=UNIST`를 GET. 200이고 `class="timetable"` 테이블 + mock 행('07', '20, 40')이 HTML에 있으면 통과. 기대값은 fixture에서 독립 산출.
- `test_busno_route.py::test_invalid_bus_warns`: warning을 단 `BusnoTimetable`을 patch하고 `?bus=999` GET. 500이 아니라 200이고 `warning-banner` + "유효하지 않은 버스번호" 문구가 있으면 통과. 잘못된 파라미터의 graceful 처리 검증.
- `test_info_route.py::test_routes_listed`: `/info` GET 시 5개 노선번호(513/713/743/753/1115)가 모두 HTML에 있으면 통과. 기대값 = F03 명세 고정 노선번호.
- `test_info_route.py::test_hexa_no_admin`: `?hexa=6` GET 응답에 `/admin`·`__mgr_auth__` 마커가 둘 다 없으면 통과. F03 숨김 관리자 진입 제거 회귀.
- `test_info_route.py::test_changelog_missing_ok`: `_STATIC_DATA`를 존재하지 않는 경로로 patch한 뒤 `/info` GET. 500 없이 200이고 노선번호 유지면 통과. changelog 부재 graceful 처리.
- `test_stops_route.py::test_stops_ok`: `/stops` GET 시 `stop-select` 셀렉터와 첫 stop_id(196040234)가 option으로 있으면 통과. 선택 UI 존재 검증.
- `test_stops_route.py::test_cache_hit`: `get_stop_data`를 호출 카운트하는 fake로 patch하고 같은 stop_id로 `/partial/stops`를 2회 GET. domain이 1회만 호출(2번째는 캐시 적중)되면 통과. 측정값은 구현 출력이 아닌 호출 횟수 1이라는 명세 기준.
- `test_stops_route.py::test_cache_expires`: AdvanceClock(수동 시각 조작)으로 stop_cache.get_or_fetch를 직접 단위 테스트. 첫 호출 fetch(count=1), 5초 후 캐시 유지(count=1), 11초 추가 경과(총 16초, TTL 10초 초과) 후 재조회(count=2)면 통과. TTL 만료 동작 검증.
- `test_unist_board_route.py::test_six_cards`: 6개 BusCard를 가진 `UnistBoardSnapshot`을 patch하고 `/unist` GET. 정규식으로 센 `<div class="bus-card...">` 개수가 정확히 6이면 통과. 6 = F07 명세(513×2 + 4)에서 독립 산출.
- `test_unist_board_route.py::test_partial`: 같은 mock으로 `/partial/unist` GET. `<html>` 태그가 없고 `id="unist-grid"`가 있으면(조각만 반환) 통과.
- `test_unist_timetable_route.py::test_grid`: hand-built `FullTimetableSnapshot`(07/08시)을 patch하고 `/timetable?day=0` GET. `timetable-grid` + 시간대 행 '07'/'08'이 있으면 통과.
- `test_unist_timetable_route.py::test_css_class_not_inline`: 같은 mock으로 GET 후 렌더 HTML에 `bus-713` 클래스가 있고 `style="color:` 인라인이 없으면 통과. F08 인라인 스타일 제거 회귀.
- `test_running_route.py::test_grid_rendered`: file-based SQLite에 ROUTEID 713 UNIST 노선 로그 2건(08:30:00, 08:32:00) 시드 후 `/running?route_id=...&date=20260601` GET. `running-table` + 통과시각 '08:30'이 있으면 통과. 기대값 = 직접 시드한 알려진 데이터.
- `test_running_route.py::test_no_data`: 빈 SQLite로 `/running` GET. 500 아닌 200이고 "검색된 버스가 없습니다"면 통과.
- `test_running_route.py::test_bad_date_handled`: `?date=abc` GET. 200 또는 400(500 아님)이고, 200이면 경고 배너/빈상태/날짜형식 메시지 중 하나가 있으면 통과. 잘못된 date의 graceful 처리.

---

## FAIL_REASONS_FOR_DESIGNER

- **none.** 모든 AC PASS, 전체 회귀 153 passed/0 fail/0 error, 산출물 전수 존재, E-13 tautology·spec 약화 적발 0건. Executor 재작업·Designer reopen 모두 불요.

---

## PASS_NOTES

- **E-13(a) 출처 추적성:** W3~W8 구현 테스트 15건이 P4-web.md §5의 P-11 자연어 의도와 1:1 대응(W3:2, W4:3, W5:3, W6:2, W7:2, W8:3). **executor-added 테스트 없음** — 전부 설계 의도에 추적 가능. spec 테스트 대체·약화 0건.
- **E-13(b) tautology 적발 0건:** 모든 기대값이 구현과 독립된 출처에서 도출됨 — busno/stops/unist_board/unist_timetable은 hand-built dataclass fixture, running은 직접 시드한 SQLite 데이터, info는 F03 고정 노선번호, cache 카운트는 명세상 "1회 호출" 기준. `assert f(x) == <현재 f(x)>` 형태 없음.
- **E-13 W7 BUS_COLORS 출처 확인:** `static/css/timetable.css`의 5개 색상값(#D32F2F/#388E3C/#1976D2/#7B1FA2/#F57C00)이 legacy `infopages/unist_timetable.py:12-18` BUS_COLORS와 정확히 일치. 임의 생성값 아님. (단, legacy/F08 §4.3은 텍스트 `color:`였고 구현은 `background-color`(흰 글씨 배지)로 렌더 — AC-2는 "CSS 클래스 + 인라인 color 없음"만 제약하므로 충족. 시각적 표현 차이는 immaterial.)
- **E-12 TP 일치:** TP-002(busno 10s 아님-정적 GET)/TP-003(stops 10s)/TP-004(unist 30s)/TP-005(timetable 정적 GET)/TP-006(running 정적)가 각 구현의 자동갱신 주기·분기·피드백과 일치. hx-trigger 확인: stops_partial 10s, unist_board 30s. INDEX.md 및 각 TP frontmatter status 모두 `implemented`로 갱신됨. W4(info)는 §9 매핑표에 TP 미배정(정상).
- **E-7 도메인 시그니처 일치:** 6개 라우트가 도메인 함수를 정확한 키워드 인자로 호출 — busno(bus,day,dep,clock,timetable_provider=), stops(stop_id,clock,client=), unist_board(clock,client=,timetable_provider=), unist_timetable(weekday=,clock=,timetable_provider=), running(parse_runs(rows,route_id)+build_running_grid(runs,stops_order)).
- **E-5 시크릿:** 신규 W3~W8 파일에 password/secret_key/api_key 하드코딩 0건.
- **E-6 TODO/FIXME:** 신규 라우트 파일에 0건.
- 회귀 안전: pytest collect 153건, 삭제된 테스트 없음. Chunk1 138 → 153(+15) 일관.

### 미세 관찰 (non-blocking, 감리 기준 외)
- `routes/stops.py`는 캐시 적중을 포함한 매 partial 요청마다 `UlsanBisClient`를 생성한다. 실제 API 호출은 mock/캐시된 `get_stop_data` 내부에 게이트되어 AC-2(호출 1회) 충족 — 클라이언트 객체 생성 자체는 사소한 비효율.
- `routes/busno.py`·`routes/info.py`에 미사용 `current_app` import. 린트 수준, 감리 기준 아님.

### 범위 밖 게이트 (P4 종료 시 별도 감리)
- **E-11 (보안 게이트, high/critical 0):** P4-web §10/EC-10에 따라 **P4 종료 시점** 게이트이며 청크 단위 검사 아님. 본 청크에서 관련 build-to(W4 hexa 제거)·시크릿 하드코딩 0건은 확인.
- **E-10 (postmortems):** 구현자 최종보고가 소켓 오류로 유실되어 구현 중 발생 에러를 열거할 수 없음. 기존 PM-001~004는 본 청크 이전 산출물. 산출물 기준으로는 미기록 에러 흔적 없음.
