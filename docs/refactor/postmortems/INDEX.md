# Postmortem Index

> 구현·디버깅·운영 중 발견한 에러의 부검 보고서 목록. 규약은 `../00-workflow.md` §8 참조.
> 부검에서 뽑은 **재발 방지 규칙 요약**은 [`docs/guide/pitfalls.md`](../../guide/pitfalls.md) 에 있다. 새 PM 을 쓰면 그 문서에도 한 줄을 추가한다.

| ID | 제목 | severity | status | component | related |
|---|---|---|---|---|---|
| [PM-001](PM-001-govtrack-missing-passage-logs.md) | 버스 통과 기록이 bus_timelog에 제대로 남지 않음 | high | verified | bushexa.crawler | F09, P2, ADR-008 |
| [PM-002](PM-002-p0-bootstrap-execution-errors.md) | P0 부트스트랩 실행 오류 3건 (dev deps·pytest 범위·caplog) | low | resolved | bushexa(packaging/test) | P0 |
| [PM-003](PM-003-xml-response-encoding.md) | 외부 XML 응답 한글 깨짐 (requests resp.text latin-1 기본) | low | resolved | bushexa.api_clients | P1, ADR-013 |
| [PM-004](PM-004-lint-self-reference-forbidden-literal.md) | 금지 리터럴 lint가 "제거했다"는 설명 docstring을 오탐 | low | resolved | bushexa.crawler / tests lint | P2, F09, F10 |
| [PM-005](PM-005-admin-lockout-until-ts-zero.md) | 로그인 lockout 미발동 (until_ts=0 sentinel 오평가) | medium | verified | bushexa.web.routes.admin | F04, P4 |
| [PM-006](PM-006-bearer-token-masking-bypass.md) | Bearer 토큰 마스킹 누락 (Authorization: Bearer token 노출) | high | verified | bushexa.web.routes.admin._mask_secrets | S7, W16, P4 |
| [PM-007](PM-007-admin-login-open-redirect.md) | 관리자 로그인 next 파라미터 open-redirect (백슬래시 우회) | medium | fixed | bushexa.web.routes.admin | S1, W10, P4 |
| [PM-008](PM-008-holiday-silent-empty-and-overwrite.md) | 공휴일 API 오류가 "공휴일 없음"으로 삼켜지고 실패 결과가 좋은 캐시·시간표를 덮어씀 | high | verified | api_clients.holiday, services.holiday_service, crawler.timetable_crawl | review #1~#3, C1 |
| [PM-009](PM-009-lite-500-schema-boot-order.md) | 새 DB에서 /lite 500 (웹이 워커의 스키마 생성에 의존) | high | fixed | services.board_support | ADR-010 |
| [PM-010](PM-010-read-connection-cache-cold-start-and-test-leak.md) | /board 콜드 18.7초 + 연결 캐시로 인한 테스트 교차 오염 | medium | fixed | services.board_support, tests/conftest | review #8 |
| [PM-011](PM-011-audit-false-negative-truncated-grep.md) | 잘린 grep 출력으로 "CSRF 미구현" 오판 (프로세스) | low | resolved | 감리 프로세스 | code-review 2026-06-05 |
| [PM-012](PM-012-ulsan-api-timeout-10s.md) | 울산 API 느린 응답이 고정 10초 timeout 에 잘림 | medium | fixed | api_clients._http | ADR-013 |
| [PM-013](PM-013-admin-password-hash-tracked-in-git.md) | 관리자 비밀번호 해시가 git 에 추적·push 됨 | high | fixed(부분 — 비밀번호 교체는 배포 시 수행) | config, .gitignore | ADR-005 |
| [PM-014](PM-014-743-reroute-published-wrong.md) | 743 경로 변경을 틀린 경로·시행일로 게시 후 3회 정정 | medium | fixed | constants, route_diagram, info.html | change-playbooks §1 |
| [PM-015](PM-015-per-process-state-under-gunicorn.md) | gunicorn 멀티 워커에서 프로세스 로컬 상태 불일치 (SSE 404, lockout, audit 유실) | medium | verified | web.routes.admin, services.recrawl_job, fileio | review #6 #7 #9 |
| [PM-016](PM-016-api-key-in-log-files.md) | API 인증키가 요청 URL 째로 로그 파일에 기록, 뷰어 마스킹 누락 | high | fixed(기존 로그 정리는 운영) | redact, logging_setup, arrival_status, recrawl_job, admin | PM-006 |

> 참고: P5 게이트의 운영 조건(레거시 `WhenMyBusRun` 비밀번호 교체, `secret/*` 0600 프로비저닝)은 코드 버그가 아니라 배포 운영 항목이므로 PM 대신 `migration-notes.md`·P5 W1 잔여목록에서 추적한다.

## 상태 범례

- **draft**: 원인·재발방지 작성 중
- **fixed**: 수정 적용, 회귀 테스트 작성됨
- **verified**: 회귀 테스트 통과 + Auditor 확인 완료

## 작성 규칙 (요약)

1. `../templates/postmortem-template.md` 복사 → `PM-{NNN}-{slug}.md`
2. 근본 원인 + 재발 방지(회귀 테스트) 필수
3. 회귀 테스트는 자연어 의도 1줄 동반 (ADR-008)
4. 본 INDEX에 한 줄 추가
5. 일반화 가능한 교훈이면 `docs/guide/pitfalls.md` 해당 절에 규칙 1줄 + PM 링크 추가
