---
status: draft
adr_id: ADR-000
designer: opus
auditor_status: pending
last_updated: YYYY-MM-DD
supersedes: null
superseded_by: null
---

# ADR-000 — {{Decision Title}}

## 컨텍스트

- 어떤 문제·제약이 결정 필요를 만들었는가?
- 영향 받는 범위 (모듈/사용자/배포 환경)
- 관련 feature doc 번호

## 결정

명령형 단문 한두 줄. (예: "데이터 영속화는 SQLite를 기본 백엔드로 하고, 환경변수 `DATABASE_URL=postgres://...`로 PostgreSQL을 선택할 수 있게 한다.")

## 대안

각 대안은 3-5줄. 채택하지 않은 이유를 명시.

### 대안 A — ...
- 장점: ...
- 단점: ...
- 기각 사유: ...

### 대안 B — ...
- 장점: ...
- 단점: ...
- 기각 사유: ...

## 결과

### 긍정적 영향
- ...

### 부정적 영향 / 비용
- ...

### 따라오는 작업 (Follow-up)
- 어떤 Phase / Feature doc이 이 결정에 의존하는가
- 코드 변경 위치 핵심

## 검증 방법

- 이 결정이 잘 적용되었는지 확인하는 구체적 명령·체크
- 예: `uv run pytest tests/db/test_dual_backend.py`

## 미해결 / 후속 결정

- 본 ADR 후에 결정되어야 할 종속 결정 목록
