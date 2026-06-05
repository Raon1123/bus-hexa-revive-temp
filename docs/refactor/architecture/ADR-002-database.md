---
status: designed
adr_id: ADR-002
designer: opus
auditor_status: pending
last_updated: 2026-06-01
supersedes: null
superseded_by: null
---

# ADR-002 — Database: SQLite 기본 + PostgreSQL 옵션 (Repository 패턴)

## 컨텍스트

- 현재 `crawl/db.py:BUS_TIMELOG`이 psycopg2로 PostgreSQL에 직접 결합.
- 단일 테이블 `bus_timelog` (writer: govtrack 데몬, reader: 관리자 화면 + running_table).
- `postgres-data/` 실제 크기 4KB — 데이터 거의 없음. 마이그레이션 비용 거의 0.
- 사용자 요구: 로컬은 가볍게(SQLite), 운영은 podman-compose 유지 가능 (Postgres 옵션).
- 관련 feature docs: F04, F05, F09

## 결정

영속화 백엔드는 두 가지를 모두 지원하되 **선택은 환경변수 `DATABASE_URL`** 한 개로 결정한다.

- `DATABASE_URL=sqlite:///./data/bushexa.db` (기본) — 로컬·단일 호스트 배포
- `DATABASE_URL=postgresql://user:pass@host:port/dbname` — 운영
- 미지정 시 기본값 사용

코드는 **Repository 패턴**으로 분리한다.

- `bushexa/db/connection.py` — DSN 파싱 + Connection 팩토리
- `bushexa/db/schema.py` — SQL DDL (양 백엔드 호환 SQL, `IF NOT EXISTS`)
- `bushexa/db/repo.py` — `BusLogRepo` (insert, query, count, export)
- 호환되지 않는 부분만 백엔드별 분기 (DATE-LIKE 문법, BOOLEAN, parameter style `?` vs `%s`)

ORM은 도입하지 않는다 (단일 테이블, 쿼리 수 한정).

## 대안

### 대안 A — SQLite로 완전 전환
- 장점: 가장 단순. 컨테이너 1개 감소.
- 단점: 운영 다중 호스트 분기 시 어려움. 향후 분석 워크로드 시 한계.
- 기각 사유: 사용자가 podman-compose 운영을 유지하길 원함. Postgres 옵션 보존이 안전.

### 대안 B — PostgreSQL 유지 (호스트 설치)
- 장점: 코드 변경 최소.
- 단점: 로컬 개발 시 여전히 PG 설치 필요. uv 한 줄로 끝나지 않음.
- 기각 사유: "편리한 가동" 요구사항 위반.

### 대안 C — SQLAlchemy ORM
- 장점: dual-backend가 자연스러움.
- 단점: 의존성 추가. 본 단일 테이블 단순 쿼리에 과한 추상화.
- 기각 사유: 단순성 우선. 직접 SQL이 유지보수 명확.

## 결과

### 긍정적 영향
- 로컬에서 `DATABASE_URL` 미설정 시 즉시 SQLite로 동작.
- 운영에서 podman-compose가 Postgres 컨테이너 제공 시 환경변수 한 줄로 전환.
- pytest는 in-memory SQLite (`sqlite:///:memory:`) 사용으로 빠르고 격리됨.
- 단일 테이블의 SQL 차이가 작아 분기 비용 낮음.

### 부정적 영향 / 비용
- 백엔드별 SQL 호환성 테스트가 CI에서 양쪽으로 돌아야 함.
- SQLite는 동시 writer 1개 가정 (govtrack 데몬만 쓰므로 OK), 그러나 별도 admin 화면이 INSERT를 추가하면 락 충돌 가능 → 본 단계에서 admin은 READ-only.

### 따라오는 작업
- F09 (govtrack): `BusLogRepo`로 INSERT 이전, 사이클당 batch transaction.
- F04 (admin), F05 (running_table): READ-only `BusLogRepo` 인터페이스 사용.
- Schema 마이그레이션 도구는 본 단계 불필요 (`IF NOT EXISTS` DDL이 양 백엔드에서 idempotent).
- 인덱스 추가 (F09 5절): SQLite/Postgres 모두 동일 문법.

## 검증 방법

```bash
# SQLite 로 동작
DATABASE_URL=sqlite:///:memory: uv run pytest tests/db/ -k sqlite

# Postgres 로 동작 (testcontainers 또는 compose)
DATABASE_URL=postgresql://bushexa:WhenMyBusRun@localhost:15432/buslog uv run pytest tests/db/ -k postgres

# 동일 시나리오 호환성
uv run pytest tests/db/test_repo_compat.py
```

## 미해결 / 후속 결정

- Q1: SQLite WAL 모드 활성화 시점 — connection 생성 시 `PRAGMA journal_mode=WAL` 호출. 본 ADR에 default 포함.
- Q2: 백업 정책 — SQLite 파일은 `.gitignore`. 운영 정기 백업은 별도 운영 문서.
