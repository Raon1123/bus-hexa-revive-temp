---
status: designed
adr_id: ADR-005
designer: opus
auditor_status: pending
last_updated: 2026-06-01
supersedes: null
superseded_by: null
---

# ADR-005 — Secrets Management

## 컨텍스트

- 현재 시크릿 위치:
  - `secret/key.txt` — 국토부/울산 BIS 공공 API 키 (gitignored)
  - `secret/db.yaml` — DB 접속 정보 (gitignored)
  - `secret/manager_password.txt` — 관리자 비밀번호 (gitignored)
  - `secret/holiday_2025.json` — 공휴일 캐시 (시크릿 아님, 데이터)
  - **공개 추적 파일에 평문 노출**: `docker-compose.yaml`, `podman-compose.yaml`에 `POSTGRES_PASSWORD: WhenMyBusRun` 하드코딩 (`docker-compose.yaml:8`).
- 관련 feature docs: F04, F09, F10

## 결정

시크릿은 **환경변수 우선**, 부재 시 **`secret/` 파일 fallback**으로 로드한다.

| 시크릿 | 환경변수 | 파일 fallback |
|---|---|---|
| 공공 API 키 | `BUSHEXA_API_KEY` | `secret/key.txt` |
| DB DSN | `DATABASE_URL` (ADR-002) | `secret/db.yaml` (legacy) |
| Flask 세션 시크릿 | `BUSHEXA_SESSION_SECRET` | (없으면 부팅 시 임시 생성 + WARNING) |
| 관리자 비밀번호 | `MANAGER_PASSWORD` (선택) | `secret/manager_password.txt` (PBKDF2 해시) |

추가 규칙:
- `.env.example`을 제공 (모든 키 이름 + 더미 값)
- `.env`는 gitignored, `python-dotenv`로 자동 로드 (개발 편의)
- compose 파일의 `POSTGRES_PASSWORD`는 `${POSTGRES_PASSWORD}` 변수 참조로 변경. 운영은 podman secret 또는 `.env` 사용.
- `secret/holiday_2025.json`은 데이터이므로 `data/` 디렉토리로 이동

## 대안

### 대안 A — 모든 시크릿을 파일만 사용 유지
- 장점: 변경 적음.
- 단점: 컨테이너 배포 시 bind-mount 강제. 환경변수가 표준.
- 기각 사유: 운영 위생.

### 대안 B — Vault / SOPS 도입
- 장점: 엔터프라이즈 grade.
- 단점: 본 앱 규모에 과스펙.
- 기각 사유: 비용 > 이익.

## 결과

### 긍정적 영향
- compose 파일에서 평문 비밀번호 제거.
- 개발자가 `.env`만 채우면 즉시 실행 가능.
- 운영은 podman-compose의 env_file 또는 secret 메커니즘으로 주입.

### 부정적 영향 / 비용
- 기존 `secret/db.yaml` 사용자가 마이그레이션 필요. 본 ADR은 한동안 fallback 유지.
- python-dotenv 의존 추가 (작음).

### 따라오는 작업
- `bushexa/config.py`에서 시크릿 로드 단일화. `AppConfig.from_env()` 팩토리.
- `.env.example` 작성 (P0 work item).
- compose 파일 수정 (ADR-006과 함께).
- 시크릿 로드 함수 단위테스트 (env 우선, 파일 fallback, 둘 다 없으면 적절한 에러).

## 검증 방법

```bash
# .env.example 존재
test -f .env.example

# compose 파일에 평문 비밀번호 없음
! grep -E 'PASSWORD: [^$]' docker/compose.yaml

# 로드 테스트
uv run pytest tests/config/test_secrets_loader.py
```

## 미해결 / 후속 결정

- API 키 rotation 절차 — 본 ADR 범위 밖, 운영 문서로 분리.
