---
status: resolved
pm_id: PM-002
phase: P0
author: opus
last_updated: 2026-06-01
severity: low
related: [P0-bootstrap]
---

# PM-002 — P0 부트스트랩 실행 오류 3건

P0(bootstrap) 실행/검증 중 발견한 3개 오류와 재발 방지책. 모두 P0 내에서
즉시 수정되었고, **P1~P5에 동일 함정이 재현되지 않도록** 규약화한다.

## 요약

| # | 증상 | 근본 원인 | 수정 | 재발 방지 |
|---|---|---|---|---|
| 1 | `uv run pytest` → `Failed to spawn: pytest` | dev 의존성을 `[project.optional-dependencies] dev`에 둠 → `uv sync`/`uv run`이 기본 설치하지 않음. `uv sync --frozen`이 오히려 dev 패키지를 prune | dev 도구를 PEP 735 `[dependency-groups] dev`로 이동 | **규약 D-1** |
| 2 | `uv run pytest` 수집 단계에서 `PermissionError: postgres-data/conftest.py` | pytest 기본 수집이 프로젝트 루트 전체를 순회 → 루트 소유 `postgres-data/`(PG 데이터)·legacy `src/`·`crawl/`까지 진입 | `[tool.pytest.ini_options] testpaths=["tests"]` + `norecursedirs` | **규약 D-2** |
| 3 | `test_setup_logging` 가 emit된 로그를 못 잡고 FAIL (stderr엔 출력됨) | `setup_logging`이 `propagate=False`로 설정 → pytest `caplog`(root 핸들러)에 레코드가 전파되지 않음 | 테스트에서 대상 로거에 직접 핸들러를 붙여 캡처 | **규약 T-1** |

## 상세

### 오류 1 — dev 의존성이 설치되지 않음
- **기대:** `uv run pytest -q`(P0 EC-2의 검증 명령)가 그대로 동작.
- **실제:** pytest 미설치로 spawn 실패. `[project.optional-dependencies]`는 opt-in이라 `uv sync`가 기본 설치하지 않으며, `--all-extras` 없이 `uv sync --frozen`을 돌리면 이미 설치된 dev 패키지를 제거한다.
- **근본 원인:** "테스트 도구"를 *기능 extra*로 분류한 모델링 오류.

### 오류 2 — pytest가 legacy/시스템 디렉토리를 수집
- **기대:** `tests/`만 수집.
- **실제:** 루트의 `postgres-data/`(`drwx------ systemd-coredump`)까지 stat하다 권한 거부로 collection 중단.
- **근본 원인:** 수집 범위 미지정 시 pytest는 rootdir 전체를 순회. 비파괴 원칙상 legacy 디렉토리가 그대로 남아 있어 충돌.

### 오류 3 — caplog vs propagate=False
- **기대:** `caplog.records`에 로그가 잡힘.
- **실제:** `bushexa` 로거가 `propagate=False`(중복 출력 방지, 의도된 설계)라 root에 붙는 `caplog` 핸들러로 전파되지 않음. **코드는 정상**, 테스트 검증 방식이 틀림.
- **근본 원인:** non-propagating 로거를 caplog로 검증하려 한 테스트 작성 오류.

## 재발 방지 규약 (P1~P5 적용)

- **D-1 (packaging):** 테스트/개발 전용 도구는 `[dependency-groups]`에 둔다. `[project.optional-dependencies]`는 런타임 기능 extra(예: `postgres`) 전용.
- **D-2 (pytest 범위):** 모든 phase의 pytest는 `testpaths=["tests"]`로 한정한다. 새 legacy/데이터 디렉토리가 생기면 `norecursedirs`에 추가. **검증 명령은 항상 프로젝트 루트에서 `uv run pytest -q`로 실행**하되 위 설정으로 격리.
- **T-1 (로깅 테스트):** `propagate=False` 로거(`bushexa*`)의 출력은 `caplog`로 검증하지 않는다. 대상 로거에 직접 핸들러를 붙이거나 `capsys`(스트림 핸들러)로 확인한다.

## 회귀 테스트 매핑

- D-1/D-2: `uv run pytest -q`가 루트에서 0 fail (P0 EC-2가 상시 회귀 가드).
- T-1: `tests/unit/test_logging_setup.py::test_setup_logging_is_idempotent_and_emits` 가 핸들러-직접-부착 방식으로 작성됨 (재발 시 즉시 FAIL).
