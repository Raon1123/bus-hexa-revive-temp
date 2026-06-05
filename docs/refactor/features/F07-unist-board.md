---
status: designed
designer: opus
auditor_status: design-pass (T01 2026-06-01, clean PASS)
last_updated: 2026-06-01
feature_id: F07
---

# F07 — UNIST 버스 정보 카드 (UNIST Board)

> 이 템플릿의 **모든 섹션**은 필수다. Executor는 슬롯을 채우되 섹션을 삭제하지 않는다. "해당 없음"은 명시적으로 적는다.

## 0. 한 줄 요약

- **As-is:** Streamlit 페이지(`infopages/unist_board.py`)가 렌더링마다 `crawl_busstop("196040234")`와 `get_timetable()`을 호출하여 3열 카드 그리드를 출력한다. 자동 갱신 없음.
- **To-be:** Flask 라우트 `GET /unist`가 초기 HTML을 렌더링하고, HTMX `hx-trigger="every 30s"`로 `GET /unist/partial`을 폴링하여 카드 그리드 전체를 30초마다 부분 갱신한다.

## 1. 사용자 시나리오

- **누가:** UNIST 구성원이 UNIST 기점/경유 노선 전체의 다음 출발편을 한눈에 파악한다.
- **어떤 의도:** 각 노선·방향별로 실시간 도착 정보와 시간표 기반 출발 예정을 카드 형식으로 확인한다.

### 정상 흐름 (Happy path)

1. 사용자가 `http://<host>/unist`에 접속한다.
2. 서버가 `get_busroute_info()`로 노선 목록을 구성하고, `crawl_busstop("196040234")`로 실시간 데이터를 조회한다.
3. 각 노선·방향 카드에 실시간 위치 정보(있으면) + 시간표 기반 출발 예정을 합쳐 최대 2개 항목을 표시한다.
4. 3열 카드 그리드로 렌더링한다.
5. HTMX가 30초마다 `GET /unist/partial`을 요청하여 카드 그리드를 갱신한다.

### 엣지 케이스

1. **BIS API 오류:** `crawl_busstop`이 빈 리스트를 반환하면 시간표 기반 데이터만으로 카드를 렌더링하고 "실시간 정보 없음" 배너를 표시한다.
2. **오늘 운행 종료:** 특정 카드의 시간표 데이터가 없고 실시간 버스도 없으면 해당 카드에 `notify_lastbus("★오늘 운행 종료☆")` 메시지를 표시한다.
3. **`via_bus_list` 인덱스 범위 초과:** `infopages/unist_board.py:39`에서 `id >= len(via_bus_list)` 조건으로 건너뛰나, `from_bus_list`는 동일 방어가 없다. 서비스 레이어에서 명시적 bounds 검사를 수행한다.
4. **`get_route_id` 반환 None:** `busno`와 `direction`의 조합이 `ROUTEID`에 없으면 `get_route_id`가 `None`을 반환한다. 이 경우 해당 카드의 실시간 데이터를 건너뛰고 시간표만 표시한다.
5. **시간표 JSON 누락:** `timetable/{busno}.json`이 없으면 `FileNotFoundError`를 잡아 해당 카드에 오류 메시지를 표시하고 나머지 카드는 정상 렌더링한다.

## 2. 현재 구현 분석 (As-Is)

### 2.1 진입점 / 파일 / 라인 참조

- 진입점: `infopages/unist_board.py:103` (`if __name__ == '__page__': unist_buspage()`)
- 핵심 함수: `unist_buspage()` (`infopages/unist_board.py:13-101`)

### 2.2 사용된 Streamlit API 전수 목록

| API | 위치 | 용도 |
|---|---|---|
| `st.columns(COLS)` (COLS=3) | `infopages/unist_board.py:14` | 경유 노선용 3열 컬럼 생성 |
| `st.columns(COLS)` (COLS=3) | `infopages/unist_board.py:17` | 기점 노선용 3열 컬럼 생성 |
| `col.container()` | `infopages/unist_board.py:36` | 각 컬럼에서 tile(카드) 컨테이너 생성 |
| `tile.write(f"#### {busno} {direction}")` | `infopages/unist_board.py:53` | 카드 헤더(노선번호·방향) 출력 |
| `tile.write(f"{present} {arrival_time}")` | `infopages/unist_board.py:66` | 실시간 위치·도착시각 출력 |
| `tile.write(notify_lastbus)` | `infopages/unist_board.py:78` | 운행 종료 메시지 출력 |
| `tile.write(f"{time_list[i]} 출발 예정")` | `infopages/unist_board.py:81` | 시간표 기반 출발 예정 출력 |
| `tile.write(notify_lastbus)` | `infopages/unist_board.py:97` | from 노선 운행 종료 메시지 출력 |
| `tile.write(f"{time_list[i]} 출발 예정")` | `infopages/unist_board.py:100` | from 노선 시간표 출발 예정 출력 |

### 2.3 데이터 흐름

1. `get_time()` (`src/tools.py:43`) → `(weekday: int, hr: int, minute: int)` — KST 기준 현재 요일·시각
2. `get_busroute_info()` (`src/tools.py:228`) → `(_, departures: dict[str, list[str]])` — 노선번호별 출발지 목록
3. `departures` 순회로 두 그룹 분류:
   - `via_bus_list: list[tuple[str, str, str]]` — `(busno, departure, direction)`: "UNIST"가 **없는** 노선 (`val`에 "UNIST" 미포함). 513 노선이 해당. 양방향 각각 추가.
   - `from_bus_list: list[tuple[str, str, str]]` — `(busno, "UNIST", direction)`: "UNIST"가 **있는** 노선. 713, 743, 753, 1115 해당.
4. `crawl_busstop("196040234")` (`src/crawl.py:125`) → `list[dict]` — 경유 정류소(`196040234`) 실시간 버스 목록
5. via 카드 (id 0, 1): `get_route_id(busno, direction)` (`src/tools.py:187`) → `route_id: str | None`으로 실시간 버스 필터링 후 `pretty_time(arrival_time)` (`src/tools.py:195`) → `(str, int, int)` 변환
6. `get_timetable(int(busno), weekday, departure)` (`src/tools.py:126`) → `list[str]` — 시간표. 현재 시각 이후 필터링. 최대 `VISUALIZE(=2)` - live 카운트 개 표시.
7. from 카드 (id 3~5): 실시간 조회 없이 시간표만 사용. `get_timetable`로 미래 출발편 최대 `VISUALIZE(=2)`개 표시.
8. 캐싱 없음. 매 Streamlit 렌더링마다 `crawl_busstop` 호출.

### 2.4 의존 모듈 그래프

```text
infopages/unist_board.py
  ├── src.scripts.notify_lastbus  (문자열 상수)
  ├── src.crawl.crawl_busstop(stopid="196040234")
  │     └── secret/key.txt  (API 키)
  │     └── http://openapi.its.ulsan.kr/UlsanAPI/getBusArrivalInfo.xo  (울산 BIS)
  ├── src.tools.get_timetable(busno, weekday, departure)
  │     └── timetable/{busno}.json
  ├── src.tools.get_time()
  │     └── src.tools.get_now()  (KST datetime)
  │     └── src.tools.get_weekday()
  │           └── src.crawl.is_holiday()
  │                 └── secret/holiday_{year}.json
  ├── src.tools.get_route_id(busno, departure)
  │     └── src.constants.ROUTEID
  ├── src.tools.get_busroute_info()
  │     └── src.constants.ROUTEID
  └── src.tools.pretty_time(arrival_time)
```

### 2.5 관찰된 결함·악취

- **결함 1 — `from_bus_list` 인덱스 범위 미방어:** `infopages/unist_board.py:85`에서 `from_bus_list[id - 3]`를 직접 인덱싱한다. `id`는 `range(6)`(via 3 + from 3)에서 오나, `from_bus_list` 길이가 3 미만이면 `IndexError`가 발생한다. `ROUTEID`에 정의된 노선 수가 변경되면 무음 오류.
- **결함 2 — `print` 문 미제거:** `infopages/unist_board.py:33`에서 `print(f"Bus {key} - Departure: {val[0]}, Direction: {val[1]}")`가 운영 환경 로그를 오염시킨다.
- **결함 3 — `get_route_id` None 미방어:** `infopages/unist_board.py:44`에서 `get_route_id(busno, direction)`이 `None`을 반환할 수 있으나, 이후 `route_id == target_route_id` 비교에서 문제없이 동작하지만 의도하지 않은 매칭 방어가 없다.
- **결함 4 — via/from 분류 로직 역전:** `infopages/unist_board.py:25-31`에서 `"UNIST" in val`이면 `from_bus_list`에 추가하고, 아니면 `via_bus_list`에 추가한다. 변수명이 직관과 반대다: "UNIST 출발(from)" 노선은 실제로 UNIST에서 출발하는 노선(713, 743, 753, 1115)이고, "via" 노선은 UNIST를 경유하는 513이다. 코드 주석이 없어 혼동을 유발한다.
- **결함 5 — `via_row + from_row` 리스트 합산:** `infopages/unist_board.py:35`에서 `via_row + from_row`로 컬럼 6개를 합산한다. `via_row`와 `from_row` 각각 `COLS(=3)`개이므로 총 6개. `id`가 0, 1이면 via, 3 이상이면 from. `id == 2`일 때는 명시적으로 처리하지 않아 빈 카드가 렌더링된다(via_bus_list가 최대 2개이므로 `id=2`는 `continue`로 건너뜀).
- **안티패턴 1 — 캐싱 부재:** via 카드 루프(id=0, 1) 내부에서 매번 `crawl_busstop("196040234")`를 호출한다(`infopages/unist_board.py:56`). 동일 stop_id에 대해 카드 수만큼 중복 API 호출이 발생한다.
- **안티패턴 2 — 시간표 필터 인라인 로직:** `infopages/unist_board.py:72-73`, `90-91`에서 `int(t.split(':')[0]) > hr or (int(t.split(':')[0]) == hr and int(t.split(':')[1]) >= minute)` 조건이 반복된다. `is_not_early()` 함수가 이미 존재하나 활용하지 않았다.

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
  | `stopid` | `196040234` | 고정 (울산과학기술원 경유 정류소) |
- **응답 형식:** XML (`<row>` 집합)
- **응답 필드:** `routeid`, `presentstopnm`, `vehicleno`, `arrivaltime` (단위: 초)
- **오류 응답:** HTTP 200 + 빈 `<row>` 집합 또는 `requests.exceptions.RequestException` → `src/crawl.py:145-147`에서 예외 시 빈 리스트 반환.

**국토부 공공데이터 API (공휴일 조회)**

- **엔드포인트:** `http://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo`
- **메서드:** GET
- **파라미터:** `serviceKey`, `solYear`, `solMonth`
- **응답 형식:** XML (`<locdate>` 집합)
- **오류 응답:** 비정상 HTTP 또는 비어있는 응답 → `secret/holiday_{year}.json` 존재 시 캐시 파일 사용.

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
| `/unist` | GET | 전체 페이지 렌더링 (초기 진입) |
| `/unist/partial` | GET | HTMX 폴링 대상: 카드 그리드만 반환 |

### 4.2 Flask 라우트 / 핸들러 시그니처

```python
# bushexa/web/routes/unist.py

from flask import Blueprint, render_template
from bushexa.web.services.unist import get_unist_board_data, UnistBoardData

bp = Blueprint("unist", __name__, url_prefix="/unist")


@bp.route("", methods=["GET"])
def unist_board() -> str:
    """UNIST 버스 카드 전체 페이지."""
    data: UnistBoardData = get_unist_board_data()
    return render_template("unist/index.html", data=data)


@bp.route("/partial", methods=["GET"])
def unist_board_partial() -> str:
    """HTMX 폴링용 부분 렌더링 — 카드 그리드만 반환."""
    data: UnistBoardData = get_unist_board_data()
    return render_template("unist/partial.html", data=data)
```

### 4.3 템플릿 & 정적 자원

- `bushexa/web/templates/unist/index.html` — 전체 레이아웃. `<div id="unist-grid">` 컨테이너에 `hx-get="/unist/partial"`, `hx-trigger="every 30s"`, `hx-swap="innerHTML"` 속성 부여.
- `bushexa/web/templates/unist/partial.html` — 카드 그리드만 포함하는 partial. `index.html`에서 `{% include %}`로 초기 렌더링에 재사용.
- `bushexa/web/templates/unist/_card.html` — 개별 버스 카드 매크로. `busno`, `direction`, `entries`(최대 2개) 파라미터 수신.
- `bushexa/web/static/js/htmx.min.js` — HTMX 라이브러리
- `bushexa/web/static/css/unist.css` — 카드 그리드 스타일

HTMX 자동 갱신 컨테이너 예시:
```html
<div id="unist-grid"
     hx-get="/unist/partial"
     hx-trigger="every 30s"
     hx-swap="innerHTML">
  {% include "unist/partial.html" %}
</div>
```

### 4.4 도메인 서비스 호출

```python
# bushexa/web/services/unist.py

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class CardEntry:
    text: str                              # 표시할 한 줄 텍스트
    source: Literal["live", "timetable"]   # 데이터 출처


@dataclass(frozen=True)
class BusCard:
    busno: str                # 노선번호 ("513", "713", ...)
    direction: str            # 목적지 표시 ("삼남행 (울산역)", "명촌행 (시내)" 등)
    entries: list[CardEntry]  # 최대 2개 항목
    is_last_bus: bool         # 모든 entries가 없을 때 True


@dataclass
class UnistBoardData:
    cards: list[BusCard]      # via 카드 + from 카드 순서
    bis_error: bool           # BIS API 실패 시 True


def get_unist_board_data(*, now: datetime | None = None) -> UnistBoardData:
    """
    UNIST 버스 카드 그리드 데이터를 반환한다.
    crawl_busstop("196040234")을 1회만 호출하고 모든 카드에 공유한다.
    """
    ...
```

### 4.5 HTMX/SSE 동작

**1차안: HTMX 폴링**

- **폴링 간격:** 30초 (`hx-trigger="every 30s"`)
- **요청 URL:** `GET /unist/partial`
- **부분 갱신 대상 selector:** `#unist-grid` (카드 그리드 전체)
- **HTMX 속성:** `hx-swap="innerHTML"` — 카드 그리드 내부 전체 교체
- **실패 시 fallback:** `hx-on::after-request` 핸들러에서 HTTP 오류 시 `#unist-error` 배너에 "갱신 실패, 재시도 중..." 메시지 표시. 마지막 성공 카드 데이터 DOM 유지.

**2차안(옵션): SSE**

- `GET /sse/unist` 엔드포인트가 `text/event-stream`을 반환하고, 서버에서 30초마다 `event: unist-update` 이벤트를 push한다.
- 클라이언트는 `hx-ext="sse"`, `sse-connect="/sse/unist"`, `sse-swap="unist-update"` 속성으로 수신한다.
- 서버 측 SSE 구현은 F-SSE 문서에서 별도 설계한다.

## 5. 데이터 모델 변경

- 해당 없음. 이 페이지는 DB를 읽거나 쓰지 않으며, 모델 변경이 없다.

## 6. 인터페이스 계약

### 6.1 함수 시그니처 (신규)

```python
from datetime import datetime


def get_unist_board_data(*, now: datetime | None = None) -> UnistBoardData:
    """
    UNIST 버스 카드 그리드 데이터를 반환한다.

    Parameters
    ----------
    now : datetime | None
        테스트용 주입 시각. None이면 KST 현재 시각 사용.

    Returns
    -------
    UnistBoardData
        cards에 via 노선 카드(경유 정류소 기반)와 from 노선 카드(시간표 기반)를 순서대로 담는다.
        BIS API 실패 시 via 카드는 시간표 전용으로 폴백, bis_error=True.
        crawl_busstop은 1회만 호출한다.
    """
    ...


def build_via_card(
    busno: str,
    departure: str,
    direction: str,
    live_buses: list[dict],
    weekday: int,
    hr: int,
    minute: int,
    *,
    visualize: int = 2,
) -> BusCard:
    """
    경유 정류소(`196040234`) 기반 카드를 생성한다.
    live_buses에서 route_id가 매칭되는 항목을 먼저 채우고, 부족분은 시간표로 채운다.
    """
    ...


def build_from_card(
    busno: str,
    departure: str,
    direction: str,
    weekday: int,
    hr: int,
    minute: int,
    *,
    visualize: int = 2,
) -> BusCard:
    """
    UNIST 출발 노선 카드를 시간표만으로 생성한다.
    실시간 API를 호출하지 않는다.
    """
    ...
```

### 6.2 데이터 타입 (dataclass)

```python
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class CardEntry:
    text: str                              # 표시 문자열 ("천상 도착 5분30초" 또는 "07:30 출발 예정")
    source: Literal["live", "timetable"]   # 데이터 출처


@dataclass(frozen=True)
class BusCard:
    busno: str                # 노선번호 문자열
    direction: str            # 목적지 + 부가설명 (예: "삼남행 (울산역)")
    entries: list[CardEntry]  # 최대 visualize(=2)개 항목, live 우선
    is_last_bus: bool         # entries가 비어 있으면 True


@dataclass
class UnistBoardData:
    cards: list[BusCard]      # via 카드(경유 기반) + from 카드(시간표 기반) 순서
    bis_error: bool           # BIS API 호출 실패 시 True
```

## 7. Acceptance Checklist

- [ ] AC-1: `GET /unist` 요청 시 HTTP 200과 `#unist-grid` 요소가 포함된 HTML을 반환한다. (검증 방법: `pytest -k test_unist_board_returns_200`)
- [ ] AC-2: `GET /unist/partial` 요청 시 HTTP 200과 카드 요소(`class="bus-card"`)가 포함된 HTML을 반환한다. (검증 방법: `pytest -k test_unist_partial_returns_cards`)
- [ ] AC-3: `crawl_busstop`이 빈 리스트를 반환할 때 카드가 시간표 기반으로 렌더링되고 `bis_error=True`가 설정된다. (검증 방법: `crawl_busstop` mock 후 `pytest -k test_unist_bis_failure_fallback`)
- [ ] AC-4: `crawl_busstop("196040234")`가 카드 생성 전체 과정에서 정확히 1회만 호출된다. (검증 방법: `crawl_busstop` mock의 call_count 확인, `pytest -k test_unist_crawl_called_once`)
- [ ] AC-5: 시간표 데이터가 없고 live 버스도 없는 카드에서 `is_last_bus=True`가 설정되고 운행 종료 메시지가 렌더링된다. (검증 방법: `pytest -k test_unist_last_bus_per_card`)
- [ ] AC-6: `unist/index.html`에 `hx-trigger="every 30s"` 속성이 존재한다. (검증 방법: `grep -q 'hx-trigger="every 30s"' bushexa/web/templates/unist/index.html`)

> Executor는 모든 AC를 ✅로 만들 때까지 task in-progress 유지. 보고 시 항목별 한 줄 근거 첨부.

## 8. 테스트 계획

### 8.1 단위 테스트 (pytest)

파일: `tests/unit/test_unist_service.py`

- `test_build_via_card_uses_live_first` — live 버스가 있을 때 `CardEntry.source == "live"`인 항목이 먼저 오는지 확인
- `test_build_via_card_falls_back_to_timetable` — live 버스가 없을 때 `source == "timetable"` 항목으로 채워지는지 확인
- `test_build_from_card_no_live_call` — `build_from_card` 호출 시 `crawl_busstop`이 호출되지 않는지 확인
- `test_build_via_card_is_last_bus_when_empty` — live와 시간표 모두 없을 때 `BusCard.is_last_bus == True` 확인
- `test_get_unist_board_data_crawl_once` — `get_unist_board_data` 호출 시 `crawl_busstop` call_count == 1 확인
- `test_get_unist_board_data_bis_error_flag` — `crawl_busstop` 예외 발생 시 `UnistBoardData.bis_error == True` 확인

### 8.2 통합 테스트

파일: `tests/integration/test_unist_routes.py`

- Flask `test_client`로 `GET /unist` → HTTP 200, `text/html` Content-Type, `#unist-grid` 포함 확인
- Flask `test_client`로 `GET /unist/partial` → HTTP 200, 카드 요소 포함 확인
- `crawl_busstop`을 `pytest.monkeypatch`로 교체하여 BIS 실패 시나리오 재현

DB fixture: 해당 없음 (이 페이지는 DB를 사용하지 않음)

### 8.3 수동 검증 시나리오

1. `uv run bushexa serve` 실행 후 `http://localhost:5000/unist` 접속
2. 각 노선 카드(513 양방향 + 713/743/753/1115 시내 방면)가 표시되는지 확인
3. 실시간 버스 항목 옆에 출처(live/timetable) 구분이 표시되는지 확인
4. 30초 대기 후 카드 그리드가 자동 갱신되는지 브라우저 DevTools Network 탭에서 `/unist/partial` 요청 확인
5. `crawl_busstop` 응답을 mock하여 빈 리스트 반환 시 시간표 전용 카드 렌더링 확인

## 9. 변경 영향 범위

- **F01-departure-board.md** — `crawl_busstop("196040234")` 동일 stop_id 사용. 서비스 레이어에서 캐시 공유 가능성 검토.
- **F06-stops.md** — `crawl_busstop` 공통 의존. BIS API 클라이언트 추상화 시 인터페이스 통일.
- **breaking change:** Yes. Streamlit `unist_buspage()` 함수가 제거되고 Flask 라우트로 대체된다. `crawl_busstop` 중복 호출 안티패턴이 제거된다.

## 10. 미해결 질문

- **Q1:** `via_bus_list`와 `from_bus_list` 분류 기준이 직관과 반대인 문제를 신규 코드에서 변수명으로 명확히 할 것. 513이 "경유(via)" 노선이고, 713/743/753/1115가 "UNIST 기점(from)" 노선임을 변수명과 주석에 명시한다. → `bushexa/web/services/unist.py` 구현 시 `via_cards`(경유, 실시간 포함)와 `from_cards`(기점, 시간표 전용) 명명 채택.
- **Q2:** F01과 F07이 모두 `crawl_busstop("196040234")`를 사용하므로, 두 라우트가 동시에 폴링 시 API 호출이 중복된다. 공유 캐시(Flask-Caching, TTL 15초)를 `bushexa/web/services/bis_client.py` 레벨에 두고 두 서비스가 공유하는 방안 검토 필요. → F-BIS-Client ADR로 별도 결정 권고.
- **Q3:** `COLS = 3` 고정이므로 via 노선(513 양방향 = 2개)과 from 노선(713, 743, 753, 1115 = 4개)을 합치면 총 6개 카드이나, 3열 × 2행 레이아웃에서 via 행 3번째 칸은 항상 비어있다. CSS Grid로 자동 채움 레이아웃으로 변경하여 빈 카드 제거 여부 결정 필요.
