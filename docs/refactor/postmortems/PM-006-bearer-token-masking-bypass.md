---
status: verified
postmortem_id: PM-006
severity: high
discovered: 2026-06-02
phase: P4 / Chunk 4 (W15+이월)
component: bushexa.web.routes.admin._mask_secrets
related: [S7, W16, "tests/web/test_admin_logs.py::test_masking_bearer_token"]
auditor_status: verified (security-audit-P4-20260602-T01 — 회귀테스트 통과·마스킹 완전성 확인)
---

# PM-006 — Bearer 토큰 마스킹 누락 (`Authorization: Bearer <token>` 노출)

> 부검(postmortem)은 **비난이 아니라 재발 방지**를 위한 기록이다. 사람이 아니라 시스템·프로세스의 결함을 본다.

## 1. 요약 (3줄)

- **증상:** `Authorization: Bearer secrettoken123` 형태의 로그 라인이 `/admin/logs` 응답 HTML에서 실제 토큰 값(`secrettoken123`)이 그대로 노출됨.
- **근본 원인:** `_mask_secrets`의 정규식 `\S+`가 공백에서 멈춰, `Authorization: Bearer`만 소비하고 `secrettoken123`은 매치 범위 밖에 남겨 마스킹 대상에서 제외됨.
- **재발 방지:** 정규식을 `(?:Bearer\s+)?\S+`로 확장해 `Bearer <토큰>` 한 쌍을 원자적으로 매치·치환 + 회귀 테스트 `test_masking_bearer_token`으로 고정.

## 2. 영향 (Impact)

- 영향 받은 기능: 관리자 로그 뷰어(`/admin/logs`) 시크릿 마스킹 (S7).
- 지속 기간: W16 구현 초기 ~ Chunk 4 이월 작업에서 발견·수정(미배포). 운영 노출 없음.
- 잠재 위험: 로그에 Bearer 토큰이 기록된 경우 관리자 화면에서 토큰 원문이 노출 → 외부 API 인증 토큰 탈취 가능성(S7 위반).

## 3. 타임라인

- Chunk 4 이월 2 작업 중 Designer 매뉴얼이 "Authorization: Bearer secrettoken123 형태 엣지케이스 포함"을 명시.
- 정규식 추적: `_mask_secrets("Authorization: Bearer secrettoken123")`
  → `authorization` 키워드 매치 → `\s*[=:]\s*`가 `: ` 소비 → `\S+`가 `Bearer`(공백 전까지만) 소비 → 치환 결과: `authorization=**** secrettoken123` → 토큰 노출.
- 정규식 수정 후 테스트 작성 → `test_masking_bearer_token` 통과 확인.

## 4. 근본 원인 분석 (Root Cause)

**취약한 정규식:**
```python
r"(?i)(password|token|secret|api_key|apikey|authorization)\s*[=:]\s*\S+"
```

- `Authorization: Bearer secrettoken123`에서:
  - `authorization` ← 키 그룹 매치
  - `\s*[=:]\s*` ← `: ` 소비
  - `\S+` ← `Bearer`만 소비(공백 문자 앞에서 멈춤)
- 치환: `authorization=****` + ` secrettoken123`(남겨짐) → 토큰 노출.

**원인 체인 (5 Whys):**
1. Bearer 토큰 노출 ←
2. `\S+`가 `Bearer`에서 멈춤 ←
3. HTTP `Authorization` 헤더의 스킴(`Bearer `) + 토큰 구조를 정규식이 인식하지 않음 ←
4. 설계 시 `key=value` 단순 형태만 고려, `key: Scheme token` 복합 형태 미설계 ←
5. 보안 마스킹 정규식에 엣지케이스 검증 없음.

## 5. 재현

```bash
python -c "
import re
pat = re.compile(r'(?i)(password|token|secret|api_key|apikey|authorization)\s*[=:]\s*\S+', re.IGNORECASE)
print(pat.sub(lambda m: m.group(1) + '=****', 'Authorization: Bearer secrettoken123'))
# 수정 전 출력: authorization=**** secrettoken123  (토큰 노출!)
"
```

## 6. 해결 (Resolution)

`bushexa/web/routes/admin.py` `_SECRET_PATTERN` 정규식을 다음으로 수정:

```python
_SECRET_PATTERN = re.compile(
    r"(?i)(password|token|secret|api_key|apikey|authorization)\s*[=:]\s*(?:Bearer\s+)?\S+",
    re.IGNORECASE,
)
```

- `(?:Bearer\s+)?` 추가: `Bearer ` 스킴 접두어가 있으면 함께 소비 후 `\S+`로 토큰 값을 캡처.
- 기존 `password=hunter2`, `api_key=ABCDEF123` 패턴은 그대로 마스킹(회귀 없음).

## 7. 재발 방지 (Prevention)

- [x] **회귀 테스트**: `tests/web/test_admin_logs.py::test_masking_bearer_token` — "Authorization: Bearer <token> 형태 로그 라인에서 토큰이 응답에 노출되지 않는지" 검증 (E-13 독립 출처).
- [x] **회귀 테스트**: `tests/web/test_admin_logs.py::test_masking_password_and_api_key` — 기존 패턴 회귀 방지.
- [ ] **프로세스**: 시크릿 마스킹 정규식 변경 시 HTTP 헤더 형태(`key: Scheme value`) 포함 테스트 필수화.

## 8. 교훈 (Lessons)

- HTTP `Authorization` 헤더는 `key: Scheme value` 3-토큰 구조다. `key=value` 단순 형태와 달리 스킴(`Bearer`, `Basic`, etc.) + 값 사이에 공백이 있다. 보안 마스킹 정규식은 이 구조를 명시적으로 처리해야 한다.
- 시크릿 패턴에 새 키워드(`authorization`)를 추가할 때 해당 키워드의 실제 출력 형태를 검증하는 엣지케이스 테스트를 반드시 함께 작성한다.

## 9. 상태

- 수정 커밋: P4 Chunk 4 (W15+이월) 구현 내 수정.
- 회귀 테스트 통과 확인: `test_masking_bearer_token` PASS, `test_masking_password_and_api_key` PASS (전체 206 passed).
- Auditor 확인: pending.
