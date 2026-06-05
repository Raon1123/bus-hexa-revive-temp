---
status: designed
designer: opus
auditor_status: design-pass (T01 2026-06-01, clean PASS)
last_updated: 2026-06-01
feature_id: F06
---

# F06 — 정류소별 버스 도착 정보 (Stops)

> 이 템플릿의 **모든 섹션**은 필수다. Executor는 슬롯을 채우되 섹션을 삭제하지 않는다. "해당 없음"은 명시적으로 적는다.

## 0. 한 줄 요약

- **As-is:** Streamlit 페이지(`infopages/stops.py`)가 selectbox로 정류소를 선택하면 `st.session_state`로 10초 캐시를 관리하며 울산 BIS API를 호출하고, Markdown 테이블을 출력한다. 자동 갱신 없음.
- **To-be:** Flask 라우트 `GET /stops`가 초기 HTML을 렌더링하고, 사용자가 정류소를 선택하면 HTMX `hx-get="/stops/partial?stop_id={id}"` 요청으로 해당 정류소 데이터만 폴링(10초)한다. 캐시는 서버 사이드 Flask-Caching(in-memory, TTL 10초)으로 처리한다.

## 1. 사용자 시나리오

- **누가:** UNIST 구성원이 특정 정류소에서 대기 중인 버스 도착 정보를 확인한다.
- **어떤 의도:** 관심 정류소를 선택하여 해당 정류소를 지나는 노선의 도착 예정 시각·현재 위치를 실시간으로 파악한다.

### 정상 흐름 (Happy path)

1. 사용자가 `http://<host>/stops`에 접속한다.
2. 서버가 `SERACH_STOPS` 기반 정류소 목록을 드롭다운으로 렌더링한다.
3. 사용자가 드롭다운에서 정류소를 선택하면 HTMX가 `GET /stops/partial?stop_id=196040234`를 즉시 요청한다.
4. 서버가 `crawl_busstop(stop_id)`를 호출하고, `ROUTEID` 필터 후 결과를 테이블로 렌더링한다.
5. HTMX가 10초마다 동일 URL을 재요청하여 `#stops-table` 영역을 갱신한다.
6. 사용자가 다른 정류소를 선택하면 HTMX가 새 `stop_id`로 즉시 재요청한다.

### 엣지 케이스

1. **BIS API 오류:** `crawl_busstop`이 빈 리스트를 반환하면 "운행 중인 버스가 없습니다." 메시지를 표시하고 폴링을 유지한다.
2. **첫 번째·두 번째 버스 간격 30분 초과:** `target_bus_list`가 2개 이상이고 두 번째 버스의 `arrival_time - 첫 번째 arrival_time > 1800`(초)이면 경고 배너를 표시한다.
3. **유효하지 않은 stop_id 파라미터:** `stop_id`가 `SERACH_STOPS`에 없으면 HTTP 400을 반환하고 오류 메시지를 표시한다.
4. **stop_id 미선택:** 쿼리 파라미터 없이 `/stops/partial`을 호출하면 HTTP 400을 반환한다.
5. **`ROUTEID` 미포함 노선:** BIS 응답에 `ROUTEID`에 없는 `route_id`가 있으면 해당 항목을 건너뛰고 나머지만 표시한다.

## 2. 현재 구현 분석 (As-Is)

### 2.1 진입점 / 파일 / 라인 참조

- 진입점: `infopages/stops.py:52` (`if __name__ == "__page__": busstop_page()`)
- 핵심 함수: `busstop_page()` (`infopages/stops.py:10-50`)
- 보조 함수: `pageblock_busstop(bus_list, route_str, verbose=True)` (`src/tools.py:161-184`)

### 2.2 사용된 Streamlit API 전수 목록

| API | 위치 | 용도 |
|---|---|---|
| `st.selectbox("정류소를 선택해주세요...", SERACH_STOPS, format_func=lambda x: STOP_IDS[x])` | `infopages/stops.py:11-13` | 정류소 선택 드롭다운 위젯 |
| `st.session_state['arrival']` (읽기/쓰기) | `infopages/stops.py:18,25,28,31` | 도착정보 10초 캐시 저장 |
| `st.session_state['timestamp']` (읽기/쓰기) | `infopages/stops.py:19,26,29` | 마지막 API 호출 시각 저장 (`HHMMSS` 문자열) |
| `st.session_state['stop_id']` (읽기/쓰기) | `infopages/stops.py:30` | 현재 선택된 정류소 ID 저장 |
| `st.error("운행 중인 버스가 없습니다...")` | `infopages/stops.py:38` | 빈 버스 목록 오류 메시지 표시 |
| `st.warning("첫 번째 버스와 두 번째 버스의 차이가 30분...")` | `infopages/stops.py:49` | 30분 간격 초과 경고 표시 |
| `st.write(table_str)` | `src/tools.py:182` | Markdown 테이블 렌더링 (`pageblock_busstop` 내부, `verbose=True`일 때) |

### 2.3 데이터 흐름

1. `st.selectbox` → `stop_id: str` (예: `"196040234"`)
2. `st.session_state` 캐시 확인:
   - `'arrival'` 키 없음 또는 경과 시간 > `UPDATE_THRESHOLD(=10)` 또는 `stop_id` 변경 → `crawl_busstop(str(stop_id))` 호출
   - 조건 불충족 → 캐시된 `st.session_state['arrival']` 사용
3. `crawl_busstop(stop_id: str)` (`src/crawl.py:125`) → `list[dict]` — 각 항목: `{route_id, present, vehicle_no, arrival_time}`(arrival_time 단위: 초)
4. `target_bus_list = [bus for bus in bus_list if bus['route_id'] in ROUTEID.keys()]` — ROUTEID 필터
5. `pageblock_busstop(target_bus_list, ROUTEID, verbose=True)` (`src/tools.py:161`) → Markdown 테이블 문자열 생성 및 `st.write()`로 출력
   - 내부에서 `pretty_time(arrival_time)` (`src/tools.py:195`) 호출 → `(str, int, int)` (표시용 문자열, 분, 초)
6. 경고 조건: `len(target_bus_list) > 2` 이고 두 번째 버스 `arrival_time - 첫 번째 arrival_time > WARNING_THRESHOLD(=30) * 60`

캐시 타임스탬프 비교: `int(now_time) - int(st.session_state['timestamp']) > UPDATE_THRESHOLD(=10)`
- `now_time`은 `get_timestr()`의 기본 포맷 `"%H%M%S"` 문자열. 예: `"143025"` → `int` 변환 후 단순 빼기. **자정 경계(예: 235959 → 000000) 시 음수가 되어 캐시 미갱신 결함 존재.**

### 2.4 의존 모듈 그래프

```text
infopages/stops.py
  ├── src.constants.ROUTEID
  ├── src.constants.STOP_IDS
  ├── src.constants.SERACH_STOPS
  ├── src.crawl.crawl_busstop(stopid: str)
  │     └── secret/key.txt  (API 키)
  │     └── http://openapi.its.ulsan.kr/UlsanAPI/getBusArrivalInfo.xo  (울산 BIS)
  └── src.tools.pageblock_busstop(bus_list, ROUTEID, verbose=True)
        ├── src.tools.pretty_time(arrival_time)
        └── st.write(table_str)  [streamlit 직접 의존]
      src.tools.get_timestr()  (캐시 타임스탬프)
```

### 2.5 관찰된 결함·악취

- **결함 1 — 자정 경계 캐시 오작동:** `infopages/stops.py:24`에서 `int(now_time) - int(st.session_state['timestamp']) > UPDATE_THRESHOLD`로 비교한다. `get_timestr()` 기본 포맷이 `"%H%M%S"`이므로 `235958 → 000002` 구간에서 결과가 음수(`2 - 235958 < 0`)가 되어 캐시를 갱신하지 않는다.
- **결함 2 — `UPDATE_THRESHOLD` 단위 불일치:** `infopages/stops.py:7`의 `UPDATE_THRESHOLD = 10`은 초(seconds) 단위이나, `HHMMSS` 정수 차이로 비교하므로 실제로는 "HHMMSS 정수 차 > 10"이다. 예: `143025 - 143015 = 10`은 통과, `143100 - 143059 = 41`은 1초 차이에도 통과. 단위 불일치로 의도한 캐시 동작이 보장되지 않는다.
- **결함 3 — `st.session_state` 멀티유저 미지원:** Streamlit `session_state`는 세션 격리되나 Flask 전환 시 서버 사이드 캐싱이 없으면 전 사용자가 캐시를 공유하거나(in-memory 전역) 각 요청마다 API를 호출한다. TTL 10초 캐시를 stop_id 단위로 Flask-Caching에 명시적으로 구현한다.
- **결함 4 — `pageblock_busstop`의 Streamlit 직접 의존:** `src/tools.py:182`에서 `st.write(table_str)`을 호출한다. Flask 환경에서는 import 오류 없이 실행될 수 있으나, Streamlit 컨텍스트가 없으면 경고 또는 silent 무작동 발생. 서비스 레이어에서는 이 함수를 사용하지 않고 Jinja2 템플릿으로 대체한다.
- **안티패턴 1 — `WARNING_THRESHOLD` 조건 오류:** `infopages/stops.py:41`에서 `len(target_bus_list) > 2`이어야 하나 실제로는 인덱스 0, 1을 참조하므로 `len(target_bus_list) >= 2`가 올바른 조건이다. 버스가 정확히 2개일 때 경고가 표시되지 않는다.
- **안티패턴 2 — 정류소 ID 오타:** `src/constants.py:55`에서 상수 이름이 `SERACH_STOPS`(Search 오타)다. 신규 코드에서는 `SEARCH_STOPS`로 수정한다.

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
  | `stopid` | 사용자 선택값 | `SERACH_STOPS` 목록 중 하나 |
- **응답 형식:** XML (`<row>` 집합)
- **응답 필드:** `routeid`, `presentstopnm`, `vehicleno`, `arrivaltime` (단위: 초)
- **오류 응답:** HTTP 200 + 빈 `<row>` 집합 또는 `requests.exceptions.RequestException` → `src/crawl.py:145-147`에서 예외 시 빈 리스트 반환.

### 3.2 데이터베이스

- 해당 없음. 이 페이지는 DB를 읽거나 쓰지 않는다.

### 3.3 정적 파일

- `secret/key.txt` — 울산 BIS API 키 (gitignored)
- `secret/holiday_{year}.json` — 공휴일 캐시 (`get_weekday` 내부 `is_holiday` 경유, 이 페이지에서는 직접 사용 없음)

## 4. 새 구현 매핑 (To-Be)

### 4.1 URL & HTTP 메서드

| URL | 메서드 | 설명 |
|---|---|---|
| `/stops` | GET | 전체 페이지 렌더링 (정류소 선택 드롭다운 + 빈 결과 컨테이너) |
| `/stops/partial` | GET | HTMX 폴링 대상: `?stop_id={id}` 파라미터, 테이블 rows만 반환 |

### 4.2 Flask 라우트 / 핸들러 시그니처

```python
# bushexa/web/routes/stops.py

from flask import Blueprint, render_template, request, abort
from bushexa.web.services.stops import get_stop_data, StopData
from bushexa.data.constants import SERACH_STOPS

bp = Blueprint("stops", __name__, url_prefix="/stops")


@bp.route("", methods=["GET"])
def stops_page() -> str:
    """정류소 선택 페이지 전체 렌더링."""
    return render_template("stops/index.html")


@bp.route("/partial", methods=["GET"])
def stops_partial() -> str:
    """
    HTMX 폴링용 부분 렌더링.
    stop_id 파라미터가 없거나 SERACH_STOPS에 없으면 HTTP 400 반환.
    """
    stop_id: str | None = request.args.get("stop_id")
    if stop_id is None or stop_id not in SERACH_STOPS:
        abort(400, description="유효하지 않은 stop_id입니다.")
    data: StopData = get_stop_data(stop_id=stop_id)
    return render_template("stops/partial.html", data=data)
```

### 4.3 템플릿 & 정적 자원

- `bushexa/web/templates/stops/index.html` — 전체 레이아웃. `<select id="stop-select">` 드롭다운에 `hx-get="/stops/partial"`, `hx-trigger="change"`, `hx-target="#stops-table"` 속성 부여. 결과 컨테이너: `<div id="stops-table">`.
- `bushexa/web/templates/stops/partial.html` — 테이블 `<tbody>` rows + 경고/오류 배너. `hx-get="/stops/partial?stop_id={{ data.stop_id }}"`, `hx-trigger="every 10s"`, `hx-swap="outerHTML"` 속성을 partial 컨테이너에 부여하여 자동 갱신.
- `bushexa/web/static/js/htmx.min.js` — HTMX 라이브러리

HTMX 드롭다운 연동 예시:
```html
<select id="stop-select"
        name="stop_id"
        hx-get="/stops/partial"
        hx-trigger="change"
        hx-include="#stop-select"
        hx-target="#stops-table"
        hx-swap="innerHTML">
  {% for sid in stop_list %}
  <option value="{{ sid }}">{{ stop_ids[sid] }}</option>
  {% endfor %}
</select>
<div id="stops-table"></div>
```

### 4.4 도메인 서비스 호출

```python
# bushexa/web/services/stops.py

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class BusArrivalRow:
    bus_number: str        # "513", "713" 등
    direction_str: str     # "513 삼남행 (울산역) 방면"
    arrival_str: str       # "5분 30초"
    present_stop: str      # 현재 정류소명
    vehicle_no: str        # 차량번호


@dataclass
class StopData:
    stop_id: str
    stop_name: str                    # STOP_IDS[stop_id]
    rows: list[BusArrivalRow]         # ROUTEID 필터 후 도착시각 오름차순
    has_no_bus: bool                  # rows 빈 경우 True
    warn_long_gap: bool               # 두 번째 버스까지 30분 초과 시 True
    error: str | None                 # API 실패 시 메시지


def get_stop_data(stop_id: str) -> StopData:
    """
    stop_id에 해당하는 정류소의 버스 도착 정보를 반환한다.
    서버 사이드 캐시(TTL 10초, stop_id 단위)를 사용한다.
    """
    ...
```

### 4.5 HTMX/SSE 동작

**1차안: HTMX 폴링**

- **초기 로드:** 드롭다운 변경 시 `hx-trigger="change"`로 즉시 요청. `GET /stops/partial?stop_id={id}`
- **자동 갱신:** partial 응답 컨테이너에 `hx-trigger="every 10s"` 부여. 선택된 stop_id로 10초마다 재요청.
- **부분 갱신 대상 selector:** `#stops-table` (드롭다운 아래 전체 결과 영역)
- **캐시:** 서버 사이드 Flask-Caching `@cache.cached(timeout=10, query_string=True)` 적용 → 동일 stop_id 10초 내 재요청은 캐시에서 반환. 타임스탬프 문자열 정수 비교 방식 제거.
- **실패 시 fallback:** partial 컨테이너에 `hx-on::after-request` 핸들러로 HTTP 오류 시 `#stops-error` 배너 표시. 마지막 성공 데이터 DOM 유지.
- **정류소 변경:** `hx-trigger="change"` 이벤트가 즉시 새 stop_id로 요청을 발생시키므로 별도 처리 불필요.

## 5. 데이터 모델 변경

- 해당 없음. 이 페이지는 DB를 읽거나 쓰지 않으며, 모델 변경이 없다.

## 6. 인터페이스 계약

### 6.1 함수 시그니처 (신규)

```python
def get_stop_data(stop_id: str) -> StopData:
    """
    stop_id에 해당하는 정류소 버스 도착 정보를 반환한다.

    Parameters
    ----------
    stop_id : str
        SERACH_STOPS 목록 내 정류소 ID. 예: "196040234"

    Returns
    -------
    StopData
        rows는 ROUTEID 필터 후 도착시각 오름차순.
        API 실패 시 rows는 빈 리스트, error 필드에 메시지 설정.
        두 번째 버스까지 30분(1800초) 초과 시 warn_long_gap=True.
    """
    ...


def filter_and_sort_arrivals(
    raw_list: list[dict],
    routeid_map: dict[str, tuple],
) -> list[BusArrivalRow]:
    """
    BIS API 원시 응답을 ROUTEID 필터·정렬하여 BusArrivalRow 리스트로 변환한다.
    routeid_map에 없는 route_id는 건너뛴다.
    """
    ...


def check_long_gap(rows: list[BusArrivalRow]) -> bool:
    """
    rows가 2개 이상이고 두 번째 버스의 도착까지 첫 번째보다 30분(1800초) 이상 차이 나면 True를 반환한다.
    rows 원소의 arrival_seconds 필드(int) 기준으로 계산한다.
    """
    ...
```

### 6.2 데이터 타입 (dataclass)

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class BusArrivalRow:
    bus_number: str        # 노선번호 문자열
    direction_str: str     # 방향 포함 표시 문자열
    arrival_str: str       # "N분 M초" 형식 표시용
    arrival_seconds: int   # 원시 초 단위 도착시간 (정렬·비교용)
    present_stop: str      # 현재 정류소명
    vehicle_no: str        # 차량번호


@dataclass
class StopData:
    stop_id: str
    stop_name: str                 # STOP_IDS[stop_id] 값
    rows: list[BusArrivalRow]      # arrival_seconds 오름차순
    has_no_bus: bool               # rows가 비어있으면 True
    warn_long_gap: bool            # 두 번째 버스까지 1800초 초과 시 True
    error: str | None              # API 실패 메시지, 정상 시 None
```

## 7. Acceptance Checklist

- [ ] AC-1: `GET /stops` 요청 시 HTTP 200과 정류소 선택 드롭다운(`<select>`)이 포함된 HTML을 반환한다. (검증 방법: `pytest -k test_stops_page_returns_200_with_select`)
- [ ] AC-2: `GET /stops/partial?stop_id=196040234` 요청 시 HTTP 200과 테이블 행이 포함된 HTML을 반환한다. (검증 방법: `pytest -k test_stops_partial_valid_stop_id`)
- [ ] AC-3: `stop_id` 파라미터가 없거나 `SERACH_STOPS`에 없는 값이면 HTTP 400을 반환한다. (검증 방법: `pytest -k test_stops_partial_invalid_stop_id_returns_400`)
- [ ] AC-4: 동일 `stop_id`로 10초 내 연속 요청 시 BIS API가 1회만 호출된다(캐시 동작). (검증 방법: `crawl_busstop` mock 후 `pytest -k test_stops_cache_hit_single_api_call`)
- [ ] AC-5: rows가 2개 이상이고 두 번째 버스 도착까지 1800초 이상일 때 `warn_long_gap=True`가 반환되고 경고 배너가 렌더링된다. (검증 방법: `pytest -k test_stops_warn_long_gap`)
- [ ] AC-6: `partial.html` 컨테이너에 `hx-trigger="every 10s"` 속성이 존재한다. (검증 방법: `grep -q 'hx-trigger="every 10s"' bushexa/web/templates/stops/partial.html`)

> Executor는 모든 AC를 ✅로 만들 때까지 task in-progress 유지. 보고 시 항목별 한 줄 근거 첨부.

## 8. 테스트 계획

### 8.1 단위 테스트 (pytest)

파일: `tests/unit/test_stops_service.py`

- `test_filter_and_sort_arrivals_excludes_unknown_route_id` — `ROUTEID`에 없는 route_id 항목이 결과에서 제외되는지 확인
- `test_filter_and_sort_arrivals_sorts_by_arrival_seconds` — 도착시각 오름차순 정렬 확인
- `test_check_long_gap_true_when_gap_over_1800s` — 두 버스 간격이 1800초 초과 시 `True` 반환 확인
- `test_check_long_gap_false_when_one_bus` — 버스가 1개이면 `False` 반환 확인
- `test_get_stop_data_api_failure_returns_empty_rows` — `crawl_busstop` mock이 빈 리스트 반환 시 `StopData.has_no_bus == True` 확인
- `test_get_stop_data_cache_prevents_duplicate_api_call` — 동일 stop_id 10초 내 재호출 시 `crawl_busstop`이 1회만 호출되는지 확인

### 8.2 통합 테스트

파일: `tests/integration/test_stops_routes.py`

- Flask `test_client`로 `GET /stops` → HTTP 200, `<select>` 태그 포함 확인
- Flask `test_client`로 `GET /stops/partial?stop_id=196040234` → HTTP 200 확인
- Flask `test_client`로 `GET /stops/partial` (파라미터 없음) → HTTP 400 확인
- `crawl_busstop`을 `pytest.monkeypatch`로 교체하여 캐시 TTL 동작 검증

DB fixture: 해당 없음 (이 페이지는 DB를 사용하지 않음)

### 8.3 수동 검증 시나리오

1. `uv run bushexa serve` 실행 후 `http://localhost:5000/stops` 접속
2. 드롭다운에서 `울산과학기술원 (경유)` 선택 → 테이블이 즉시 갱신되는지 확인
3. 10초 대기 후 테이블이 자동 갱신되는지 브라우저 DevTools Network 탭에서 `/stops/partial?stop_id=196040234` 요청 확인
4. 다른 정류소 선택 시 즉시 새 데이터로 교체되는지 확인
5. 브라우저 오프라인 모드 전환 후 오류 배너 표시 및 기존 데이터 유지 확인

## 9. 변경 영향 범위

- **F01-departure-board.md** — `crawl_busstop` 공통 의존. 캐싱 정책(stop_id별 TTL 10초)이 F01의 캐싱 방식(`196040234` 고정)과 일관성을 유지해야 한다.
- **F07-unist-board.md** — `crawl_busstop("196040234")` 동일 stop_id 사용. Flask-Caching 설정을 공유 가능.
- **breaking change:** Yes. Streamlit `busstop_page()` 함수가 제거되고 Flask 라우트로 대체된다. `st.session_state` 캐시 로직이 서버 사이드 Flask-Caching으로 완전히 교체된다.

## 10. 미해결 질문

- **Q1:** Flask-Caching의 캐시 백엔드를 `SimpleCache`(개발, 단일 프로세스)와 `RedisCache`(운영, 멀티 프로세스)로 분기할지, 또는 단순 `SimpleCache`만 사용할지 결정 필요. → `config.py` 환경변수(`CACHE_TYPE`)로 분기하는 방안 검토.
- **Q2:** `SERACH_STOPS` 오타(`SERACH` → `SEARCH`) 수정 시 기존 `src/constants.py`를 직접 수정할지, 신규 `bushexa/data/constants.py`에서만 수정할지 확인 필요. (Stage 2 이후 결정 예정)
- **Q3:** `arrival_time` 필드 단위가 초(seconds)인지 확인 필요. `src/crawl.py`의 파싱 로직과 API 문서(DOCX) 비교 후 `BusArrivalRow.arrival_seconds` 변환 로직에 반영.
