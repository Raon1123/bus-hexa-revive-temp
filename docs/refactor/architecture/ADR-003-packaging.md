---
status: designed
adr_id: ADR-003
designer: opus
auditor_status: pending
last_updated: 2026-06-01
supersedes: null
superseded_by: null
---

# ADR-003 — Packaging: uv + pyproject.toml + console_scripts

## 컨텍스트

- 현재 환경: `requirements.yaml` (conda env, 140+ 패키지). Dockerfile에서 `conda env create -f requirements.yaml`.
- 실제 직접 import는 ~8개 (streamlit, pandas, openpyxl, beautifulsoup4, requests, psycopg2, yaml, pytz).
- 빌드 시간 길고 이미지 큼.
- 사용자 요구: `uv` 채택.

## 결정

패키징은 **`pyproject.toml` + `uv`**로 한다.

- Python: 3.12 고정 (`.python-version` 또는 pyproject `requires-python = ">=3.12,<3.13"`)
- 직접 의존성 명시 (`[project] dependencies`)
- 선택 의존성 그룹 (`[project.optional-dependencies]`): `postgres`, `dev`
- 콘솔 스크립트:
  ```toml
  [project.scripts]
  bushexa = "bushexa.cli:main"
  ```
- 락파일: `uv.lock` (커밋 대상)
- 가상환경: `.venv/` (gitignore)

## 대안

### 대안 A — venv + requirements.txt
- 장점: 의존도 최소. 어떤 머신에서도 동작.
- 단점: 락파일 부재로 재현성 약함. uv 대비 느림.
- 기각 사유: 사용자 선택은 uv.

### 대안 B — Poetry
- 장점: 성숙도 높음.
- 단점: uv 대비 30~100배 느림. Python 자동 설치 미지원.
- 기각 사유: uv가 동등 이상.

### 대안 C — Conda 유지
- 장점: 변경 최소.
- 단점: 사용자 요구사항 위반, 이미지 거대.
- 기각 사유: 비-목표.

## 결과

### 긍정적 영향
- `uv sync` 한 줄로 환경 재현.
- `uv run bushexa serve`로 CLI 진입.
- Docker 이미지: `python:3.12-slim` + uv 한 줄 설치, conda 제거.
- 락파일 커밋으로 결정론적 빌드.

### 부정적 영향 / 비용
- 개발자가 uv 설치 필요 (`curl -LsSf https://astral.sh/uv/install.sh | sh`). 문서화 필요.
- 일부 native deps (psycopg2)은 wheel 사용 (`psycopg2-binary`) 또는 시스템 libpq 의존. 운영 이미지는 wheel 사용을 기본.

### 따라오는 작업
- `pyproject.toml` 초안 작성 (P0 work item).
- Dockerfile 재작성 (`docker/Dockerfile`, python:3.12-slim).
- `README.md`에 uv 설치 안내.
- 기존 `requirements.yaml`, `Dockerfile`(루트), `runscript.sh` 폐기 (cutover 시점).

## 검증 방법

```bash
uv sync
uv run python -c "import bushexa; print(bushexa.__version__)"
uv run bushexa --help
uv lock --check    # 락파일 정합성
```

## 미해결 / 후속 결정

- 시스템 libpq 의존성을 어떻게 처리할지 — `psycopg2-binary`는 wheel 제공. 운영에서 SSL 인증서 등 이슈 시 `psycopg[binary]` 또는 시스템 libpq로 전환 검토.
