# Postmortem Index

> 구현·디버깅·운영 중 발견한 에러의 부검 보고서 목록. 규약은 `../00-workflow.md` §8 참조.

| ID | 제목 | severity | status | component | related |
|---|---|---|---|---|---|
| [PM-001](PM-001-govtrack-missing-passage-logs.md) | 버스 통과 기록이 bus_timelog에 제대로 남지 않음 | high | verified | bushexa.crawler | F09, P2, ADR-008 |
| [PM-002](PM-002-p0-bootstrap-execution-errors.md) | P0 부트스트랩 실행 오류 3건 (dev deps·pytest 범위·caplog) | low | resolved | bushexa(packaging/test) | P0 |
| [PM-003](PM-003-xml-response-encoding.md) | 외부 XML 응답 한글 깨짐 (requests resp.text latin-1 기본) | low | resolved | bushexa.api_clients | P1, ADR-013 |
| [PM-004](PM-004-lint-self-reference-forbidden-literal.md) | 금지 리터럴 lint가 "제거했다"는 설명 docstring을 오탐 | low | resolved | bushexa.crawler / tests lint | P2, F09, F10 |
| [PM-005](PM-005-admin-lockout-until-ts-zero.md) | 로그인 lockout 미발동 (until_ts=0 sentinel 오평가) | medium | verified | bushexa.web.routes.admin | F04, P4 |
| [PM-006](PM-006-bearer-token-masking-bypass.md) | Bearer 토큰 마스킹 누락 (Authorization: Bearer token 노출) | high | verified | bushexa.web.routes.admin._mask_secrets | S7, W16, P4 |
| [PM-007](PM-007-admin-login-open-redirect.md) | 관리자 로그인 next 파라미터 open-redirect (백슬래시 우회) | medium | fixed | bushexa.web.routes.admin | S1, W10, P4 |

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
