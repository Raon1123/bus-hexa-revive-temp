---
status: designed
adr_id: ADR-008
designer: opus
auditor_status: pending
last_updated: 2026-06-01
supersedes: null
superseded_by: null
---

# ADR-008 — Testing Strategy (특히 Crawling 정밀 테스트)

> 사용자 요구사항: **"crawling하는 과정에 있어서 세밀하게 pytest도 설계하여야 한다. 버스가 지나간 기록을 log하는데 이 부분이 제대로 동작하지 않고 있는게 지금의 한계이다."**
> 본 ADR은 그 한계 회복을 위한 pytest 설계 원칙·계층·도구·실행 정책을 정한다.

## 컨텍스트

- 현재 테스트 인프라 0건 (`tests/` 디렉토리 없음).
- govtrack 데몬 결함(F09 H1~H10)이 회귀로 보호되지 않음.
- 외부 API 의존이 강해 통합 테스트 비용 큼.
- 관련 feature docs: F09 (가장 중요), F04, F10, 전 도메인.

## 결정

테스트는 **3-계층 + 1보조 시뮬레이션 계층**으로 구성한다.

| 계층 | 위치 | 의존 | 속도 | 비중 |
|---|---|---|---|---|
| Unit | `tests/unit/`, `tests/crawler/`, `tests/db/sqlite_only` | 순수 함수, in-memory | <50ms/case | 70% |
| Integration | `tests/web/`, `tests/integration/` | Flask test_client, in-memory SQLite, mock HTTP | <500ms/case | 20% |
| Postgres compat | `tests/db/postgres/` | testcontainers-python | 1-3s/case | 5% |
| Simulation | `tests/simulation/` | 시뮬레이션 framework + 결정론 seed | <200ms/case | 5% |

### 도구 선택

- pytest 8.x
- `pytest-mock` (mocker)
- `pytest-asyncio` 미도입 (Flask sync 모델, ADR-001)
- `respx` 또는 `responses` — HTTP mock (requests 라이브러리 기반)
- `freezegun` — 시간 동결 (KST 시간 비교)
- `testcontainers` (postgres 호환만)
- `hypothesis` (선택) — parsers, timetable 검증 property-based

### 외부 의존 격리 규칙

- **Unit 계층은 네트워크 호출 0건**. `requests.get` 호출은 반드시 `respx` 또는 `mocker.patch`로 차단. 위반 시 테스트 실패.
- **Postgres compat 계층 외**에서는 Postgres 미사용.
- 시간 비교는 `freezegun.freeze_time("2026-06-01T08:30:00+09:00")`로 KST 동결.

### Fixture 디렉토리

`tests/fixtures/`에 실제 응답 표본 저장:

- `tago/busloc_normal.json` (3 items)
- `tago/busloc_empty.json` (totalCount=0)
- `tago/busloc_single.json` (totalCount=1, dict form vs list form 양쪽)
- `tago/busloc_error_99.json` (resultCode=99)
- `tago/route_stops.json`
- `ulsan/arrival_normal.xml`
- `ulsan/arrival_no_bus.xml`
- `ulsan/timetable_page1.xml`, `_page2.xml`
- `holiday/2026.xml`

이 표본은 `api-manual/` DOCX의 응답 예시를 손으로 추출하여 만든다.

### 테스트 케이스 자연어 의도 (필수 규약)

모든 test case는 **자연어 검증 의도**를 동반한다. 감리(Auditor)가 그 설명만 읽고 "이 테스트가 무엇을, 어떤 입력/조건에서, 무엇이 참이어야 통과하는지"를 세부적으로 설명할 수 있어야 한다.

- 구현 시: 각 test 함수에 **docstring 1-2줄**로 검증 의도를 적는다.
  ```python
  def test_warm_from_repo_suppresses_false_positive():
      """데몬 재시작 시 warm_from_repo로 직전 위치를 적재하면,
      첫 사이클에서 차량이 같은 정류장에 있을 때 INSERT가 발생하지 않음을 검증한다 (H2 회귀)."""
      ...
  ```
- 설계 시 (Phase/feature doc): 각 케이스를 `test_name: 자연어 의도 1줄` 형식으로 기재 (P-11).
- 감리 시: 실행 감리 보고서의 `TEST_CASE_EXPLANATIONS` 섹션에 각 케이스의 의도를 자연어로 기술. docstring·assert를 읽어도 의도가 불명하면 그 케이스는 FAIL (E-8).
- 회귀 매트릭스(아래)의 각 결함은 대응 테스트의 자연어 의도에 "어느 결함(H-번호)을 막는지" 명시한다.

### 결정론적 시간

- 모든 시간 의존 코드는 `Clock` Protocol 주입 받는다.
- 테스트는 `FakeClock(now=...)` 사용.
- 운영은 `KSTClock()` 사용.

### Crawling 시뮬레이션 (특별 강조)

`tests/simulation/test_polling_sampling.py`:

- 차량 운행 모델: 정류장 N개, 각 정류장 머무름 시간 분포 `Normal(mean=8s, std=3s)`, 정류장 간 주행 시간 `Normal(mean=60s, std=15s)`.
- 시뮬레이션: 차량을 1000초 동안 운행시키며 매 1초마다 위치 업데이트.
- 폴링: 별도 sampler가 5/10/20초 간격으로 차량 위치 조회.
- 비교 지표:
  - "실제 통과한 정류장 횟수" vs "기록된 INSERT 횟수"
  - 폴링 간격별 누락률 (recall)
  - 중복 INSERT률 (precision)
- 검증 임계:
  - 폴링 10초 → recall ≥ 75%
  - 폴링 5초 → recall ≥ 90%
  - 폴링 20초 → recall ≥ 50% (현 운영 수준)
- 결정론: `numpy.random.default_rng(seed=42)` 또는 stdlib `random.Random(seed=42)` 고정.

### 회귀 보호 매트릭스 (F09 결함 ↔ 테스트)

| 결함 | 테스트 파일 | 메서드 |
|---|---|---|
| H1 sampling rate | `tests/simulation/test_polling_sampling.py` | `test_recall_at_*` |
| H2 in-memory false-positive | `tests/crawler/test_restart_no_falsepositive.py` | `test_warm_from_repo_suppresses` |
| H3 KeyError stop_ids | `tests/crawler/test_unknown_stop_safe.py` | `test_unknown_stop_inserts_null_name` |
| H4 예외 격리 | `tests/crawler/test_recorder_isolation.py` | `test_one_vehicle_failure_no_cascade` |
| H5 batch commit | `tests/crawler/test_batch_commit_and_reconnect.py` | `test_cycle_single_transaction`, `test_reconnect_after_drop` |
| H6 API failure alert | `tests/crawler/test_api_failure_alerting.py` | `test_five_consecutive_failures_trigger_alert` |
| H7 night window | `tests/crawler/test_night_window.py` | `test_short_sleep_in_night_when_configured` |
| H8 logging_file 경로 | `tests/crawler/test_tsv_path_config.py` | `test_path_from_env_or_arg` |
| H9 컨테이너 경로 | (lint test) | `test_no_hardcoded_app_logs` (`! grep -rn '/app/logs' bushexa/`) |
| H10 cursor close 순서 | `tests/db/test_repo_context_manager.py` | `test_close_order_safe` |

각 결함당 ≥1 테스트, 1순위(H1)는 시뮬레이션 + 단위 양쪽.

### CI 실행 정책

- 기본 `uv run pytest`: unit + integration + simulation (Postgres 제외) → 빠른 피드백
- `uv run pytest --postgres`: 모든 계층 + Postgres compat
- 신규 결함 발견 시 회귀 테스트 작성 → 매트릭스에 추가 후 커밋

### 커버리지 목표

- 본 단계: line coverage 측정만, 임계 미강제 (모든 신규 코드가 새로 작성됨).
- 후속 단계: `bushexa/crawler/`, `bushexa/db/` 70% 이상 권장.

## 대안

### 대안 A — 통합 테스트만 (E2E 중심)
- 장점: 사용자 관점.
- 단점: 외부 API 의존, 느림, flaky.
- 기각 사유: 핵심 결함 회귀 보호엔 단위 테스트가 필수.

### 대안 B — 시뮬레이션 생략
- 장점: 작성 비용 감소.
- 단점: H1(sampling rate)는 시뮬레이션 없이 검증 어려움.
- 기각 사유: 사용자 1순위 결함이라 회귀 보호 필요.

### 대안 C — testcontainers 미도입, Postgres 호환은 수동 검증
- 장점: 의존 감소.
- 단점: dual-backend 약속 (ADR-002) 검증 불가.
- 기각 사유: 약속 위반.

## 결과

### 긍정적 영향
- govtrack 모든 가설별 결함이 명시적 회귀 테스트를 가진다.
- 외부 API 호출 0건의 빠른 unit 계층.
- dual-backend 호환성 자동 검증.

### 부정적 영향 / 비용
- 테스트 코드 초기 작성 비용 (예상 30-40 케이스).
- testcontainers 사용 시 CI에서 docker-in-docker 또는 podman 권한 필요.
- 시뮬레이션 임계값 조정 작업 (false alarm 줄이기).

### 따라오는 작업
- `tests/conftest.py`에 `FakeClock`, `TempSqliteDb`, `MockTagoClient` fixture 정의 (P0 work item).
- `tests/fixtures/` 표본 데이터 작성 (P0).
- 회귀 매트릭스에 따라 각 결함 테스트 작성 (P1~P3 분산).

## 검증 방법

```bash
# 전체 실행
uv run pytest -q

# crawler만
uv run pytest tests/crawler/ -v

# 결정론 시드 고정
uv run pytest tests/simulation/ --randomly-dont-shuffle

# postgres 포함
uv run pytest --postgres

# 외부 호출 누수 감지 (전역 fixture에서 requests.get monkeypatch 후 호출 시 fail)
uv run pytest tests/ -k "not postgres" -W error::pytest.PytestUnraisableExceptionWarning
```

## 미해결 / 후속 결정

- Q1: 시뮬레이션 임계값의 정확한 보정 — 실측 데이터 (현 govtrack 로그) 기반 튜닝 후속 작업.
- Q2: load test (Flask + SSE) 도입 시점 — 본 단계 범위 밖.
- Q3: 외부 API 회귀를 위한 contract test — 분기별 한 번 실행, 본 ADR에서는 비강제.
