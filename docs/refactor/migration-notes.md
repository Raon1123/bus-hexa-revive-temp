---
status: active
phase_id: P5
last_updated: 2026-06-02
---

# 운영 마이그레이션 노트 — bushexa (Streamlit/conda → Flask/uv)

본 문서는 P5 cutover 담당 운영자를 위한 단계별 지침이다.  
각 단계에 실제 실행 가능한 명령을 포함한다.

---

## cutover 전 백업

cutover 전에 반드시 아래 데이터를 안전한 위치에 백업한다.

```bash
# 현재 위치 확인
cd /path/to/bus-hexa-revive-temp

# 1. PostgreSQL 데이터 전체 백업
PGPASSWORD="$(cat secret/db.yaml | grep password | awk '{print $2}')" \
  pg_dump -h localhost -p 15432 -U bushexa bushexa \
  > backup/bushexa_$(date +%Y%m%d_%H%M%S).sql

# 또는 postgres-data/ 디렉터리 자체를 tarball
tar czf backup/postgres-data-$(date +%Y%m%d_%H%M%S).tar.gz postgres-data/

# 2. secret/ 백업 (API key, DB 자격증명)
cp -r secret/ backup/secret-$(date +%Y%m%d_%H%M%S)/

# 3. timetable JSON 백업
cp -r data/timetable/ backup/timetable-$(date +%Y%m%d_%H%M%S)/

# 4. 로그 보관
tar czf backup/logs-$(date +%Y%m%d_%H%M%S).tar.gz logs/

# 백업 목록 확인
ls -lh backup/
```

> **중요**: `postgres-data/` 는 PG14 → PG14 마이그레이션이므로 볼륨 호환성 유지.

---

## .env 작성 가이드

기존 `secret/db.yaml` 과 `secret/key.txt` 에서 값을 추출하여 `.env` 를 작성한다.

### secret/db.yaml 형식 (참고)

```yaml
user: bushexa
password: <비밀번호>
host: localhost
port: 5432
dbname: bushexa
```

### .env 작성 방법

```bash
# 템플릿 복사
cp .env.example .env

# 편집
nano .env
```

`.env` 에 설정할 항목:

```bash
# 울산 BIS / 국토부 TAGO API 키
BUSHEXA_API_KEY=<secret/key.txt 내용>

# PostgreSQL 자격증명 (secret/db.yaml 에서 추출)
POSTGRES_USER=<db.yaml user>
POSTGRES_PASSWORD=<db.yaml password>
POSTGRES_DB=<db.yaml dbname>

# 앱이 postgres 컨테이너에 접속할 URL
DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}

# Flask 세션 서명 키 (새로 생성 권장)
BUSHEXA_SESSION_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# HTTPS 운영 환경에서 반드시 true 로 설정 (S1 보안 요구사항)
BUSHEXA_SESSION_COOKIE_SECURE=true

# 로그 수준 (운영: INFO, 개발: DEBUG)
BUSHEXA_LOG_LEVEL=INFO

# 로그 디렉터리 (기본값: logs/)
BUSHEXA_LOG_DIR=logs
```

### secret/ 파일 권한 설정 (S8 보안 요구사항)

```bash
# 모든 secret 파일을 소유자만 읽을 수 있게 설정
chmod 600 secret/*.txt secret/*.yaml secret/*.key 2>/dev/null || true
ls -la secret/
# 결과: -rw------- 이어야 함
```

`.env` 파일도 동일하게 보호한다:

```bash
chmod 600 .env
```

---

## cutover 5단계

> **전제**: 백업 완료, `.env` 작성 완료, docker/podman 설치 확인.

### 단계 1 — 기존 서비스 중단

```bash
# 기존 compose 서비스 확인
podman-compose ps 2>/dev/null || docker compose ps 2>/dev/null

# 기존 컨테이너 중단 (구 compose 파일 사용)
podman-compose down 2>/dev/null || docker compose down 2>/dev/null
```

### 단계 2 — 이미지 빌드

```bash
# 새 이미지 빌드
docker compose -f docker/compose.yaml build

# 빌드 성공 확인
docker images bushexa:latest
# 이미지 크기가 500MB 미만이어야 함
```

### 단계 3 — DB 스키마 마이그레이션

```bash
# PostgreSQL 컨테이너 먼저 기동
docker compose -f docker/compose.yaml up -d postgres

# 헬스체크 대기 (최대 60초)
until docker compose -f docker/compose.yaml ps postgres | grep -q "(healthy)"; do
    echo "postgres 초기화 대기 중..."; sleep 3
done

# 신규 스키마 적용
docker compose -f docker/compose.yaml run --rm web init-db
```

### 단계 4 — 전체 서비스 기동

```bash
# 전체 서비스 기동
docker compose -f docker/compose.yaml up -d

# 상태 확인
docker compose -f docker/compose.yaml ps

# 웹 접속 확인 (호스트 포트 8017)
curl -sf http://localhost:8017/board && echo "board: OK"
curl -sf http://localhost:8017/admin/login && echo "admin/login: OK"
```

### 단계 5 — 스모크 테스트 실행

```bash
# HTTP-200 체크 (SMOKE_SKIP_FEED=1로 API key 없이도 실행 가능)
SMOKE_SKIP_FEED=1 bash scripts/smoke_compose.sh

# 전체 스모크 (API key + 네트워크 필요)
bash scripts/smoke_compose.sh

# 로그 실시간 확인
docker compose -f docker/compose.yaml logs -f
```

---

## 롤백 절차

cutover 후 문제가 발생하면 아래 순서로 롤백한다.

### 즉시 롤백 (신규 컨테이너 중단)

```bash
# 신규 서비스 종료
docker compose -f docker/compose.yaml down

# _legacy/ 에 보관된 구 파일 확인
ls _legacy/

# 구 compose 파일 복원
cp _legacy/docker-compose.yaml ./docker-compose.yaml     # 또는
cp _legacy/podman-compose.yaml ./podman-compose.yaml

# 구 서비스 재가동 (구 compose 사용)
podman-compose up -d
# 또는
docker compose up -d
```

### DB 롤백 (필요 시)

```bash
# 신규 스키마가 데이터를 손상시킨 경우에만 수행
# (PG14 → PG14 이므로 일반적으로 불필요)

# 백업에서 복구
PGPASSWORD=<비밀번호> psql -h localhost -p 15432 -U bushexa bushexa \
  < backup/bushexa_<타임스탬프>.sql
```

> **참고**: `_legacy/` 디렉터리는 git 없는 환경에서의 안전망이다.  
> cutover 시 파일을 삭제하지 말고 `_legacy/` 로 이동한다 (P5-W6).

---

## 사후 모니터 체크리스트

cutover 후 1주일간 아래 항목을 매일 점검한다.

### 매일 확인 (1주)

```bash
# 서비스 상태
docker compose -f docker/compose.yaml ps

# govtrack 크롤 누락 점검 (CycleStats 가 최근 30분 내 있어야 함)
docker compose -f docker/compose.yaml logs worker-govtrack --since 30m | grep CycleStats
# 결과 없으면: 크롤러 중단 가능성 → docker compose restart worker-govtrack

# arrival 루프 누락 점검
docker compose -f docker/compose.yaml logs worker-arrival --since 30m | grep -i "upsert\|arrival"
# 결과 없으면: arrival 루프 중단 가능성 → docker compose restart worker-arrival

# 웹 응답 확인
curl -sf http://localhost:8017/board -o /dev/null && echo "web: OK" || echo "web: FAIL"
```

### 1주 후 최종 확인

```bash
# 전체 스모크 재실행
bash scripts/smoke_compose.sh

# DB 데이터 무결성 확인
psql "postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:15432/${POSTGRES_DB}" \
  -c "SELECT COUNT(*) FROM bus_arrivals; SELECT COUNT(*) FROM bus_positions;"

# 로그 오류 집계
docker compose -f docker/compose.yaml logs --since 168h 2>&1 | grep -c ERROR || echo "ERROR 0건"
```

이상이 없으면 `_legacy/` 디렉터리를 보관 압축하고 cutover를 완료로 선언한다:

```bash
tar czf backup/_legacy-$(date +%Y%m%d).tar.gz _legacy/
# _legacy/ 는 즉시 삭제하지 않고 30일 후 정리 권장
```
