---
status: designed
adr_id: ADR-013
designer: opus
auditor_status: pending
last_updated: 2026-06-01
supersedes: null
superseded_by: null
---

# ADR-013 — 오류는 반드시 로그로 남기고, 크롤러/데몬 루프는 죽지 않고 계속 돈다

## 컨텍스트

- **사용자 지시:** "로그에는 문제가 생기면(에러가 발생하면) 로그로 남기고 계속 돌아갈 수 있도록 한다."
- govtrack(국토부 위치 → `bus_timelog`)과 arrival poller(울산 도착 → `bus_arrival_cache`)는 **5~10초 주기의 무한 루프**다. 한 번의 API 타임아웃·잘못된 응답·DB 일시 오류·파싱 실패로 **루프 전체가 죽으면** 통과 기록과 도착 백업본이 모두 멈춘다(서비스 중단).
- legacy는 부분적으로만 대응한다: `crawl_loc`은 5회 재시도, `crawl_busstop`은 `RequestException` 시 `[]` 반환. 그러나 (a) **silent swallow**가 있다 — `crawl_busstop`의 `except: route_id = None`은 어떤 예외인지 로그 없이 삼킨다(관찰 불가), (b) 한 노선 실패가 사이클 전체를 멈추는 경로가 남아 있다.
- PM-001(통과 기록 누락)도 결국 "조용히 실패하고 계속"의 변종 — 무엇이 왜 안 남았는지 로그가 없어 진단이 어려웠다.
- 관련: F09(govtrack, `CycleStats.total_errors`·`RouteStats.api_error` 이미 설계됨), ADR-010(arrival poller), ADR-012(파일 로그), F04 §4.5/§4.6(상태·로그 뷰어), PM-001.

## 결정

**오류 격리(isolate) + 기록(log) + 계속(continue)** 을 크롤러/데몬의 기본 규율로 한다.

1. **루프는 예외로 종료되지 않는다.** govtrack/arrival 폴러의 while-loop 본체는 try/except로 감싸 한 *사이클*의 미처리 예외도 잡아 로그 후 다음 주기로 넘어간다. 프로세스가 죽는 유일한 경로는 명시적 종료 신호(SIGTERM/KeyboardInterrupt)뿐이다.
2. **실패 단위를 가장 좁게 격리한다.** 사이클 > **노선** > 요청/파싱/insert 순으로 try/except를 둬, 한 노선(또는 한 정류장) 실패가 같은 사이클의 다른 노선 처리를 막지 않는다. F09 `RouteStats(api_ok, api_error)` / `CycleStats(total_errors)`로 집계.
3. **모든 잡은 예외는 반드시 로그한다 — silent swallow 금지.** 단위 실패는 `logger.warning`/`logger.error`(필요 시 `logger.exception`으로 스택)로 KST 타임스탬프와 **맥락(노선·정류장·시도횟수)** 을 남긴다. legacy의 `except: pass`류 무로그 흡수는 금지(감리에서 적발).
4. **재시도는 백오프와 상한을 갖는다.** 일시 오류(네트워크)는 짧은 sleep 백오프 후 ≤N회 재시도. 무한 즉시 재시도 금지(ADR-010의 과호출=시간오차 회피와 정합). 상한 초과 시 그 단위만 skip하고 로그.
5. **fail-fast 예외 — 부팅 치명 오류.** 시크릿/설정 누락, DB DSN 불가 등 *계속 돌려도 의미 없는* 부팅 단계 오류는 명확한 메시지로 즉시 종료(ADR-005 `ConfigError`). "계속 돈다"는 **런타임 일시 오류**에 적용되며 구성 오류를 가리지 않는다.
6. **관측성 합성.** 사이클 통계는 `GovtrackStatusReader`(F04 §4.5 상태 모니터)가, 오류 로그 라인은 `logs/bushexa.log`(ADR-012 sink) → 관리자 로그 뷰어(F04 §4.6)가 관찰한다. 즉 본 ADR + ADR-012 + F04로 "에러를 남기고 + 관리자가 본다"가 완성.

## 적용 범위

- **P1(클라이언트):** TagoClient/UlsanBisClient/HolidayClient는 네트워크/파싱 오류를 **삼키지 말고** 로그하거나 *타입이 있는 예외*(TagoError/ParseError)로 올린다. "빈 결과"와 "오류"를 구분(빈 결과는 정상, 오류는 로그). 루프 지속 책임은 호출자(P2 데몬)에 있으나, 클라이언트는 관찰 가능한 신호를 남긴다.
- **P2(데몬):** while-loop·per-route try/except·백오프·CycleStats를 구현. 주입 결함으로 루프 지속을 회귀 테스트(ADR-008 fake/주입).
- **P1 파일 쓰기(ADR-012):** 파일 쓰기 실패도 로그 후 처리(원자적 쓰기라 부분손상 없음).

## 대안

### 대안 A — 예외 전파, supervisor가 프로세스 재시작 (let-it-crash)
- 장점: 코드 단순, 상태 깨끗이 리셋.
- 단점: 재시작 사이 공백, 컨테이너 재시작 폭주 가능, 한 노선 오류로 전체 사이클 손실. 관찰성↓(왜 죽었는지 로그 빈약).
- 기각: 5~10초 주기 연속성·관찰성 요구에 부적합. 단 부팅 치명 오류는 본 결정 5와 같이 fail-fast(부분 채택).

### 대안 B — 모든 예외 silent ignore + 계속 (legacy 변종)
- 장점: 루프는 분명 계속 돈다.
- 단점: **무엇이 실패했는지 영영 모름**(PM-001류 진단 불가). 사용자 "로그로 남기고"에 정면 위배.
- 기각.

### 대안 C — 본 결정(격리+로그+계속+백오프, 부팅은 fail-fast)
- 채택. 연속성·관찰성·과호출 회피를 모두 만족.

## 결과

### 긍정적 영향
- 한 노선/정류장/요청 실패가 서비스를 멈추지 않음 → 통과 기록·도착 백업 연속.
- 모든 실패가 `logs/bushexa.log`에 남아 관리자 뷰어로 사후 진단 가능(PM-001 재발 시 즉시 근거 확보).
- 과호출 백오프로 ADR-010 시간오차 회피와 정합.

### 부정적 영향 / 비용
- try/except 경계와 로깅이 늘어 코드량↑. 너무 굵게 잡으면 진짜 버그를 숨길 수 있어 **가장 좁게** 잡아야 함(설계 2).
- 로그량↑ — 반복 실패 시 동일 메시지 폭주 가능 → 필요 시 rate-limit/요약(후속 Q).

### 따라오는 작업
- **P1:** 클라이언트의 오류/빈결과 구분 + 로깅. 테스트로 "오류는 예외/로그, 빈결과는 빈 리스트" 검증.
- **P2:** 데몬 루프 resilience work item + 주입 결함 회귀 테스트("한 노선 예외 → 다른 노선은 계속, 사이클 완료, 오류 1 집계").
- **PM-001 연계:** govtrack 통과 기록 누락 수정 시, 실패 시 반드시 로그가 남도록(조용한 누락 금지)을 회귀에 포함.
- **F09:** silent swallow 금지 문구를 §결함 항목에 명시.
- **감리:** `! grep -rn "except.*:\s*$\|except.*: pass\|except.*: continue" bushexa/crawler/` 류로 무로그 흡수 적발(보안/실행 감리).

## 검증 방법

```bash
# 한 노선이 예외를 던져도 루프가 다음 노선을 처리하고 사이클이 완료되는지 (P2)
uv run pytest tests/crawler/test_daemon_resilience.py -k "continue_on_error or cycle_completes"
# 클라이언트가 오류를 삼키지 않고 로그/예외로 신호하는지 (P1)
uv run pytest tests/api_clients/ -k "error or logs"
# silent swallow가 없는지
! grep -rn "except[^:]*:\s*\(pass\|continue\)\s*$" bushexa/ --include='*.py'
```

## 미해결 / 후속 결정

- Q1: 반복 동일 오류 로그 폭주 억제(dedup/rate-limit) — P2 운영 관찰 후 결정. 초기엔 그대로 남김(누락보다 과다가 안전).
- Q2: 사이클 실패율 임계 초과 시 알림(이메일/웹훅)할지 — 현재 범위 밖, F04 상태 모니터 시각화로 시작.
- Q3: 백오프 파라미터(재시도 횟수·sleep)의 노선/정류장별 차등 — 기본 공통값, 실측 후 조정.
