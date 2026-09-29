---
status: living
last_verified: 2026-09-29 (HEAD 8dc582e)
audience: 화면·템플릿·CSS·노선도를 수정하는 사람·AI 세션
---

# UI 디자인 설계

> 화면별 상호작용 명세는 `docs/refactor/touchpoints/TP-*.md`, 레거시(Streamlit) 화면과의 동등성은
> `docs/refactor/legacy-ui-reference.md` 에 있다. 이 문서는 **현재 구현된 디자인 시스템**과 수정 규칙을 적는다.
> 경로는 `bushexa/web/` 기준.

## 1. 설계 원칙

1. **서버 렌더링 우선.** 첫 화면은 완성된 HTML 로 그린다. JS 는 보조(HTMX 부분 갱신, 시계, 모바일 아코디언)다.
2. **조용한 자동 갱신.** 폴링 교체는 토스트·깜박임 없이 컨테이너만 바꾼다. 포커스·스크롤·내비는 유지한다.
3. **실패해도 500 을 내지 않는다.** API/캐시 실패 시 오류 배너 + 시간표 fallback 을 보여 주고 폴링은 계속한다.
4. **색만으로 상태를 전달하지 않는다.** 노선 색에는 항상 번호 텍스트, FIRST/SECOND 에는 라벨이 붙는다.
5. **저사양 경로를 보장한다.** `/lite` 는 폰트·JS·CSS 0 의 순수 HTML 표다.
6. **외부 CDN 금지.** htmx·폰트는 `static/vendor/` 에 벤더링되어 있다.
7. **레거시 동등성.** 사이드바 3그룹 IA, 상단 현재시각, 칩형 세그먼트, FIRST `#DC143C` / SECOND `#0000CD`, 버스당 2행·최대 10대, 노선 색 고정.

## 2. 템플릿 계층

| 템플릿 | 역할 |
|---|---|
| `templates/_base.html` | 공개 셸 — 사이드바(3그룹, `(endpoint, emoji, t(key))` 목록), 탑바 `.lang-switcher`(`?lang=ko|en`), flash, footer. 블록: `title`, `page_title`, `extra_head`, `sidebar_nav`, `sidebar_footer`, `content`, `extra_scripts` |
| board, busno, running, unist_timetable(+`css/timetable.css`), unist_board, stops, info(+`css/info.css`) | `_base` 상속 |
| `templates/admin/_admin_base.html` | `_base` 상속, 관리자 사이드바 + 로그아웃 POST 폼 + `css/admin.css` |
| `templates/board_lite.html` | **독립 문서**(상속 없음). `<meta http-equiv="refresh" content="15">`, `<table border=1>`, FIRST/SECOND 는 `*`/`+` 접두 |

### 2.1 HTMX 부분 갱신

| 조각 | 엔드포인트 | 트리거 / swap | hx 속성 위치 |
|---|---|---|---|
| `partial/board_table.html` | `/partial/board` | every 15s, `innerHTML` | `board.html` 의 `#board-table` |
| `stops_partial.html` | `/partial/stops?stop_id=` | every 10s, `outerHTML` | **조각 자신**이 hx 속성을 다시 내보냄(올바른 패턴) |
| `unist_partial.html` | `/partial/unist` | every 30s, `outerHTML` | `unist_board.html` 바깥 div 에만 있음 — **결함, §7** |

**규칙: `outerHTML` swap 을 쓰면 응답 조각이 hx 속성을 포함해야 한다.** 아니면 첫 교체 후 폴링이 멈춘다. 안전한 기본은 바깥 컨테이너 고정 + `innerHTML`.

조각 템플릿은 `<html>`/`<head>` 없이 쓰고, 전체 페이지가 같은 조각을 `{% include %}` 해 첫 렌더와 갱신 결과를 일치시킨다.

## 3. 디자인 토큰

### 3.1 색

| 용도 | 값 |
|---|---|
| Primary(사이드바·활성·제목) | `#1a237e` |
| 표 헤더 / hover | `#3949ab` / `#303f9f` |
| 강조(활성 내비 테두리·포커스 링) | `#ff9800` |
| 배경 / 본문 / 테두리 | `#f5f5f5` / `#333` / `#e0e0e0`·`#eee` |
| FIRST / SECOND 태그 | `#DC143C`(깜박임) / `#0000CD` |

**노선 색(고정, 3곳 동기화 필수)**

| 노선 | 색 | |
|---|---|---|
| 513 | `#D32F2F` | 빨강 |
| 713 | `#388E3C` | 초록 |
| 743 | `#1976D2` | 파랑 |
| 753 | `#7B1FA2` | 보라 |
| 1115 | `#F57C00` | 주황 |

정의 위치: `static/style.css` 의 `.route-NNN { --route }`, `static/css/timetable.css` 의 `.bus-NNN`, `route_diagram.py` 의 `COLORS`(노선도 카드의 `--route`). 새 노선을 추가하거나 색을 바꾸면 세 곳을 함께 고친다.

### 3.2 글꼴

- `--font-ui`: Pretendard(400/600/700, self-hosted woff2) → 시스템 한글 폰트.
- `--font-board`(Seoul Namsan)는 정의만 되어 있고 **사용되지 않는다**. 쓰지 않을 거면 새 참조를 만들지 말 것.

### 3.3 레이아웃·반응형

- `main` 최대 폭 900px. 간격 변수는 없다(하드코딩 px).
- 브레이크포인트: **720px** 사이드바 → off-canvas(CSS 체크박스 `#nav-toggle`), **640px** 카드 1열, **560px** `.c-present` 열 숨김, **480px** 보드 모바일 아코디언·44px 터치 타깃(`js/boardmobile.js` 의 `MOBILE_BP=480` 과 동기화), **360px** 추가 축소.
- 다크 모드 없음. 유일한 어두운 면은 opt-in Split-flap 보드(`.dboard.flap`, `#0b0f14` 배경·`#ffb000` 글자).

## 4. 컴포넌트 (모두 `style.css`, 별도 표기 제외)

| 분류 | 클래스 |
|---|---|
| 배너 | `.info-banner`(파랑, 공지), `.warning-banner`(노랑, **두 번 정의됨**), `.error-banner`(주황, API 실패) |
| 빈 상태 | `.empty-state` |
| flash | `.flash-list .flash.{error,warning,success,info}` (admin.css 가 success/error 를 다른 색으로 덮어씀) |
| 표 | `.board-table`, `.stops-table`, `.running-table`(sticky 헤더·첫 열), `table.timetable`, `.timetable-grid`(timetable.css) |
| 출발 게시판 | `.dboard.table`/`.dboard.flap`, `.dboard-toolbar`, `.seg`/`.seg-btn.active`, 행 `.dboard-row.is-first/.is-second/.is-open`, 셀 `.c-time/.c-route-cell/.c-dest/.c-present/.c-flag`, `.tag-first/.tag-second`, `.via-label` |
| 칩 | `.bus-btn`, `.day-btn`(.active) |
| 카드 | `.bus-card-grid`(3열), `.bus-card`, `.bus-card-header`(배경 `var(--route)`), `.entry-live`/`.entry-timetable`, 막차 후 `.bus-card.last-bus`(opacity .6) |
| 정보 페이지 | `.info-table`, `.changelog-list`, `.route-note`, 노선도 `.route-view-toggle`, `.route-view`, `.route-map`, `.route-svg`(`.route-station`, `.route-pill-btn`, `.is-dim`), `.route-chip`, `.route-map-panel`, 목록 `.route-lines`, `.route-stops`(info.css) |
| 관리자 | `.admin-table`, `.admin-form`, `.btn-danger-sm`(admin.css) |

알려진 충돌: `.btn-primary` 가 `style.css`(`#1a237e`)와 `admin.css`(`#3182ce`)에서 다르다. 새 버튼은 기존 클래스를 재사용하고 새 색을 만들지 않는다.

## 5. i18n

- `i18n.py` 의 평면 dict `TRANSLATIONS["section.name"]["ko"|"en"]`. 지원 언어 ko(기본)·en.
- 언어 결정: `?lang=` → 쿠키 → ko. `?lang=` 이 유효하면 1년 쿠키 저장.
- 누락 키는 lang → ko → **키 문자열 자체**로 떨어져 화면에 그대로 보인다(누락이 눈에 띄도록).
- 템플릿: `{{ t('board.notice.743') }}`.
- **새 문구 추가 절차:** ko·en 둘 다 넣은 키 추가 → 템플릿 리터럴을 `t()` 로 교체 → `tests/web/test_i18n.py` 통과 확인.
- 커버리지는 부분적이다(`t()` 호출은 `_base`·`board`·`unist_board` 뿐). 새로 쓰는 공개 화면 문구는 `t()` 로 쓴다.
- **확장 설계는 ADR-014(draft)** — UI 문자열은 코드 사전, 정류소 이름은 관리자가 편집하는 1:1 사전. 정류소 이름·도메인 f-string·상수 라벨을 번역하려면 먼저 ADR-014 를 읽는다.

## 6. 노선도 (`/info`: A 지도 + B 노선별 목록, A/B 테스트)

PR #6 에서 두 방식을 함께 둔다. 첫 방문에 하나를 무작위로 보여 주고(쿠키 `route_map_view`), "지도로 보기 / 목록으로 보기"로 바꿀 수 있다.
노선 사실(정차 순서·경유점·시행일)은 **`route_diagram.py` 한 곳**에만 있고, 목록(B)은 그것을 읽어 만든다.

**A. 개략 지도** — `web/route_diagram.py` → 인라인 SVG. 옛 가로 레인 SVG(라벨 겹침·공유 박스가 사이 레인을 삼킴, PM-014)와 다른 방식이다.

| 데이터 | 의미 |
|---|---|
| `NODES` | 노드 → 격자 좌표 `Node(x, y, label, anchor)`. x 서→동, y 북→남. 실제 위치(TAGO 좌표)를 **참고**해 방향·순서만 맞춘다. `label=None` 은 선 모양용 경유점(정차 아님) |
| `LINE_PATHS` | 노선별 운행 순서(경유점 포함), **최신 노선 기준**. 라벨 있는 노드 = 정차 |
| `ROUTE_CHANGES` | 시행일 있는 변경 `RouteChange(line, effective, old, new, summary)`. 시행일(KST, `get_now`) 전에는 `new` 구간을 `old` 로 되돌려 그린다 |
| `RAILS` | 철도 배경(KTX 경부고속선·동해선). `stations` 정류장에 환승 테두리 |
| `STOP_NOTE` | 정류장 정보 패널 설명 |
| `COLORS`, `LINE_ORDER` | 노선 색(§3.1 동기화), 나란한 구간의 기본 쌓기 순서 |
| `constants.ROUTE_MAP_STOP_LINK` | 정류장 → 실시간 도착 `stop_id`. 값은 반드시 `SERACH_STOPS` 안 |

그리기 규칙과 함정:
- 모든 구간은 가로·세로·45°(`test_paths_octilinear`). 노드 좌표는 서로 겹치면 안 된다(`test_paths_defined`).
- 여러 노선이 같은 구간을 지나면 평행 오프셋으로 나란히 그린다. 쌓는 순서는 구간 양 끝에서 갈라지는 방향(`_side_score`)으로 정해 **교차는 정류장 캡슐 안에서만** 생긴다. 경유점에서 교차가 보이면 경유점을 정류장 쪽으로 옮기거나 경로를 나눈다.
- 이름이 같아도 실제 정차 지점이 다르면 다른 노드: 구영리 `구영`(선바위·우미린·범서파출소 길, 713·753·1115) vs `범서중`(현대2차·우미린2차·범서중 길, 513·743), `태화강역`(1번 정류소, 713·743·753) vs `태화강역광장`(1115).
- 동서·남북 관계는 `test_rough_geography` 가 지킨다. 좌표를 옮기면 그 테스트와 **브라우저 렌더**(라벨·pill·철도 겹침)를 함께 본다. 옛 경로(시행 전)도 따로 렌더해 본다.
- 상호작용은 `static/js/route_map.js`(노선 강조·정류장 패널·A/B 전환·이벤트). JS 없이도 SVG 는 완성된 그림이고, 전환은 `?view=a|b` 링크로 동작한다.

**B. 노선별 정류장 목록** — `web/route_lines.py` `build_route_lines(today)`. `route_diagram` 의 경로에서 정류장만 뽑고, 시행 전 변경은 "10/3부터"/"10/2까지" 예고로 함께 보인다. 표시명은 `STOP_LABEL`, 링크는 UNIST → `/busno?bus=`, `ROUTE_MAP_STOP_LINK` → `/stops?stop_id=`(미리 선택·즉시 조회).

**A/B 카운터** — `services/route_map_ab.py`, `<data_dir>/route_map_ab.json`(날짜별, `locked_update_json`, git ignore). 노출 `view_a/b` 는 서버가, 전환 `switch_to_a/b`·조작 이벤트는 `POST /info/event`(sendBeacon)로 센다. 관리자 대시보드에 방식별 노출·전환·전환율.

- 텍스트(`VIA_STOPS`, `info.html` 표·배너)는 날짜 게이트가 없으므로 "10/3부터"처럼 문구에 시행일을 적는다.
- 테스트: `tests/web/test_route_diagram.py`(지도 규칙·지리·날짜 게이트·철도·상호작용 속성), `tests/web/test_route_map_page.py`(목록·A/B·`/stops` 미리 선택·관리자 표).
- 수정 후 `/info` 를 브라우저로 열어 두 방식을 모두 눈으로 확인한다.

## 7. 알려진 UI 결함 (2026-09-29)

| 항목 | 내용 | 위치 |
|---|---|---|
| `/unist` 자동 갱신이 1회 후 멈춤 | 바깥 `div#unist-grid` 에만 hx 속성이 있고, `outerHTML` 로 교체되는 조각의 `div#unist-grid` 에는 없다. 초기 렌더에서 같은 id 가 중첩되기도 한다 | `templates/unist_board.html`, `templates/unist_partial.html` |
| `/lite` 에 공지 배너 없음 | 743 공지 같은 운영 공지가 lite 사용자에게 보이지 않는다 | `templates/board_lite.html` |
| 변경이력 추가/삭제가 audit 되지 않음 | 다른 관리자 편집은 `_audit` 기록 | `routes/admin.py` changelog 핸들러 |
| 미사용 웹폰트 | SeoulNamsan 3종(약 3.4MB)이 번들에 있으나 참조 없음 | `static/vendor/fonts` |

## 8. 관리자 UI 규약

- 모든 폼에 `<input type="hidden" name="csrf_token" value="{{ session['csrf_token'] }}">`. fetch/XHR 은 `X-CSRFToken` 헤더.
- 흐름은 **POST → `flash(msg, "success"|"error")` → redirect (PRG)**. 파괴적 버튼은 `onclick="return confirm(...)"`.
- 편집 액션은 `_audit(action, **details)` 로 감사 로그를 남긴다.
- 장시간 작업은 SSE: POST 가 `job_id` 반환 → `EventSource` 가 `progress`/`done`/`error` 수신(`static/js/admin-recrawl.js`). 잡 상태는 **파일**에 둔다(워커 간 공유, [PM-015](../refactor/postmortems/PM-015-per-process-state-under-gunicorn.md)).
- 진행 표시 영역은 `aria-live="polite"`.

## 9. 접근성·성능 체크리스트

- [ ] 선택 UI 는 `<a>` 또는 `<select>` — 키보드 도달 가능.
- [ ] 모바일 인터랙티브 셀은 `role="button" tabindex="0" aria-expanded` + Enter/Space.
- [ ] 애니메이션은 `prefers-reduced-motion` 에서 끈다(flap 사례).
- [ ] 상태는 색 + 텍스트.
- [ ] 새 정적 자원은 `static/vendor/` 에 두고 CDN 을 쓰지 않는다.
- [ ] 무거운 자원이 추가되면 `/lite` 경로는 영향이 없는지 확인한다.
- [ ] 응답 시간은 `Server-Timing` 헤더(`web/timing.py` 의 `span()`)로 본다.
