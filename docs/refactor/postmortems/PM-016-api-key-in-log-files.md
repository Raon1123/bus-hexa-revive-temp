---
status: draft
postmortem_id: PM-016
severity: high
discovered: 2026-09-29
phase: 문서화 조사 (API 활용 조사 중 발견)
component: bushexa.api_clients.*, bushexa.logging_setup, bushexa.web.routes.admin._mask_secrets
related: [PM-006, ADR-013, S7, docs/guide/api-usage.md]
auditor_status: pending
---

# PM-016 — data.go.kr 인증키가 요청 URL 째로 로그 파일에 기록되고, 관리자 로그 뷰어가 마스킹하지 못함

> 부검(postmortem)은 **비난이 아니라 재발 방지**를 위한 기록이다. 사람이 아니라 시스템·프로세스의 결함을 본다.
> **상태: draft — 원인 분석까지 완료, 수정·회귀 테스트 미작성.**

## 1. 요약 (3줄)

- **증상:** `logs/*.log` 에 `serviceKey=<실제 키>` 가 포함된 줄이 수백 건 있다. `/admin/logs` 뷰어도 이를 그대로 보여 준다.
- **근본 원인:** 인증키가 GET 쿼리스트링으로 전송되므로 (a) `requests` 예외 메시지(`Max retries exceeded with url: ...?serviceKey=...`)를 `logger.error(..., exc)` 로 남길 때, (b) DEBUG 레벨에서 urllib3 가 요청 줄을 찍을 때 키가 기록된다. 뷰어의 `_SECRET_PATTERN` 은 `password|token|secret|api_key|apikey|authorization` 만 다루고 `serviceKey` 를 모른다.
- **재발 방지(제안):** 로깅 단계에서 `serviceKey=` 값을 지우는 `logging.Filter` 를 모든 핸들러에 부착하고, 뷰어 패턴에 `servicekey` 를 추가하며, urllib3 로거를 WARNING 으로 고정한다.

## 2. 영향 (Impact)

2026-09-29 로컬 `logs/` 기준 `serviceKey=` 포함 줄 수(값은 확인하지 않음):

| 파일 | ERROR | DEBUG |
|---|---|---|
| `bushexa.log` | 316 | 3 |
| `bushexa-crawl.log` | 1 | 65 |
| `bushexa-arrival.log` | 2 | 42 |
| `bushexa-cache.log` | 0 | 4 |

- ERROR 줄은 **INFO 운영 설정에서도** 생긴다(네트워크 오류 때마다).
- `logs/` 는 `.gitignore` 대상이라 git 유출은 없다. 노출 경로는 로그 파일 접근자, `/admin/logs` 열람자, 로그를 복사·공유하는 경우.
- 키가 노출되면 제3자가 우리 일일 한도를 소진시킬 수 있다.

## 3. 타임라인 (발견 경위)

- 2026-09-29 API 활용 문서화를 위한 조사 중 로그 샘플을 읽다가 발견. `grep -c "serviceKey=" logs/*.log` 로 규모 확인, `_mask_secrets("…?serviceKey=AbC…")` 가 원문을 그대로 반환함을 확인.

## 4. 근본 원인 분석 (Root Cause)

- 5 Whys: 키가 로그에 있다 ← 예외 문자열에 URL 이 들어 있다 ← data.go.kr 규약상 키가 쿼리스트링이다 ← 로깅 계층에 시크릿 필터가 없다 ← PM-006 에서 **표시 계층(뷰어)** 만 마스킹했고 **기록 계층**은 다루지 않았다.
- 뷰어 패턴이 알려진 키워드 목록 방식이라, 새 시크릿 이름(`serviceKey`)을 추가하지 않으면 뚫린다(PM-006 과 같은 계열).
- 기존 테스트가 못 잡은 이유: 마스킹 테스트가 `password=`, `api_key=`, `Bearer` 만 다룬다. 실제 로그 문자열로 된 테스트가 없다.

## 5. 재현 (Reproduction)

```bash
uv run python -c "from bushexa.web.routes.admin import _mask_secrets; print(_mask_secrets('GET /x?serviceKey=AbC%2Bdef&pageNo=1'))"
# 기대: serviceKey=**** , 실제: 원문 그대로
```

## 6. 해결 (Resolution) — 미적용, 제안

1. `bushexa/logging_setup.py` 에 `serviceKey=[^&\s)'"]+` 를 치환하는 `logging.Filter` 를 두고 `setup_logging` 이 만드는 모든 핸들러에 부착한다(기록 계층 차단).
2. `bushexa/web/routes/admin.py` `_SECRET_PATTERN` 에 `servicekey` 추가(표시 계층 이중 방어). 기존 로그 파일에도 효과가 있다.
3. `logging.getLogger("urllib3").setLevel(logging.WARNING)` 로 DEBUG 요청 줄 차단.
4. 이미 기록된 로그 파일은 교체·삭제를 운영자가 결정한다. 키가 외부로 복사된 적이 있다면 data.go.kr 에서 키 재발급을 검토한다.

## 7. 재발 방지 (Prevention) — **필수**

- [ ] **회귀 테스트**: `tests/unit/test_logging_setup.py` — "requests 예외 메시지에 포함된 serviceKey 가 로그 파일에 기록되지 않는다".
- [ ] **회귀 테스트**: `tests/web/test_admin_logs.py` — "로그 뷰어가 `?serviceKey=` 쿼리 값을 마스킹한다".
- [ ] **프로세스**: 새 외부 API·시크릿을 추가할 때 마스킹 패턴 갱신을 체크리스트에 포함(`docs/guide/change-playbooks.md` §3).

## 8. 교훈 (Lessons)

- 시크릿 마스킹은 **기록 시점**에 한다. 표시 시점 마스킹은 파일 자체의 노출을 막지 못한다.
- 예외 객체를 로그에 넣으면 URL·헤더 등 시크릿이 섞일 수 있다. 쿼리스트링 인증을 쓰는 API 는 특히 그렇다.
- 관련: [PM-006](PM-006-bearer-token-masking-bypass.md)(같은 마스킹 패턴의 키워드 누락), [PM-013](PM-013-admin-password-hash-tracked-in-git.md)(시크릿 위생).

## 9. 상태

- 수정 커밋: 없음
- 회귀 테스트: 없음
- Auditor 확인: pending
