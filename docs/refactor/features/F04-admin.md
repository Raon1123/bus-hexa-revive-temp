---
status: designed
designer: opus
auditor_status: design-pass (T02 2026-06-01, F-5 fixed §4.4 반환타입 완비; 잔여 C-3는 FROZEN 면제)
last_updated: 2026-06-02
feature_id: F04
---

# F04 — 관리자 페이지 (Admin Panel)

> 현재 `?hexa=6` 카운트 트릭으로 숨겨진 관리자 영역을 정식 인증 라우트 `/admin/*`으로 승격하고,
> 데이터 수동 조회 / 시간표 직접 편집 / govtrack 데몬 모니터 / 비밀번호 재설정을 통합한다.

## 0. 한 줄 요약

- **As-is:** `info.py` 안에서 query param `?hexa=6` 카운트로 `manager_page()`를 호출. 비밀번호 게이트 통과 후 (a) 비밀번호 재설정, (b) 시간표 재크롤 트리거, (c) DB 단순 쿼리 브라우저 제공. Streamlit session_state로 인증 상태 유지.
- **To-be:** 별도 Flask blueprint `/admin/*`. 서버 사이드 세션(쿠키 기반). 데이터 브라우저는 필터+페이지네이션+CSV export. 시간표는 **JSON 직접 편집 UI** + 검증 + 백업. govtrack 데몬 status 모니터 표출. 비밀번호 재설정 유지(PBKDF2).

## 1. 사용자 시나리오

- **누가/의도:** 운영 관리자. 데이터 정합성 점검, 시간표 갱신, 데몬 상태 확인.
- **Happy path:**
  1. `/admin/login` 접속 → 비밀번호 입력 → 세션 발급
  2. `/admin` 대시보드 진입 — 데몬 상태 카드, 빠른 액션 링크
  3. `/admin/data` — 필터링된 bus_timelog 조회, 페이지 이동, CSV 다운로드
  4. `/admin/timetable` — 노선 선택, JSON 편집기 + 시간 추가/삭제, 저장
  5. `/admin/timetable/recrawl` — vacation 토글 + 트리거, 진행상황 SSE 스트림
  6. `/admin/password` — 비밀번호 재설정 (현재 비밀번호 검증 + 신규 + 확인)
  7. `/admin/logs` — 애플리케이션/크롤러 로그 tail 관찰 (level·lines 필터) — **TP-015**
  8. `/admin/logout`

- **엣지 케이스:**
  - **E1**: 세션 만료된 상태로 보호 라우트 접근 → `/admin/login`으로 redirect (next= 파라미터로 복귀)
  - **E2**: `secret/manager_password.txt` 부재 + `MANAGER_PASSWORD` env 미설정 → 첫 부팅 모드로 setup 페이지 제공 (비밀번호 강제 설정)
  - **E3**: 시간표 편집 중 다른 관리자가 동시 편집 → 마지막 저장이 승리 (낙관적 잠금 불필요, 백업으로 복구). 변경 전 백업 자동 생성
  - **E4**: 시간표 JSON에 잘못된 형식 (`"25:00"`, 중복, 비-string) 저장 시도 → 422 + 에러 메시지
  - **E5**: 재크롤 도중 API 키 실패 → SSE로 에러 라인 전송, 부분 결과는 백업 후 롤백 옵션
  - **E6**: 데이터 브라우저에서 결과 100만 행 → LIMIT 1000 강제, "Total exceeded" 경고
  - **E7**: CSV export 시 한글 인코딩 (UTF-8 BOM 추가 또는 명시)
  - **E8**: 비밀번호 재설정 시 평문(legacy)으로 저장되어 있던 파일 → 신규 PBKDF2로 강제 업그레이드

## 2. 현재 구현 분석 (As-Is)

### 2.1 진입점 / 파일 / 라인 참조
- 진입 트리거: `infopages/info.py:79-101` (`?hexa=6` 카운트, manager_page 동적 import)
- 관리자 본체: `infopages/manager.py:10-117` (`manager_page`)
- 비밀번호 해시: `infopages/manager.py:125-152` (`hash_password`, `verify_password`)
- 시간표 재크롤: `src/crawl.py:374-433` (`crawl_target_timetable`)
- DB 읽기: `crawl/db.py:102-143` (`get_log_by_route_id`, `get_by_stop_id`, `get_by_vehicle_number`, `get_all`)

### 2.2 사용된 Streamlit API 전수 목록

| API | 위치 | 용도 |
|---|---|---|
| `st.title` | manager.py:11 | 페이지 타이틀 |
| `st.session_state["__mgr_auth__"]` | manager.py:15-48 | 로그인 상태 |
| `st.form("manager-login", clear_on_submit=False)` | manager.py:19 | 로그인 폼 |
| `st.text_input(type="password")` | manager.py:20, 53, 54 | 비밀번호 입력 |
| `st.form_submit_button` | manager.py:21, 55 | 폼 제출 |
| `st.error` | manager.py:34, 36, 58, 60, 92 | 오류 표시 |
| `st.stop` | manager.py:39, 93 | 페이지 종료 |
| `st.success` | manager.py:41, 71, 81 | 성공 표시 |
| `st.columns([8,1])` | manager.py:44 | 우측 정렬 컬럼 |
| `st.button` | manager.py:46, 78, 100 | 액션 버튼 |
| `st.rerun` | manager.py:48 | 로그아웃 후 리로드 |
| `st.subheader` | manager.py:50, 75, 87 | 섹션 제목 |
| `st.caption` | manager.py:51 | 부연 설명 |
| `st.form("reset-password", clear_on_submit=True)` | manager.py:52 | 비밀번호 재설정 폼 |
| `st.toggle` | manager.py:76 | vacation 모드 |
| `st.divider` | manager.py:85 | 구분선 |
| `st.selectbox` | manager.py:95 | 쿼리 모드 |
| `st.text_input("Value")` | manager.py:98 | 쿼리 인자 |
| `st.dataframe(df, use_container_width=True)` | manager.py:115 | 결과 표시 |
| `st.warning` | manager.py:112 | 결과 없음 |
| `st.exception(e)` | manager.py:73, 117 | 예외 표시 |
| `st.query_params` | info.py:79 | hidden unlock trigger |

### 2.3 데이터 흐름
- 인증: env `MANAGER_PASSWORD` (해시 가능) 또는 `secret/manager_password.txt` 파일 → `verify_password`
- 비밀번호 갱신: `hash_password` (PBKDF2-SHA256, 200000 iter) → `secret/manager_password.txt` 0o600
- 시간표 재크롤: 버튼 클릭 → `crawl_target_timetable(is_vacation)` 동기 호출 → 내부에서 Streamlit `st.text/st.success/st.error`로 진행 보고
- DB 브라우저: 모드 → 해당 메서드 호출 → `pd.DataFrame` → `st.dataframe`

### 2.4 의존 모듈 그래프

```text
infopages/manager.py
  ├── os, hashlib
  ├── streamlit, pandas
  ├── src.crawl.crawl_target_timetable   # Streamlit-coupled (F10에서 분리)
  └── crawl.db.BUS_TIMELOG               # psycopg2

infopages/info.py
  └── infopages.manager.manager_page    # dynamic import via ?hexa=6
```

### 2.5 관찰된 결함·악취

- **D1**: `?hexa=6` 트릭은 URL을 아는 사람 누구에게나 노출. 비밀번호 게이트는 있지만 사회공학 위험. 정식 `/admin/login`로 승격 필요
- **D2**: `manager.py:120` `if __name__ == "__page__":` 트릭 — Streamlit st.Page 진입 마커. 재사용 불가 패턴
- **D3**: DB 연결 실패 시 `st.stop()`만 → 사용자에게 원인 노출 부족
- **D4**: 시간표 편집 불가 (현재 재크롤만). 부분 보정 불가능
- **D5**: 데이터 브라우저에 페이지네이션 없음 → 대규모 결과 시 브라우저 멈춤 위험
- **D6**: 날짜 필터 없음 (`targetday` 파라미터 매소드 시그니처엔 있지만 UI 노출 안됨)
- **D7**: 재크롤 진행 중 화면 freeze → 진행상황 미노출 (Streamlit 동기 모델 한계)
- **D8**: 비밀번호 재설정에 **현재 비밀번호 검증 없음** → 세션 탈취 시 즉시 변경 가능 (보안 약점)
- **D9**: 비밀번호 파일이 legacy 평문이면 `verify_password`는 통과시키지만 신규 입력 시 그대로 평문 비교 → silent legacy 잔존

## 3. 외부 의존성

### 3.1 외부 API
- **시간표 재크롤만 (F10에서 정의)**: `http://openapi.its.ulsan.kr/UlsanAPI/BusTimetable.xo`

### 3.2 데이터베이스
- 읽기: `bus_timelog` 전 컬럼, 필터: route_id, stop_id, vehicle_no, idx LIKE 'YYYYMMDD_%' (날짜)
- 쓰기: 없음 (관리자 직접 INSERT는 본 단계 제공 안 함)

### 3.3 정적 파일
- 읽기/쓰기: `secret/manager_password.txt` (0o600)
- 읽기/쓰기: `data/timetable/*.json` (구 `timetable/*.json`)
- 쓰기: `data/timetable_backup/{busno}.{YYYYMMDD-HHMMSS}.json` (편집 전 백업)

## 4. 새 구현 매핑 (To-Be)

### 4.1 URL & HTTP 메서드

| 메서드 | 경로 | 인증 | 용도 |
|---|---|---|---|
| GET | `/admin/login` | public | 로그인 폼 |
| POST | `/admin/login` | public | 로그인 처리, 세션 발급, next= redirect |
| POST | `/admin/logout` | required | 세션 폐기 |
| GET | `/admin/` | required | 대시보드 |
| GET | `/admin/data` | required | DB 브라우저 (쿼리스트링 필터, 페이지네이션) |
| GET | `/admin/data.csv` | required | CSV export (동일 필터) |
| GET | `/admin/timetable` | required | 노선 선택 화면 |
| GET | `/admin/timetable/<busno>` | required | 편집기 (요일/출발지 탭, 시간 목록) |
| POST | `/admin/timetable/<busno>` | required | 저장 (검증 후 백업 + atomic rename) |
| POST | `/admin/timetable/recrawl` | required | 재크롤 작업 시작 (백그라운드 job ID 반환) |
| GET | `/admin/timetable/recrawl/<job_id>/stream` | required | SSE 진행상황 스트림 |
| GET | `/admin/govtrack/status` | required | 데몬 status JSON (F09 연계) |
| GET | `/admin/govtrack/status/stream` | required | SSE status push (5초 간격) |
| GET | `/admin/logs` | required | 애플리케이션 로그 tail 뷰 (level/lines 필터) |
| GET | `/admin/logs/stream` | required | SSE 라이브 로그 tail (선택) |
| GET | `/admin/password` | required | 비밀번호 재설정 폼 |
| POST | `/admin/password` | required | 현재 비밀번호 검증 + 신규 저장 |

### 4.2 Flask 라우트 / 핸들러 시그니처

```python
# bushexa/web/routes/admin.py
from flask import Blueprint, request, session, redirect, url_for, render_template, abort, Response, jsonify
from bushexa.services.auth import AuthService
from bushexa.services.timetable_editor import TimetableEditor
from bushexa.services.timetable_crawl import TimetableCrawlJob
from bushexa.services.govtrack_status import GovtrackStatusReader
from bushexa.db.repo import BusLogRepo

bp = Blueprint("admin", __name__, url_prefix="/admin")

def login_required(view):
    """데코레이터: session['admin_authed'] 가 True가 아니면 /admin/login으로 redirect."""

@bp.get("/login")
def login_form() -> str: ...

@bp.post("/login")
def login_submit() -> Response: ...

@bp.post("/logout")
@login_required
def logout() -> Response: ...

@bp.get("/")
@login_required
def dashboard() -> str: ...

@bp.get("/data")
@login_required
def data_browser() -> str:
    """쿼리: ?route_id=&stop_id=&vehicle=&day=YYYYMMDD&page=1&size=100"""

@bp.get("/data.csv")
@login_required
def data_csv() -> Response:
    """동일 필터로 CSV (UTF-8 BOM) streaming response, max_rows=10000"""

@bp.get("/timetable")
@login_required
def timetable_index() -> str:
    """노선 목록 (data/timetable/*.json 자동 탐색)"""

@bp.get("/timetable/<busno>")
@login_required
def timetable_edit(busno: str) -> str:
    """편집 화면. JSON을 weekday × departure 그리드로 표출."""

@bp.post("/timetable/<busno>")
@login_required
def timetable_save(busno: str) -> Response:
    """form: weekday=0|1|2, departure=<str>, times=<json array>. atomic save + 백업"""

@bp.post("/timetable/recrawl")
@login_required
def timetable_recrawl_start() -> Response:
    """form: vacation=on|off. 백그라운드 job 시작, job_id 반환 (JSON)."""

@bp.get("/timetable/recrawl/<job_id>/stream")
@login_required
def timetable_recrawl_stream(job_id: str) -> Response:
    """SSE: text/event-stream"""

@bp.get("/govtrack/status")
@login_required
def govtrack_status() -> Response: ...

@bp.get("/govtrack/status/stream")
@login_required
def govtrack_status_stream() -> Response: ...

@bp.get("/password")
@login_required
def password_form() -> str: ...

@bp.post("/password")
@login_required
def password_change() -> Response:
    """form: current=&new=&confirm="""
```

### 4.3 템플릿 & 정적 자원

```text
bushexa/web/templates/admin/
├── base.html              # 사이드바 + flash messages
├── login.html
├── dashboard.html
├── data_browser.html      # 필터 form + 결과 표 + 페이지네이션 + CSV 다운로드 버튼
├── timetable_index.html
├── timetable_edit.html    # weekday 탭 + 시간 list 편집 + 추가/삭제 버튼 (HTMX hx-post)
├── timetable_recrawl.html # vacation 토글 + 시작 버튼 + SSE 로그 영역
├── govtrack_status.html
└── password.html

bushexa/web/static/admin/
├── admin.css
└── admin.js               # HTMX 부트, SSE 핸들러, drag-reorder (선택)
```

### 4.4 도메인 서비스 호출

```python
# bushexa/services/auth.py
class AuthService:
    def __init__(self, secret_path: Path, env_password: str | None): ...
    def verify(self, plain: str) -> bool:
        """입력 평문 비밀번호를 저장된 해시(또는 legacy 평문)와 비교."""
        ...
    def change_password(self, current_plain: str, new_plain: str) -> Result:
        """반환: Result.ok | Result.error('current_invalid'|'too_short'|'io_error')
        legacy 평문 발견 시 새 비밀번호로 자동 PBKDF2 변환."""
        ...
    def set_initial(self, new_plain: str) -> Result:
        """Designer 추가(2026-06-02): setup 모드 최초 비밀번호 설정.
        반환: Result.ok | Result.error('already_set'|'too_short'|'io_error').
        ★보안: 이미 비밀번호가 존재하면(=not needs_setup) error('already_set')로 거부
        — 인증 없는 비밀번호 재설정 방지(S1/S2 방어심층). new_plain을 PBKDF2 해시로
        atomic write + chmod 0600. W10 setup 분기는 private _hash_password 복제 대신 이 메서드를 쓴다."""
        ...
    @property
    def needs_setup(self) -> bool:
        """`secret/manager_password.txt`가 없고 env도 없으면 True. setup 모드 전환에 사용."""
        ...

# bushexa/services/timetable_editor.py
class TimetableEditor:
    SCHEMA: TypedDict  # {weekday_str: {departure: [HH:MM, ...]}}
    def __init__(self, dir: Path, backup_dir: Path): ...
    def list_routes(self) -> list[RouteSummary]: ...
    def load(self, busno: str) -> TimetableData: ...
    def save(self, busno: str, data: TimetableData) -> SaveResult:
        """검증 → backup → tmp write → fsync → rename. 검증 실패 시 ValidationError."""
    def validate(self, data: TimetableData) -> list[ValidationIssue]: ...

# bushexa/services/timetable_crawl.py (F10에서 정의)
class TimetableCrawlJob:
    def start(self, *, vacation: bool) -> str:
        """비동기 시작, job_id 반환. stdlib threading.Thread + queue.Queue."""
        ...
    def progress(self, job_id: str) -> Iterator[ProgressEvent]:
        """job_id에 해당하는 진행 이벤트 스트림 반환."""
        ...

# bushexa/services/govtrack_status.py
class GovtrackStatusReader:
    """데몬이 SQLite 또는 status.json에 마지막 사이클 결과를 기록. Reader는 그것을 읽기만."""
    def latest(self) -> GovtrackStatus | None:
        """가장 최근 사이클 상태. 없으면 None."""
        ...
    def history(self, limit: int = 50) -> list[GovtrackStatus]:
        """최근 limit개 사이클 상태를 역순으로 반환."""
        ...

# bushexa/db/repo.py
class BusLogRepo:
    def query_paged(self, *, route_id: str | None, stop_id: str | None,
                    vehicle_no: str | None, day: date | None,
                    page: int = 1, size: int = 100) -> PagedResult[LogRow]: ...
    def count(self, **filters) -> int: ...
    def export_csv(self, **filters, max_rows: int = 10000) -> Iterator[bytes]: ...
```

### 4.5 HTMX/SSE 동작

- 시간표 편집: 시간 1개 추가/삭제는 HTMX `hx-post` partial update (해당 weekday 패널만 갱신)
- 재크롤 진행: SSE `text/event-stream`, 한 줄당 `event: progress\ndata: {"route":"713","day":0,"page":2}\n\n`
- govtrack status: 대시보드 카드를 SSE 5초 간격 갱신
- 실패 시: SSE 자동 재연결 (브라우저 기본 retry 3초) + UI 표식

### 4.6 애플리케이션 로그 뷰어 (관리자) — 신규 (TP-015)

> 운영 관리자가 브라우저에서 **애플리케이션/크롤러 로그**(govtrack 데몬 하트비트·경고·예외 등)를 직접 관찰한다. `bus_timelog` 데이터 브라우저(§4.1 `/admin/data`)와 별개로, `logging_setup`이 적재하는 `logs/bushexa.log`(RotatingFileHandler)를 **읽기 전용**으로 tail 한다.

**라우트**
- `GET /admin/logs` — 최근 로그 라인 뷰. 쿼리 `?level=INFO&lines=200` (해당 level 이상만, `lines` ≤ 2000).
- `GET /admin/logs/stream` — SSE 라이브 tail (선택, MVP 이후 단계).

**핸들러 시그니처** (`bushexa/web/routes/admin.py`, §4.2 코드블록에 추가)

```python
@bp.get("/logs")
@login_required
def logs_view() -> str:
    """애플리케이션 로그 tail. 쿼리: ?level=INFO&lines=200 (lines<=2000)."""

@bp.get("/logs/stream")
@login_required
def logs_stream() -> Response:
    """SSE 라이브 tail (선택). text/event-stream."""
```

**서비스** (`bushexa/services/log_reader.py`, ADR-007 services 레이어에 신규 모듈)

```python
@dataclass(frozen=True)
class LogLine:
    ts: str          # KST ISO 타임스탬프 (파싱 실패 시 원문)
    logger: str      # 예: "bushexa.crawler"
    level: str       # "INFO" | "WARNING" | "ERROR" ...
    message: str
    raw: str         # 원본 라인

class LogTailReader:
    """설정된 로그 디렉토리 안의 단일 파일만 읽는 read-only tail 리더."""
    def __init__(self, log_dir: Path, filename: str = "bushexa.log") -> None: ...
    def tail(self, lines: int = 200, level: str | None = None) -> list[LogLine]:
        """파일 끝에서 최대 `lines`줄을 역순(최신 우선)으로 읽어 파싱·필터.
        `lines`는 2000으로 상한."""
    def stream(self) -> "Iterator[LogLine]":
        """append된 신규 라인을 순차 yield (SSE용, 선택)."""
```

**보안 (보안 감리 S-카테고리 연계)**
- **경로 고정**: 파일 경로는 `config.log_dir / filename`으로만 구성한다. **사용자 입력으로 경로를 받지 않는다** → path traversal·임의 파일 읽기 차단 (S3 injection / S6 SSRF·LFI).
- `lines`·`level`은 검증한다 (정수, `lines` ≤ 2000; `level`은 표준 레벨 집합 화이트리스트).
- `login_required` 필수. 애플리케이션은 로그에 비밀번호·API 키를 남기지 않는다(로깅 규약); 표출 전 알려진 시크릿 패턴은 마스킹.
- 현재 활성 `bushexa.log`만 대상 (회전 백업 `.1~.5`는 본 단계 비노출).

**Acceptance**
- [ ] AC-L1: `GET /admin/logs` 비로그인 접근 → 302 `/admin/login` (AC-A1과 동일 게이트)
- [ ] AC-L2: INFO/ERROR가 섞인 로그에서 `?level=ERROR` → ERROR 이상 라인만, 최신이 위로
- [ ] AC-L3: `?lines=99999` → 실제 반환 ≤ 2000 (상한 강제)
- [ ] AC-L4: 로그 파일 부재 시 500이 아니라 빈 목록 + "로그 파일이 아직 없습니다" 안내
- [ ] AC-L5: 미지원 경로 파라미터(`?file=../../secret/key.txt`)는 무시되고 고정 경로만 사용

**테스트** (`tests/admin/test_log_reader.py` + `tests/web/test_admin_logs.py`)
- `test_tail_returns_recent_lines_last_first` — 임시 로그 파일에 10줄 기록 후 `tail(lines=5)`가 마지막 5줄을 최신순으로 반환하는지 검증.
- `test_tail_filters_by_level` — INFO/ERROR 혼합 파일에서 `level="ERROR"`가 ERROR 라인만 남기는지 검증.
- `test_tail_caps_lines_at_2000` — `lines=10**6` 요청 시 반환 길이가 2000 이하인지 검증 (DoS·메모리 상한).
- `test_missing_log_file_returns_empty` — 파일이 없을 때 예외 없이 빈 리스트를 돌려주는지 검증.
- `test_logs_route_requires_login` — 비로그인 `GET /admin/logs`가 로그인으로 redirect 되는지 검증.
- `test_logs_route_uses_fixed_path` — 쿼리로 경로를 주입해도 설정된 고정 경로만 읽는지(traversal 차단) 검증.

**의존/연계**
- `logging_setup.setup_logging(log_dir=...)`가 web(serve)·crawler(crawl-loop) 양쪽에서 호출되어 `logs/bushexa.log`가 적재되어야 본 뷰가 의미를 가진다.
- `AppConfig`에 `log_dir`(기본 `./logs`) 필드를 **P4에서 추가**하고, serve/crawl 진입에서 `setup_logging(log_dir=config.log_dir)`를 호출한다. (P2 데몬도 동일 디렉토리 사용)

## 5. 데이터 모델 변경

- 신규 디스크 자원: `data/timetable_backup/` (변경 전 자동 백업)
- `secret/manager_password.txt` 위치/포맷 유지. 단 legacy 평문 발견 시 다음 성공 인증의 비밀번호 변경 단계에서 자동 PBKDF2 마이그레이션
- 신규 환경변수: `BUSHEXA_SESSION_SECRET` (Flask secret_key 용), `MANAGER_PASSWORD` (선택, 컨테이너 부트스트랩)

## 6. 인터페이스 계약

```python
@dataclass(frozen=True)
class LogRow:
    idx: str
    stop_id: str
    route_id: str
    vehicle_no: str
    stop_name: str | None
    route_nm: str | None

@dataclass(frozen=True)
class PagedResult[T]:
    rows: list[T]
    page: int
    size: int
    total: int

TimetableData = dict[str, dict[str, list[str]]]  # weekday → departure → ["HH:MM", ...]

@dataclass(frozen=True)
class ValidationIssue:
    weekday: str
    departure: str
    index: int
    code: Literal["bad_format", "duplicate", "out_of_range", "not_string"]
    value: str

@dataclass(frozen=True)
class GovtrackStatus:
    # Designer 사후 정정(2026-06-02): 본래 스케치(last_cycle_at/last_inserts)는
    # P2 실구현 bushexa/services/govtrack_status.py 와 불일치. 실제 계약은 아래와 같다.
    cycle_started_at: str
    total_inserts: int
    total_errors: int
    committed: bool
    route_breakdown: dict[str, int]
    consecutive_failures: int
    last_success_at: str | None

@dataclass(frozen=True)
class Result:
    # Designer 사후 정정(2026-06-02): 성공 필드명은 `success`로 한다.
    # (`ok`라는 필드명은 팩토리 `Result.ok()`와 이름이 충돌해 type:ignore를 유발하므로 금지.)
    success: bool
    code: str | None = None          # 실패 사유 코드(None when success); 'current_invalid'|'too_short'|'io_error'
    @classmethod
    def ok(cls) -> "Result": return cls(success=True)
    @classmethod
    def error(cls, code: str) -> "Result": return cls(success=False, code=code)

@dataclass(frozen=True)
class SaveResult:
    # Designer 사후 정정(2026-06-02): W11 산출물 계약을 명문화.
    busno: str
    backup_path: Path | None         # 백업이 생성된 경우 그 경로(신규 파일이면 None)
```

> **Designer 사후 정정(2026-06-02):** §6의 `Result`/`SaveResult`는 본래 스케치였다. W9/W11 구현 중 (a) `Result` 성공필드는 `success`로 확정(필드 `ok`와 팩토리 `ok()` 이름충돌 회피), (b) `SaveResult(busno, backup_path)` 확정. **W10에서 Result를 소비하기 전 `AuthService.Result`의 필드 `ok`→`success`로 정리**하고 `# type: ignore` 제거할 것.

## 7. Acceptance Checklist

### 인증
- [ ] AC-A1: GET `/admin/`에 비로그인 접근 → 302 → `/admin/login?next=/admin/`
- [ ] AC-A2: 잘못된 비밀번호 5회 연속 → rate limit (10초 lockout, Flask `flask-limiter` 또는 자체 in-memory)
- [ ] AC-A3: 비밀번호 변경 시 현재 비밀번호 검증 실패 → 422
- [ ] AC-A4: legacy 평문 비밀번호로 인증 성공 → 다음 비밀번호 변경에서 자동 PBKDF2 마이그
- [ ] AC-A5: `needs_setup=True`이면 `/admin/login`이 setup 모드 폼 노출 (현재 비밀번호 칸 없음)
- [ ] AC-A6: 세션 쿠키 secure(=True if request.is_secure), httponly(=True), samesite=Lax

### 데이터 브라우저
- [ ] AC-D1: 필터 조합 `?route_id=195000177&day=20260601` 결과 행 수 == 동일 조건 raw query (검증: pytest fixture)
- [ ] AC-D2: 페이지네이션 next/prev 링크 정확
- [ ] AC-D3: `/admin/data.csv`가 UTF-8 BOM 시작, 헤더 한글 깨지지 않음, 최대 10000행
- [ ] AC-D4: 결과 0행 시 빈 표 + "No rows" 안내
- [ ] AC-D5: 잘못된 day 형식 (`?day=abc`) → 400

### 시간표 편집
- [ ] AC-T1: GET `/admin/timetable/713` → 평일/토/일 3개 weekday 탭 + 각 departure 시간 list
- [ ] AC-T2: POST 저장 시 검증: `HH:MM` 형식, 0≤HH≤23, 0≤MM≤59, 중복 자동 제거 + 정렬
- [ ] AC-T3: 저장 직전 `data/timetable_backup/713.{ts}.json` 생성 확인
- [ ] AC-T4: 저장은 atomic (tmp + rename), 동시 두 요청이 동기 안전
- [ ] AC-T5: 잘못된 weekday key (`"3"`) 저장 시도 → 422
- [ ] AC-T6: HTMX 부분 갱신: 시간 1건 추가 POST → 해당 panel HTML만 응답

### 재크롤
- [ ] AC-R1: POST `/admin/timetable/recrawl` → job_id 발급 + 200
- [ ] AC-R2: SSE 스트림 첫 5초 안에 `progress` 이벤트 최소 1건 송신
- [ ] AC-R3: 완료 시 `event: done\ndata: {"ok":true}` 이벤트, 그 후 close
- [ ] AC-R4: 실패 시 `event: error\ndata: {"reason":"..."}` 후 close
- [ ] AC-R5: 동일 시점 동시 2개 재크롤 요청 → 두 번째는 409 Conflict

### Govtrack 모니터
- [ ] AC-G1: 데몬이 1회 이상 정상 사이클 후 `/admin/govtrack/status` 응답에 `last_success_at` 존재
- [ ] AC-G2: 데몬 미동작 시 `consecutive_failures > 0`로 표시 + 카드 빨간 강조
- [ ] AC-G3: SSE 스트림이 5초 간격으로 push, 클라이언트 종료 시 서버 측 cleanup

### 비밀번호 재설정
- [ ] AC-P1: 빈 신규 비밀번호 → 422
- [ ] AC-P2: 8자 미만 → 422
- [ ] AC-P3: confirm 불일치 → 422
- [ ] AC-P4: 성공 시 `secret/manager_password.txt` 갱신 + 권한 0600 + PBKDF2 포맷

## 8. 테스트 계획

### 8.1 단위 테스트 (pytest)

`tests/admin/`:

1. **`test_auth_service.py`**
   - `test_verify_pbkdf2_correct`, `test_verify_pbkdf2_wrong`, `test_verify_legacy_plain`
   - `test_change_password_requires_current`
   - `test_change_password_migrates_legacy`
   - `test_needs_setup_when_no_file_no_env`

2. **`test_timetable_editor.py`**
   - `test_load_save_roundtrip`
   - `test_save_creates_backup`
   - `test_save_atomic` (mocked rename failure → original 보존)
   - `test_validate_rejects_bad_format`
   - `test_validate_dedup_sorts`
   - `test_validate_rejects_out_of_range`

3. **`test_bus_log_repo_query.py`**
   - `test_filter_by_route_id`, `test_filter_by_day`, `test_pagination`, `test_count`, `test_export_csv_utf8_bom`

### 8.2 통합 테스트 (Flask test_client)

`tests/web/`:

4. **`test_admin_auth_flow.py`**
   - 비로그인 → 302 → 로그인 후 원 페이지 도달
   - 잘못된 비밀번호 5회 → 423/429 응답

5. **`test_admin_data_browser.py`**
   - 시드된 SQLite로 필터 결과 검증

6. **`test_admin_timetable_edit.py`**
   - 편집기 GET → 200, HTML에 모든 weekday 탭 존재
   - POST 저장 후 파일 변경 + 백업 생성 확인

7. **`test_admin_recrawl_sse.py`**
   - mock TimetableCrawlJob으로 SSE 스트림 받아 `progress` 이벤트 ≥1, `done` 이벤트 종결 확인

### 8.3 수동 검증 시나리오

1. `uv run bushexa serve` 후 `http://localhost:5000/admin/login` 접속
2. 초기 setup 화면 → 비밀번호 설정 → 대시보드 도달
3. `/admin/data` → 필터 `route_id=195000177`, `day=20260601` → 결과 표 확인
4. CSV 다운로드 → 엑셀에서 한글 깨짐 확인 (BOM 효과)
5. `/admin/timetable/713` → 평일 UNIST 출발 첫 시간을 `05:00`에서 `05:01`로 변경 → 저장
6. `data/timetable_backup/713.*.json` 생성 확인
7. `/admin/timetable/recrawl` → vacation 토글 OFF → 시작 → 진행 로그가 SSE로 실시간 출력
8. `/admin/govtrack/status` → 데몬 마지막 사이클 정보 확인 (데몬 가동 중일 때)
9. 비밀번호 재설정 → 현재 비밀번호 + 신규 8자 이상 + confirm → 성공
10. 로그아웃 → 다시 `/admin/`접근 → 로그인 화면 리다이렉트

## 9. 변경 영향 범위

- 영향 받는 다른 feature doc: **F03** (info에서 `?hexa=6` 트릭 제거), **F09** (status reader가 데몬 출력에 의존), **F10** (재크롤 job 인터페이스 공유)
- Breaking change: **Yes**
  - `?hexa=6` 진입 제거 (기존 사용자가 알고 있던 경로 차단)
  - `secret/manager_password.txt` 포맷 유지 + legacy 호환

## 10. 미해결 질문

- Q1: rate limit 구현 — `flask-limiter` 추가할지, 자체 in-memory dict로 처리할지. 단일 노드 가정 시 후자가 간단.
- Q2: 시간표 편집 시 drag-reorder UX 도입 여부 — MVP에서는 단순 추가/삭제로 출발.
- Q3: 재크롤 job 영속화 — 현재 in-memory dict 가정 (서버 재시작 시 작업 유실). 운영 안정성 필요 시 SQLite job table 도입 고려.
- Q4: 관리자 다중 사용자 지원 — 현 단계는 단일 관리자 비밀번호 1개. 향후 user table 도입 시 별도 ADR.
