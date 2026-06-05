---
status: designed
adr_id: ADR-011
designer: opus
auditor_status: pending
last_updated: 2026-06-01
supersedes: null
superseded_by: null
---

# ADR-011 — 정적 상수(노선·정류장 메타데이터)는 route API로 완화 가능, 단 표출 화면의 정류소 번호는 고정

## 컨텍스트

- **사용자 지시:** "거의 상수로 박혀 있는 부분에 대해서도 API로 완화시킬 수 있을듯 하다. 또한 우리가 표출해야 하는 화면의 정류소 번호는 고정이라 생각해도 좋다."
- 현재 `src/constants.py`에는 세 종류의 하드코딩 데이터가 섞여 있다:
  1. **표출 설정 (고정)** — `SERACH_STOPS`(화면이 도착정보를 보여줄 17개 정류장), `UNISTBUS`/`UNIST_STR`(화면 구성), `WEEKDAY_STR`. 이는 *우리가 무엇을 보여줄지*에 대한 제품 결정이다.
  2. **노선 식별 (준고정)** — `ROUTEID` 키(route_id)와 `[0]`(버스번호)·`[1]`(방면)·`[2]`(기점). 국토부 cityCode·route_id 체계에 묶임.
  3. **API 파생 가능 데이터 (완화 대상)** — `STOP_IDS`(stop_id→한글명), `ROUTEID[*][3]`(노선별 정류장 시퀀스). 이 둘은 국토부 **BusRouteInfoInqireService** `getRouteAcctoThrghSttnList`가 `(nodeord, nodeid, nodenm, routeid)`로 그대로 반환한다(legacy `parse_route_json` 참조).
- 즉 (3)은 손으로 유지보수할 필요 없이 API에서 끌어올 수 있고, 정류장 개편 시 코드 수정 없이 갱신된다. 반면 (1)은 API로 "발견"할 성질이 아니라 우리가 정하는 고정 집합이다.
- 관련: F09(govtrack), F06(stops), W1(constants), W7(`fetch_route_stops`), W10(`parse_route`).

## 결정

상수를 **역할별로 분리**하고, API 파생 가능 데이터만 완화한다.

1. **표출 정류소 집합은 고정한다.** 화면이 보여줄 정류장 번호(`SERACH_STOPS` 및 노선 식별 `ROUTEID` 키/버스번호/방면)는 **constants가 권위 소스**다. 동적 정류장 발견 로직을 만들지 않는다(사용자 확인: 표출 정류소 번호는 고정).
2. **stop_id→명칭·노선 정류장 시퀀스는 route API로 완화 가능**하게 둔다. `TagoClient.fetch_route_stops(route_id)`(W7) + `parse_route`(W10)가 `(nodeord, nodeid, nodenm, routeid)`를 반환하고, 이로부터 `stop_id→nodenm` 매핑과 노선 시퀀스를 구성할 수 있다.
3. **constants는 "고정 표출 설정 + 파생 데이터의 시드/폴백" 두 역할**을 갖는다. 파생 데이터(STOP_IDS 명칭)는 API 갱신값이 있으면 그것을, 없으면(네트워크 실패·미수집) constants 값을 쓴다 — **constants는 항상 동작하는 폴백**.
4. **API 완화는 점진적**이다. P1은 *경로(fetch_route_stops + parse_route)*만 구현/검증한다. constants를 실제로 대체·갱신하는 서비스(`StopMetadataService`: route API → `stop_id→name` 캐시)는 **P3에서** 도입하며, 그 전까지 P1~P2는 constants를 그대로 읽는다(동작 불변).
5. govtrack의 `stop_name` 채움은 우선순위 `메타데이터 캐시(있으면) → STOP_IDS.get(nodeid) → None`을 따른다. 캐시 미도입 단계에서는 `STOP_IDS.get`만으로 현행과 동일.

## 대안

### 대안 A — 전부 API화 (constants 폐기)
- 장점: 단일 소스, 수기 유지보수 0.
- 단점: 네트워크 실패 시 화면 정류소 명칭이 비고, 표출 집합까지 API 의존이 되어 *무엇을 보여줄지*가 외부 데이터에 흔들림. 부팅 시 API 필수.
- 기각: 사용자가 "표출 정류소는 고정"이라 명시. 폴백 없는 외부 의존은 가용성 저하.

### 대안 B — 전부 하드코딩 유지 (현행)
- 장점: 무network, 결정적.
- 단점: 정류장 개편 시 수기 갱신, `STOP_IDS` 누락 시 govtrack `stop_name` 깨짐(데이터 무결성은 W1 테스트로 방어 중이나 근본은 수기).
- 기각: 사용자가 "API로 완화"를 원함.

### 대안 C — 본 결정 (역할 분리 + 파생만 완화 + 폴백)
- 채택. 표출 고정성과 유지보수 완화를 동시에 만족, 네트워크 실패에 강건.

## 결과

### 긍정적 영향
- 정류장 명칭·시퀀스를 API로 자동 갱신 가능(수기 유지보수↓), 단 화면이 보여줄 대상은 고정으로 예측 가능.
- 네트워크 실패에도 constants 폴백으로 화면·govtrack 동작 보장.
- `parse_route`/`fetch_route_stops`가 P1에 이미 설계되어 추가 구조 비용 0.

### 부정적 영향 / 비용
- 메타데이터 캐시(P3) 도입 전까지는 "완화 경로만 존재, 실제 갱신은 미사용" 상태 — 사용자에게 이 점을 명시.
- 우선순위 병합(캐시→constants) 로직이 P3에 추가됨.

### 따라오는 작업
- **P1 (불변 동작):** W7 `fetch_route_stops`, W10 `parse_route`를 구현·테스트(파생 경로 확보). W1 constants는 값 무변경 유지(표출 고정 소스 겸 폴백).
- **P3:** `StopMetadataService`(route API → `stop_id→name` 캐시, TTL/수동 새로고침) 도입. govtrack `stop_name` 채움을 `캐시→STOP_IDS.get` 우선순위로.
- **F09/F06:** `stop_name` 출처 우선순위 문구 추가(캐시→폴백).

## 검증 방법

```bash
# 파생 경로가 동작: route 응답에서 (nodeord,nodeid,nodenm,routeid) 추출
uv run pytest tests/crawler/test_parser_bus_location.py -k route
uv run python -c "from bushexa.api_clients.tago import TagoClient; print('getRouteAcctoThrghSttnList' in TagoClient('x').route_base_url)"
# 표출 집합은 여전히 constants 고정 (동적 발견 없음)
uv run python -c "from bushexa.data.constants import SERACH_STOPS; print(len(SERACH_STOPS))"  # 17
```

## 미해결 / 후속 결정

- Q1: 메타데이터 캐시 저장소(P3) — 별 테이블 `stop_meta(stop_id PK, name, updated_at)` vs JSON 파일. ADR-002 dual-backend 일관성 위해 테이블 유력.
- Q2: 캐시 새로고침 트리거 — 관리자 버튼(F04) vs 주기 크롤. 표출 고정이므로 빈도 낮음, 수동 우선.
- Q3: `ROUTEID` 방면 문자열(`[1]`)도 API화할지 — 한글 표기가 제품 문구라 고정 유지가 합리적.
