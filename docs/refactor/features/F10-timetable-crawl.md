---
status: draft
designer: opus
auditor_status: pending
last_updated: 2026-06-01
feature_id: F10
---

# F10 — 시간표 재크롤 (Timetable Re-Crawl)

> 이 템플릿의 **모든 섹션**은 필수다. Executor는 슬롯을 채우되 섹션을 삭제하지 않는다. "해당 없음"은 명시적으로 적는다.

## 0. 한 줄 요약

- **As-is:** `src/crawl.py`의 `crawl_target_timetable` / `crawl_timetable` 함수가 울산 BIS OpenAPI에서 시간표를 수집하고 `timetable/*.json`에 저장하나, 함수 내부에 `import streamlit as st` 및 `st.*` 호출이 산재하여 UI 컨텍스트 없이 실행 시 깨진다.
- **To-be:** `bushexa/crawler/timetable.py` 모듈이 Streamlit 의존 없이 표준 `logging`과 콜백 인터페이스를 사용하며, 관리자 UI(F04 SSE)와 CLI(`uv run bushexa crawl-timetable`) 양쪽에서 동일하게 호출 가능하다. 결과는 atomic write로 `data/timetable/*.json`에 저장한다.

## 1. 사용자 시나리오

**대상:** 관리자 (버스 노선 시간표 변경 시 재크롤이 필요한 운영자).

**정상 흐름 — 관리자 UI (Happy path):**
1. 관리자가 `/admin/timetable/crawl` 페이지에 접근(인증 완료 상태)한다.
2. vacation 모드 여부를 선택하고 "재크롤 시작" 버튼을 클릭한다.
3. 서버가 SSE 스트림(`/admin/sse/crawl-progress`)을 열고 진행상황 이벤트를 순차 전송한다.
4. 브라우저가 각 이벤트를 수신해 진행 로그를 실시간으로 표시한다.
5. 크롤링 완료 후 SSE 스트림이 `done` 이벤트로 종료된다.
6. `data/timetable/513.json`, `713.json`, `743.json`, `753.json`, `1115.json`이 갱신된다.

**정상 흐름 — CLI:**
1. 관리자가 터미널에서 `uv run bushexa crawl-timetable` (또는 `--vacation` 플래그 추가)을 실행한다.
2. 진행상황이 `stdout`에 출력된다.
3. 완료 후 `data/timetable/*.json`이 갱신된다.

**엣지 케이스:**
1. **외부 API 503/타임아웃:** 최대 5회 재시도(`MAX_RETRY=5`) 후에도 실패하면 해당 노선·요일 조합을 건너뛰고 나머지를 계속 진행한다. 콜백으로 오류를 보고한다.
2. **`total_cnt == 0` 응답:** 해당 노선·요일 조합의 시간표가 없는 것으로 간주하고 빈 리스트를 반환한다. JSON 파일에 빈 배열로 저장한다.
3. **파일 쓰기 권한 없음:** atomic write(임시파일 후 `os.replace`) 중 `OSError` 발생 시 로깅하고 예외를 호출자에게 전파한다. 기존 JSON 파일은 훼손되지 않는다.
4. **vacation 모드 day_of_week 매핑 오류:** `week_offset`이 3 이상인 API 응답이 없을 경우 빈 시간표로 저장하고 경고를 로깅한다.
5. **크롤 중 관리자 세션 만료:** SSE 연결이 끊어지더라도 서버 사이드 크롤링은 계속 진행된다. 재접속 시 완료 상태를 확인할 수 있다.

## 2. 현재 구현 분석 (As-Is)

### 2.1 진입점 / 파일 / 라인 참조

- `src/crawl.py:374` — `crawl_target_timetable(is_vacation: bool = False)`: 전체 크롤의 진입점
- `src/crawl.py:300` — `crawl_timetable(routeno: int, day_of_week: int)`: 단일 노선·요일 크롤
- `src/crawl.py:245` — `request_timetable(page_no, num_of_rows, routeno, day_of_week)`: 단일 API 페이지 요청
- `src/crawl.py:435-437` — `__main__` 블록: `python -m src.crawl` 직접 실행 시 `crawl_target_timetable(is_vacation=True)` 호출
- `runscript.sh`: `python -m src.crawl`을 cron/docker entrypoint에서 호출

### 2.2 사용된 Streamlit API 전수 목록

| API | 위치 | 용도 |
|---|---|---|
| `import streamlit as st` | `src/crawl.py:326` | `crawl_timetable` 내 지연 임포트 (비-UI 모듈에서 호출) |
| `st.text(...)` | `src/crawl.py:342` | 각 페이지 요청 진행 상황 출력 |
| `st.error(...)` | `src/crawl.py:350` | 응답 오류 메시지 출력 |
| `st.error(...)` | `src/crawl.py:356` | 재시도 실패 메시지 출력 |
| `st.success(...)` | `src/crawl.py:358` | 재시도 성공 메시지 출력 |
| `import streamlit as st` | `src/crawl.py:401` | `crawl_target_timetable` 내 지연 임포트 |
| `st.text(...)` | `src/crawl.py:409` | 노선·요일 크롤 시작 알림 출력 |

### 2.3 데이터 흐름

- `crawl_target_timetable(is_vacation)` → `ROUTEID` 상수에서 버스번호-노선ID 매핑 구성 → 노선번호×요일 조합별 `crawl_timetable(busno, week)` 호출 → `request_timetable(page, row, routeno, day_of_week)` 반복 호출 → XML 파싱 → `(time: str, direction: int)` 튜플 리스트 → `ROUTEID` direction 매핑 후 `departure` 키 기준 분류 → `timetable/*.json` write
- API 응답 shape (XML): `<item><time>HHMM</time><direction>1|2</direction></item>` (BeautifulSoup `row` 태그 파싱)
- 저장 JSON shape: `{week_index: {departure_str: ["HH:MM", ...]}}` (예: `{"0": {"덕하": ["05:20", ...]}, "1": {...}}`)
- 캐싱: 없음. 세션 상태: 없음.
- 의존 상수: `ROUTEID` (`src/constants.py:13`) — key: route_id, value: `(busno, terminal, departure, stop_ids)` tuple

### 2.4 의존 모듈 그래프

```text
src/crawl.py
  ├── src.constants.ROUTEID
  ├── src.constants.ULSAN_CITYCODE
  ├── src.constants.ULSAN_PREFIX
  ├── requests
  ├── bs4.BeautifulSoup
  ├── json
  ├── os
  ├── time.sleep
  └── streamlit (지연 임포트, crawl_timetable:326, crawl_target_timetable:401)
```

### 2.5 관찰된 결함·악취

- **결함 1 — 비-UI 모듈의 Streamlit 지연 임포트 (`src/crawl.py:326`):** `crawl_timetable` 함수 안에서 `import streamlit as st`를 실행한다. `src/crawl.py`는 크롤러 비즈니스 로직 모듈이므로 UI 프레임워크 의존이 없어야 한다. Streamlit 컨텍스트 없이 실행 시 임포트는 성공하지만 `st.text()` 등 렌더링 호출이 경고를 발생시키거나 silent failure한다.

- **결함 2 — `st.text/st.error/st.success` 호출 산재 (`src/crawl.py:342,350,356,358,409`):** 진행상황 보고 로직이 Streamlit 렌더링 함수에 결합되어 있다. `runscript.sh`가 `python -m src.crawl`을 Streamlit 컨텍스트 없이 호출하므로, 이 호출들은 경고 스팸 또는 silent failure를 일으킨다. CLI 실행과 UI 실행이 동일 함수를 공유하는 것이 불가능하다.

- **결함 3 — `runscript.sh`에서 Streamlit 컨텍스트 없는 실행 (`src/crawl.py:435-437` 연동):** `python -m src.crawl`은 `crawl_target_timetable(is_vacation=True)`를 직접 호출한다. 이때 함수 내부의 `import streamlit as st`와 `st.*` 호출은 Streamlit 런타임 없이 실행되어 정의되지 않은 동작을 유발한다.

- **결함 4 — 중복된 status_code 체크 (`src/crawl.py:334-358`):** `crawl_timetable` 내 루프에서 `response is None or response.status_code != 200`을 `for retry` 블록 내(line 334)와 블록 종료 후(line 348)에 두 번 검사한다. `for-else` 구조상 retry 루프를 `break`로 탈출했으면 `response`가 유효한 200 응답임이 보장된다. 이중 체크는 불필요한 분기이며 코드 이해를 방해한다.

- **결함 5 — 페이지네이션 종료 조건 off-by-one 위험 (`src/crawl.py:329`):** `range(1, (total_cnt // request_row) + 2)` 계산에서 `total_cnt`가 `request_row`의 배수일 때 불필요한 빈 페이지를 한 번 더 요청한다. 예: `total_cnt=50, request_row=50`이면 `range(1, 3)` → 페이지 1, 2 요청. 페이지 2는 빈 응답을 반환한다. API 오류는 아니나 불필요한 네트워크 요청과 latency를 유발한다.

## 3. 외부 의존성

### 3.1 외부 API

**울산 BIS 시간표 API**

- **엔드포인트 URL:** `http://openapi.its.ulsan.kr/UlsanAPI/BusTimetable.xo`
- **HTTP 메서드:** GET
- **파라미터:**

| 파라미터명 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `serviceKey` | string | 필수 | API 인증키 (`secret/key.txt`에서 로드) |
| `pageNo` | int | 필수 | 페이지 번호 (1부터 시작) |
| `numOfRows` | int | 필수 | 페이지당 행 수 (현재 50) |
| `routeNo` | int | 필수 | 버스 노선번호 (예: 513, 713, 743, 753, 1115) |
| `dayOfWeek` | int | 필수 | 요일 코드. 평일=0, 토요일=1, 일요일/공휴일=2; vacation 모드: 평일=3, 토요일=4, 일요일/공휴일=5 |

- **응답 형식:** XML
- **응답 구조 (성공 시):**

```xml
<response>
  <header>
    <resultCode>00</resultCode>
    <resultMsg>OK</resultMsg>
  </header>
  <body>
    <totalCnt>28</totalCnt>
    <items>
      <row>
        <time>0520</time>
        <direction>1</direction>
      </row>
      ...
    </items>
  </body>
  <tableInfo>
    <totalCnt>28</totalCnt>
  </tableInfo>
</response>
```

- `<time>` 값 형식: `HHMM` (4자리 문자열, 예: `"0520"` → `"05:20"`)
- `<direction>` 값: `1` (방향 A) 또는 `2` (방향 B). `ROUTEID` 내 정렬 순서로 direction 1/2를 departure에 매핑한다.
- **오류 응답:** HTTP 상태코드 200이 아닌 경우 또는 `response is None`. API 자체 오류 코드는 `<resultCode>`로 반환되나 현재 구현은 status_code만 검사한다.
- **참고 문서:** `api-manual/OpenAPI활용가이드_울산광역시_BIS_v4.2.docx`

### 3.2 데이터베이스

해당 없음. 이 기능은 DB를 읽거나 쓰지 않는다. 결과는 JSON 파일로만 저장된다.

### 3.3 정적 파일

- **읽기:** `secret/key.txt` — API 인증키. `get_apikey("secret/key.txt")`로 로드한다. 새 구현에서는 `bushexa/config.py`의 환경변수(`ULSAN_API_KEY`) 또는 `secret/key.txt` 폴백으로 로드한다.
- **쓰기:** `timetable/{busno}.json` (현재) → 새 구현에서 `data/timetable/{busno}.json`. 파일 5개: `513.json`, `713.json`, `743.json`, `753.json`, `1115.json`.
- **의존 상수:** `src/constants.py:13` 의 `ROUTEID` — 버스번호, 방면, departure 문자열 매핑. 새 구현에서 `bushexa/data/constants.py`로 이동한다.

## 4. 새 구현 매핑 (To-Be)

### 4.1 URL & HTTP 메서드

- `POST /admin/timetable/crawl` → 크롤링 작업 시작. Body: `{"vacation": true|false}`. 인증 필수.
- `GET /admin/sse/crawl-progress` → SSE 스트림. 진행상황 이벤트 전송. 인증 필수.

### 4.2 Flask 라우트 / 핸들러 시그니처

```python
# bushexa/web/routes/admin.py (F04와 공유 Blueprint)
from flask import Blueprint, request, Response, stream_with_context
from bushexa.crawler.timetable import crawl_target_timetable

bp = Blueprint("admin", __name__, url_prefix="/admin")

@bp.post("/timetable/crawl")
@login_required
def trigger_crawl() -> tuple[dict, int]:
    """크롤링 작업을 비동기로 시작하고 job_id를 반환한다."""
    vacation: bool = request.json.get("vacation", False)
    job_id: str = start_crawl_job(vacation=vacation)
    return {"job_id": job_id}, 202

@bp.get("/sse/crawl-progress")
@login_required
def crawl_progress_sse() -> Response:
    """SSE 스트림으로 진행상황 이벤트를 전송한다."""
    def event_stream():
        for event in iter_crawl_events():
            yield f"data: {event}\n\n"
    return Response(stream_with_context(event_stream()),
                    mimetype="text/event-stream")
```

CLI 엔트리포인트:

```python
# bushexa/cli.py
import click
from bushexa.crawler.timetable import crawl_target_timetable

@click.command("crawl-timetable")
@click.option("--vacation", is_flag=True, default=False,
              help="vacation 모드 (요일 오프셋 +3) 적용")
def cmd_crawl_timetable(vacation: bool) -> None:
    """울산 BIS API에서 시간표를 재크롤하고 data/timetable/*.json을 갱신한다."""
    crawl_target_timetable(
        is_vacation=vacation,
        on_progress=lambda msg: click.echo(msg),
    )
```

### 4.3 템플릿 & 정적 자원

- `bushexa/web/templates/admin/timetable_crawl.html` — 크롤 트리거 UI. `admin/base.html` 상속.
- SSE 수신 및 진행 로그 표시를 위한 인라인 JS (EventSource API 사용). 별도 JS 파일로 분리 가능하나 최소 구현은 인라인으로 충분하다.
- CSS: 기존 admin 공통 스타일시트 재사용.

### 4.4 도메인 서비스 호출

- `bushexa.crawler.timetable.crawl_target_timetable(is_vacation, on_progress)` → `None` (완료 시) 또는 예외 발생 (치명적 실패 시)
- `bushexa.crawler.timetable.crawl_timetable(routeno, day_of_week, on_progress)` → `list[tuple[str, int]]` (시간, direction 튜플 리스트)
- `bushexa.crawler.timetable.request_timetable(page_no, num_of_rows, routeno, day_of_week)` → `requests.Response | None`

### 4.5 HTMX/SSE 동작 (실시간 화면만)

- **SSE 토픽:** `/admin/sse/crawl-progress`
- **이벤트 타입:** `progress` (진행 메시지), `error` (오류 메시지), `done` (완료)
- **부분 갱신 대상 selector:** `#crawl-log` — 관리자 페이지 내 로그 출력 영역. 각 이벤트 수신 시 `<li>` 요소를 append한다.
- **실패시 fallback:** EventSource `onerror` 핸들러가 재연결을 3회 시도한다. 재연결 실패 시 "연결 끊김" 메시지를 `#crawl-log`에 추가하고 스트림을 닫는다.
- **폴링 간격:** SSE 사용으로 폴링 없음. 서버 push 방식.

## 5. 데이터 모델 변경 (있는 경우만)

DB 변경: 해당 없음.

**JSON 파일 경로 변경:**

| 현재 | 신규 |
|---|---|
| `timetable/513.json` | `data/timetable/513.json` |
| `timetable/713.json` | `data/timetable/713.json` |
| `timetable/743.json` | `data/timetable/743.json` |
| `timetable/753.json` | `data/timetable/753.json` |
| `timetable/1115.json` | `data/timetable/1115.json` |

**JSON 스키마 유지:** 기존 스키마 `{week_index_str: {departure_str: ["HH:MM", ...]}}` 를 그대로 유지한다. 기존 파일을 `data/timetable/`로 복사하면 하위 호환된다.

마이그레이션 스크립트: 필요 시 `cp timetable/*.json data/timetable/` 한 줄로 충분하다. 별도 스크립트 파일 불필요.

## 6. 인터페이스 계약

### 6.1 함수 시그니처 (신규)

```python
# bushexa/crawler/timetable.py
from __future__ import annotations
import logging
from collections.abc import Callable
from typing import TypeAlias

ProgressCallback: TypeAlias = Callable[[str], None]

def crawl_target_timetable(
    is_vacation: bool = False,
    on_progress: ProgressCallback | None = None,
) -> None:
    """
    전체 노선(513, 713, 743, 753, 1115)×요일(0,1,2) 조합을 크롤하고
    data/timetable/{busno}.json을 atomic write로 갱신한다.

    Args:
        is_vacation: True이면 day_of_week에 3을 더해 방학 시간표 API를 호출한다.
        on_progress: 진행 메시지 콜백. None이면 logging.getLogger(__name__)에만 기록한다.

    Raises:
        OSError: data/timetable/ 경로 쓰기 실패 시.
    """
    ...


def crawl_timetable(
    routeno: int,
    day_of_week: int,
    on_progress: ProgressCallback | None = None,
) -> list[tuple[str, int]]:
    """
    단일 노선·요일 조합의 전체 페이지를 크롤하고 (time, direction) 튜플 리스트를 반환한다.

    Args:
        routeno: 버스 노선번호 (정수, 예: 513).
        day_of_week: API 요일 코드 (0-5).
        on_progress: 진행 메시지 콜백.

    Returns:
        list[tuple[str, int]]: (time: "HH:MM", direction: 1|2) 튜플 리스트.
        빈 리스트이면 해당 노선·요일 조합의 시간표가 없음을 의미한다.

    Raises:
        RuntimeError: MAX_RETRY 초과 후에도 첫 페이지를 가져오지 못한 경우.
    """
    ...


def request_timetable(
    page_no: int,
    num_of_rows: int,
    routeno: int,
    day_of_week: int,
) -> "requests.Response | None":
    """
    울산 BIS API에서 시간표 단일 페이지를 요청한다.

    Returns:
        requests.Response: 성공 시.
        None: 모든 재시도 실패 시.
    """
    ...
```

### 6.2 데이터 타입 (dataclass / TypedDict)

```python
from typing import TypedDict, NamedTuple, Literal

# 최상위 시간표 JSON 구조: 노선 1개 분량.
# 키 weekday_str ∈ {"0","1","2"}, 키 departure ∈ {"UNIST","명촌",...}, 값은 ["HH:MM", ...] 정렬·중복 제거
TimetableJSON = dict[str, dict[str, list[str]]]

class TimetableDeparturePack(TypedDict):
    """단일 weekday 내 departure→times 매핑."""
    # 키 예: "UNIST", "명촌", "꽃바위" 등 ROUTEID[*][2] 값
    # 값: 오름차순 정렬 "HH:MM" 문자열 list
    # mypy가 이해할 수 있도록 별칭으로 사용한다.
    # TypedDict는 동적 키이므로 한 항목 수준만 명시한다.
    __required_keys__: frozenset[str]  # type: ignore[misc]
    # 실제 사용 시 dict[str, list[str]] 형태로 다룬다.

class TimetableRow(NamedTuple):
    """크롤 결과 1행. (time, direction)."""
    time: str            # "HH:MM"
    direction: Literal[1, 2]   # 1=출발지에서 시내방향, 2=시내에서 출발지 방향

class ProgressEvent(TypedDict):
    """SSE로 송신하는 진행 이벤트."""
    event: Literal["progress", "error", "done"]
    route: str           # "713" 등 버스번호
    day: int             # 0~6
    page: int            # API 페이지 번호
    message: str
```

## 7. Acceptance Checklist (Executor가 사용)

- [ ] AC-1: `bushexa/crawler/timetable.py`에 `import streamlit` 구문이 존재하지 않는다. (검증 방법: `grep -r "import streamlit" bushexa/crawler/` 결과 빈 출력)
- [ ] AC-2: `uv run bushexa crawl-timetable --vacation`이 Streamlit 없이 실행되어 `data/timetable/*.json` 5개 파일을 생성한다. (검증 방법: 명령 실행 후 `ls data/timetable/*.json | wc -l` 결과 5)
- [ ] AC-3: 관리자 UI에서 재크롤 트리거 후 SSE 스트림이 `done` 이벤트를 수신하고 `data/timetable/*.json`의 mtime이 갱신된다. (검증 방법: `stat data/timetable/513.json` mtime 비교)
- [ ] AC-4: `request_timetable` 재시도 로직에서 `st.error/st.success` 호출이 제거되고 `logging.getLogger(__name__).error/info`로 대체된다. (검증 방법: `grep -n "st\." bushexa/crawler/timetable.py` 결과 빈 출력)
- [ ] AC-5: atomic write 구현 — 파일 쓰기 도중 프로세스가 종료되어도 기존 JSON 파일이 훼손되지 않는다. (검증 방법: `bushexa/crawler/timetable.py`에서 `tempfile` 또는 `os.replace` 사용 코드 확인)
- [ ] AC-6: 단위 테스트 `pytest tests/unit/test_timetable_crawl.py`가 통과한다. (검증 방법: `uv run pytest tests/unit/test_timetable_crawl.py -v` 결과 all passed)

> Executor는 모든 AC를 체크할 때까지 task in-progress 유지. 보고 시 항목별 한 줄 근거 첨부.

## 8. 테스트 계획

### 8.1 단위 테스트 (pytest)

- `tests/unit/test_timetable_crawl.py`에 추가
- `test_request_timetable_success`: `requests.get`을 mock하여 200 응답 시 `Response` 객체를 반환하는지 확인한다.
- `test_request_timetable_returns_none_on_all_retries_failed`: 네트워크 예외가 5회 연속 발생 시 `None`을 반환하는지 확인한다.
- `test_crawl_timetable_parses_xml_correctly`: 샘플 XML fixture를 파싱하여 `[("05:20", 1), ("06:00", 2)]` 형태의 결과를 반환하는지 확인한다.
- `test_crawl_timetable_empty_total_cnt`: `totalCnt=0` XML 응답 시 빈 리스트를 반환하는지 확인한다.
- `test_crawl_target_timetable_writes_json`: `crawl_timetable`을 mock하고 `crawl_target_timetable` 실행 후 `data/timetable/513.json`이 생성되는지 확인한다.
- `test_crawl_target_timetable_atomic_write`: 임시파일 → `os.replace` 패턴으로 쓰기가 수행되는지 확인한다 (monkeypatch로 `os.replace` 호출 여부 검증).
- `test_pagination_correct_page_count`: `total_cnt=100, request_row=50`일 때 페이지 2개(1, 2)만 요청하는지 확인한다.
- `test_no_streamlit_import`: `importlib`로 모듈을 로드하고 `streamlit` 의존이 없음을 확인한다.

### 8.2 통합 테스트

- Flask `test_client`를 사용한다.
- `test_trigger_crawl_unauthorized`: 인증 없이 `POST /admin/timetable/crawl` 시 401 반환 확인.
- `test_trigger_crawl_authorized`: 인증 후 `POST /admin/timetable/crawl` 시 202 반환 및 `job_id` 포함 JSON 반환 확인 (`crawl_target_timetable`은 mock).
- `test_sse_crawl_progress_stream`: SSE 엔드포인트가 `text/event-stream` Content-Type으로 응답하는지 확인.

### 8.3 수동 검증 시나리오

1. `uv run bushexa crawl-timetable --vacation` 실행 후 터미널에 진행 메시지 출력 확인.
2. 명령 완료 후 `ls -la data/timetable/` 로 5개 JSON 파일의 mtime이 현재 시각으로 갱신됨 확인.
3. `python -c "import json; d=json.load(open('data/timetable/513.json')); assert '0' in d"` — JSON 스키마 유효성 확인.
4. 관리자 UI에서 "재크롤 시작" 버튼 클릭 후 `#crawl-log` 영역에 진행 메시지가 실시간으로 표시됨 확인.
5. 크롤 완료 후 SSE 스트림에서 `done` 이벤트 수신 확인 (브라우저 DevTools Network 탭).

## 9. 변경 영향 범위

- **F04 (관리자 페이지):** 크롤 트리거 UI(`/admin/timetable/crawl`)와 SSE 엔드포인트(`/admin/sse/crawl-progress`)를 F04 admin Blueprint에 추가한다. F04 구현 전까지 F10의 관리자 UI 트리거는 동작하지 않는다.
- **F01 (출발 게시판) / F05~F09 (시간표 표시 관련 페이지):** `data/timetable/*.json` 경로가 `timetable/*.json`에서 변경된다. 해당 JSON을 읽는 모든 페이지가 경로를 업데이트해야 한다.
- breaking change: **Yes** — `src/crawl.py`의 `crawl_target_timetable`, `crawl_timetable` 함수가 `bushexa/crawler/timetable.py`로 이전되며 기존 `src/` 임포트 경로가 폐기된다. JSON 저장 경로도 변경된다.

## 10. 미해결 질문 (있다면)

- `data/timetable/` vs `timetable/` 최종 경로: `01-overview.md`에서 "timetable/ 기존 위치 유지 가능 (data/ 로 이동도 고려)"로 표기되어 있다. 이 문서는 `data/timetable/`을 선택하나, 팀에서 최종 확정이 필요하다.
- `dayOfWeek` API 파라미터의 vacation 값(3, 4, 5) 동작: `api-manual/OpenAPI활용가이드_울산광역시_BIS_v4.2.docx`에서 확인 필요. 현재 코드는 vacation 시 `week_offset=3`을 더하는 방식이나, API 스펙과 일치하는지 검증이 필요하다.
