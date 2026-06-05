---
status: designed
adr_id: ADR-006
designer: opus
auditor_status: pending
last_updated: 2026-06-01
supersedes: null
superseded_by: null
---

# ADR-006 — Deployment: podman-compose + python:slim 단일 이미지

## 컨텍스트

- 운영 서버는 podman으로 컨테이너 관리.
- 현재 두 컨테이너 (`bus`=Streamlit, `bus_postgres`=PG14). bind-mount로 코드 라이브 갱신.
- conda 기반 거대 이미지 (>2GB 추정).
- 사용자 요구: docker-compose/podman-compose 경로 **유지**, 로컬은 가볍게.

## 결정

배포 구조를 다음과 같이 한다.

### 디렉토리
```text
docker/
├── Dockerfile          # python:3.12-slim + uv 기반 단일 스테이지 (또는 multi-stage)
├── compose.yaml        # 운영 base
└── compose.dev.yaml    # 개발 override (선택, bind-mount)
```

### 이미지
- Base: `python:3.12-slim-bookworm`
- 빌드 단계: `uv` 설치 → `uv sync --frozen` → 앱 복사
- 런타임: non-root user, `TZ=Asia/Seoul`, `ENTRYPOINT ["uv","run","bushexa"]`
- 단일 이미지에서 두 서비스 분기:
  - `command: ["serve"]` — Flask 웹
  - `command: ["crawl-loop"]` — govtrack 데몬

### compose.yaml (운영)
```yaml
services:
  web:
    image: bushexa:latest
    build: { context: .., dockerfile: docker/Dockerfile }
    command: ["serve", "--host", "0.0.0.0", "--port", "5000"]
    env_file: ../.env
    ports: ["8017:5000"]
    depends_on: [postgres]
    restart: always
    volumes:
      - ../data:/app/data       # SQLite 또는 timetable 데이터
      - ../secret:/app/secret:ro
      - ../logs:/app/logs

  worker:
    image: bushexa:latest
    command: ["crawl-loop"]
    env_file: ../.env
    depends_on: [postgres]
    restart: always
    volumes:
      - ../data:/app/data
      - ../secret:/app/secret:ro
      - ../logs:/app/logs

  postgres:
    image: postgres:14
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    ports: ["15432:5432"]
    restart: always
    volumes:
      - ../postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      retries: 10

networks:
  default:
    name: bushexa
```

### 로컬 개발
- compose 사용 불필요. `uv sync && uv run bushexa serve` + (선택) `uv run bushexa crawl-loop &`.
- DB는 SQLite 기본 (`data/bushexa.db`).

## 대안

### 대안 A — 단일 컨테이너 (web + worker 한 프로세스)
- 장점: 컨테이너 1개 감소.
- 단점: 워커 죽으면 웹도 죽음, 또는 보호 위한 supervisord 필요. 책임 분리 약함.
- 기각 사유: 책임 분리 우선.

### 대안 B — Postgres 컨테이너 제거 (SQLite만)
- 장점: 컨테이너 단순화.
- 단점: 운영 다중 호스트 확장 불가.
- 기각 사유: 옵션은 유지하되 dual-backend로 양쪽 지원 (ADR-002).

### 대안 C — Dockerfile 그대로 (conda 유지)
- 장점: 변경 비용 0. 기존 운영자의 친숙도 유지. 빌드 단계 검증 누적.
- 단점: 이미지 크기 2GB+ 유지. 빌드 시간 분 단위. conda forge 의존성 변동성. python:slim 대비 보안 패치 채널 협소.
- 기각 사유: 사용자 요구 (uv 채택) 위반이며, 본 ADR-003 결정과 직접 충돌.

## 결과

### 긍정적 영향
- 이미지 크기 대폭 감소 (예상 < 300MB).
- 빌드 시간 단축.
- web/worker 책임 분리, 한쪽 재시작이 다른 쪽 영향 없음.
- compose 파일에 healthcheck로 `sleep 10` 제거.

### 부정적 영향 / 비용
- 운영자가 `.env` 작성 필요 (기존 평문 → 외부화).
- depends_on healthcheck 동작 확인 필요.
- bind-mount 경로 변경 (`./logs` → `../logs` 상대 경로 또는 절대 경로).

### 따라오는 작업
- `docker/Dockerfile`, `docker/compose.yaml` 작성 (P-끝 work item).
- 기존 루트 `Dockerfile`, `docker-compose.yaml`, `podman-compose.yaml`, `runscript.sh` 제거 (cutover).
- README 배포 안내 갱신.
- 운영 마이그레이션 노트: 기존 `postgres-data/` 호환성 (PG14 → PG14, 유지).

## 검증 방법

```bash
# 이미지 빌드
podman-compose -f docker/compose.yaml build

# 컴포즈 검증
podman-compose -f docker/compose.yaml config

# 기동 (dry)
podman-compose -f docker/compose.yaml up -d
podman-compose -f docker/compose.yaml ps
curl -sf http://localhost:8017/ > /dev/null
podman-compose -f docker/compose.yaml down
```

## 미해결 / 후속 결정

- TLS 종단 — nginx/caddy 리버스 프록시 별도 컨테이너 도입 여부. 운영 환경별로 결정, 본 ADR 범위 밖.
- 로그 외부 sink (loki, syslog) — 운영 정책으로 분리.
