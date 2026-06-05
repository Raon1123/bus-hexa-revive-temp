---
status: implemented
phase_id: P0
designer: opus
auditor_status: execution-pass (2026-06-01, EC-1~8 green, 9 tests pass)
last_updated: 2026-06-01
depends_on: []
---

# P0 — Bootstrap (패키지·도구·테스트 골격)

## 1. 목적

신규 `bushexa/` 패키지 구조, `uv` 기반 종속성, 테스트 인프라(conftest + fixtures), 시크릿 로더, `.env.example`을 마련한다. **이 Phase가 끝나면 빈 코드라도 `uv run pytest`가 0 fail로 돌아간다.**

## 2. 시작 조건 (Entry Criteria)

- [ ] 의존 Phase: 없음 (P0)
- [ ] ADR-001~008 모두 Auditor PASS
- [ ] F01~F10 feature doc 모두 Auditor PASS
- [ ] 현재 작업 브랜치 분기 (예: `refactor/p0-bootstrap`)

## 3. 종료 조건 (Exit Criteria — Auditor checklist)

- [ ] EC-1: `uv sync` 무오류 (검증: `uv sync --frozen` exit 0)
- [ ] EC-2: `uv run pytest -q` 0 fail / 0 error (skip 허용, 빈 테스트도 허용)
- [ ] EC-3: `uv run bushexa --help` 출력에 `serve`, `crawl-once`, `crawl-loop` 서브커맨드 존재
- [ ] EC-4: `bushexa/` 디렉토리 구조가 ADR-007과 일치 (필수 모듈 파일 빈 stub OK)
- [ ] EC-5: `.env.example` 존재, 모든 시크릿 키 포함 (`BUSHEXA_API_KEY`, `DATABASE_URL`, `BUSHEXA_SESSION_SECRET`, `MANAGER_PASSWORD`, `POSTGRES_*`)
- [ ] EC-6: `tests/fixtures/` 표본 9종 모두 존재
- [ ] EC-7: 신규 코드에 `import streamlit` 0건 (검증: `! grep -rn 'import streamlit' bushexa/`)
- [ ] EC-8: README에 "Quick start" 섹션 존재 + `uv` 명령 ≥3건 (W9 cover, 검증: `grep -q '^## Quick start' README.md && [ $(grep -c '\buv ' README.md) -ge 3 ]`)

### 3.1 EC ↔ Work Item AC 매핑 (P-8 추적성)

| EC | 검증 대상 | 충족하는 Work Item AC |
|---|---|---|
| EC-1 | `uv sync` 무오류 | W1: AC-W1-1, AC-W1-2 |
| EC-2 | `pytest` 0 fail | W4: AC-W4-1; W5: AC-W5-1, AC-W5-2; W6: AC-W6-1 |
| EC-3 | 서브커맨드 노출 | W3: AC-W3-1, AC-W3-2 |
| EC-4 | 디렉토리 구조 | W2: AC-W2-1, AC-W2-2 |
| EC-5 | `.env.example` 키 | W4: AC-W4-2, AC-W4-3; W8: AC-W8-2 |
| EC-6 | fixtures 9종 | W6: AC-W6-2; W7: AC-W7-1, AC-W7-2 |
| EC-7 | streamlit 0건 | 전 work item 공통 제약 (W2~W7) |
| EC-8 | README Quick start | W9: AC-W9-1, AC-W9-2 |

> 모든 work item AC가 ≥1개 EC에 매핑됨을 확인. 누락 없음.

## 4. Work Item 분해

| ID | 작업 제목 | 소요 | 의존 | 산출물 |
|---|---|---|---|---|
| W1 | pyproject.toml + uv 초기화 | S | — | pyproject.toml, uv.lock, .python-version |
| W2 | bushexa 패키지 골격 생성 | S | W1 | bushexa/**/*.py (stub 포함) |
| W3 | cli.py & subcommands stub | S | W2 | bushexa/cli.py, __main__.py |
| W4 | config.py & 시크릿 로더 | M | W2 | bushexa/config.py + .env.example + 테스트 |
| W5 | logging_setup.py | S | W2 | bushexa/logging_setup.py |
| W6 | tests/conftest.py + fixtures 디렉토리 | M | W2 | tests/conftest.py, tests/fixtures/*.{json,xml} |
| W7 | API 응답 표본 작성 (DOCX → fixture) | M | — | tests/fixtures/tago/, tests/fixtures/ulsan/, tests/fixtures/holiday/ |
| W8 | .gitignore / .env.example 갱신 | S | — | .gitignore, .env.example |
| W9 | README 초안 (uv 안내, 디렉토리 설명) | S | W2 | README.md (refactor 브랜치 한정) |

## 5. Work Item 상세

### W1 — pyproject.toml + uv 초기화
**Owner:** unassigned
**Depends:** —
**산출물:**
- `pyproject.toml`
- `uv.lock`
- `.python-version`

**지시사항:**
1. `uv init --package --name bushexa --python 3.12 .` 실행 (또는 동등한 pyproject 직접 작성)
2. `[project]` 섹션에 `dependencies` 작성:
   - `flask>=3.0`, `jinja2>=3.1`, `requests>=2.32`, `beautifulsoup4>=4.12`, `pandas>=2.2`, `openpyxl>=3.1`, `pyyaml>=6.0`, `pytz>=2024.1`, `python-dotenv>=1.0`
3. `[project.optional-dependencies]` 작성:
   - `postgres = ["psycopg2-binary>=2.9"]`
   - `dev = ["pytest>=8", "pytest-mock>=3", "responses>=0.25", "freezegun>=1.5", "testcontainers[postgres]>=4"]`
4. `[project.scripts] bushexa = "bushexa.cli:main"` 추가
5. `uv sync --all-extras --frozen` 실행하여 lockfile 생성
6. `.python-version`에 `3.12` 기록

**Acceptance:**
- [ ] AC-W1-1: `pyproject.toml`이 위 dependencies 명시 (검증: `grep -E 'flask|requests|pytest' pyproject.toml`)
- [ ] AC-W1-2: `uv sync --frozen` exit 0

**검증 명령:**
```bash
uv sync --frozen
uv lock --check
```

---

### W2 — bushexa 패키지 골격 생성
**Owner:** unassigned
**Depends:** W1
**산출물:**
- `bushexa/__init__.py` (`__version__ = "0.1.0"`)
- `bushexa/__main__.py`
- `bushexa/data/{__init__.py,constants.py,timetable.py}`
- `bushexa/time_utils.py`
- `bushexa/api_clients/{__init__.py,tago.py,ulsan_bis.py,holiday.py}`
- `bushexa/db/{__init__.py,connection.py,schema.py,repo.py}`
- `bushexa/crawler/{__init__.py,parsers.py,state.py,recorder.py,timetable_crawl.py,daemon.py}`
- `bushexa/domain/{__init__.py,board.py,stops.py,unist_board.py,running.py}`
- `bushexa/services/{__init__.py,auth.py,timetable_editor.py,timetable_crawl.py,govtrack_status.py}`
- `bushexa/web/{__init__.py,app.py,routes/__init__.py,routes/board.py,...}`

**지시사항:**
1. ADR-007 디렉토리 트리를 그대로 생성 (`find -type d` 같은 도구로 생성 후 `touch __init__.py` 일괄)
2. 모든 모듈에 docstring 한 줄 + `pass` 또는 `...`
3. `bushexa/__init__.py`에 `__version__`만
4. `bushexa/web/templates/`, `bushexa/web/static/` 디렉토리도 빈 채로 생성

**Acceptance:**
- [ ] AC-W2-1: `uv run python -c "import bushexa, bushexa.web, bushexa.crawler, bushexa.db, bushexa.domain, bushexa.services, bushexa.api_clients, bushexa.data"` 성공
- [ ] AC-W2-2: 각 서브패키지에 `__init__.py` 존재

**검증 명령:**
```bash
uv run python -c "import bushexa, bushexa.web, bushexa.crawler, bushexa.db, bushexa.domain, bushexa.services, bushexa.api_clients, bushexa.data; print('ok')"
find bushexa -type d -not -name __pycache__ | xargs -I{} test -f {}/__init__.py
```

---

### W3 — cli.py & subcommands stub
**Owner:** unassigned
**Depends:** W2
**산출물:**
- `bushexa/cli.py` — argparse 또는 click 기반 main(), 서브커맨드 `serve`, `crawl-once`, `crawl-loop`, `init-db`, `crawl-timetable`
- `bushexa/__main__.py` — `from .cli import main; main()`

**지시사항:**
1. `argparse.ArgumentParser` + `add_subparsers(dest="command", required=True)`
2. 각 서브커맨드는 정의만, 본체는 `print(f"TODO: {command}")` 또는 `NotImplementedError`
3. `--help` 출력 시 모든 서브커맨드 노출 확인
4. `pyproject.toml`의 `[project.scripts]` bushexa 진입점 동작 확인

**Acceptance:**
- [ ] AC-W3-1: `uv run bushexa --help`가 5개 서브커맨드 노출
- [ ] AC-W3-2: `uv run python -m bushexa --help`도 동등 결과

**검증 명령:**
```bash
uv run bushexa --help | grep -E "serve|crawl-once|crawl-loop|init-db|crawl-timetable"
```

---

### W4 — config.py & 시크릿 로더
**Owner:** unassigned
**Depends:** W2
**산출물:**
- `bushexa/config.py` — `AppConfig` dataclass + `from_env()` 팩토리
- `.env.example`
- `tests/config/test_secrets_loader.py`

**지시사항:**
1. ADR-005 표 그대로 우선순위 구현: env → `secret/` 파일 fallback
2. `AppConfig` 필드: `api_key: str`, `database_url: str`, `session_secret: str`, `manager_password_path: Path`, `data_dir: Path`, `tz: tzinfo`, `log_level: str`
3. `python-dotenv`로 `.env` 자동 로드 (있을 때만)
4. `BUSHEXA_SESSION_SECRET` 부재 시 임시 키 + WARNING 로그
5. `secret/key.txt`, `secret/db.yaml` 호환 유지
6. 단위테스트: env 우선, 파일 fallback, 둘 다 없을 때 에러 (api_key/database_url)

**Acceptance:**
- [ ] AC-W4-1: `uv run pytest tests/config/ -v` 통과
- [ ] AC-W4-2: `.env.example`이 5개 키 (`BUSHEXA_API_KEY`, `DATABASE_URL`, `BUSHEXA_SESSION_SECRET`, `MANAGER_PASSWORD`, `POSTGRES_*` 묶음)와 더미 값 포함
- [ ] AC-W4-3: env에 `BUSHEXA_API_KEY` 설정시 `secret/key.txt`보다 우선 적용 (테스트로 확인)

**검증 명령:**
```bash
uv run pytest tests/config/test_secrets_loader.py -v
grep -E 'BUSHEXA_API_KEY|DATABASE_URL|BUSHEXA_SESSION_SECRET' .env.example
```

---

### W5 — logging_setup.py
**Owner:** unassigned
**Depends:** W2
**산출물:**
- `bushexa/logging_setup.py` — `setup_logging(level: str = "INFO", log_dir: Path | None = None)`

**지시사항:**
1. `logging.config.dictConfig` 기반
2. 콘솔 핸들러 + 옵션으로 RotatingFileHandler (`logs/bushexa.log`, 10MB, 5 backup)
3. 포맷: `%(asctime)s [%(name)s] %(levelname)s: %(message)s`
4. KST 시간 (formatter converter override)
5. `bushexa`, `bushexa.crawler`, `bushexa.web` 로거 정의

**Acceptance:**
- [ ] AC-W5-1: `from bushexa.logging_setup import setup_logging; setup_logging()` 무오류
- [ ] AC-W5-2: 로그 메시지에 KST 시간 표기 (검증: `uv run pytest tests/unit/test_logging_setup.py::test_kst_timestamp`)

**검증 명령:**
```bash
uv run python -c "from bushexa.logging_setup import setup_logging; import logging; setup_logging(); logging.getLogger('bushexa').info('test')"
uv run pytest tests/unit/test_logging_setup.py -v
```

---

### W6 — tests/conftest.py + fixtures 디렉토리
**Owner:** unassigned
**Depends:** W2
**산출물:**
- `tests/__init__.py`
- `tests/conftest.py`
- `tests/fixtures/` (디렉토리만, 표본은 W7)

**지시사항:**
1. `conftest.py`에 다음 fixture 정의:
   - `fake_clock` — ADR-008의 `FakeClock(now)` 구현, 기본 `2026-06-01T08:30:00+09:00`
   - `tmp_sqlite_db` — `tempfile.NamedTemporaryFile` → SQLite path, 종료 시 cleanup
   - `mock_tago_client` — `MagicMock(spec=TagoClient)` (TagoClient 미구현이면 Protocol stub)
   - `app_config_test` — env-less AppConfig (memory DB)
2. `tests/conftest.py`에 외부 호출 차단 fixture (autouse=False, 옵트인):
   - `no_network` — `monkeypatch.setattr(requests, 'get', _raise)` 패치
3. 디렉토리 `tests/fixtures/`, `tests/fixtures/tago/`, `tests/fixtures/ulsan/`, `tests/fixtures/holiday/` 생성

**Acceptance:**
- [ ] AC-W6-1: `uv run pytest --collect-only` 무오류 (conftest 자체 로딩 OK)
- [ ] AC-W6-2: `tests/fixtures/{tago,ulsan,holiday}` 디렉토리 모두 존재

**검증 명령:**
```bash
uv run pytest --collect-only -q
test -d tests/fixtures/tago && test -d tests/fixtures/ulsan && test -d tests/fixtures/holiday
```

---

### W7 — API 응답 표본 작성
**Owner:** unassigned
**Depends:** —
**산출물:** 9개 fixture 파일:
- `tests/fixtures/tago/busloc_normal.json` (3 items)
- `tests/fixtures/tago/busloc_empty.json` (totalCount=0)
- `tests/fixtures/tago/busloc_single_dict.json` (totalCount=1, item이 dict)
- `tests/fixtures/tago/busloc_single_list.json` (totalCount=1, item이 list)
- `tests/fixtures/tago/busloc_error_99.json` (resultCode=99)
- `tests/fixtures/tago/route_stops.json` (정류장 목록)
- `tests/fixtures/ulsan/arrival_normal.xml`
- `tests/fixtures/ulsan/arrival_no_bus.xml`
- `tests/fixtures/holiday/2026.xml`

**지시사항:**
1. `api-manual/오픈API활용가이드_국토교통부(TAGO)_버스위치정보v1.0.docx`에서 응답 예시 추출
2. `api-manual/OpenAPI활용가이드_울산광역시_BIS_v4.2.docx`에서 도착정보 응답 추출
3. README.md (`docs/refactor/01-overview.md`의 buslog example) 참고
4. 실제 운영 응답 한 사이클을 캡처해 변형하는 것도 허용 (단 API 키 마스킹)
5. 한국어 필드값 그대로 유지 (UTF-8)

**Acceptance:**
- [ ] AC-W7-1: 9개 파일 모두 존재
- [ ] AC-W7-2: 각 fixture는 valid JSON/XML (parsing 가능)

**검증 명령:**
```bash
ls tests/fixtures/tago/ tests/fixtures/ulsan/ tests/fixtures/holiday/ | wc -l   # 최소 9
uv run python -c "import json; [json.load(open(p)) for p in __import__('glob').glob('tests/fixtures/tago/*.json')]"
uv run python -c "from xml.etree import ElementTree as ET; [ET.parse(p) for p in __import__('glob').glob('tests/fixtures/ulsan/*.xml')]"
```

---

### W8 — .gitignore / .env.example 갱신
**Owner:** unassigned
**Depends:** —
**산출물:**
- `.gitignore` (갱신)
- `.env.example` (신규)

**지시사항:**
1. `.gitignore`에 다음 추가:
   - `.venv/`
   - `__pycache__/`
   - `*.pyc`
   - `.env`
   - `data/bushexa.db*`
   - `data/timetable_backup/`
   - `logs/`
2. `.env.example`은 W4에서 정의된 5개 키 더미값
3. 기존 `.claudeignore`는 그대로

**Acceptance:**
- [ ] AC-W8-1: `.gitignore` 갱신 라인 모두 포함
- [ ] AC-W8-2: `.env.example`에 5개 키

**검증 명령:**
```bash
grep -E '\.venv|\.env$|data/bushexa.db' .gitignore
test -f .env.example
```

---

### W9 — README 초안
**Owner:** unassigned
**Depends:** W2
**산출물:**
- `README.md` (리팩토링 브랜치 한정, 기존 README는 유지하되 섹션 추가 형태)

**지시사항:**
1. 다음 섹션 추가 (기존 README는 보존):
   - "## Quick start (refactor branch)" — `uv sync && uv run bushexa serve`
   - "## Project layout" — bushexa/ 트리 (ADR-007 인용)
   - "## Tests" — `uv run pytest -q`
2. 본격 cutover는 P5에서 진행, 여기서는 dev-friendly 안내

**Acceptance:**
- [ ] AC-W9-1: README에 "Quick start" 섹션 존재
- [ ] AC-W9-2: `uv` 명령 ≥3건 인용

**검증 명령:**
```bash
grep -E "^## Quick start" README.md
grep -c '\buv ' README.md
```

## 6. 병렬화 그래프

```text
W1 ──┬──▶ W2 ──┬──▶ W3
     │         ├──▶ W4
     │         ├──▶ W5
     │         ├──▶ W6
     │         └──▶ W9
     │
W7   ──── (W2와 무관, 독립)
W8   ──── (모두와 무관)
```

병렬 가능 그룹:
- **Group A (동시 가능)**: W1, W7, W8
- **Group B (Group A 완료 후)**: W2
- **Group C (W2 후 모두 동시)**: W3, W4, W5, W6, W9

## 7. 리스크 & 롤백

### 리스크
- R1: `psycopg2-binary` wheel 부재 OS (예: musl 알파인) — 본 단계는 slim debian 가정, 운영 이미지는 ADR-006 검증
- R2: uv 미설치 환경 — 문서로 안내, 설치 명령 README 포함
- R3: fixture 작성 시 실제 API 응답과 미세 차이 — 후속 phase에서 표본 보강

### 롤백
- 신규 디렉토리(`bushexa/`, `tests/`, `data/`)만 추가, 기존 `app.py`/`infopages/`/`src/`/`crawl/` 무손상
- 롤백 = `git checkout main -- pyproject.toml uv.lock .python-version` + `rm -rf bushexa tests data`

## 8. Auditor 감리 포인트 (설계 단계)

- [ ] DA-1: 9개 work item 모두 단일 책임. (W2는 패키지 전체 골격이지만 stub 한정으로 단일 책임 인정)
- [ ] DA-2: 사이클 없음. W7/W8은 독립, 나머지는 W1→W2→{W3,4,5,6,9}로 일렬.
- [ ] DA-3: 모든 work item에 산출물 경로 명시
- [ ] DA-4: 모든 work item에 AC + 검증 명령
- [ ] DA-5: 병렬 가능 그룹 (A: W1/W7/W8, C: W3/4/5/6/9) 식별
- [ ] DA-6: EC-1~7 객관적 검증 가능 (명령 + 파일 존재)
- [ ] DA-7: L 크기 없음. M 4건 (W4, W6, W7, W2도 M 경계) → 추가 분해 시도 안내: W7은 fixture 종류별로 W7a~e 분해 가능하지만 모두 유사 작업이라 단일 단위 유지.
