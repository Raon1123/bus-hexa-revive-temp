---
status: designed
designer: opus
auditor_status: design-pass (T01 2026-06-01, clean PASS)
last_updated: 2026-06-01
feature_id: F01
---

# F01 — 출발 게시판 (Departure Board)

> 이 템플릿의 **모든 섹션**은 필수다. Executor는 슬롯을 채우되 섹션을 삭제하지 않는다. "해당 없음"은 명시적으로 적는다.

## 0. 한 줄 요약

- **As-is:** Streamlit 페이지(`infopages/departure_board.py`)가 매 렌더링마다 울산 BIS API를 동기 호출하여 시간표+실시간 도착정보를 HTML 테이블로 출력한다. 자동 갱신 없음.
- **To-be:** Flask 라우트 `GET /board`가 초기 HTML을 렌더링하고, HTMX `hx-trigger="every 15s"`로 `GET /board/partial`을 폴링하여 테이블 영역만 부분 갱신한다. SSE는 옵션 2로 별도 메모.

## 1. 사용자 시나리오

- **누가:** UNIST 구성원(학생·교직원)이 통학버스 출발 시각을 확인한다.
- **어떤 의도:** 현재 시각 기준 앞으로 도착할 버스를 노선번호·도착시각·현재위치 순으로 파악한다.

### 정상 흐름 (Happy path)

1. 사용자가 브라우저에서 `http://<host>/board`에 접속한다.
2. 서버는 현재 KST 요일·시각을 계산하고, 모든 노선의 시간표에서 미래 출발편을 수집한다.
3. 서버는 울산 BIS API(`stop_id=196040234`)에서 실시간 버스 목록을 조회하여 시간표와 병합한다.
4. 최대 10개 항목을 도착시각 오름차순으로 정렬하여 HTML 테이블을 렌더링한다.
5. 브라우저가 페이지를 표시하면 HTMX가 15초 후 `GET /board/partial`을 자동 요청한다.
6. 서버는 부분 렌더링(테이블 행 집합)만 반환하고, HTMX가 `#board-table` 영역을 교체한다.
7. 갱신 사이클이 반복된다.

### 엣지 케이스

1. **BIS API 실패:** `crawl_busstop`이 빈 리스트를 반환하거나 예외를 발생시키면 시간표 전용 데이터만 렌더링하고, 테이블 상단에 "실시간 정보 없음" 배너를 표시한다.
2. **오늘 운행 종료:** 미래 출발편이 없고 실시간 버스도 없으면 `notify_lastbus("★오늘 운행 종료☆")` 메시지만 표시한다.
3. **시간표 JSON 누락:** `timetable/{busno}.json`이 없으면 `FileNotFoundError`를 잡아 503을 반환하고 오류 로그를 남긴다.
4. **HTMX 폴링 중 네트워크 단절:** `hx-swap-oob`와 별도 오류 컨테이너를 사용하여 마지막 성공 데이터를 보존한 채 재시도 메시지를 표시한다.
5. **`ROUTEID` 조회 실패(KeyError):** `route_id`가 `ROUTEID`에 없는 버스가 BIS 응답에 포함되면 해당 항목을 건너뛰고 처리를 계속한다.

## 2. 현재 구현 분석 (As-Is)

### 2.1 진입점 / 파일 / 라인 참조

- 진입점: `infopages/departure_board.py:148` (`if __name__ == "__page__": board_page()`)
- 핵심 함수: `board_page()` (`infopages/departure_board.py:13-95`)
- 보조 함수: `html_timetable()` (`infopages/departure_board.py:98-145`)

### 2.2 사용된 Streamlit API 전수 목록

| API | 위치 | 용도 |
|---|---|---|
| `st.write(f"Current time is ...")` | `infopages/departure_board.py:17` | 현재 요일·시각 텍스트 출력 |
| `st.warning(notify_lastbus)` | `infopages/departure_board.py:46` | 운행 종료 경고 메시지 표시 |
| `st.error("Error while fetching ...")` | `infopages/departure_board.py:53` | BIS API 오류 메시지 표시 |
| `st.warning("운행 중인 버스가 없습니다...")` | `infopages/departure_board.py:57` | 실시간 버스 없음 경고 표시 |
| `st.write("Timetable")` | `infopages/departure_board.py:84` | "Timetable" 섹션 헤더 출력 |
| `st.markdown(html_str, unsafe_allow_html=True)` | `infopages/departure_board.py:95` | 커스텀 HTML 테이블 렌더링 |

### 2.3 데이터 흐름

1. `get_time()` (`src/tools.py:43`) → `(weekday: int, hr: int, minute: int)` — KST 기준 현재 요일(0=평일, 1=토, 2=일/공휴일)·시각 반환
2. `get_busroute_info()` (`src/tools.py:228`) → `(busnos: list[str], departure_dict: dict[str, list[str]])` — `ROUTEID` 상수에서 노선번호 목록과 출발지 매핑 추출
3. `get_timetable(bus_number: int, weekday: int, departure: str)` (`src/tools.py:126`) → `list[str]` (`["HH:MM", ...]`) — `timetable/{busno}.json`에서 해당 요일·출발지 시간표 로드
4. `is_not_early(arrival_time: str, hr, minute)` (`src/tools.py:212`) → `bool` — 현재 시각보다 미래인지 필터
5. `crawl_busstop("196040234")` (`src/crawl.py:125`) → `list[dict]` — 울산 BIS API XML 파싱, 각 항목은 `{route_id, present, vehicle_no, arrival_time}`(단위: 초)
6. `get_timestr(get_now([0,0,int(arrival_time)]), "%H:%M")` (`src/tools.py:52`) — 초 단위 도착시간을 HH:MM 문자열로 변환
7. `VIA_STOPS[bus_number][terminal.split()[0]]` (`src/constants.py:36`) — 경유지 문자열 조회
8. 캐싱 없음. 매 Streamlit 렌더링마다 BIS API를 직접 호출한다.

최종 `time_list` shape: `list[tuple[str, str, str, str]]` — `(arrival_time_str, bus_number, present_str, via_string)`

### 2.4 의존 모듈 그래프

```text
infopages/departure_board.py
  ├── src.constants.WEEKDAY_STR
  ├── src.constants.ROUTEID
  ├── src.constants.VIA_STOPS
  ├── src.crawl.crawl_busstop(stopid="196040234")
  │     └── secret/key.txt  (API 키)
  │     └── http://openapi.its.ulsan.kr/UlsanAPI/getBusArrivalInfo.xo  (울산 BIS)
  ├── src.scripts.notify_lastbus  (문자열 상수)
  ├── src.tools.get_time()
  │     └── src.tools.get_now()  (KST datetime)
  │     └── src.tools.get_weekday()
  │           └── src.crawl.is_holiday()
  │                 └── secret/holiday_{year}.json
  ├── src.tools.get_timetable(bus_number, weekday, departure)
  │     └── timetable/{busno}.json
  ├── src.tools.get_busroute_info()
  │     └── src.constants.ROUTEID
  ├── src.tools.get_now([0,0,int(arrival_time)])
  ├── src.tools.get_timestr(now, "%H:%M")
  └── src.tools.is_not_early(arrival_time, hr, minute)
```

### 2.5 관찰된 결함·악취

- **결함 1 — KeyError 미방어:** `infopages/departure_board.py:64-65`에서 `ROUTEID[route_id]`를 직접 인덱싱하나, BIS API가 `ROUTEID`에 없는 `route_id`를 반환하면 `KeyError`로 페이지가 500 오류 없이 Streamlit 예외 화면을 출력한다.
- **결함 2 — 캐싱 부재:** 매 렌더링마다 `crawl_busstop`을 호출하므로 Streamlit의 rerun(위젯 상호작용 포함)마다 외부 API를 호출한다. BIS API 지연 시 사용자 대기가 늘어난다.
- **결함 3 — `arrival_time` 단위 혼용:** `infopages/departure_board.py:68`에서 `int(arrival_time)`을 초로 가정하여 `get_now([0,0,int(arrival_time)])`를 호출하나, 이 값이 실제로 초인지 문자열인지 코드 주석 없음. BIS API 응답 포맷 변경 시 오류 무음으로 전파된다.
- **결함 4 — `st.markdown(unsafe_allow_html=True)`:** `html_timetable()`이 생성하는 HTML에 사용자 입력이 없으므로 XSS 위험은 낮으나, Flask 이전 후에는 Jinja2 자동 이스케이프로 대체하여 해당 패턴을 제거한다.
- **안티패턴 1 — `crawl_timetable` 내부 `import streamlit`:** `src/crawl.py:326,401`에서 비-UI 모듈이 `import streamlit`을 호출한다. Flask 환경에서는 임포트 오류 또는 silent 부작용이 발생한다.
- **안티패턴 2 — 운행 종료 시 조기 반환:** `infopages/departure_board.py:46-47`에서 `time_list`가 비면 `return`하여 실시간 API 호출 자체를 건너뛴다. 시간표 누락과 BIS API 미응답을 구분하지 않는다.

## 3. 외부 의존성

### 3.1 외부 API

**울산 BIS 버스 도착 정보 API**

- **엔드포인트:** `http://openapi.its.ulsan.kr/UlsanAPI/getBusArrivalInfo.xo`
- **메서드:** GET
- **파라미터:**
  | 파라미터 | 값 | 설명 |
  |---|---|---|
  | `serviceKey` | `{API_KEY}` | `secret/key.txt`에서 로드 |
  | `pageNo` | `1` | 고정 |
  | `numOfRows` | `50` | 고정 |
  | `stopid` | `196040234` | 경유 정류소 ID (울산과학기술원 경유) |
- **응답 형식:** XML (`<row>` 집합)
- **응답 필드:** `routeid`, `presentstopnm`, `vehicleno`, `arrivaltime` (단위: 초)
- **오류 응답:** HTTP 200 + 빈 `<row>` 집합 또는 `requests.exceptions.RequestException`. `src/crawl.py:145-147`에서 예외 시 빈 리스트 반환.

**국토부 공공데이터 API (공휴일 조회)**

- **엔드포인트:** `http://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo`
- **메서드:** GET
- **파라미터:** `serviceKey`, `solYear`, `solMonth`
- **응답 형식:** XML (`<locdate>` 집합)
- **오류 응답:** 비정상 HTTP 또는 비어 있는 응답 → `secret/holiday_{year}.json` 존재 시 캐시 파일 사용.

### 3.2 데이터베이스

- 해당 없음. 이 페이지는 DB를 읽거나 쓰지 않는다.

### 3.3 정적 파일

- `timetable/{busno}.json` — 노선별 시간표 JSON. `busno`는 `513`, `713`, `743`, `753`, `1115`.
  - 구조: `{ "0": { "덕하": ["HH:MM", ...], "삼남": [...] }, "1": {...}, "2": {...} }`
- `secret/key.txt` — 울산 BIS API 키 (gitignored)
- `secret/holiday_{year}.json` — 공휴일 캐시 (gitignored)

## 4. 새 구현 매핑 (To-Be)

### 4.1 URL & HTTP 메서드

| URL | 메서드 | 설명 |
|---|---|---|
| `/board` | GET | 전체 페이지 렌더링 (초기 진입) |
| `/board/partial` | GET | HTMX 폴링 대상: 테이블 rows만 반환 |

### 4.2 Flask 라우트 / 핸들러 시그니처

```python
# bushexa/web/routes/board.py

from flask import Blueprint, render_template
from bushexa.web.services.board import get_board_data, BoardData

bp = Blueprint("board", __name__, url_prefix="/board")


@bp.route("", methods=["GET"])
def departure_board() -> str:
    """출발 게시판 전체 페이지."""
    data: BoardData = get_board_data()
    return render_template("board/index.html", data=data)


@bp.route("/partial", methods=["GET"])
def departure_board_partial() -> str:
    """HTMX 폴링용 부분 렌더링 — 테이블 행만 반환."""
    data: BoardData = get_board_data()
    return render_template("board/partial.html", data=data)
```

### 4.3 템플릿 & 정적 자원

- `bushexa/web/templates/board/index.html` — 전체 레이아웃. `<div id="board-table">` 컨테이너에 `hx-get="/board/partial"`, `hx-trigger="every 15s"`, `hx-swap="innerHTML"` 속성 부여.
- `bushexa/web/templates/board/partial.html` — 테이블 `<tbody>` rows만 포함하는 partial. `index.html`에서 `{% include %}`로도 재사용 가능.
- `bushexa/web/static/js/htmx.min.js` — HTMX 라이브러리 (CDN 또는 로컬)
- `bushexa/web/static/css/board.css` — 테이블 스타일 (FIRST/SECOND 강조색 포함)

### 4.4 도메인 서비스 호출

```python
# bushexa/web/services/board.py

from dataclasses import dataclass
from typing import Literal
from datetime import datetime


@dataclass(frozen=True)
class DepartureRow:
    arrival_time: str          # "HH:MM"
    bus_number: str            # "513", "713" 등
    present: str               # "삼남행 출발예정" 또는 "천상 도착"
    via_string: str            # "구영리 - 굴화주공 - ..." 경유지 문자열
    source: Literal["live", "timetable"]


@dataclass
class BoardData:
    current_time: str          # "HH:MM"
    weekday_str: str           # "평일 (working day)" 등
    rows: list[DepartureRow]   # 최대 10개, 도착시각 오름차순
    error: str | None          # BIS API 오류 시 메시지, 정상 시 None
    is_last_bus: bool          # 운행 종료 여부


def get_board_data(*, now: datetime | None = None) -> BoardData:
    """출발 게시판에 필요한 데이터를 조회·병합하여 반환한다."""
    ...
```

### 4.5 HTMX/SSE 동작

**1차안: HTMX 폴링**

- **폴링 간격:** 15초 (`hx-trigger="every 15s"`)
- **요청 URL:** `GET /board/partial`
- **부분 갱신 대상 selector:** `#board-table` (테이블 `<tbody>` 전체)
- **HTMX 속성:**
  ```html
  <div id="board-table"
       hx-get="/board/partial"
       hx-trigger="every 15s"
       hx-swap="innerHTML">
    {# 초기 렌더링 시 partial 내용을 서버에서 직접 포함 #}
    {% include "board/partial.html" %}
  </div>
  ```
- **실패 시 fallback:** HTMX `hx-on::after-request` 핸들러에서 HTTP 오류 시 `#board-error` 배너에 "갱신 실패, 재시도 중..." 메시지를 표시한다. 마지막 성공 데이터는 DOM에 유지된다.

**2차안(옵션): SSE**

- `GET /sse/board` 엔드포인트가 `text/event-stream`을 반환하고, 서버에서 15초마다 `event: board-update` 이벤트를 push한다.
- 클라이언트는 `hx-ext="sse"`, `sse-connect="/sse/board"`, `sse-swap="board-update"` 속성으로 수신한다.
- 서버 측 SSE 구현은 F-SSE 문서에서 별도 설계한다.

## 5. 데이터 모델 변경

- 해당 없음. 이 페이지는 DB를 읽거나 쓰지 않으며, 모델 변경이 없다.

## 6. 인터페이스 계약

### 6.1 함수 시그니처 (신규)

```python
def get_board_data(*, now: datetime | None = None) -> BoardData:
    """
    현재 시각(KST) 기준 출발 게시판 데이터를 반환한다.

    Parameters
    ----------
    now : datetime | None
        테스트용 주입 시각. None이면 KST 현재 시각 사용.

    Returns
    -------
    BoardData
        rows는 도착시각 오름차순 최대 10개.
        BIS API 실패 시 rows는 시간표 기반 항목만 포함하고 error 필드에 메시지 설정.
    """
    ...


def build_timetable_rows(
    busnos: list[str],
    departure_dict: dict[str, list[str]],
    weekday: int,
    hr: int,
    minute: int,
) -> list[DepartureRow]:
    """시간표 JSON에서 현재 시각 이후 출발편을 DepartureRow 리스트로 변환한다."""
    ...


def merge_live_rows(
    timetable_rows: list[DepartureRow],
    live_buses: list[dict],
) -> list[DepartureRow]:
    """
    실시간 버스 데이터를 시간표 행과 병합한다.
    동일 (bus_number, terminal) 조합의 시간표 행을 제거하고 live 행으로 대체한다.
    ROUTEID에 없는 route_id는 건너뛴다.
    """
    ...
```

### 6.2 데이터 타입 (dataclass)

```python
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class DepartureRow:
    arrival_time: str          # "HH:MM" 형식
    bus_number: str            # 노선번호 문자열 ("513", "713", ...)
    present: str               # 현재 위치 + 상태 문자열
    via_string: str            # 경유지 설명 문자열
    source: Literal["live", "timetable"]


@dataclass
class BoardData:
    current_time: str          # "HH:MM"
    weekday_str: str           # WEEKDAY_STR[weekday] 값
    rows: list[DepartureRow]   # 도착시각 오름차순, 최대 10개
    error: str | None          # 오류 메시지, 정상 시 None
    is_last_bus: bool          # True이면 "오늘 운행 종료" 표시
```

## 7. Acceptance Checklist

- [ ] AC-1: `GET /board` 요청 시 HTTP 200과 `#board-table` 요소가 포함된 HTML을 반환한다. (검증 방법: `pytest -k test_board_page_returns_200` 실행)
- [ ] AC-2: `GET /board/partial` 요청 시 HTTP 200과 테이블 행(`<tr>`) 집합만 반환한다. (검증 방법: `pytest -k test_board_partial_returns_rows` 실행)
- [ ] AC-3: 울산 BIS API 호출이 실패할 때 시간표 기반 데이터만으로 페이지가 정상 렌더링되고 오류 배너가 표시된다. (검증 방법: `crawl_busstop`을 mock하여 빈 리스트 반환 후 `pytest -k test_board_bis_failure` 실행)
- [ ] AC-4: `time_list`가 비어 있고 live 버스도 없을 때 "오늘 운행 종료" 메시지가 렌더링된다. (검증 방법: `pytest -k test_board_last_bus_message` 실행)
- [ ] AC-5: `ROUTEID`에 없는 `route_id`가 BIS 응답에 포함될 때 KeyError 없이 해당 항목을 건너뛰고 나머지를 정상 출력한다. (검증 방법: `pytest -k test_board_unknown_route_id_skipped` 실행)
- [ ] AC-6: `board/index.html`에 `hx-get="/board/partial"`, `hx-trigger="every 15s"` 속성이 존재한다. (검증 방법: `grep -q 'hx-trigger="every 15s"' bushexa/web/templates/board/index.html`)

> Executor는 모든 AC를 ✅로 만들 때까지 task in-progress 유지. 보고 시 항목별 한 줄 근거 첨부.

## 8. 테스트 계획

### 8.1 단위 테스트 (pytest)

파일: `tests/unit/test_board_service.py`

- `test_build_timetable_rows_filters_past_departures` — `hr=23, minute=59`로 호출 시 빈 리스트 반환 확인
- `test_build_timetable_rows_includes_future_departures` — 현재 시각보다 1분 이후 시간표 항목이 포함되는지 확인
- `test_merge_live_rows_replaces_timetable_entry` — 동일 (bus_number, terminal) 시간표 행이 live 행으로 교체되는지 확인
- `test_merge_live_rows_skips_unknown_route_id` — `ROUTEID`에 없는 route_id 항목이 결과에 포함되지 않는지 확인
- `test_get_board_data_bis_failure_returns_timetable_only` — `crawl_busstop` mock이 빈 리스트 반환 시 `BoardData.error`가 None이 아니고 `rows`가 비어있지 않은지 확인
- `test_get_board_data_last_bus_sets_flag` — 미래 출발편과 live 버스가 모두 없을 때 `BoardData.is_last_bus == True` 확인

### 8.2 통합 테스트

파일: `tests/integration/test_board_routes.py`

- Flask `test_client`로 `GET /board` 요청 → HTTP 200, `text/html` Content-Type, `#board-table` 포함 확인
- Flask `test_client`로 `GET /board/partial` 요청 → HTTP 200, `<tr>` 태그 포함 확인
- `crawl_busstop`을 `pytest.monkeypatch`로 교체하여 오류 시나리오 재현

DB fixture: 해당 없음 (이 페이지는 DB를 사용하지 않음)

### 8.3 수동 검증 시나리오

1. `uv run bushexa serve` 실행 후 `http://localhost:5000/board` 접속
2. 노선번호·도착시각·현재위치가 표시되는지 확인
3. 15초 대기 후 테이블이 자동으로 갱신되는지 브라우저 DevTools Network 탭에서 `/board/partial` 요청 확인
4. 브라우저 오프라인 모드 전환 후 오류 배너 표시 확인
5. 운행이 없는 심야 시간대를 `now` 파라미터로 주입하여 "오늘 운행 종료" 메시지 확인

## 9. 변경 영향 범위

- **F06-stops.md** — `crawl_busstop` 공통 의존. 서비스 레이어 추상화 시 인터페이스 동일하게 유지.
- **F07-unist-board.md** — `crawl_busstop("196040234")` 동일 stop_id 사용. 캐싱 정책을 공유 가능.
- **breaking change:** Yes. Streamlit `board_page()` 함수가 제거되고 Flask 라우트로 대체되므로, 기존 Streamlit 멀티페이지 앱의 `pages/` 진입점에서 이 페이지를 참조하는 코드가 삭제되어야 한다.

## 10. 미해결 질문

- **Q1:** `crawl_busstop`의 `arrival_time` 필드 단위가 API 문서상 초(seconds)인지 분(minutes)인지 확인 필요. 현재 코드(`infopages/departure_board.py:68`)는 초로 가정하나 API 문서(DOCX) 원문 확인 필요. → 확인 후 `DepartureRow.arrival_time` 변환 로직에 반영.
- **Q2:** `timetable/{busno}.json` 파일을 `bushexa/data/timetable/`으로 이동할지, 현 `timetable/` 위치를 유지할지 결정 필요. (`01-overview.md` Stage 2 이후 결정 예정)
- **Q3:** 공휴일 캐시 파일(`secret/holiday_{year}.json`)이 없을 때 BIS API 즉시 호출 여부 — 개발 환경에서 네트워크 없을 경우 대안 전략 필요.
