---
status: designed
designer: opus
auditor_status: design-pass (T02 2026-06-01, F-9 fixed; 잔여 C-3는 FROZEN 면제)
last_updated: 2026-06-01
feature_id: F05
---

# F05 — 운행 재구성 테이블 (running_table)

> 이 템플릿의 **모든 섹션**은 필수다. Executor는 슬롯을 채우되 섹션을 삭제하지 않는다. "해당 없음"은 명시적으로 적는다.

## 0. 한 줄 요약

- **As-is:** Streamlit 페이지(`infopages/running_table.py`)에서 날짜·노선을 선택하면 `bus_timelog` DB 조회 후 차량별 운행 구간을 파싱해 정류장 × 운행 횟수 DataFrame으로 표시한다.
- **To-be:** Flask GET 핸들러 `/running`이 쿼리스트링 `?route_id=195000178&date=20250601`을 받아 `RunService.build_table(route_id, date)` 도메인 서비스를 호출하고, Jinja2 템플릿에 HTML 테이블로 렌더링한다.

## 1. 사용자 시나리오

- **대상:** 관리자 또는 고급 이용자. 특정 날짜·노선의 실제 운행 이력을 정류장별 통과 시각으로 확인하려는 의도.
- **정상 흐름 (Happy path):**
  1. 사용자가 `/running`에 접근한다 (쿼리스트링 없음).
  2. 서버가 기본값(어제 날짜, 첫 번째 노선)으로 페이지를 렌더링한다.
  3. 사용자가 날짜를 선택하고 노선을 선택한다 → `?route_id=195000178&date=20250601` GET 요청.
  4. 서버가 `BusTimelogRepository.get_log_by_route_id(route_id, date)` 를 호출해 로그를 조회한다.
  5. `RunService.build_table(logs, route_id, timetable)` 이 `parse_runs` → `parse_each_vehicle` 순으로 로그를 처리해 운행 목록을 반환한다.
  6. 서버가 정류장별 통과 시각 테이블을 HTML로 렌더링해 반환한다.
- **엣지 케이스:**
  - 선택한 날짜·노선에 대한 DB 로그가 없으면: "검색된 버스가 없습니다" 메시지를 테이블 대신 표시한다.
  - `date` 파라미터 형식이 `YYYYMMDD`가 아니면: HTTP 400 응답 또는 기본값(어제)으로 폴백하고 경고를 표시한다.
  - `route_id`가 `ROUTEID` 상수에 없으면: HTTP 400 또는 기본 노선으로 폴백하고 경고를 표시한다.
  - `parse_each_vehicle` 에서 `stop_id`가 `ROUTEID[route_id][3]` 목록에 없는 경우(`stop_ids.index(stop_id)` ValueError): 해당 로그를 조용히 건너뛴다 (현재 구현과 동일, `infopages/running_table.py:166`의 `continue`).
  - DB 연결 실패(SQLite 파일 없음 또는 Postgres 연결 불가): HTTP 500 대신 사용자 친화적 오류 메시지를 렌더링하고 서버 로그에 상세 오류를 기록한다.
  - `parse_each_vehicle` 언패킹 분기(`infopages/running_table.py:159-162`)에서 컬럼 수 불일치: 신규 구현에서는 DB 컬럼을 TypedDict로 명시해 해당 분기를 제거한다.

## 2. 현재 구현 분석 (As-Is)

### 2.1 진입점 / 파일 / 라인 참조

- 진입점: `infopages/running_table.py:17` — `board_page()` 함수
- 핵심 로직:
  - `board_page()`: infopages/running_table.py:17-91 (UI + 오케스트레이션)
  - `parse_timelog()`: infopages/running_table.py:94-115 (타임로그 문자열 → datetime 파싱)
  - `parse_timetable()`: infopages/running_table.py:118-122 (시간표 문자열 → time 파싱)
  - `parse_runs()`: infopages/running_table.py:125-139 (차량별 그룹화 후 개별 운행 분리)
  - `parse_each_vehicle()`: infopages/running_table.py:142-177 (단일 차량 로그 → 운행 회차 분리)

### 2.2 사용된 Streamlit API 전수 목록

| API | 위치 | 용도 |
|---|---|---|
| `st.info("시범적으로 ...")` | infopages/running_table.py:20 | 안내 메시지 표시 |
| `st.date_input("날짜를 선택하세요", ...)` | infopages/running_table.py:22-24 | 날짜 선택 위젯 (기본값: 어제) |
| `st.selectbox("노선을 선택하세요", route_ids, format_func=...)` | infopages/running_table.py:30-32 | 노선 선택 드롭다운 |
| `st.write(df)` | infopages/running_table.py:86 | 운행 테이블 DataFrame 렌더링 |
| `st.error("검색된 버스가 없습니다.")` | infopages/running_table.py:51 | 결과 없음 오류 메시지 |
| `st.error(e)` | infopages/running_table.py:91 | DataFrame 생성 실패 오류 표시 |

### 2.3 데이터 흐름

- `BUS_TIMELOG()` 인스턴스 생성 (crawl/db.py:7-56) → psycopg2로 Postgres 연결 (SQLite 지원 없음)
- `get_weekday(targetdate)` → `day_of_week: int` (공휴일 반영)
- `get_timetable(ROUTEID[targetroute][0], day_of_week, ROUTEID[targetroute][1])` → `list[str]` ("HH:MM")
  - `timetable` 변환: `[parse_timetable(t) for t in timetable]` → `list[datetime.time]`
- `db.get_log_by_route_id(route_id, date_str)` → `list[tuple]` — DB 컬럼: `(idx, stop_id, route_id, route_nm, vehicle_number, stop_name)` 또는 `(idx, stop_id, route_id, vehicle_number)` (4컬럼 버전 존재)
  - `logs` 변환: `[(parse_timelog(log[0]), *log[1:])]` → `list[tuple[datetime, str, str, ...]]`
- `parse_runs(logs, route_id, start_stop=stops[1])` → `list[list[tuple]]` — 각 원소는 단일 운행의 (datetime, stop_id, route_id, vehicle_number) 로그 목록
- `table = {stop_id: []}` → `pd.DataFrame(table)` → 전치(`.T`) → `st.write(df)`
- 캐싱: 미사용. 매 렌더마다 DB 쿼리 실행.
- 세션 상태: 미사용.

### 2.4 의존 모듈 그래프

```text
infopages/running_table.py
  ├── src.constants.ROUTEID
  ├── src.constants.STOP_IDS
  ├── src.tools.get_timetable()       → timetable/{busno}.json
  ├── src.tools.get_weekday()         → src.tools.get_now(), src.crawl.is_holiday()
  └── crawl.db.BUS_TIMELOG
        └── psycopg2                  → Postgres (secret/db.yaml 또는 환경변수)
              └── bus_timelog 테이블
                    컬럼: idx, stop_id, route_id, route_nm, vehicle_number, stop_name
```

### 2.5 관찰된 결함·악취

- **DB 연결이 Postgres 전용**: `crawl/db.py:1`에서 `import psycopg2`만 사용, SQLite 지원 없음. 신규 구현에서 repository 패턴 적용 시 SQLite/Postgres dual-backend를 지원해야 한다.
- **`parse_each_vehicle` 언패킹 분기 (infopages/running_table.py:159-162)**: 4컬럼과 6컬럼 로그를 동시에 처리하는 bare `except:` 분기가 존재한다. 스키마 불일치를 은폐하며 타입 추론을 방해한다. 신규 구현에서는 TypedDict로 DB 반환값을 명시하고 이 분기를 제거한다.
- **`parse_each_vehicle` 미완성 회차 처리 (infopages/running_table.py:142-177)**: 루프 종료 후 마지막 `route` 리스트가 `rets`에 추가되지 않는다 (마지막 운행 회차 유실 버그).
- **`start_stop` 파라미터 미사용**: `parse_runs`에서 `start_stop=stops[1]`을 받지만 `parse_each_vehicle` 내부에서 사용되지 않는다. 매개변수 의미가 명확하지 않다.
- **`table` 딕셔너리 key-value 길이 불일치 위험**: 운행마다 stops 개수를 맞추지 않으면 `pd.DataFrame(table)` 생성 실패 (현재 `try/except`로 은폐, infopages/running_table.py:81-91). 정류장 미통과 시 "レ" 마커로 채우는 로직이 `stops[1:]`에만 적용되어 `stops[0]`은 별도 처리.
- **비UI 모듈에서 `import streamlit as st`**: `src/tools.py:12` 참조. Flask 환경 오염.

## 3. 외부 의존성

### 3.1 외부 API

해당 없음. 이 페이지는 외부 API를 호출하지 않는다. DB에 저장된 로그를 읽기만 한다.

### 3.2 데이터베이스

- **테이블**: `bus_timelog`
- **읽는 컬럼**: `idx` (타임스탬프 문자열, `YYYYMMDD_HH:MM:SS` 또는 `YYYY-MM-DD_HH:MM:SS` 형식), `stop_id`, `route_id`, `vehicle_number` (route_nm, stop_name은 선택적)
- **쿼리 패턴**: `SELECT * FROM bus_timelog WHERE route_id = %s AND idx LIKE %s` (`crawl/db.py:102-116`)
  - `idx LIKE '20250601_%'` 패턴으로 날짜 필터링
- **현재 백엔드**: Postgres only (`psycopg2`)
- **신규 백엔드**: SQLite (개발), Postgres (운영) — repository 패턴으로 추상화
  - SQLite에서는 `LIKE` 연산자 동일하게 동작함 (SQLite/Postgres 공통 SQL 패턴 유지)

### 3.3 정적 파일

- `timetable/{busno}.json` — 첫 번째 정류장 도착 시각 추정에 사용. 키 구조: `{weekday_idx: {departure: ["HH:MM", ...]}}`.

## 4. 새 구현 매핑 (To-Be)

### 4.1 URL & HTTP 메서드

- `GET /running` — 쿼리스트링: `?route_id={route_id}&date={YYYYMMDD}`
  - 파라미터 모두 선택적. 없으면 기본값 적용 (route_id=첫 번째 route_id, date=어제 KST 날짜).
  - 파라미터가 유효하면 운행 테이블 렌더링.
  - 파라미터가 유효하지 않으면 경고 메시지와 함께 기본값으로 렌더링.

### 4.2 Flask 라우트 / 핸들러 시그니처

```python
# bushexa/web/routes/running.py
from flask import Blueprint, request, render_template
from bushexa.web.services.running import get_running_page_data

bp = Blueprint("running", __name__)

@bp.route("/running")
def running_page() -> str:
    route_id = request.args.get("route_id", default=None)
    date = request.args.get("date", default=None)
    ctx = get_running_page_data(route_id=route_id, date=date)
    return render_template("running.html", **ctx)
```

### 4.3 템플릿 & 정적 자원

- `bushexa/web/templates/running.html` — 메인 템플릿
  - `bushexa/web/templates/_base.html` 상속
  - 날짜 선택: `<input type="date" name="date">` form 요소 (GET 제출)
  - 노선 선택: `<select name="route_id">` — `ROUTEID` 키 목록, `format_func`에 해당하는 label은 `"{bus_no}번 {terminal}행"` 형식
  - 안내 메시지: `<div class="info-banner">시범적으로 과거의 운행 정보를 제공합니다.</div>`
  - 현재 시각 표시: `<p class="current-time">{{ current_time }}</p>` (KST)
  - 운행 테이블: `<div class="table-container"><table class="running-table">` — thead(정류장명), tbody(운행 회차 × 정류장 통과시각)
  - 결과 없음: `{% if not runs %}` 블록으로 "검색된 버스가 없습니다" 표시
  - 경고/오류: `{% if warning %}` 블록
- 필요한 정적 JS/CSS:
  - `bushexa/web/static/css/running.css` — 테이블 스타일, 가로 스크롤
  - 추가 JS 불필요 (정적 결과 페이지)

### 4.4 도메인 서비스 호출

- `bushexa.web.services.running.get_running_page_data(route_id, date)` → `RunningPageContext` (아래 6.2 참조)
  - 내부에서 `bushexa.db.repos.timelog.BusTimelogRepository.get_log_by_route_id(route_id, date)` 호출
  - 내부에서 `bushexa.domain.running.RunService.build_table(logs, route_id, timetable)` 호출
  - `RunService.build_table`은 `parse_runs` + `parse_each_vehicle` 로직을 포함
- `bushexa.domain.running.RunService` — 도메인 서비스 클래스 (또는 모듈 레벨 함수 모음)
  - `parse_runs(logs, route_id)` → `list[list[TimelogEntry]]`
  - `parse_each_vehicle(vehicle_logs, route_id)` → `list[list[TimelogEntry]]`
  - `build_table(runs, stops, stop_nms, timetable)` → `RunTableData`

### 4.5 HTMX/SSE 동작 (실시간 화면만)

해당 없음. 이 페이지는 과거 DB 로그를 조회하는 정적 결과 페이지이며 실시간 갱신이 불필요하다.

## 5. 데이터 모델 변경 (있는 경우만)

- 신규 테이블·컬럼: 없음. 기존 `bus_timelog` 테이블 스키마 유지.
- SQLite 지원 추가: `bushexa/db/schema.sql`에 `bus_timelog` CREATE TABLE 정의 추가 (SQLite 호환 타입 사용). 기존 Postgres 테이블 스키마와 동일.
- 마이그레이션: 기존 Postgres 데이터 유지. `bushexa/db/migrations/` 디렉토리에 스크립트 위치 예약.
- 기존 데이터 보존 전략: 현재 `postgres-data/`가 4KB(거의 비어있음, 01-overview.md 참조). 마이그레이션 부담 없음.

## 6. 인터페이스 계약

### 6.1 함수 시그니처 (신규)

```python
# bushexa/web/services/running.py
from __future__ import annotations
import datetime
from bushexa.web.services.running import RunningPageContext

def get_running_page_data(
    route_id: str | None,
    date: str | None,
) -> RunningPageContext:
    """
    운행 재구성 테이블 페이지에 필요한 모든 컨텍스트를 계산한다.

    - route_id: ROUTEID 키 문자열. None이면 첫 번째 route_id 사용.
    - date: "YYYYMMDD" 형식 날짜 문자열. None이면 어제 KST 날짜 사용.

    반환: RunningPageContext
    """
    ...


# bushexa/domain/running.py
def parse_timelog(timelog: str) -> datetime.datetime:
    """
    타임로그 인덱스 문자열을 datetime으로 파싱한다.
    지원 형식: "YYYYMMDD_HH:MM:SS", "YYYY-MM-DD_HH:MM:SS"
    """
    ...


def parse_runs(
    logs: list[TimelogEntry],
    route_id: str,
) -> list[list[TimelogEntry]]:
    """
    차량 번호별로 로그를 그룹화한 후 parse_each_vehicle을 호출해
    개별 운행 회차 목록을 반환한다.
    """
    ...


def parse_each_vehicle(
    vehicle_logs: list[TimelogEntry],
    route_id: str,
) -> list[list[TimelogEntry]]:
    """
    단일 차량의 시간순 로그를 정류장 순번 역행 지점에서 분리해
    운행 회차 목록을 반환한다.
    마지막 미완성 route도 반드시 rets에 추가한다 (기존 버그 수정).
    """
    ...


# bushexa/db/repos/timelog.py
class BusTimelogRepository:
    def get_log_by_route_id(
        self,
        route_id: str,
        targetday: str | None = None,
    ) -> list[TimelogEntry]:
        """
        route_id와 날짜(YYYYMMDD)로 bus_timelog를 조회한다.
        SQLite와 Postgres 양쪽에서 동일하게 동작한다.
        """
        ...
```

### 6.2 데이터 타입 (dataclass / TypedDict)

```python
from __future__ import annotations
import datetime
from dataclasses import dataclass, field
from typing import TypedDict


class TimelogEntry(TypedDict):
    timestamp: datetime.datetime    # parse_timelog 결과
    stop_id: str
    route_id: str
    vehicle_number: str


class RunTableCell(TypedDict):
    value: str    # "HH:MM", "미" (출발역 추정), "レ" (미통과), "" (데이터 없음)


@dataclass(frozen=True)
class RunTableData:
    stop_names: list[str]                    # 정류장 표시명 목록 (stop_name_filter 적용)
    rows: list[list[RunTableCell]]           # 운행 회차 × 정류장


@dataclass(frozen=True)
class RunningPageContext:
    current_time: str                        # "평일 (working day) 09:05" KST 현재 시각
    route_options: list[tuple[str, str]]     # [(route_id, "713번 UNIST행"), ...]
    selected_route_id: str
    selected_date: str                       # "YYYYMMDD" 형식
    table: RunTableData | None               # None이면 결과 없음
    warning: str | None
```

## 7. Acceptance Checklist (Executor가 사용)

- [ ] AC-1: `GET /running?route_id=195000178&date=20250601` 요청 시 정류장 × 운행 테이블이 렌더링된다. (검증 방법: `pytest tests/routes/test_running.py::test_running_renders_table` — SQLite in-memory fixture 사용)
- [ ] AC-2: 해당 날짜·노선에 로그가 없으면 "검색된 버스가 없습니다" 메시지가 포함된 HTTP 200 응답을 반환한다. (검증 방법: `pytest tests/routes/test_running.py::test_running_empty_result`)
- [ ] AC-3: `parse_each_vehicle`에서 마지막 운행 회차가 유실되지 않는다 (버그 수정 검증). (검증 방법: `pytest tests/unit/test_running_service.py::test_parse_each_vehicle_last_run_preserved`)
- [ ] AC-4: SQLite backend로 `get_log_by_route_id` 호출 시 올바른 결과가 반환된다. (검증 방법: `pytest tests/unit/test_timelog_repo.py::test_get_log_by_route_id_sqlite`)
- [ ] AC-5: 현재 시각이 KST 기준으로 페이지 상단에 올바르게 표시된다. (검증 방법: 수동 확인 또는 `pytest tests/routes/test_running.py::test_running_shows_kst_time`)

> Executor는 모든 AC를 ✅로 만들 때까지 task in-progress 유지. 보고 시 항목별 한 줄 근거 첨부.

## 8. 테스트 계획

### 8.1 단위 테스트 (pytest)

- `tests/unit/test_running_service.py`에 추가
  - `test_parse_timelog_both_formats`: `"20210819_12:00:00"`과 `"2021-08-19_12:00:00"` 두 형식 모두 동일한 datetime으로 파싱되는지 확인
  - `test_parse_each_vehicle_last_run_preserved`: 단일 차량 로그에서 마지막 회차가 반환 목록에 포함되는지 확인 (기존 버그 회귀 방지)
  - `test_parse_runs_groups_by_vehicle`: 여러 차량 로그가 차량 번호별로 올바르게 분리되는지 확인
  - `test_parse_each_vehicle_unknown_stop_skipped`: `stop_id`가 `ROUTEID[route_id][3]`에 없는 로그는 조용히 건너뛰는지 확인
- `tests/unit/test_timelog_repo.py`에 추가
  - `test_get_log_by_route_id_sqlite`: SQLite in-memory DB에 테스트 데이터 삽입 후 `get_log_by_route_id` 반환값이 올바른 형식인지 확인

### 8.2 통합 테스트

- Flask test_client 시나리오 (`tests/routes/test_running.py`):
  - `GET /running` → HTTP 200, 노선 선택 옵션 포함 확인
  - `GET /running?route_id=195000178&date=20250601` → HTTP 200 (SQLite fixture 사용)
  - `GET /running?route_id=INVALID` → HTTP 200, 경고 메시지 포함 확인
- DB fixture: `conftest.py`에 SQLite in-memory `BusTimelogRepository` fixture 정의 (`pytest-fixture` 패턴).

### 8.3 수동 검증 시나리오

1. 브라우저에서 `http://localhost:5000/running` 접근 → 페이지 상단에 현재 KST 시각 확인, 안내 배너 확인
2. 날짜 입력 필드에서 어제 날짜 확인
3. 노선 선택 드롭다운에서 "713번 UNIST행" 선택
4. 폼 제출 → URL이 `?route_id=195000178&date=YYYYMMDD`로 변경 확인
5. DB에 해당 날짜 로그가 있으면 정류장 × 운행 테이블이 표시되는지 확인
6. 로그가 없으면 "검색된 버스가 없습니다" 메시지 확인

## 9. 변경 영향 범위

- F02 (busno): `get_timetable`, `get_weekday` 공유 서비스 함수 사용. `bushexa.data.timetable` 모듈 설계 영향.
- F08 (unist_timetable): `get_timetable`, `get_busroute_info` 공유.
- F04 (admin): `BusTimelogRepository`를 관리자 페이지의 데이터 브라우저와 공유.
- F09 (govtrack daemon): `BusTimelogRepository.insert_log`를 govtrack이 사용. repository 추상화가 govtrack 코드에도 영향.
- breaking change: No — 기존 Streamlit 페이지와 독립적으로 공존 가능.

## 10. 미해결 질문 (있다면)

- `parse_each_vehicle`의 `start_stop` 파라미터(`infopages/running_table.py:128`)가 실제로 사용되지 않는다. 설계 의도가 불명확하므로 신규 구현에서 제거하기 전에 원래 설계 목적을 확인해야 한다. (확인 대상: 기존 이슈 또는 커밋 히스토리)
- DB 반환 컬럼이 4개 버전(`idx, stop_id, route_id, vehicle_number`)과 6개 버전(`idx, stop_id, route_id, route_nm, vehicle_number, stop_name`)이 공존하는 원인을 확인해야 한다. 신규 구현에서는 6컬럼 스키마로 통일한다.
