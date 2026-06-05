---
status: designed
adr_id: ADR-010
designer: opus
auditor_status: pending
last_updated: 2026-06-01
supersedes: null
superseded_by: null
---

# ADR-010 — 울산 BIS 도착정보는 전용 크롤러가 5~10초로 DB 백업, 화면은 백업본을 읽는다

## 컨텍스트

- **운영 지식 (사용자 확인):** 울산 BIS 도착정보 API는 **너무 자주 호출하면 응답 시각에 오차**가 발생한다. 또한 사용자 수에 비례한 직접 호출은 rate limit·불안정을 부른다.
- 현 운영은 이를 막기 위해 **5~10초 간격으로 크롤링하여 백업본을 자체 DB에 저장**하고, 화면은 그 백업본을 읽는 방식으로 운영 중이다.
- 초기 리팩토링 설계(F06 stops, F01 board, F07 unist_board)는 "매 요청 시 울산 API 직접 호출 + 10초 in-process 메모리 캐시"로 잡혀 있어 **이 운영 방식과 불일치**한다. 메모리 캐시는 (a) 다중 워커 간 불일치, (b) 재시작 시 소실, (c) 여전히 사용자 트래픽이 크롤 주기를 흔들 수 있음.
- 관련 feature: F01, F06, F07. 관련 ADR: ADR-002(DB), ADR-004(realtime).

## 결정

실시간 도착정보의 외부 호출과 화면 조회를 **분리**한다.

1. **전용 크롤러(arrival poller)**가 `SERACH_STOPS`(추적 정류장 17개)를 **5~10초 간격**(`BUSHEXA_ARRIVAL_POLL_SECONDS`, 기본 7초)으로 울산 BIS `getBusArrivalInfo`에서 크롤한다.
2. 크롤 결과를 DB **백업 테이블 `bus_arrival_cache`**에 stop_id별로 **upsert**(최신 스냅샷 + 갱신 시각)한다.
3. 화면(F01/F06/F07)과 HTMX 폴링은 **울산 API를 직접 호출하지 않고** `bus_arrival_cache`(백업본)만 읽는다.
4. 화면은 백업본의 `fetched_at`을 함께 노출해 "N초 전 기준" 신선도를 표시한다.
5. 호출 빈도는 **사용자 수와 무관하게** 고정(정류장 수 × 1/poll)이며, 시간 오차를 유발하는 과호출을 원천 차단한다.

govtrack(국토부 위치 → `bus_timelog`)과 arrival poller(울산 도착 → `bus_arrival_cache`)는 **별개의 크롤러**다. 둘 다 worker 컨테이너에서 구동한다.

## 대안

### 대안 A — 매 요청 직접 호출 + 메모리 캐시 (초기안)
- 장점: 구현 단순, DB 테이블 불필요.
- 단점: 다중 워커 캐시 불일치, 재시작 소실, 트래픽이 크롤 주기를 흔들어 **시간 오차 유발**. 운영 방식과 불일치.
- 기각 사유: 사용자가 확인한 시간 오차 문제를 못 막는다.

### 대안 B — 외부 캐시(Redis)로 백업
- 장점: 빠른 공유 캐시, TTL 관리 용이.
- 단점: 인프라 1종 추가(컨테이너↑), 단일 호스트 규모에 과함. 영속성 위해 결국 DB 필요.
- 기각 사유: ADR-002의 dual-backend DB로 충분, 의존 최소화 우선.

### 대안 C — 화면이 직접 호출하되 전역 rate limiter로 throttle
- 장점: 테이블 불필요.
- 단점: 동시 요청이 한 호출을 기다리며 직렬화, SSE/HTMX 다수 연결 시 병목. 백업·신선도 표시 불가.
- 기각 사유: 백업본 영속·다중 워커 일관 요구를 못 채움.

## 결과

### 긍정적 영향
- 울산 API 호출량이 **고정**(17 정류장 × 1/7초 ≈ 2.4 req/s)되어 시간 오차·rate limit 회피.
- 화면 응답이 빨라짐(외부 호출 제거, DB 조회만).
- 다중 워커·재시작에도 백업본 일관.
- 신선도(`fetched_at`) 노출로 사용자 신뢰↑.

### 부정적 영향 / 비용
- `bus_arrival_cache` 테이블·upsert 로직·poller 데몬 신규 필요.
- 백업본이라 최대 poll 주기만큼(≤10초) 지연 — 실시간성 약간 희생(허용 범위).
- worker가 govtrack + arrival 2개 루프를 구동(또는 2개 worker).

### 따라오는 작업
- **ADR-004 갱신:** F01/F06/F07의 데이터 소스를 "live API"→"`bus_arrival_cache` 백업본"으로 정정. HTMX 폴링은 백업본 조회.
- **P1:** `db/schema.py`에 `bus_arrival_cache`(stop_id PK, payload, fetched_at) 추가. `BusArrivalRepo` 추가.
- **P2:** arrival poller work item 추가(`bushexa/crawler/arrival_poller.py`, CLI `arrival-loop`), 5~10초 크롤 + upsert. 회귀 테스트(주기 고정·과호출 방지).
- **P3:** domain board/stops/unist_board가 client 대신 `BusArrivalRepo`를 읽도록 시그니처 변경.
- **F06/F01/F07:** 데이터 흐름·캐시 섹션을 백업본 기반으로 수정.
- **PM 연계:** 과호출로 인한 시간오차는 잠재 결함 — 발생 시 postmortem.

## 검증 방법

```bash
# poller가 고정 주기로만 울산 API를 호출하는지 (사용자 트래픽 무관)
uv run pytest tests/crawler/test_arrival_poller.py -k "poll_interval or no_overcall"
# 화면이 울산 API를 직접 호출하지 않는지 (백업본만 읽음)
! grep -rn 'UlsanBisClient\|getBusArrivalInfo' bushexa/domain/ bushexa/web/routes/
# 백업본 신선도 표시
uv run pytest tests/web/test_stops_route.py -k freshness
```

## 미해결 / 후속 결정

- Q1: poll 주기 정확값(5 vs 7 vs 10초)은 실측 시간오차와 quota로 보정. 기본 7초로 출발.
- Q2: `bus_arrival_cache`를 통과 이력(`bus_timelog`)과 합칠지 — 본 ADR은 별도 테이블(스냅샷 upsert vs append 이력 성격이 다름).
- Q3: arrival poller를 govtrack과 한 프로세스(2 루프)로 둘지, 별 worker로 둘지 — 운영 부하 보고 P2에서 결정. 기본은 한 worker 내 2 스레드.
