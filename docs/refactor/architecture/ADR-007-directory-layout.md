---
status: designed
adr_id: ADR-007
designer: opus
auditor_status: pending
last_updated: 2026-06-01
supersedes: null
superseded_by: null
---

# ADR-007 — Directory Layout: `bushexa/` 패키지 통합

## 컨텍스트

- 현재 구조: `app.py` (Streamlit 엔트리), `infopages/`, `src/`, `crawl/` 디렉토리 분산. import path가 `from src.crawl import ...`, `from crawl.db import ...` 등 일관 없음.
- 신규 패키지로 통합하여 단일 import root 제공 필요.
- 관련 ADR: ADR-001~006 모두.

## 결정

신규 패키지 루트를 **`bushexa/`**로 한다. 모든 새 코드는 그 아래 위치.

```text
bus-hexa-revive-temp/
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
├── README.md
├── docker/
│   ├── Dockerfile
│   ├── compose.yaml
│   └── compose.dev.yaml
├── bushexa/
│   ├── __init__.py
│   ├── __main__.py             # python -m bushexa
│   ├── cli.py                  # console_script entry (`bushexa` command)
│   ├── config.py               # AppConfig.from_env()
│   ├── logging_setup.py        # logging.config.dictConfig
│   ├── data/                   # 정적 데이터 로딩
│   │   ├── __init__.py
│   │   ├── constants.py        # ROUTEID, STOP_IDS, SERACH_STOPS 등 (구 src/constants.py)
│   │   └── timetable.py        # JSON 로더, 검증 (구 src/tools.py 일부)
│   ├── time_utils.py           # KST datetime, 평일/주말/공휴일 분기
│   ├── api_clients/            # 외부 API 클라이언트
│   │   ├── __init__.py
│   │   ├── tago.py             # 국토부 BusLcInfo, BusRouteInfo
│   │   ├── ulsan_bis.py        # 울산 BIS arrival, timetable
│   │   └── holiday.py          # 공휴일 API
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py       # DSN 파싱, sqlite/postgres
│   │   ├── schema.py           # DDL + 인덱스
│   │   └── repo.py             # BusLogRepo
│   ├── crawler/
│   │   ├── __init__.py
│   │   ├── parsers.py          # parse_busloc 등
│   │   ├── state.py            # VehicleTimeline
│   │   ├── recorder.py         # GovtrackRecorder
│   │   ├── timetable_crawl.py  # 시간표 재크롤
│   │   └── daemon.py           # CLI: crawl-loop, crawl-once
│   ├── domain/                 # 비즈니스 로직 (UI 무관)
│   │   ├── __init__.py
│   │   ├── board.py            # departure_board 합성
│   │   ├── stops.py            # stop arrivals
│   │   ├── unist_board.py
│   │   └── running.py          # parse_runs from logs
│   ├── services/               # UI에서 호출하는 응용 서비스
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── timetable_editor.py
│   │   ├── timetable_crawl.py  # 재크롤 job 관리 (UI 어댑터)
│   │   └── govtrack_status.py
│   └── web/
│       ├── __init__.py
│       ├── app.py              # create_app() 팩토리
│       ├── routes/
│       │   ├── __init__.py
│       │   ├── board.py        # /board, /partial/board
│       │   ├── busno.py
│       │   ├── info.py
│       │   ├── stops.py
│       │   ├── unist_board.py
│       │   ├── unist_timetable.py
│       │   ├── running.py
│       │   └── admin.py
│       ├── templates/
│       │   ├── base.html
│       │   ├── board.html
│       │   ├── partial/
│       │   │   └── board_table.html
│       │   ├── admin/
│       │   │   └── ...
│       │   └── ...
│       └── static/
│           ├── style.css
│           ├── app.js
│           ├── vendor/
│           │   └── htmx.min.js
│           └── media/
│               ├── hexaLogo.ico
│               └── graphisnotmap.png
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── tago_busloc_normal.json
│   │   ├── ulsan_arrival_sample.xml
│   │   └── ...
│   ├── unit/
│   │   ├── test_constants.py
│   │   ├── test_time_utils.py
│   │   ├── test_parsers.py
│   │   └── ...
│   ├── crawler/
│   │   ├── test_vehicle_timeline.py
│   │   ├── test_recorder_isolation.py
│   │   ├── test_restart_no_falsepositive.py
│   │   └── ...
│   ├── db/
│   │   ├── test_repo_sqlite.py
│   │   ├── test_repo_postgres.py
│   │   └── test_repo_compat.py
│   ├── web/
│   │   ├── test_board_route.py
│   │   ├── test_admin_auth_flow.py
│   │   └── ...
│   └── integration/
│       ├── test_daemon_smoke.py
│       └── test_e2e_serve.py
├── data/
│   ├── timetable/              # JSON (구 timetable/*.json)
│   ├── timetable_backup/       # 관리자 편집 백업 (gitignored)
│   └── bushexa.db              # SQLite (gitignored)
├── secret/                     # gitignored
├── logs/                       # gitignored
└── docs/
    └── refactor/               # 본 디렉토리
```

레이어 의존 방향 (단방향):

```text
web → services → domain → (db | api_clients | data)
crawler → (db | api_clients | data | domain)
config → (env, secret loading)
```

`web`은 `crawler`를 import하지 않는다 (역방향). 관리자가 `services.timetable_crawl`을 통해 호출.

## 대안

### 대안 A — 기존 src/, crawl/, infopages/ 유지
- 장점: 변경 비용 0. 기존 import 경로 보존.
- 단점: 3개 디렉토리 import root가 분산되어 namespace 충돌 위험. infopages는 Streamlit st.Page 트릭 의존. 신규 코드가 어느 root에 속해야 하는지 규칙 부재.
- 기각 사유: 통합 패키지가 가독성·import 일관성에 유리하며, ADR-001 (Flask) 적용 시 infopages 디렉토리 의미가 사라짐.

### 대안 B — 모놀리식 single file
- 장점: 파일 수 최소. import 명시 불필요. 작은 도구 범주에서 통상 권장.
- 단점: 8개 UI 페이지 + 데몬 + 관리자 + DB 추상화가 한 파일에 모이면 행 수가 수천을 넘어 코드 리뷰·테스트 격리·임포트 충돌이 심해짐. 신규 기능 추가 시 diff 크기가 비대해지고 병렬 작업이 어려움.
- 기각 사유: 본 프로젝트 규모(이미 module 분리 필요한 수준) 초과.

### 대안 C — `src/bushexa/` 패키지 + setuptools `src` 레이아웃
- 장점: 표준 src-layout, 테스트 격리 강함.
- 단점: 진입 경로 길어짐. uv도 `src-layout` 지원하지만 본 프로젝트 규모에 과함.
- 기각 사유: 본 단계는 flat-layout으로 충분.

## 결과

### 긍정적 영향
- 모든 import가 `from bushexa.xxx import ...` 형태로 일관.
- 레이어 명확화로 의존성 단방향 강제.
- 테스트 구조가 패키지 구조와 mirror.

### 부정적 영향 / 비용
- 대규모 이동 → 한 번에 cutover 필요. 점진 이전 시 두 import root 공존 가능 (`bushexa/` + legacy `src/`).
- 기존 코드 참조 PR이 깨질 수 있음 (운영 코드라면 영향).

### 따라오는 작업
- P1~P5 work item이 본 레이아웃을 그대로 따름.
- `pyproject.toml`의 `[tool.uv.workspace]` 또는 단일 패키지 설정.
- `data/timetable/`로 이동, 기존 `timetable/` 참조 코드 업데이트.

## 검증 방법

```bash
# 패키지 import 성공
uv run python -c "import bushexa; import bushexa.web; import bushexa.crawler"

# 레이어 위반 검사 (간단)
! grep -rn 'from bushexa.crawler' bushexa/web/
! grep -rn 'from bushexa.web' bushexa/crawler/
! grep -rn 'from bushexa.web' bushexa/domain/

# 테스트 디렉토리 구조
test -d tests/crawler && test -d tests/web && test -d tests/db
```

## 미해결 / 후속 결정

- `data/timetable/`로의 위치 변경 시 `crawl_target_timetable`의 `os.makedirs('timetable')` 같은 하드코딩 경로 일괄 검색·치환 필요 (P0 work item에 포함).
