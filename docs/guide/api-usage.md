---
status: living
last_verified: 2026-09-29 (feat/busan-routes, TAGO 열차·지하철 추가)
audience: 크롤러·API 클라이언트를 수정하거나 수집 장애를 진단하는 사람·AI 세션
---

# 국토교통부 TAGO · 울산광역시 BIS · 특일정보 API 활용

> 공식 매뉴얼 원본은 [`api-manual/`](../../api-manual/) (TAGO 버스도착·위치·정류소·노선 v1.0, 울산 BIS v4.2).
> 이 문서는 **우리 코드가 실제로 쓰는 부분**, 알려진 이상동작, 호출량 전략을 정리한다.
> 코드 경로는 `bushexa/` 기준.

## 1. API 인벤토리

| 제공처 / 오퍼레이션 | 코드가 쓰는 URL | 보내는 파라미터 | 코드가 의존하는 필드 | 호출 주체 |
|---|---|---|---|---|
| **TAGO 버스위치** `getRouteAcctoBusLcList` | `http://apis.data.go.kr/1613000/BusLcInfoInqireService/getRouteAcctoBusLcList` | serviceKey, pageNo=1, numOfRows=70, `_type=json`, `cityCode=26`, `routeId='USB'+노선ID` | `header.resultCode`, `body.totalCount`, `items.item[]` → `nodeid`(USB 접두 제거), `nodenm`, `vehicleno`, `nodeord` | worker-govtrack |
| TAGO 노선별 경유정류소 `getRouteAcctoThrghSttnList` | `…/BusRouteInfoInqireService/getRouteAcctoThrghSttnList` | 동일 | nodeord, nodeid, nodenm | **운영 미사용**(클라이언트만 존재) |
| **울산 BIS 도착정보** `getBusArrivalInfo.xo` | `http://openapi.its.ulsan.kr/UlsanAPI/getBusArrivalInfo.xo` | serviceKey, pageNo=1, numOfRows=50, `stopid` | `<row>` → `routeid`, `presentstopnm`, `vehicleno`, `arrivaltime`(초) | worker-arrival, govtrack 폴백 |
| **울산 BIS 시간표** `BusTimetable.xo` | `http://openapi.its.ulsan.kr/UlsanAPI/BusTimetable.xo` | pageNo, numOfRows=50, `routeNo`(버스 번호), `dayOfWeek` | `<row>` TIME(`HHMM`), DIRECTION(1 정/2 역), `totalcnt`(페이징) | worker-cache-refresh, CLI, 관리자 재크롤 |
| **TAGO 열차정보** `GetStrtpntAlocFndTrainInfo` | `https://apis.data.go.kr/1613000/TrainInfo/GetStrtpntAlocFndTrainInfo` | serviceKey, `_type=json`, numOfRows=500, pageNo, `depPlaceId`, `arrPlaceId`, `depPlandTime`(YYYYMMDD) | `trainno`, `traingradename`, `depplandtime`/`arrplandtime`(YYYYMMDDHHMMSS), `adultcharge` | worker-cache-refresh, CLI `crawl-rail`, 관리자 `/admin/rail` |
| **TAGO 지하철정보** `GetSubwaySttnAcctoSchdulList` | `https://apis.data.go.kr/1613000/SubwayInfo/GetSubwaySttnAcctoSchdulList` | serviceKey, `_type=json`, numOfRows=500, pageNo, `subwayStationId`, `dailyTypeCode`(01/02/03), `upDownTypeCode`(U/D) | `depTime`/`arrTime`(HHMMSS, 없으면 `"0"`), `endSubwayStationId`/`Nm` | worker-cache-refresh, CLI `crawl-rail` |
| **특일정보(한국천문연구원)** `getRestDeInfo` | `http://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo` | serviceKey, solYear, solMonth(`%02d`) | `<locdate>` YYYYMMDD, resultCode `00` | worker-cache-refresh(부팅 + 매일), 관리자 미리보기 |

코드 위치: `api_clients/tago.py`, `api_clients/tago_rail.py`(열차·지하철), `api_clients/ulsan_bis.py`, `api_clients/holiday.py`, 공통 전송은 `api_clients/_http.py`.

### 1.1 식별자 체계

- **인증키 1개**를 모든 제공처에 쓴다(data.go.kr 발급). `BUSHEXA_API_KEY` 또는 `secret/key.txt`.
- 울산 `cityCode = 26` (`data/constants.py` 의 `ULSAN_CITYCODE`). 매뉴얼 예시는 25(대전)이니 복사하지 말 것.
- **TAGO ID = `'USB'` + 울산 BIS 9자리 ID** (`ULSAN_PREFIX`). 예: 울산 노선 `195000177` ↔ TAGO `USB195000177`. 정류장도 같은 규칙.
- 추적 대상:
  - `ROUTEID` — 5개 노선(513/713/743/753/1115) × 2방향 = 10개.
  - `EXTRA_TRACKED_ROUTES` — UNIST 를 지나지 않지만 운행 기록을 모으는 노선(1224·5001 × 2방향). govtrack 은 `TRACKED_ROUTES`(= 둘의 합, 14개)를 추적한다. 게시판·시간표·`/stops` 는 `ROUTEID` 만 본다. 5001(울산역 리무진, TAGO routeid `USB196000455` 울산역→꽃바위 / `USB196000456` 꽃바위→울산역)은 UNIST 에 서지 않고 양방향 모두 진목회관에 선다 — `/ktx` ② 안.
  - `EXTRA_TIMETABLE_BUSES` — ROUTEID 밖이지만 울산 BIS 시간표를 받는 노선(5001·1224). 5001: 방향 1(작은 routeid)=울산역 기점, 2=꽃바위 기점. 1224: 방향 1(195000247)=농소 기점(노포 방면, 첫차 04:40), 2(195000248)=노포 기점(첫차 06:14) — TAGO 노선 목록의 기·종점과 대조 확인(2026-09-30). 시간표 시각은 **기점 출발**이라 좋은삼정병원앞 통과 시각이 아니다(실시간은 arrival 캐시). 울산역발은 자정 `00:00` 막차가 있다(운행일 24:00 으로 정렬).
  - `SERACH_STOPS` — 도착정보 폴링 정류장 17개(철자 `SERACH` 는 원본 유지, 고치지 말 것).
  - `UNIST_VIA_STOP_ID = "196040234"`.
- 철도 역 ID(부산 루트): 열차 `RAIL_STATIONS`(울산 `NATH13717`, 태화강 `NAT750726`, 부산 `NAT014445`, 부전 `NAT750046`), 동해선 광역전철 `METRO_STATIONS`(태화강 `MTRKRK6K132`, 벡스코 `MTRKRK6K119`, 부전 `MTRKRK6K110`). 수집 구간은 `RAIL_PAIRS`·`METRO_QUERIES`. 역 목록은 `TrainInfo/GetCtyAcctoTrainSttnList`(cityCode 26·21), `SubwayInfo/GetKwrdFndSubwaySttnList` 로 확인했다.
- 울산 시간표 `dayOfWeek`: 0 평일, 1 토, 2 일/공휴일, 3~5 방학 변형. 코드는 0·1·2(+방학 모드 3)를 크롤한다. `time_utils.get_weekday` 의 0/1/2 와 같은 의미다.

### 1.2 매뉴얼 기준 제약

- TAGO: 오퍼레이션당 **30 tps**, 위치정보 갱신 "실시간(10~20초)", 노선정보 "일 1회".
- 울산 BIS: XML 전용, `resultCode 200` 성공 / `300` 실패, 30 tps.
- **일일 트래픽 한도는 매뉴얼에 없다.** 키별로 data.go.kr 마이페이지에서 확인해야 한다(§4, 미기록 항목).
- TAGO 오류 코드(`cmmMsgHeader` XML): 1 APPLICATION_ERROR, 4 HTTP_ERROR, 12 NO_OPENAPI_SERVICE, 20 SERVICE_ACCESS_DENIED, **22 LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS**, **30 SERVICE_KEY_IS_NOT_REGISTERED**, 31 DEADLINE_HAS_EXPIRED, 32 UNREGISTERED_IP, 99 UNKNOWN.
- 울산 도착정보 매뉴얼은 ROUTEID·VEHICLENO 필드를 문서화하지 않았지만 실제 응답에는 온다. 코드가 이 비문서 필드에 의존한다는 점을 기억할 것.

## 2. 클라이언트 계층 설계

```text
 crawler/ (govtrack, arrival, cache_refresh, timetable_crawl)
     │
     ├─ CompositeLocationClient ── TAGO 우선 ──(TagoError/RequestException)──> 울산 도착정보 폴백
     ├─ UlsanBisClient (도착정보·시간표)
     └─ HolidayClient
            │
            └─ _http.get_with_service_key(url, key, params, timeout)   ← 모든 호출의 단일 관문
                   · serviceKey = unquote(key)  (이중 인코딩 방지)
                   · timeout = 명시 인자 > BUSHEXA_API_TIMEOUT_SECONDS > 15s

 web/ (공개 화면) ── CachedArrivalClient ── bus_arrival_cache(SQLite)   ← 네트워크 호출 없음 (ADR-010)
```

### 2.1 공통 규칙

| 규칙 | 이유 | 근거 |
|---|---|---|
| 모든 호출은 `get_with_service_key` 경유 | 키 인코딩을 한 곳에서 처리. 복제본 하나가 빠지면 인증 실패가 조용히 "빈 결과"가 된다 | [PM-008](../refactor/postmortems/PM-008-holiday-silent-empty-and-overwrite.md) |
| XML 파서에는 `resp.content`(bytes)를 넘긴다 | charset 헤더가 없으면 `resp.text` 가 latin-1 로 디코드되어 한글이 깨진다 | [PM-003](../refactor/postmortems/PM-003-xml-response-encoding.md) |
| HTTP 200 이어도 **본문 resultCode 를 검사**한다 | data.go.kr 게이트웨이는 키·한도 오류를 200 + XML 로 준다 | PM-008 |
| 오류는 타입 예외로: `TagoError(result_code)`, `UlsanBisError`, `HolidayError`, `ParseError` (`api_clients/errors.py`) | "빈 결과"와 "오류" 구분 | ADR-013 |
| 실패 결과로 좋은 캐시·파일을 덮지 않는다 | 한 번의 장애가 며칠치 데이터를 지운다 | PM-008 |
| 전송 계층 재시도는 없다. 재시도는 호출자 책임(시간표 크롤만 3회, 1s·2s 대기) | 폴링 루프 자체가 재시도 역할 | `crawler/timetable_crawl.py` |

### 2.2 제공처별 처리

- **TAGO** (`tago.py` `_get_json`):
  - `_type=json` 을 요청해도 실패 시 **빈 본문 또는 XML** 이 온다. `<` 로 시작하면 `returnReasonCode`/`returnAuthMsg` 를 뽑아 `TagoError`.
  - 결과 1건이면 `items.item` 이 **list 가 아니라 dict**, 0건이면 `items: ""`. `_items_as_list` 가 정규화한다. 새 TAGO 호출을 추가하면 반드시 이 함수를 거친다.
  - `resultCode != "00"` → `TagoError`.
- **울산 BIS** (`ulsan_bis.py` `check_response`):
  - HTTP 상태 → `<resultcode>`(200) → 게이트웨이 오류 순으로 검사. 어느 표지도 없으면 통과시킨다.
  - **의도된 비대칭:** `fetch_arrivals` 는 오류를 로그하고 `[]` 반환(루프가 계속 돌도록). `fetch_timetable_page` 는 예외를 올린다.
- **TAGO 열차·지하철** (`tago_rail.py`): 본문 검사는 `tago.get_tago_json` 공용 경로(버스 TAGO 와 같음). 신규 GW 엔드포인트는 키·서비스 오류를 **HTTP 400·403 + JSON `OpenAPI_ServiceResponse`** 로 준다 → `TagoError(returnReasonCode)`. 페이지는 `totalCount` 에 닿을 때까지 모으고(중복 제거 전 행 수로 판정), 모자라면 `ParseError`.
  - 저장·병합 규칙은 `services/rail_timetable.py` 머리 주석: 실패·빈 결과·급감이면 기존 유지, 중앙값 대비 급감한 새 날짜는 `suspect: true`.
- **특일정보**: 항상 예외. 호출자(`services/holiday_service.py`)가 해당 월 캐시를 보존하고, 캐시에 없는 달은 `holidays` 패키지로 오프라인 gap-fill. 공휴일 판단은 패키지에 맡긴다(제헌절은 2026년부터 공휴일 재지정, 이름 문자열 필터는 locale 의존이라 제거됨 — `f80e55e`).
- **CompositeLocationClient** (`composite_location.py`):
  - TAGO 가 `TagoError`/`RequestException` 이면 해당 노선의 추적 정류장들에 울산 도착정보를 호출해 `routeid` 가 일치하는 차량을 모으고, `presentstopnm` 을 정류장 ID 로 역매핑한다. 결과는 `result_code="ULSAN"`, `node_ord=None`(순방향 게이트 미적용).
  - 정류장별 8초 캐시 + 단일 락(병렬 fetch 중 TAGO 가 동시에 죽어도 울산 호출이 쇄도하지 않게).
  - 이름 → ID 해석: 노선 인지형 인덱스 우선, 같은 노선에 동명 정류장이 여럿이면 건너뜀 → 전역 정확 일치 → 괄호 제거 이름(유일할 때만).
  - `ParseError` 는 폴백을 **발동하지 않는다**.
- **CachedArrivalClient** (`cached_arrival.py`): `fetch_arrivals` 드롭인. `bus_arrival_cache` 만 읽고 `last_fetched_at` 으로 신선도를 제공한다. `services/board_support.arrival_client()` 가 모든 공개 화면에 배선한다.

## 3. 호출량 전략

| 호출자 | 사이클당 | 주기 | 가동 | 일일 추정 |
|---|---|---|---|---|
| govtrack → TAGO | 14(`TRACKED_ROUTES` 노선×방향, 1224·5001 포함), 기본 순차 | 사이클 **후** 15s 휴식 | 20h(01~05시 야간 휴식) | 상한 67,200, 관측 기준 약 42~56k |
| arrival → 울산 도착정보 | 18(정류장, 좋은삼정병원앞 포함), 기본 순차 | 사이클 후 7s 휴식 | **24h(야간 휴식 없음)** | 호출당 1.2~1.5s 관측 → 약 50k. `FETCH_WORKERS=4` 면 110k+ |
| govtrack 폴백 → 울산 | 노선의 추적 정류장 수만큼(8s 캐시로 중복 제거) | TAGO 장애 시 | — | 가변 |
| cache-refresh → 특일정보 | 2(이번 달·다음 달) | 부팅 + 하루 1회 | — | ≈ 4 |
| cache-refresh → 울산 시간표 | 5노선 × 3요일 × 페이지 | 하루 1회(02~03시) | — | 15~45 + 수동 재크롤 |
| cache-refresh → TAGO 열차정보 | 7구간(울산→부산·서울·수서, 부산·서울·수서→울산(/ktx 오는 편), 태화강→부전) × 14일 + 정차역 후보 41역(울산→서울 10·수서 8, 서울·수서→울산 같은 역 거꾸로, 부전 5) × (가까운 3일 + 요일구분별 첫 날짜, 보통 4~5일) | 하루 1회(02~03시) + 부팅 시 그날 미성공이면 | — | ≈ 300 (+부팅 300) |
| cache-refresh → TAGO 지하철정보 | 3역 × 3요일구분 (페이지 1) | 위와 같음 | — | ≈ 9 (+부팅 9) |

설계 원칙:

1. **화면 트래픽과 API 트래픽을 분리한다.** 방문자 수와 무관하게 API 호출량이 일정하다(ADR-010). 공개 라우트에 API 호출을 넣지 않는다.
2. **폴링 주기는 런타임 설정.** `/admin/crawl-settings` → `data/crawl_settings.json`(3~600s), 매 사이클 재읽기. CLI `--poll` 보다 우선한다.
3. **병렬 fetch 는 게이트 뒤에.** `BUSHEXA_{GOVTRACK,ARRIVAL}_FETCH_WORKERS` 기본 1. 올리면 순간 tps 가 늘고 TAGO "세션 부족" 오류(§4)를 유발할 수 있으니 오류율을 비교한 뒤 승격한다.
4. **폴링 주기와 기록 정확도의 트레이드오프.** 버스가 정류장에 머무는 시간은 5~10초라 폴링이 길수록 통과 기록 recall 이 떨어진다(10s ≈ 0.825, recorder 감사 2-4). 15s 는 측정된 적이 없다. 주기를 늘릴 때는 `tests/simulation/` 에 해당 주기 시뮬레이션을 추가한다.
5. **timeout ≤ 폴링 주기를 의식한다.** 현재 timeout 15s = govtrack 주기 15s. 느린 응답이 사이클을 밀어낸다.

## 4. 알려진 이상동작과 대응

| 현상 | 상태 | 대응 |
|---|---|---|
| 이중 인코딩된 serviceKey → `SERVICE_KEY_IS_NOT_REGISTERED` 가 200 으로 옴 | 해결 | `_http.get_with_service_key` 의 unquote |
| charset 없는 XML 한글 깨짐 | 해결 | bytes 파싱 |
| TAGO 단건 dict / 빈 `items:""` | 해결 | `_items_as_list`, 픽스처 `busloc_single_dict.json` |
| TAGO `99 가용한 세션이 존재하지 않습니다 (30/30)` (2026-09-29 관측, 순차 호출 중에도 발생) | 관찰 중 | 울산 폴백으로 흡수. 병렬 fetch 승격 전 이 오류 빈도를 기준선으로 기록할 것 |
| 울산 응답 지연·무응답(10~15s read timeout, 6월·9월 관측) | 완화 | timeout 15s 설정화([PM-012](../refactor/postmortems/PM-012-ulsan-api-timeout-10s.md)), 노선·정류장 단위 격리 |
| **울산 장애가 "도착 버스 없음"으로 보임** | **미해결** | `fetch_arrivals` 가 오류 시 `[]` 를 반환하고, poller 가 그 `[]` 를 새 `fetched_at` 으로 upsert 하며 성공으로 집계한다. 화면은 신선한 "도착 정보 없음"을 보여 주고 `arrival_status` 도 정상으로 나온다. 권장: 오류 시 upsert 를 건너뛰어 직전 스냅샷과 옛 타임스탬프를 유지하고 실패로 집계 |
| **이른 아침 TAGO 항목의 필드 누락**(`nodeid`/`nodenm`/`nodeord` 없음, 레거시 덤프 `logs/error_*.json` 다수가 05시대) | **미해결** | `parse_busloc` 가 노선 전체를 `ParseError` 로 실패시키고, 폴백도 발동하지 않는다. 권장: 파서에서 불량 항목만 건너뛰고 로그 |
| 울산 폴백의 정류장 이름 매칭률이 낮음(`presentstopnm` 이 9자 근처에서 잘려 오는 것으로 관측, `(UNIST)`/`(시내)` 접미사 불일치) | **미해결** | 폴백 시 위치 해석 실패가 많다. 권장: 노선 인덱스 내 접두/정규화 매칭. `presentstopnm` 이 현재 정류장인지 다음 정류장인지도 미확정(recorder 감사 T4) |
| 요청 URL 에 담긴 API 키가 로그·상태 파일에 기록됨 | 해결(2026-09-29) | `bushexa/redact.py` 를 로그 포매터·상태 파일·로그 뷰어에 적용. 수정 이전 로그는 운영자가 정리([PM-016](../refactor/postmortems/PM-016-api-key-in-log-files.md) §6.2) |
| 모든 기본 URL 이 `http://` | 미해결 | 키가 평문 전송된다. data.go.kr 은 https 지원, 울산 호스트는 확인 필요 |
| `BUSHEXA_ARRIVAL_POLL_SECONDS` 가 동작하지 않음 | **미해결** | CLI `arrival-loop --poll` 기본값 7.0 이 항상 명시 인자로 넘어가 env 를 이긴다. 실제로 주기를 바꾸려면 관리자 크롤 설정을 쓴다 |
| 폐기된 TAGO 열차 경로 `TrainInfoService/getStrtpntAlocFndTrainInfo` → resultCode 12 `NO_OPENAPI_SERVICE` | 해결 | 신규 경로 `TrainInfo/GetStrtpntAlocFndTrainInfo`(오퍼레이션 대문자 시작) |
| 열차정보가 `numOfRows`/`pageNo` 를 무시하고 매번 전량을 줌 | 대응 | `_collect_pages` 가 새 항목 없는 페이지에서 멈춤. 지하철정보는 페이지를 지킴 |
| 열차정보가 같은 열차를 도착시각만 1분 다르게 두 번 줌(2026-10-09 태화강→부전 00705) | 대응 | (열차번호, 출발시각) 중복 제거, 완결성은 원 행 수로 판정. 픽스처 `tago_rail/route_duplicate_row.json` |
| 열차정보가 특정 날짜만 편수 급감(2026-10-13 울산→부산 3편, 평소 60편대). 약 30일 너머는 0건 | 대응 | 기존 값 유지 / 첫 수집이면 `suspect` 표시. 수집 범위는 14일 |
| 동해선 토요일(`dailyTypeCode=02`) 시간표가 0건 | 대응 | 읽을 때 03(일·공휴일)으로 대체(`METRO_SATURDAY_FALLBACK`). 실제 토요일 운행이 휴일 시간표와 같은지는 코레일 공지로 재확인 필요 |
| 지하철 역별 시간표에 열차번호가 없음 | 대응 | 시각만으로 잇는다(`domain/rail_match.py`, `rail_timetable.metro_trips`): 소요시간 최빈값(태화강→벡스코 55.5분, →부전 76분) + 추월 없음 가정으로 가장 이른 미배정 도착을 배정(지연 최대 15분 대기). 중간역(일광) 출발 편은 남는다. 평일·휴일 42편 전부 매칭, 벡스코→부전 구간 20.5~26.5분으로 교차 검증 |
| 정차역 목록을 주는 오퍼레이션이 없음 | 대응 | `RAIL_STOP_CANDIDATES` 후보역마다 "출발역 → 후보역" 을 조회해 같은 출발시각 열차가 나오면 정차로 본다(가까운 3일). 후보 조회가 하나라도 실패하면 그 날짜 정차역은 `None`(모름) — 통과로 그리지 않는다 |
| SRT 가 열차정보 응답에 없음(울산→부산 61편 전부 KTX 계열, 차종 코드 17 SRT 는 목록에만 있음) | 해당 없음 | SRT 는 필요 없다(소유자 결정 2026-09-29) |
| 일일 트래픽 한도 미기록 | 미해결 | 키별 한도를 확인해 이 문서 §1.2 에 적는다. TAGO 개발계정 한도가 낮게 잡혀 있다면 govtrack 만으로 초과할 수 있다(확인 필요) |

## 5. 테스트 방법 (네트워크 없이)

- 단위 테스트는 네트워크를 쓰지 않는다. `responses` 라이브러리로 HTTP 를 가짜로 만들고, `tests/conftest.py` 의 `no_network` 픽스처는 `requests.get/post` 호출 시 실패시킨다.
- 크롤러 테스트는 가짜 클라이언트(`tests/crawler/_fakes.py` 의 `FakeTagoClient` 등) + 주입된 clock·sleep·`stop_event` 를 쓴다.
- 실응답 샘플 픽스처: `tests/fixtures/tago/`(normal, empty, error_99, single_dict, single_list, route_stops), `tests/fixtures/tago_rail/`(열차 정상·빈·중복행·GW 키오류, 동해선 태화강 평일·토요일 빈 응답), `tests/fixtures/ulsan/`(arrival_normal, arrival_no_bus, timetable_normal), `tests/fixtures/holiday/2026.xml`.
  - **주의:** 울산 도착정보 픽스처는 실제 형식(`<tableInfo><resultCode>200`)이 아닌 임의 스키마다. `check_response` 가 모르는 형식을 통과시키기 때문에 통과하고 있을 뿐이다. 울산 응답 처리를 고칠 때는 실응답으로 픽스처를 교체한다.
- 새 오류 형식을 만나면: 응답 본문을 **키를 지운 뒤** 픽스처로 저장하고, 그 픽스처로 "예외가 난다" 또는 "캐시를 보존한다" 테스트를 먼저 쓴다.
- 철도 라이브 확인: `uv run bushexa crawl-rail`(요약만 출력, `data/rail_timetable.json` 에 병합). 운영에서는 관리자 `/admin/rail` 의 "지금 다시 받기"(같은 규칙, 백그라운드 잡·진행 표시).
- KTX 연계표 점검(네트워크 없음): `uv run bushexa ktx-connections --dir out|in --to busan|seoul|suseo --day 0|1|2 [--json]`. 열차번호(`no`)는 TAGO 열차정보 응답에 이미 있어 별도 수집이 없다 — 표기는 `/ktx` 에서만 하고 `/busan`·`/seoul` 은 시각으로 잇는다(소유자 결정).
- 라이브 확인은 `scripts/smoke_compose.sh`(키 필요, `SMOKE_SKIP_FEED=1` 이면 HTTP 200 만)와 `uv run bushexa crawl-once --route 195000177 --dry-run`.

## 6. 장애 진단 순서

```bash
# 1) 워커가 살아 있나
podman compose -f docker/compose.yaml exec app supervisorctl -c /app/docker/supervisord.conf status
# 2) 사이클 통계 (정상이면 CycleStats 가 주기적으로 찍힘)
grep CycleStats logs/bushexa-crawl.log | tail -5
# 3) 제공처 오류 코드 확인 (키가 찍힌 줄은 보여주지 않도록 마스킹)
grep -E "TagoError|UlsanBisError|HolidayError|timed out" logs/bushexa-*.log | sed -E 's/serviceKey=[^& )]+/serviceKey=***/g' | tail -20
# 4) 단발 호출로 재현 (DB 쓰기 없음)
uv run bushexa crawl-once --route 195000177 --dry-run
```

- 관리자 화면: `/admin/`(govtrack 상태 SSE), `/admin/logs?src=crawl|arrival|cache`.
- 오류 코드 22(한도 초과)·30(키 미등록)은 코드로 못 고친다. 키 상태를 data.go.kr 에서 확인한다.
