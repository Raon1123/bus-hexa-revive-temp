---
status: fixed
postmortem_id: PM-012
severity: medium
discovered: 2026-06-05
phase: 운영 관찰 (라이브 테스트)
component: bushexa.api_clients._http, tago, ulsan_bis, holiday
related: [ADR-013, "tests/api_clients/test_http_timeout.py", docs/guide/api-usage.md]
auditor_status: pass
---

# PM-012 — 울산 API 느린 응답이 고정 10초 timeout 에 잘려 수집 공백 발생

> 부검(postmortem)은 **비난이 아니라 재발 방지**를 위한 기록이다. 사람이 아니라 시스템·프로세스의 결함을 본다.

## 1. 요약 (3줄)

- **증상:** 울산 BIS 응답이 느리거나 간헐적으로 무응답일 때 요청이 10초에서 끊겨 사이클 실패·통과 기록 공백이 생겼다.
- **근본 원인:** 세 클라이언트(TAGO·울산·공휴일)에 `timeout=10.0` 이 하드코딩되어 운영자가 조정할 수 없었다.
- **재발 방지:** `resolve_api_timeout()` — 명시 인자 > env `BUSHEXA_API_TIMEOUT_SECONDS` > 기본 15초. govtrack 기본 폴링도 10→15초.

## 2. 영향

- govtrack 통과 기록 누락(PM-001 계열 증상과 구분하기 어려움), 도착정보 캐시 갱신 지연.

## 3. 타임라인

- 2026-06-05 라이브 측정에서 느린 응답 관찰. 2026-06-06 `2242d57` 로 수정.

## 4. 근본 원인

- 외부 호출 timeout 이 설정이 아니라 상수였다.
- 같은 커밋에서 compose 의 `dockerfile:` 경로가 `docker/Dockerfile` 로 바뀌었지만 커밋 메시지에 없었고, 틀린 주석이 남았다(`ebdc8a3` 에서 삭제). 이후 CI 에 `docker build -f docker/Dockerfile` 잡이 추가됐다.

## 6. 해결

- `bushexa/api_clients/_http.py` `resolve_api_timeout`, 세 클라이언트 생성자 `timeout: float | None = None`.
- `.env.example` 에 크롤러 튜닝 섹션.

## 7. 재발 방지 (Prevention) — **필수**

- [x] **회귀 테스트**: `tests/api_clients/test_http_timeout.py::test_default_is_15`, `::test_env_override`, `::test_explicit_beats_env`, `::test_all_clients_use_resolved_default`, `::test_explicit_constructor_timeout_preserved`.
- [x] **코드 가드**: timeout 해석을 한 함수로.
- [ ] 남은 위험: env 에 숫자가 아닌 값을 넣으면 클라이언트 생성 시 `ValueError`. 기본 timeout(15s)이 govtrack 폴링 주기(15s)와 같아 한 사이클이 다음 사이클을 밀 수 있다.
- [ ] 남은 위험: 폴링 15초는 recorder 감사(2-4)가 권고한 ≤5초보다 길다. 15초 recall 시뮬레이션 테스트가 없다.

## 8. 교훈

- 외부 호출 timeout·재시도·폴링 주기는 처음부터 설정값으로 둔다.
- 설정 기본값을 바꿀 때는 측정 근거와 부작용(폴링 주기와의 관계, recall)을 함께 기록한다.
- 커밋 메시지에 없는 부수 변경(compose 경로)은 리뷰에서 놓친다. 한 커밋 한 목적.
