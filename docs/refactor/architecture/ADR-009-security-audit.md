---
status: designed
adr_id: ADR-009
designer: opus
auditor_status: pending
last_updated: 2026-06-01
supersedes: null
superseded_by: null
---

# ADR-009 — 구현 후 보안 위협 감리를 별도 단계로 수행한다

## 컨텍스트

- 본 앱은 공공 API 키, 관리자 인증, 사용자 입력(쿼리스트링·폼), DB 접근, SSE/HTMX 부분 렌더, 시간표 파일 쓰기를 다룬다 — 보안 표면이 분명히 있다.
- 기존 코드에 이미 약점: compose 파일 평문 DB 비밀번호, `?hexa=6` 숨김 관리자, 비밀번호 변경 시 현재 비밀번호 미검증(F04 D8), bare `except`로 오류 은폐.
- 사용자 요구: **"프로그램 작성 이후 보안 위협에 대한 검사도 감리할 수 있도록 계획한다."**
- 관련: F04(admin), ADR-005(secrets), ADR-010(외부 API), 전 web Phase(P4).

## 결정

보안 감리를 **구현 후 전용 단계**로 두고, `docs/refactor/auditor/security-audit-criteria.md` 기준으로 수행한다.

- **시점:** P4(web 구현) 종료 후 · P5(cutover) 전에 **보안 감리 게이트**를 통과해야 한다. 이후 각 변경 PR에도 경량 재적용.
- **수행 주체:** 별도 Auditor 컨텍스트(설계자·구현자와 분리). 보조로 `/security-review` skill을 활용한다.
- **범위(위협 카테고리):** 인증·세션, 권한, 입력 검증/인젝션(SQL·명령·경로), XSS(Jinja 자동이스케이프·HTMX), CSRF, SSRF(외부 API URL 구성), 시크릿 노출, 의존성 취약점, 안전한 기본값(쿠키 플래그·에러 메시지 정보 누출), 파일 쓰기 안전성(시간표 편집 경로 traversal), 레이트리밋/DoS.
- **산출물:** `reports/security-audit-<ts>.md` — 카테고리별 발견·심각도·재현·수정 권고. 발견된 실제 결함은 `postmortems/`에 PM으로 등재(00-workflow §8).
- **게이트 규칙:** high/critical 발견이 0건이어야 P5 진입. medium 이하는 등록 + 기한 합의.

## 대안

### 대안 A — 보안을 별도 단계 없이 코드리뷰에 포함
- 장점: 단계 추가 없음.
- 단점: 체계적 위협 카테고리 누락 위험, 책임 불명확.
- 기각 사유: 사용자가 "감리"로 분리 요구. 전용 기준·게이트가 추적성에 유리.

### 대안 B — 외부 침투테스트만
- 장점: 실전 검증.
- 단점: 비용·일정, 코드 레벨 약점(시크릿·인젝션)은 정적 감리가 더 효율.
- 기각 사유: 본 규모엔 정적 감리 + `/security-review`가 우선. 침투테스트는 후속 옵션.

## 결과

### 긍정적 영향
- 보안이 "있으면 좋은 것"이 아니라 **게이트**가 되어 누락 방지.
- 위협 카테고리 체크리스트로 감리 재현성 확보.
- 발견→PM→회귀 테스트로 재발 방지 루프에 편입.

### 부정적 영향 / 비용
- P4↔P5 사이 게이트로 일정 약간 증가.
- security-audit-criteria 유지보수 필요.

### 따라오는 작업
- `auditor/security-audit-criteria.md` 작성(본 ADR과 함께 골격 제공).
- Phase **P6-security-audit** 신설(또는 P5 진입 조건에 보안 게이트 포함).
- ADR-005(secrets)·F04(admin) 약점이 보안 감리 1차 대상.
- CI에 의존성 취약점 스캔(`uv`/`pip-audit` 류) 고려.

## 검증 방법

```bash
# 보안 감리 기준 존재
test -f docs/refactor/auditor/security-audit-criteria.md
# 시크릿 하드코딩 0건 (예시 게이트)
! grep -rEn 'password\s*=\s*["'"'"'][^"'"'"']+' bushexa/
! grep -rn 'WhenMyBusRun' docker/ bushexa/
# Jinja 자동이스케이프 활성 확인 (템플릿 |safe 남용 점검)
! grep -rn '| *safe' bushexa/web/templates/ || echo "review each |safe use"
```

## 미해결 / 후속 결정

- Q1: 보안 게이트를 별도 Phase(P6)로 둘지 P5 entry 조건으로 흡수할지 — 본 ADR은 P6 신설을 권고하되 규모에 따라 흡수 허용.
- Q2: 의존성 스캔 도구 선정(`pip-audit` vs `uv` 내장) — 후속.
- Q3: CSRF 방어 수준(Flask-WTF 토큰 도입 여부) — 관리자 폼 한정 도입 검토.
