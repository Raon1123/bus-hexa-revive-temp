---
status: designed
adr_id: ADR-004
designer: opus
auditor_status: pending
last_updated: 2026-06-01
supersedes: null
superseded_by: null
---

# ADR-004 — Realtime: HTMX 폴링 + SSE 혼용 전략

## 컨텍스트

- 현재 모든 실시간 화면은 사용자 수동 새로고침 의존.
- 신규 적용 대상: F01 departure_board (메인 보드), F06 stops (정류장 도착), F07 unist_board (UNIST 카드).
- 추가 SSE 용도: F04 admin govtrack status push, F10 timetable recrawl progress.
- 단일 Flask 프로세스 가정. 동시 사용자 수 적음 (학내 대상).

## 결정

화면 종류별 갱신 전략을 분리한다.

| 화면 | 기본 패턴 | 간격 | 비고 |
|---|---|---|---|
| F01 departure_board | **HTMX polling** | 15초 | 전체 보드 partial swap |
| F06 stops | **HTMX polling** | 10초 | 사용자가 stop 선택 후 그 stop만. 서버 캐시 10초 |
| F07 unist_board | **HTMX polling** | 30초 | 카드 그리드 전체 |
| F04 govtrack status | **SSE** | 서버 push 5초 | 데몬이 status 갱신 시 동기적 push |
| F04/F10 recrawl progress | **SSE** | 이벤트 단위 | job 진행 중 동안 |

HTMX 폴링은 `<div hx-trigger="every 15s" hx-get="/partial/board" hx-swap="innerHTML">` 형태로 구현.
SSE는 Flask `Response(stream_with_context(generator), mimetype='text/event-stream')` 패턴.

## 대안

### 대안 A — 모든 화면 SSE
- 장점: 즉시성 ↑, 서버 push 모델.
- 단점: 정류장 도착처럼 단순 폴링이 충분한 경우 과한 인프라. 프록시/캐시 호환성 신경 써야.
- 기각 사유: 본 앱 부하 작음, 단순 폴링이 충분.

### 대안 B — 모든 화면 단순 폴링
- 장점: 가장 단순.
- 단점: 관리자 status / recrawl progress가 push 필요 → 폴링은 어색.
- 기각 사유: 데몬 status / 재크롤 로그는 SSE가 자연스러움.

### 대안 C — WebSocket
- 장점: 양방향, 표준.
- 단점: 본 앱은 양방향 불필요. Flask에 추가 설정 (`flask-sock` 등) 필요.
- 기각 사유: 과스펙.

## 결과

### 긍정적 영향
- 폴링 화면은 HTML partial fragment만 갱신 → 깜빡임 없음, 캐싱 친화.
- SSE 화면은 서버 능동 push로 진행상황 실시간 반영.
- 두 패턴 모두 Flask 단일 프로세스로 처리 가능.

### 부정적 영향 / 비용
- 폴링 간격 × 사용자 수 = API 호출량 증가. 외부 공공 API quota 모니터링 필요.
- SSE 연결은 워커 1개당 1개 점유 (sync Flask). 운영 시 동시 접속자 수 모니터 (admin은 거의 1명 가정).

### 따라오는 작업
- **ADR-010 연계 (중요):** F01/F06/F07의 실시간 데이터 소스는 울산 API 직접 호출이 아니라 `bus_arrival_cache` **백업본**이다. 전용 arrival poller가 5~10초로 크롤·DB upsert하고, HTMX 폴링(화면→서버)은 백업본만 조회한다. 따라서 HTMX 폴링 간격은 외부 API rate limit·시간오차와 무관하다.
- F01/F06/F07 feature doc의 4.5 섹션에 HTMX selector/간격 명시 (Sonnet executor가 채움)
- F04 admin이 SSE generator 구현 (status reader가 데몬 상태 변화 시 yield)
- F10 timetable recrawl이 progress callback을 SSE generator로 어댑팅
- 서버 캐시 (F06용 10초 stop_id 캐시): in-process dict + lock, 또는 `flask-caching`. 본 단계는 in-process dict 충분.

## 검증 방법

```bash
# 폴링 화면 partial 응답
curl -sf http://localhost:5000/partial/board | grep -c '<tr>'

# SSE 헤더
curl -N -sf http://localhost:5000/admin/govtrack/status/stream | head -3
# event: status\ndata: {...}\n\n 형식 확인

# 폴링 간격 (브라우저 또는 selenium): hx-trigger 속성 검사
grep -rn 'hx-trigger="every' bushexa/web/templates/
```

## 미해결 / 후속 결정

- 외부 API quota 한도 (F09 Q1과 동일). quota 근접 시 폴링 간격 동적 조정 vs 사용자 알림 결정 필요.
- 다중 워커 (gunicorn -w N) 운영 시 SSE 연결 분포 / 상태 공유 — 본 단계는 단일 워커 가정.
