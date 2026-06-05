---
status: designed
designer: opus
auditor_status: design-pass (T02 2026-06-01, F-9 fixed; 잔여 C-3는 FROZEN 면제)
last_updated: 2026-06-01
feature_id: F08
---

# F08 — 전체 시간표 컬러 그리드 (unist_timetable)

> 이 템플릿의 **모든 섹션**은 필수다. Executor는 슬롯을 채우되 섹션을 삭제하지 않는다. "해당 없음"은 명시적으로 적는다.

## 0. 한 줄 요약

- **As-is:** Streamlit 페이지(`infopages/unist_timetable.py`)에서 요일을 선택하면 모든 버스 노선의 시간표를 시(Hour) × 분(Minute) 컬러 배지 형식의 self-contained HTML로 생성해 `st.html()`로 표시한다.
- **To-be:** Flask GET 핸들러 `/timetable`이 쿼리스트링 `?day=0`을 받아 `bushexa.web.services.timetable.get_full_timetable(day)` 서비스를 호출하고, `BUS_COLORS` dict를 CSS 클래스로 전환한 Jinja2 템플릿에 직접 렌더링한다.

## 1. 사용자 시나리오

- **대상:** UNIST 통학버스 이용자 전체. 특정 요일의 모든 버스 노선 시간표를 한 눈에 비교하려는 의도.
- **정상 흐름 (Happy path):**
  1. 사용자가 `/timetable`에 접근한다 (쿼리스트링 없음).
  2. 서버가 현재 KST 요일 인덱스를 계산해 해당 요일의 전체 시간표를 기본값으로 렌더링한다.
  3. 사용자가 요일 버튼(예: Saturday)을 클릭한다 → `?day=1` GET 요청.
  4. 서버가 모든 버스 노선의 `timetable/{busno}.json`에서 해당 요일 첫 번째 출발지 시간표를 읽는다.
  5. 시간대(Hour)별로 버스 번호·분(Minute)을 모아 정렬하고, 각 버스 번호에 해당하는 CSS 클래스를 부여한다.
  6. Jinja2 템플릿이 범례(legend) + 시간표 그리드를 HTML로 렌더링해 반환한다.
- **엣지 케이스:**
  - `day` 파라미터가 0·1·2 범위를 벗어나면: `day=0`으로 강제 초기화한다.
  - 특정 버스의 `timetable/{busno}.json`을 읽는 데 실패하면: 해당 버스를 건너뛰고 나머지 버스 시간표는 정상 표시한다 (현재 구현의 `pass` 처리 유지, infopages/unist_timetable.py:69-71).
  - `schedules_by_hour`가 비어 있으면(모든 버스 JSON 읽기 실패): "No timetable data available." 메시지를 렌더링한다.
  - `ROUTEID`에 출발지 목록(`departure_dict[busno_str]`)이 비어 있는 버스가 있으면: 해당 버스를 건너뛴다.

## 2. 현재 구현 분석 (As-Is)

### 2.1 진입점 / 파일 / 라인 참조

- 진입점: `infopages/unist_timetable.py:30` — `page()` 함수
- 핵심 함수:
  - `page()`: infopages/unist_timetable.py:30-82 (UI + 오케스트레이션)
  - `generate_timetable_html()`: infopages/unist_timetable.py:84-169 (self-contained HTML 생성)
  - `highlight_bus_rows()`: infopages/unist_timetable.py:20-28 (Streamlit DataFrame 스타일러, 신규 구현에서 불필요)

### 2.2 사용된 Streamlit API 전수 목록

| API | 위치 | 용도 |
|---|---|---|
| `st.write(f"Current time is ...")` | infopages/unist_timetable.py:34 | 현재 KST 시각·요일 표시 |
| `st.segmented_control("Select weekday", options, default=options[weekday])` | infopages/unist_timetable.py:37 | 요일 선택 (Weekday/Saturday/Sunday/Holiday) |
| `st.warning("Please select a day of the week.")` | infopages/unist_timetable.py:40 | 요일 미선택 경고 |
| `st.info("No timetable data available.")` | infopages/unist_timetable.py:74 | 시간표 데이터 없음 안내 |
| `st.html(html_code)` | infopages/unist_timetable.py:82 | self-contained HTML 직접 삽입 |

### 2.3 데이터 흐름

- `get_time()` → `(day_of_week: int, hr: int, minute: int)` — KST 현재 시각, 공휴일 반영 요일 인덱스
- `get_busroute_info()` → `(busnos: list[str], departure_dict: dict[str, list[str]])` — ROUTEID에서 추출
  - `busnos = sorted([int(b) for b in busnos])` (infopages/unist_timetable.py:49) — 정수로 변환 후 정렬
- `get_timetable(busno, selected_weekday_idx, departure_point)` → `list[str]` ("HH:MM") — 버스별 반복 호출
- `schedules_by_hour: dict[str, list[tuple[str, int]]]` — `{hour_str: [(minute_str, busno_int), ...]}`
- `generate_timetable_html(schedules_by_hour, sorted_hours)` → `str` (완성된 HTML 문자열)
  - 내부에서 `BUS_COLORS` dict 참조해 인라인 `style="color: {hex_color};"` 속성 생성
- `st.html(html_code)` — Streamlit iframe으로 삽입
- 캐싱: 미사용.
- 세션 상태: 미사용.

### 2.4 의존 모듈 그래프

```text
infopages/unist_timetable.py
  ├── src.constants.WEEKDAY_STR
  ├── BUS_COLORS (파일 내 상수, infopages/unist_timetable.py:12-18)
  ├── src.tools.get_timetable()       → timetable/{busno}.json
  ├── src.tools.get_time()            → src.tools.get_now(), src.tools.get_weekday()
  │     └── src.crawl.is_holiday()
  └── src.tools.get_busroute_info()  → src.constants.ROUTEID
```

### 2.5 관찰된 결함·악취

- **`generate_timetable_html`이 Python 코드 내부에 HTML/CSS를 하드코딩**: self-contained HTML 생성기(infopages/unist_timetable.py:84-169)가 Python 문자열로 CSS와 HTML을 관리한다. 유지보수가 어렵고 Jinja2 템플릿 이식이 더 적합하다.
- **인라인 style 속성으로 색상 관리**: `style="color: {hex_color};"` 패턴이 Python 코드 안에 있어 디자인 변경 시 코드 수정 필요. CSS 클래스(`.bus-513`, `.bus-713` 등)로 전환한다.
- **`highlight_bus_rows` 함수 미사용**: infopages/unist_timetable.py:20-28에 정의되어 있으나 `page()` 내부 실제 렌더링 경로에서 호출되지 않는다 (DataFrame 스타일러용으로 남아있으나 `st.html` 경로에서 불필요). 데드코드.
- **`textwrap.dedent` 사용이 불필요**: `generate_timetable_html`의 HTML 템플릿이 `textwrap.dedent`로 처리되는데(infopages/unist_timetable.py:168), Jinja2 템플릿으로 이전하면 이 패턴이 자연히 제거된다.
- **비UI 모듈에서 `import streamlit as st`**: `src/tools.py:12` 참조. Flask 환경 오염 (F02와 공통).

## 3. 외부 의존성

### 3.1 외부 API

해당 없음. 이 페이지는 외부 API를 호출하지 않는다.

### 3.2 데이터베이스

해당 없음. DB 접근 없음.

### 3.3 정적 파일

- `timetable/{busno}.json` — 버스번호별 JSON 시간표 파일.
  - 대상 파일: `timetable/513.json`, `timetable/713.json`, `timetable/743.json`, `timetable/753.json`, `timetable/1115.json`
  - 각 버스의 첫 번째 출발지(`departure_dict[busno_str][0]`) 시간표만 사용.
  - `src/tools.py:get_timetable:130` 참조

## 4. 새 구현 매핑 (To-Be)

### 4.1 URL & HTTP 메서드

- `GET /timetable` — 쿼리스트링: `?day={0|1|2}`
  - `day` 파라미터 없으면 현재 KST 요일 인덱스를 기본값으로 사용.
  - `day`가 0·1·2 범위 밖이면 `day=0`으로 강제 초기화.

### 4.2 Flask 라우트 / 핸들러 시그니처

```python
# bushexa/web/routes/timetable.py
from flask import Blueprint, request, render_template
from bushexa.web.services.timetable import get_full_timetable_data

bp = Blueprint("timetable", __name__)

@bp.route("/timetable")
def timetable_page() -> str:
    day = request.args.get("day", default=None, type=int)
    ctx = get_full_timetable_data(day=day)
    return render_template("timetable.html", **ctx)
```

### 4.3 템플릿 & 정적 자원

- `bushexa/web/templates/timetable.html` — 메인 템플릿
  - `bushexa/web/templates/_base.html` 상속
  - 현재 시각 표시: `<p class="current-time">{{ current_time }}</p>` (KST)
  - 요일 선택: `<nav class="day-selector">` + `<a href="?day=0">` 버튼 3개 (active 클래스로 현재 선택 강조)
  - 범례(legend): `{% for bus_no in bus_legend %}<span class="bus-badge bus-{{ bus_no }}">{{ bus_no }}</span>{% endfor %}`
  - 시간표 그리드:
    ```
    <table class="timetable-table">
      <thead><tr><th>Hour</th><th>Minutes</th></tr></thead>
      <tbody>
        {% for row in timetable_rows %}
        <tr class="timetable-row">
          <td>{{ row.hour }}</td>
          <td>
            {% for dep in row.departures %}
            <span class="bus-badge bus-{{ dep.busno }}">{{ dep.minute }} ({{ dep.busno }})</span>
            {% endfor %}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    ```
  - 데이터 없음: `{% if not timetable_rows %}<p>No timetable data available.</p>{% endif %}`
- 필요한 정적 JS/CSS:
  - `bushexa/web/static/css/timetable.css` — 테이블 스타일 + 버스 번호별 색상 클래스
    ```css
    /* BUS_COLORS → CSS 클래스 변환 */
    .bus-513 { color: #D32F2F; font-weight: bold; }
    .bus-713 { color: #388E3C; font-weight: bold; }
    .bus-743 { color: #1976D2; font-weight: bold; }
    .bus-753 { color: #7B1FA2; font-weight: bold; }
    .bus-1115 { color: #F57C00; font-weight: bold; }
    ```
  - `bushexa/web/static/js/timetable.js` — 요일 버튼 클릭 시 `?day=N` URL로 이동 (Vanilla JS, 또는 `<a href>` 직접 링크로 JS 불필요)

### 4.4 도메인 서비스 호출

- `bushexa.web.services.timetable.get_full_timetable_data(day)` → `TimetablePageContext` (아래 6.2 참조)
  - 내부에서 `bushexa.data.timetable.get_busroute_info()` 호출
  - 내부에서 각 버스별 `bushexa.data.timetable.get_timetable(busno, day, departure)` 호출
  - 현재 KST 시각은 `bushexa.data.timetable.get_time()` 사용

### 4.5 HTMX/SSE 동작 (실시간 화면만)

해당 없음. 이 페이지는 정적 시간표 표시 페이지이며 실시간 갱신이 불필요하다. 요일 전환은 일반 GET 링크로 처리한다.

## 5. 데이터 모델 변경 (있는 경우만)

해당 없음. 신규 테이블·컬럼·인덱스 없음. 기존 `timetable/*.json` 파일 구조 그대로 사용.

## 6. 인터페이스 계약

### 6.1 함수 시그니처 (신규)

```python
# bushexa/web/services/timetable.py
from __future__ import annotations
from bushexa.web.services.timetable import TimetablePageContext

def get_full_timetable_data(day: int | None) -> TimetablePageContext:
    """
    전체 시간표 페이지에 필요한 모든 컨텍스트를 계산한다.

    - day: 요일 인덱스 (0=평일, 1=토, 2=일/공휴일). None이면 현재 KST 요일 사용.
      0·1·2 범위 밖의 값은 0으로 강제 초기화한다.

    반환: TimetablePageContext
    """
    ...


# bushexa/data/timetable.py (F02와 공유)
def get_timetable(busno: int, weekday: int, departure: str) -> list[str]:
    """
    timetable/{busno}.json에서 해당 weekday·departure의 시간표를 반환한다.
    반환: "HH:MM" 문자열 목록.
    """
    ...


def get_busroute_info() -> tuple[list[str], dict[str, list[str]]]:
    """
    ROUTEID 상수에서 버스번호 목록과 버스별 출발지 목록을 추출한다.
    반환: (busnos, departure_dict) — busnos는 문자열 목록.
    """
    ...
```

### 6.2 데이터 타입 (dataclass / TypedDict)

```python
from dataclasses import dataclass, field
from typing import TypedDict


class DepartureEntry(TypedDict):
    minute: str    # "MM" 형식
    busno: int     # 예: 713


class TimetableRow(TypedDict):
    hour: str                          # "HH" 형식
    departures: list[DepartureEntry]   # 해당 시(Hour)의 모든 출발 항목 (분 오름차순 정렬)


@dataclass(frozen=True)
class TimetablePageContext:
    current_time: str           # "평일 (working day) 09:05" KST 현재 시각 문자열
    day_options: list[str]      # ["Weekday", "Saturday", "Sunday/Holiday"]
    selected_day: int           # 0, 1, 2
    bus_legend: list[int]       # 범례 버스번호 목록 (오름차순, 예: [513, 713, 743, 753, 1115])
    timetable_rows: list[TimetableRow]  # 빈 리스트이면 데이터 없음
```

## 7. Acceptance Checklist (Executor가 사용)

- [ ] AC-1: `GET /timetable?day=0` 요청 시 모든 버스 번호의 평일 시간표가 컬러 배지로 렌더링된다. (검증 방법: `pytest tests/routes/test_timetable.py::test_timetable_renders_weekday` 또는 `curl -s http://localhost:5000/timetable?day=0 | grep 'bus-713'`)
- [ ] AC-2: `day` 파라미터 없이 `GET /timetable` 접근 시 현재 KST 요일에 해당하는 시간표가 기본으로 렌더링된다. (검증 방법: `pytest tests/routes/test_timetable.py::test_timetable_default_day`)
- [ ] AC-3: `.bus-513`, `.bus-713` 등 CSS 클래스가 렌더링된 HTML에 존재하고, 인라인 style 속성으로 색상이 직접 지정되지 않는다 (CSS 클래스 전환 검증). (검증 방법: `pytest tests/routes/test_timetable.py::test_timetable_uses_css_class_not_inline_style`)
- [ ] AC-4: 현재 시각이 KST 기준으로 페이지 상단에 올바르게 표시된다. (검증 방법: 수동 브라우저 확인 또는 `pytest tests/services/test_timetable_service.py::test_current_time_kst`)
- [ ] AC-5: 모든 버스 JSON을 읽는 데 실패해도 HTTP 500이 아닌 "No timetable data available." 메시지가 포함된 HTTP 200을 반환한다. (검증 방법: `pytest tests/routes/test_timetable.py::test_timetable_all_json_missing`)

> Executor는 모든 AC를 ✅로 만들 때까지 task in-progress 유지. 보고 시 항목별 한 줄 근거 첨부.

## 8. 테스트 계획

### 8.1 단위 테스트 (pytest)

- `tests/unit/test_timetable_service.py`에 추가
  - `test_get_full_timetable_data_weekday`: `day=0`으로 호출 시 `selected_day=0`이고 `timetable_rows`가 비어 있지 않은지 확인 (mock `get_timetable` 사용)
  - `test_get_full_timetable_data_invalid_day`: `day=5`로 호출 시 `selected_day=0`으로 초기화되는지 확인
  - `test_get_full_timetable_data_missing_json`: 특정 버스 JSON 부재 시 해당 버스가 결과에서 제외되고 나머지는 정상 반환되는지 확인
  - `test_timetable_rows_sorted_by_hour_and_minute`: 반환된 `timetable_rows`의 hour가 오름차순이고 각 row의 `departures`가 minute 오름차순인지 확인

### 8.2 통합 테스트

- Flask test_client 시나리오 (`tests/routes/test_timetable.py`):
  - `GET /timetable` → HTTP 200, day_selector 포함 HTML 확인
  - `GET /timetable?day=1` → HTTP 200, `selected_day=1` 반영 확인
  - `GET /timetable?day=99` → HTTP 200, `day=0`으로 폴백 확인
- DB fixture: 해당 없음 (DB 미사용)

### 8.3 수동 검증 시나리오

1. 브라우저에서 `http://localhost:5000/timetable` 접근 → 페이지 상단에 현재 KST 시각 확인
2. 현재 요일에 해당하는 버튼이 활성(active) 상태인지 확인
3. 범례에 513, 713, 743, 753, 1115가 각각 고유한 색상으로 표시되는지 확인
4. "Saturday" 버튼 클릭 → URL이 `?day=1`로 변경되고 토요일 시간표가 렌더링되는지 확인
5. 각 행의 배지가 CSS 클래스(`.bus-713` 등)로 색상이 적용되어 있는지 브라우저 개발자 도구로 확인 (인라인 style 없음)

## 9. 변경 영향 범위

- F02 (busno): `get_timetable`, `get_busroute_info`, `get_time` 서비스 함수를 공유한다. `bushexa.data.timetable` 모듈이 두 feature에 동시 영향.
- F05 (running_table): `get_timetable` 공유.
- F07 (unist_board): `get_timetable`, `get_busroute_info` 공유. UNIST 출발 카드와 동일 데이터 소스.
- F01 (departure_board): `get_timetable` 공유 (출발 게시판이 timetable과 live data를 합성).
- breaking change: No — 기존 Streamlit 페이지와 신규 Flask 라우트는 독립적으로 공존 가능 (Stage 3 마이그레이션 전략 따름).

## 10. 미해결 질문 (있다면)

- `generate_timetable_html`이 각 버스의 첫 번째 출발지(`departure_dict[busno_str][0]`)만 사용하는 것이 의도된 동작인지 확인이 필요하다 (infopages/unist_timetable.py:55). 513번 버스의 경우 `departure_dict["513"] = ["덕하", "삼남"]`이므로 "덕하" 출발 시간표만 표시된다. 전체 시간표 뷰에서 방향 구분을 추가할지 현재 스펙으로 유지할지는 사용자 확인이 필요하다.
