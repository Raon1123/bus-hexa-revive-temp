---
status: designed
designer: opus
auditor_status: design-pass (T02 2026-06-01, F-9 fixed; 잔여 C-3는 FROZEN 면제)
last_updated: 2026-06-01
feature_id: F02
---

# F02 — 버스번호별 시간표 (busno)

> 이 템플릿의 **모든 섹션**은 필수다. Executor는 슬롯을 채우되 섹션을 삭제하지 않는다. "해당 없음"은 명시적으로 적는다.

## 0. 한 줄 요약

- **As-is:** Streamlit 페이지(`infopages/busno.py`)에서 segmented_control × 2와 selectbox로 버스번호·요일·출발지를 선택하면 시간표를 DataFrame으로 표시한다.
- **To-be:** Flask GET 핸들러 `/busno`가 쿼리스트링 `?bus=713&day=0&dep=UNIST`를 받아 Jinja2 템플릿에 시간표 데이터를 넘기고, HTML `<table>`로 렌더링한다.

## 1. 사용자 시나리오

- **대상:** UNIST 통학버스 이용자. 특정 버스번호로 오늘 또는 다른 요일의 출발 시각을 확인하려는 의도.
- **정상 흐름 (Happy path):**
  1. 사용자가 `/busno`에 접근한다 (쿼리스트링 없음).
  2. 서버는 현재 KST 시각을 계산해 기본 요일 인덱스를 결정하고, 버스 번호 목록·요일 선택·출발지 선택 UI를 렌더링한다.
  3. 사용자가 버스 번호(예: 713)를 선택한다 → `?bus=713` 포함 GET 요청.
  4. 서버는 해당 버스의 출발지 목록을 결정하고, 현재 요일 기본값과 함께 다시 렌더링한다.
  5. 사용자가 요일(예: Weekday)과 출발지(예: UNIST)를 선택한다 → `?bus=713&day=0&dep=UNIST` GET 요청.
  6. 서버가 `timetable/713.json`을 읽어 시간표 데이터를 구성하고 결과 테이블을 렌더링한다.
- **엣지 케이스:**
  - `bus` 파라미터가 없거나 유효하지 않은 값(`?bus=999`)이면: 기본 버스 선택 화면을 렌더링하고 경고 메시지를 표시한다.
  - `day` 파라미터가 0·1·2 범위를 벗어나면: `day=0`으로 강제 초기화한다.
  - `dep` 파라미터가 해당 버스의 유효 출발지 목록에 없으면: 첫 번째 출발지로 폴백하고 경고 메시지를 표시한다.
  - `timetable/{busno}.json` 파일이 없으면: HTTP 500 대신 사용자 친화적 오류 메시지(`시간표 파일을 찾을 수 없습니다`)를 렌더링한다.
  - 시간표 JSON의 해당 `weekday` + `dep` 키 조합이 비어 있으면: "등록된 시간표가 없습니다" 메시지를 테이블 대신 표시한다.

## 2. 현재 구현 분석 (As-Is)

### 2.1 진입점 / 파일 / 라인 참조

- 진입점: `infopages/busno.py:11` — `page()` 함수
- 핵심 함수: `page()` (전체 UI 및 로직 포함, infopages/busno.py:11-64)
- 헬퍼: `src/tools.py:get_timetable:126`, `src/tools.py:get_time:43`, `src/tools.py:get_busroute_info:228`

### 2.2 사용된 Streamlit API 전수 목록

| API | 위치 | 용도 |
|---|---|---|
| `st.write(f"Current time is ...")` | infopages/busno.py:15 | 현재 KST 시각·요일 표시 |
| `st.segmented_control("Select bus number", busnos, default=busnos[0])` | infopages/busno.py:17 | 버스번호 선택 (탭형 컨트롤) |
| `st.segmented_control("Select weekday", options, default=options[weekday])` | infopages/busno.py:21 | 요일 선택 (Weekday/Saturday/Sunday/Holiday) |
| `st.warning("Please select a day of the week.")` | infopages/busno.py:24 | 요일 미선택 경고 |
| `st.selectbox("Select departure of bus: 출발지 선택", terminals)` | infopages/busno.py:29 | 출발지 선택 드롭다운 |
| `st.warning("Please select a departure.")` | infopages/busno.py:32 | 출발지 미선택 경고 |
| `st.write("Timetable")` | infopages/busno.py:37 | 테이블 제목 출력 |
| `st.dataframe(df, column_config=config, width=300)` | infopages/busno.py:60 | Hour/Minute 시간표 테이블 렌더링 |
| `st.column_config.NumberColumn("Hour")` | infopages/busno.py:56 | 인덱스 컬럼 "Hour" 설정 |
| `st.column_config.Column("Minute")` | infopages/busno.py:57 | "Minute" 컬럼 설정 |

### 2.3 데이터 흐름

- `get_time()` → `(day_of_week: int, hr: int, minute: int)` — KST 현재 시각, 공휴일 반영 요일 인덱스
- `get_busroute_info()` → `(busnos: list[str], departure_dict: dict[str, list[str]])` — 전체 버스 번호 목록과 버스별 출발지 목록
- `get_timetable(busno: int, weekday: int, departure: str)` → `list[str]` ("HH:MM" 형식) — `timetable/{busno}.json`에서 읽음
- 캐싱: Streamlit `@st.cache_data` 미사용. 매 렌더마다 JSON 파일 직접 읽음.
- 세션 상태: 미사용. 선택값은 쿼리스트링·위젯 상태에만 존재.

### 2.4 의존 모듈 그래프

```text
infopages/busno.py
  ├── src.constants.WEEKDAY_STR
  ├── src.tools.get_timetable()       → timetable/{busno}.json 읽기
  ├── src.tools.get_time()            → src.tools.get_now(), src.tools.get_weekday()
  │     └── src.crawl.is_holiday()   → 공휴일 판별
  └── src.tools.get_busroute_info()  → src.constants.ROUTEID
```

### 2.5 관찰된 결함·악취

- **`src/tools.py`가 `import streamlit as st`를 포함** (`tools.py:12`): 비-UI 모듈이 Streamlit에 오염되어 있어, Flask 환경에서 임포트 시 런타임 오류 발생 가능. `get_timetable`, `get_time`, `get_busroute_info`를 이전할 때 tools.py에서 `st` import를 제거해야 한다.
- **`busnos`가 문자열 목록으로 반환되지만 `get_timetable`은 `int`를 요구**: `infopages/busno.py:35`에서 `int(busno)` 변환을 별도로 수행. 타입 불일치가 interface contract에 반영되지 않음.
- **`timetable` dict 키가 `hr` 변수와 충돌**: `infopages/busno.py:43`에서 outer scope의 `hr`(시각 정보)와 inner loop의 `hr` 변수가 동일 이름을 사용해 상태 오염 위험이 있다.
- **예외처리 부재**: `get_timetable` 호출 시 파일 없음(`FileNotFoundError`) 또는 키 없음(`KeyError`)에 대한 try/except가 없다.

## 3. 외부 의존성

### 3.1 외부 API

해당 없음. 이 페이지는 외부 API를 호출하지 않는다. 공휴일 판별(`is_holiday`)은 내부 로직 또는 로컬 데이터를 사용한다.

### 3.2 데이터베이스

해당 없음. DB 접근 없음.

### 3.3 정적 파일

- `timetable/{busno}.json` — 버스번호별 JSON 시간표 파일. 키 구조: `{weekday_idx: {departure: ["HH:MM", ...]}}`.
  - 대상 파일: `timetable/513.json`, `timetable/713.json`, `timetable/743.json`, `timetable/753.json`, `timetable/1115.json`
  - `src/tools.py:get_timetable:130` 참조

## 4. 새 구현 매핑 (To-Be)

### 4.1 URL & HTTP 메서드

- `GET /busno` — 쿼리스트링: `?bus={busno}&day={0|1|2}&dep={departure}`
  - 파라미터 모두 선택적. 없으면 기본값 적용 (bus=busnos[0], day=현재 KST 요일, dep=해당 버스 첫 번째 출발지).
  - 파라미터가 모두 유효하면 시간표 테이블 포함 렌더링.
  - 파라미터 일부만 제공되면 해당 파라미터까지 반영하여 나머지는 기본값으로 렌더링.

### 4.2 Flask 라우트 / 핸들러 시그니처

```python
# bushexa/web/routes/busno.py
from flask import Blueprint, request, render_template
from bushexa.web.services.busno import get_busno_page_data

bp = Blueprint("busno", __name__)

@bp.route("/busno")
def busno_page() -> str:
    bus = request.args.get("bus", default=None)
    day = request.args.get("day", default=None, type=int)
    dep = request.args.get("dep", default=None)
    ctx = get_busno_page_data(bus=bus, day=day, dep=dep)
    return render_template("busno.html", **ctx)
```

### 4.3 템플릿 & 정적 자원

- `bushexa/web/templates/busno.html` — 메인 템플릿
  - `bushexa/web/templates/_base.html` 상속 (`{% extends "_base.html" %}`)
  - 버스번호 선택: `<nav>` + `<a>` 버튼 목록 (active 클래스로 현재 선택 강조)
  - 요일 선택: `<nav>` + `<a>` 버튼 3개 (Weekday / Saturday / Sunday/Holiday)
  - 출발지 선택: `<select name="dep">` form 요소, GET 제출
  - 시간표: `<table class="timetable">` — thead(Hour/Minute), tbody 행 반복
  - 현재 시각 표시: `<p class="current-time">{{ current_time }}</p>`
  - 경고 메시지: `{% if warning %}` 블록
- 필요한 정적 JS/CSS:
  - `bushexa/web/static/css/busno.css` — 테이블 스타일
  - `bushexa/web/static/js/busno.js` — 버스번호/요일 클릭 시 URL 파라미터 갱신 후 GET 제출 (Vanilla JS, HTMX 불필요)

### 4.4 도메인 서비스 호출

- `bushexa.web.services.busno.get_busno_page_data(bus, day, dep)` → `BusnoPageContext` (아래 6.2 참조)
  - 내부에서 `bushexa.data.timetable.get_timetable(busno, weekday, departure)` 호출
  - 내부에서 `bushexa.data.timetable.get_busroute_info()` 호출
  - 현재 KST 시각은 `bushexa.data.timetable.get_time()` 또는 `datetime.datetime.now(tz=KST)` 사용

### 4.5 HTMX/SSE 동작 (실시간 화면만)

해당 없음. 이 페이지는 정적 결과 표시 페이지이며 실시간 갱신이 불필요하다. 모든 파라미터 변경은 일반 GET 폼 제출로 처리한다.

## 5. 데이터 모델 변경 (있는 경우만)

해당 없음. 신규 테이블·컬럼·인덱스 없음. 기존 `timetable/*.json` 파일 구조 그대로 사용.

## 6. 인터페이스 계약

### 6.1 함수 시그니처 (신규)

```python
# bushexa/web/services/busno.py
from __future__ import annotations
from bushexa.web.services.busno import BusnoPageContext

def get_busno_page_data(
    bus: str | None,
    day: int | None,
    dep: str | None,
) -> BusnoPageContext:
    """
    버스번호별 시간표 페이지에 필요한 모든 컨텍스트를 계산한다.

    - bus: 버스 번호 문자열 (예: "713"). None이면 busnos[0]으로 기본값 설정.
    - day: 요일 인덱스 (0=평일, 1=토, 2=일/공휴일). None이면 현재 KST 요일 사용.
    - dep: 출발지 문자열 (예: "UNIST"). None이면 해당 버스 첫 번째 출발지로 기본값 설정.

    반환: BusnoPageContext (timetable_rows가 빈 리스트이면 데이터 없음 상태)
    """
    ...


# bushexa/data/timetable.py
def get_timetable(busno: int, weekday: int, departure: str) -> list[str]:
    """
    timetable/{busno}.json에서 해당 weekday·departure의 시간표를 반환한다.
    반환: "HH:MM" 문자열 목록. 파일 없음 → FileNotFoundError, 키 없음 → KeyError.
    """
    ...


def get_busroute_info() -> tuple[list[str], dict[str, list[str]]]:
    """
    ROUTEID 상수에서 버스번호 목록과 버스별 출발지 목록을 추출한다.
    반환: (busnos, departure_dict) — busnos는 문자열 목록, departure_dict는 {busno_str: [departure, ...]}
    """
    ...


def get_time() -> tuple[int, int, int]:
    """
    현재 KST 시각을 (day_of_week, hour, minute)로 반환한다.
    day_of_week: 0=평일, 1=토요일, 2=일요일/공휴일 (is_holiday 반영).
    """
    ...
```

### 6.2 데이터 타입 (dataclass / TypedDict)

```python
from dataclasses import dataclass, field
from typing import TypedDict


class TimetableRow(TypedDict):
    hour: str        # "HH" 형식
    minutes: str     # "MM, MM, MM" 형식 (쉼표 구분)


@dataclass(frozen=True)
class BusnoPageContext:
    current_time: str               # "평일 (working day) 09:05" 형식 KST 현재 시각 문자열
    busnos: list[str]               # 전체 버스번호 목록 (예: ["513", "713", ...])
    selected_bus: str               # 현재 선택된 버스번호
    day_options: list[str]          # ["Weekday", "Saturday", "Sunday/Holiday"]
    selected_day: int               # 0, 1, 2
    terminals: list[str]            # 선택된 버스의 출발지 목록
    selected_dep: str               # 현재 선택된 출발지
    timetable_rows: list[TimetableRow]  # 빈 리스트이면 데이터 없음
    warning: str | None             # 경고 메시지. 없으면 None.
```

## 7. Acceptance Checklist (Executor가 사용)

- [ ] AC-1: `GET /busno?bus=713&day=0&dep=UNIST` 요청 시 시간표 테이블이 렌더링된다. (검증 방법: `pytest tests/routes/test_busno.py::test_busno_renders_timetable` 실행 또는 `curl -s http://localhost:5000/busno?bus=713&day=0&dep=UNIST | grep '<table'`)
- [ ] AC-2: `bus` 파라미터 없이 `GET /busno` 접근 시 기본 버스가 선택된 상태로 정상 응답(HTTP 200)한다. (검증 방법: `curl -o /dev/null -w "%{http_code}" http://localhost:5000/busno` → 200)
- [ ] AC-3: 유효하지 않은 버스번호(`?bus=9999`)로 요청 시 경고 메시지가 포함된 페이지가 렌더링되며 HTTP 200을 반환한다. (검증 방법: `pytest tests/routes/test_busno.py::test_busno_invalid_bus`)
- [ ] AC-4: 현재 시각이 KST 기준으로 페이지 상단에 올바르게 표시된다. (검증 방법: 수동 브라우저 확인 또는 `pytest tests/services/test_busno_service.py::test_current_time_kst`)
- [ ] AC-5: `timetable/713.json`이 없는 상태에서 요청 시 HTTP 500이 아닌 사용자 친화적 오류 페이지가 반환된다. (검증 방법: `pytest tests/routes/test_busno.py::test_busno_missing_json`)

> Executor는 모든 AC를 ✅로 만들 때까지 task in-progress 유지. 보고 시 항목별 한 줄 근거 첨부.

## 8. 테스트 계획

### 8.1 단위 테스트 (pytest)

- `tests/unit/test_busno_service.py`에 추가
  - `test_get_busno_page_data_defaults`: `bus=None, day=None, dep=None`으로 호출 시 busnos[0], 현재 요일, 첫 출발지가 기본값으로 설정되는지 확인
  - `test_get_busno_page_data_invalid_bus`: 유효하지 않은 bus값 입력 시 `warning` 필드가 None이 아닌지 확인
  - `test_get_busno_page_data_timetable_rows`: 유효한 파라미터로 호출 시 `timetable_rows`가 올바른 hour/minutes 형식인지 확인
  - `test_get_busno_page_data_missing_json`: JSON 파일 부재 시 `timetable_rows`가 빈 리스트이고 `warning`이 설정되는지 확인

### 8.2 통합 테스트

- Flask test_client 시나리오 (`tests/routes/test_busno.py`):
  - `GET /busno` → HTTP 200, `busnos` 목록 포함 HTML 렌더링 확인
  - `GET /busno?bus=713&day=0&dep=UNIST` → HTTP 200, `<table` 태그 포함 확인
  - `GET /busno?bus=9999` → HTTP 200, 경고 메시지 포함 확인
- DB fixture: 해당 없음 (DB 미사용)

### 8.3 수동 검증 시나리오

1. 브라우저에서 `http://localhost:5000/busno` 접근 → 페이지 상단에 현재 KST 시각 확인
2. 버스번호 버튼 클릭(예: 713) → URL이 `?bus=713`으로 변경되고 해당 버스 정보 표시 확인
3. 요일 버튼 클릭(예: Saturday) → URL이 `?bus=713&day=1`로 변경 확인
4. 출발지 선택(예: UNIST) → URL이 `?bus=713&day=1&dep=UNIST`로 변경되고 시간표 테이블 표시 확인
5. 테이블이 Hour 컬럼과 Minute 컬럼으로 구성되어 있고 정렬이 올바른지 확인

## 9. 변경 영향 범위

- F08 (unist_timetable): 동일한 `get_timetable`, `get_busroute_info`, `get_time` 서비스 함수를 공유한다. `bushexa.data.timetable` 모듈 설계가 두 feature에 동시 영향을 준다.
- F01 (departure_board): `get_busroute_info` 공유.
- F05 (running_table), F07 (unist_board): `get_timetable`, `get_busroute_info`, `get_time` 공유.
- breaking change: No — 기존 Streamlit 페이지와 신규 Flask 라우트는 독립적으로 공존 가능 (Stage 3 마이그레이션 전략 따름).

## 10. 미해결 질문 (있다면)

- `get_busroute_info()`가 반환하는 `busnos`가 문자열 목록인지 정수 목록인지 현재 구현(`src/tools.py:228-244`)에서 일관되지 않다 (ROUTEID의 `routes[0]`은 문자열 "713" 형태). 신규 서비스에서는 문자열 목록으로 통일하는 것으로 결정하되, `get_timetable` 호출 시 `int()` 변환 책임을 서비스 레이어에 둔다. (확인 대상: ADR 또는 데이터 레이어 설계 문서)
