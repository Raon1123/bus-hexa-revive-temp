---
status: fixed
postmortem_id: PM-016
severity: high
discovered: 2026-09-29
phase: 문서화 조사 (API 활용 조사 중 발견)
component: bushexa.api_clients.*, bushexa.logging_setup, bushexa.web.routes.admin._mask_secrets
related: [PM-006, ADR-013, S7, docs/guide/api-usage.md]
auditor_status: pending
fix: 2026-09-29 fix/api-key-log-masking
---

# PM-016 — data.go.kr 인증키가 요청 URL 째로 로그 파일에 기록되고, 관리자 로그 뷰어가 마스킹하지 못함

> 부검(postmortem)은 **비난이 아니라 재발 방지**를 위한 기록이다. 사람이 아니라 시스템·프로세스의 결함을 본다.
> **상태: fixed (2026-09-29).** 코드 수정·회귀 테스트 완료. 수정 이전에 기록된 로그 파일 정리는 운영자 작업(§6.2).

## 1. 요약 (3줄)

- **증상:** `logs/*.log` 에 `serviceKey=<실제 키>` 가 포함된 줄이 수백 건 있다. `/admin/logs` 뷰어도 이를 그대로 보여 준다.
- **근본 원인:** 인증키가 GET 쿼리스트링으로 전송되므로 (a) `requests` 예외 메시지(`Max retries exceeded with url: ...?serviceKey=...`)를 `logger.error(..., exc)` 로 남길 때, (b) DEBUG 레벨에서 urllib3 가 요청 줄을 찍을 때 키가 기록된다. 뷰어의 `_SECRET_PATTERN` 은 `password|token|secret|api_key|apikey|authorization` 만 다루고 `serviceKey` 를 모른다.
- **재발 방지:** 가림 규칙을 `bushexa/redact.py` 한 곳에 두고 **기록 시점**(로그 포매터, 상태·진행 파일)과 **표시 시점**(관리자 로그 뷰어) 모두에 적용했다.

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

## 6. 해결 (Resolution)

### 6.1 코드

| 위치 | 변경 |
|---|---|
| `bushexa/redact.py` (신규) | `redact_secrets(text)` — `service_?key=<값>` 의 값만 `***` 로 치환(대소문자 무시, 값은 `&`·공백·따옴표·괄호에서 끝). 다른 쿼리 파라미터는 진단용으로 보존 |
| `bushexa/logging_setup.py` `KSTFormatter.format` | 모든 출력 줄(메시지·예외 트레이스백)에 적용. `setup_logging` 의 모든 핸들러가 이 포매터를 쓰므로 root 로 전파되는 urllib3·requests 로그도 가려진다 |
| `bushexa/services/arrival_status.py` | `last_error_msg`(관리자 대시보드 표시)를 저장 전 가림 |
| `bushexa/services/recrawl_job.py` | 진행 JSONL 한 줄 전체와 메타 `error`(둘 다 SSE 로 브라우저 전달)를 저장 전 가림 |
| `bushexa/web/routes/admin.py` `_mask_secrets` | 표시 시점에 한 번 더 적용(수정 이전 로그 대비) |

- 검토한 대안: `logging.Filter` 로 `record.msg/args` 를 고치는 방식은 예외 트레이스백(`exc_text`)을 놓친다. 포매터 출력 문자열에 적용하는 쪽이 누락 경로가 없다.
- urllib3 DEBUG 요청 줄은 끄지 않았다. 값이 가려지므로 DEBUG 진단 용도로 남겨 둔다.

### 6.2 수정 이전 로그 파일 정리 (운영자, 배포 시 1회)

기존 로그 파일에는 키가 그대로 남아 있다. 파일이 root 소유이고 실행 중인 프로세스가 열고 있으므로 **멈춘 뒤** 치환하고 다시 시작한다.

```bash
podman compose -f docker/compose.yaml stop app
sudo sed -i -E "s/(service_?key=)[^&[:space:]\"'()<>]+/\\1***/Ig" logs/*.log*
podman compose -f docker/compose.yaml start app
grep -ic "servicekey=[^*]" logs/*.log*   # 모두 0 이어야 함
```

키가 로그 밖(메신저·이슈 등)으로 복사된 적이 있으면 data.go.kr 에서 키 재발급을 검토한다.

## 7. 재발 방지 (Prevention) — **필수**

- [x] **회귀 테스트** (수정 전 코드에서 4건 모두 실패 확인):
  - `tests/unit/test_redact.py` — URL·따옴표·괄호·대소문자 변형에서 값만 가리고 다른 파라미터는 보존한다.
  - `tests/unit/test_logging_setup.py::test_log_file_never_contains_service_key` — bushexa 로거 메시지, root 로 전파되는 urllib3 DEBUG 줄, 예외 트레이스백 세 경로 모두 로그 파일에 키가 남지 않는다.
  - `tests/web/test_admin_logs.py::test_masking_service_key_in_request_url` — 수정 이전 로그의 키도 뷰어가 가린다.
  - `tests/services/test_arrival_status.py::test_last_error_msg_redacts_service_key` — 대시보드용 상태 파일에 키가 저장되지 않는다.
  - `tests/services/test_recrawl_job.py::test_error_payload_and_meta_redact_service_key` — 재크롤 진행 JSONL·메타·SSE 오류 값에 키가 없다.
- [x] **코드 가드**: 가림 규칙 단일 출처 `bushexa/redact.py`.
- [x] **프로세스**: 새 외부 API·시크릿을 추가하면 `redact.py` 패턴을 갱신한다(`docs/guide/change-playbooks.md` §3).
- [ ] **운영**: 수정 이전 로그 파일 정리(§6.2).

## 8. 교훈 (Lessons)

- 시크릿 마스킹은 **기록 시점**에 한다. 표시 시점 마스킹은 파일 자체의 노출을 막지 못한다.
- 로그만이 아니라 `str(exc)` 를 저장하는 모든 곳(상태 파일, SSE 진행 기록)이 기록 지점이다.
- 예외 객체를 로그에 넣으면 URL·헤더 등 시크릿이 섞일 수 있다. 쿼리스트링 인증을 쓰는 API 는 특히 그렇다.
- 관련: [PM-006](PM-006-bearer-token-masking-bypass.md)(같은 마스킹 패턴의 키워드 누락), [PM-013](PM-013-admin-password-hash-tracked-in-git.md)(시크릿 위생).

## 9. 상태

- 수정 커밋: fix/api-key-log-masking (2026-09-29)
- 회귀 테스트: 전체 633 passed
- Auditor 확인: pending
