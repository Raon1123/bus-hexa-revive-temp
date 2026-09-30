# 부산 가는 길(/busan) v2 구현 계획

- 문서 위치: `docs/busan-routes/02-plan.md`. 짝 문서는 `docs/busan-routes/01-required-timetables.md`(루트별 필요한 시간표 레퍼런스)입니다.
- 작성일: 2026-09-29 (KST)
- 기준 코드
  - worktree `bushexa-busan-routes`의 HEAD `abaac07`. /busan v1(`c645092`, `3041de4`, `abaac07`)은 origin/master와 로컬 master에 모두 들어 있습니다.
  - 로컬 master `531af6c`는 origin/master보다 7커밋 앞서 있습니다(기한형 공지, timetable-ux 문서, 1115 공지). 동시에 3커밋 뒤처져 있습니다(PR #9 splitflap).
- 조사 원자료와 재현 스크립트: `/tmp/claude-1000/-home-mlv-project-bushexa-bus-hexa-revive-temp/fe06107b-dea9-45b3-8779-4887783d26bf/scratchpad/`
  - 이 계획에서 새로 계산한 값은 `r1_bands.py`, `r2_bands.py`, `r3_travel_v2.py`, `sim2.py`, `sim_r1.py`, `sim_r2.py`, `metro_verify.py`/`.json`에서 나왔습니다.
- 배포는 오너가 직접 합니다. 각 PR은 **병합 준비 상태까지만** 만들고, push·merge·deploy는 하지 않습니다.

---

## 0. 한눈에 보기

1. **새 페이지를 만드는 작업이 아닙니다.** v1은 이미 병합되어 있습니다. 이 계획의 범위는 두 가지입니다.
   - 사용자 요구를 채웁니다. 세 루트, 목적지(서면·부전·남포 / 노포 / 해운대·송정), 루트별 시간표가 대상입니다.
   - **틀린 시각이 나올 수 있는 경로를 막습니다.**
2. **날짜가 급한 일이 두 개 있습니다.**
   - 10/3: 743·1115 노선이 개편됩니다.
   - 10/5(월, 대체공휴일): 동해선이 평일 편성으로 운행할 가능성이 큽니다. 지금 코드는 이날 휴일표를 씁니다.
   - 그래서 작은 긴급 PR(PR-A0)을 따로 둡니다.
3. **설계의 핵심**
   - 모든 시각을 `TimeToken`으로 다룹니다. 토큰에는 기준 지점, 출처, 범위, 표본 수가 붙습니다.
   - 탑승 전 통과 예측에는 **통일 게이트 규칙(규칙 U)**을 적용합니다. 513과 1224에 같은 규칙이 적용되고, 노선 번호로 분기하지 않습니다.
   - 부산 루트용 레지스트리는 따로 두고, `ROUTEID`와 `SERACH_STOPS`는 건드리지 않습니다.
4. **PR 순서:** PR-A0(긴급) → PR-A1(정확성) → PR-A2(데이터 신선도) → PR-B(루트 1·3 목적지 완성, 1호선) → PR-C(루트 2) → P2.5(10/3 이후 재확인) → PR-E(이력 예측) → PR-F(확장)
5. **가장 큰 오너 결정은 B-D10입니다.** 게이트를 통과하지 못한 과거 기록 기반 "참고 예측"을 탑승 전 예측 등급으로 허용할지 정해야 합니다. 루트 1의 "울산역 도착 시간" 요구를 PR-B에서 채울지, PR-E(운영 이력 약 30일 필요)까지 미룰지가 이 결정에 달려 있습니다.

---

## 1. 현황

### 1.1 v1의 동작과 결함 (코드로 확인)

| 루트 | v1이 하는 일 | 요구 대비 공백 |
|---|---|---|
| 1. 513 → 울산역 → KTX | 513 UNIST 경유(`196040234`) 실시간 ETA에 16분을 더해 울산역 도착을 냅니다. 10분 여유 뒤 첫 KTX를 잡아 부산역 도착을 냅니다. 실시간이 없으면 덕하 출발 칩에 "UNIST 통과 아님" 라벨을 붙입니다 | 서면·남포·부전 도착이 없습니다. 실시간이 없는 시간대에는 울산역 도착이 없습니다. 루트 전체 시간표가 없습니다 |
| 2. 743·753 → 좋은삼정 → 1224 | 743·753 UNIST 출발 시각과 "1224 준비 중" 배너만 보여 줍니다 | 1224 시간표, 환승, 노포 도착이 모두 없습니다 |
| 3. 버스 → 태화강역 → 동해선 | 4개 노선 UNIST 출발에 요일별 중앙값 상수와 도보 5·8분을 더해 첫 동해선을 잡습니다. 벡스코·부전 도착과 일반열차 목록을 보여 줍니다 | 신해운대·송정·센텀 도착이 없습니다. 동해선 전체 시각표가 없습니다 |

| ID | 결함 | 근거 |
|---|---|---|
| D-1 | 저장소 시간표가 BIS 현행과 다릅니다. 513 평일은 28편 대 32편이고 대칭차가 46입니다. 2026-04~06 덕하 기점 목격 시각은 **BIS 현행표와 3분 안에서 96% 일치**했지만 저장소 표와는 22%만 일치했습니다. 753 평일(50 대 56편), 713 토요일, 1115 전 요일도 BIS 현행표가 당시 운행과 맞습니다. 반대로 **743 주말은 저장소 표가 4~6월 운행과 맞고 BIS 현행표가 다릅니다.** BIS가 10/3 개편표를 이미 반영했을 가능성이 있지만 미확인입니다 | `01-required-timetables.md` §6 |
| D-2 | ETA 기준 시각이 `now`이고 신선도 게이트가 없습니다 | `domain/busan.py:158`, `domain/seoul.py:67-71` |
| D-3 | 요일별 상수만 쓰고 시간대를 무시합니다. 753 평일 16~19시 실측은 중앙값 89.7분(p90 101.1분)인데 상수는 75분입니다 | `constants.py:294-299`, 재계산 `r3_travel_v2.py` |
| D-4 | `_hhmm`이 `% 1440`으로 자정을 접어서 "내일" 표시가 없습니다 | `domain/busan.py:77-79` |
| D-5 | 743 참고값은 10/3 개편 전 표본입니다. 1115는 개편 구간(명촌정문~성원상떼빌 → 아산로)이 태화강역광장보다 **하류**라서 가는 방향은 영향이 없습니다 | `data/changelog.json:36` |
| D-6 | 추정값에 범위·표본 수·기간 표기가 없습니다 | 템플릿 |
| D-7 (신규) | 00:00~03:00에 서비스일(`service_minutes`, 03시 이전은 +24h)과 달력일(`get_weekday(today)`)이 어긋납니다. 예를 들어 토요일 00:30에는 토요일표 전체가 "지난 편"이 됩니다. 9/29 KTX 항목에 들어 있는 9/30 00:22·00:43 편은 00시대에 조회하는 달력일(9/30) 항목에 없어서 빠집니다 | `domain/rail_match.py:21-29`, `domain/busan.py:79-80,125-126`, `routes/busan.py:45-52` |
| D-8 (신규) | 라우트가 `METRO_QUERIES`를 위치 인덱스로 읽습니다. 목록에 역을 추가하면 벡스코·부전이 조용히 바뀝니다 | `routes/busan.py:50-51` |
| D-9 (신규) | 10/5 대체공휴일에 `metro_day_type`이 '03'(휴일표)을 냅니다. 하지만 TAGO 열차 데이터상 KTX 울산→부산의 10/5 편성은 평일(10/6)과 대칭차 0, 휴일(10/4)과 대칭차 5입니다. rail.blue의 10/5 동해선도 평일표입니다 | `services/rail_timetable.py:272-274`, `data/rail_timetable.json` |
| D-10 (설계 제약) | 1호선 운행 시간 모델이 없습니다. KTX 부산 도착 00:05·00:43·01:04 편 뒤에는 1호선이 끊겨 있습니다 | TAGO 1호선 부산역 D 막차 23:49:15, U 막차 00:12:30 |

### 1.2 확인된 인프라 사실 (2026-09-29 재확인)

- **TAGO 응답**
  - `TrainInfo`·`SubwayInfo`는 현재 키로 정상 응답합니다. `rail_timetable.json` 갱신 시각은 21:23입니다.
  - 울산→부산 KTX는 평일(9/30) 59편, 일요일(10/4) 65편입니다. 00시대 2편도 포함됩니다.
  - 동해선 태화강 U는 평일 45편(부전행 42편), 휴일 42편입니다. 토요일(02) 표는 비어 있습니다.
- **역 ID(2026-09-29 재호출로 확인)**
  - 동해선: 송정 `MTRKRK6K121`(U 평일 50편), 신해운대 `K120`, 센텀 `K118`
  - 부산 1호선: 부산 `MTRBS10113`, 노포 `10134`, 서면 `10119`, 부전 `10120`, 남포 `10111`
  - `MTRBS10113`은 키워드 검색에는 나오지 않습니다. 그러나 D 방향 종착이 "노포(종합버스터미널)"이고, 역간 소요로 보면 남포(+4분)와 서면(+10.5분) 사이에 있습니다. 부산역으로 확인했습니다.
- **1호선 요일 구분**: 토요일(02)이 **비어 있지 않습니다.** 부산역 D 기준 평일 177편, 토 167편, 휴일 160편입니다. 따라서 `METRO_SATURDAY_FALLBACK`은 동해선에만 적용되는 규칙입니다.
- **1호선 운행 시간(평일)**
  - 부산역 D(노포 방면): 05:26:45~23:49:15
  - 부산역 U(다대포 방면): 05:49:30~00:12:30
  - 노포 U: 05:08:00~23:31:00
  - 고정 소요(부산역 기준): 남포 4.0분(U), 서면 10.5분(D), 부전 12.5분(D)
  - 고정 소요(노포 기준, U): 부전 약 26.5분, 서면 28.0분, 부산 39.0분, 남포 42.5분
  - 일관성 확인: 노포>부산 − 노포>서면 = 11 ≈ 부산>서면 10.5
- **좋은삼정병원앞 `193030929`**: 743(22번째)·753(23번째)·1224(15번째)가 같은 정류장 ID로 섭니다. 도착정보 한 번 호출로 세 노선 ETA가 함께 옵니다.
- **1224**
  - 노선 ID: `195000247`(농소 → 노포), `195000248`(노포 → 농소)
  - BIS `routeNo=1224`: 평일 60편, 토·일·공휴일 58편
- **SRT**: 2026-09-01부터 KTX로 통합 운행합니다. 정책브리핑 2026-08-31 기사이고, `constants.py`에 오너 결정 "SRT 필요 없음"이 있습니다.
- **이력**
  - 이력 예측 코드는 어느 브랜치에도 없습니다.
  - 지정된 운영 DB의 `bus_timelog`는 16행입니다.
  - 참고값은 모두 레거시 `logs/logs.tsv`(2026-04-16~06-01, 139,852행)와 `bbus/logs/logs.tsv`(2026-01~02)에서 나왔습니다.
  - **운영 서버 이력의 보존 기간은 미확인**입니다.
- **브랜치**
  - `bushexa-nopo-1224` worktree(`feat/nopo-1224-arrival`)는 `edacb33`(= origin/master) 상태이고 커밋이 없습니다. 이름으로 보아 PR-C와 범위가 겹칩니다.
  - 로컬 master 공지의 `SURFACES`에는 `busan`이 없습니다. `ALL_SURFACES = "all"`은 있습니다.
- **도착 캐시 `fetched_at`**: 폴러 **사이클 시작 시각**이 모든 정류장에 같은 값으로 저장됩니다(`arrival_poller.py:115-125`). 폴링 주기는 관리자가 3~600초로 바꿀 수 있습니다(`crawl_settings.py:27-28`).

---

## 2. 목표와 비범위

**목표**

1. 세 루트를 사용자가 말한 목적지까지 안내합니다.
   - 루트 1: 513 → 울산역 → KTX → 부산역 → 1호선 → **남포·서면·부전**(부산역 포함)
   - 루트 2: 743·753 → 좋은삼정병원앞(같은 정류장) → 1224 → **노포동**(→ 1호선 서면 참고)
   - 루트 3: 713·743·753·1115 → 태화강역 → 동해선 → **신해운대(해운대)·송정**(센텀·벡스코·부전 포함)
2. **루트별로 필요한 버스·열차 전체 시간표**를 페이지 안에서 보여 줍니다(`<details>` 접이식). 표의 원본 목록은 `01-required-timetables.md`에 있습니다.
3. 오너 결정 O-1~O-5를 페이지 전체에 적용합니다.
   - 모든 시각에 `basis`와 `source`를 데이터로 붙입니다.
   - 기점 시각(513 덕하, 1224 농소)은 라벨을 붙여 보여 주기만 하고, 연결 계산·순위·카운트다운에는 넣지 않습니다.
   - 탑승 전 통과 예측의 우선순위는 실시간 > 이력(게이트 통과) > (B-D10 승인 시) 참고 예측 > 라벨 붙은 기점 시각입니다.
   - 노선 번호로 분기하지 않습니다.
4. KTX(옛 SRT 계통 포함)와 다른 열차 구간은 **`RAIL_PAIRS` 한 줄 + 여정 레지스트리 한 줄**을 추가하면 켜지게 합니다.

**비범위**

- 요금 계산과 예매 연동. 외부 링크 한 줄만 둡니다.
- 부산 시내버스, 도시철도 2~4호선. 해운대 해수욕장까지의 연계도 제외하고 "역 도착까지만 안내"합니다.
- 임의 출발지·목적지 경로 탐색
- 1224 GPS 상시 추적(B-D2)
- 다크 모드, SVG 지도
- `/timetable`·`/unist`의 513 표기 이관. 이 작업은 timetable-ux PR의 몫이고, 부산 페이지는 공통 부품의 첫 소비자로서 설계만 맞춥니다.
- **`ROUTEID`와 `SERACH_STOPS` 변경.** `/board`·`/unist`·`/busno`·`/running`·`/stops`, 관리자, 크롤, govtrack으로 새어 나가는 것을 막습니다. `len(ROUTEID)==10`을 유지합니다.
- `info.html` 수정. `feat/route-map-geo-ab`가 병합된 뒤 교차 링크만 후속 커밋으로 넣습니다.

---

## 3. 정확성 원칙

### 3.1 시각 토큰

```python
@dataclass(frozen=True)
class TimeToken:
    at: datetime                 # KST, 날짜 포함. 이 값이 권위. "HH:MM" 문자열·분 정수는 파생값일 뿐 비교에 쓰지 않는다
    basis: str                   # "unist" | "stop" | "station" | "origin"
    source: str                  # "live" | "schedule" | "history" | "reference" | "assumed"
    lo: datetime | None = None   # p10. 없으면 at
    hi: datetime | None = None   # p90. 없으면 at
    n: int | None = None
    ref_key: str | None = None   # SEGMENT_REFERENCE 키(기간·출처 표시용)
    flags: frozenset[str] = frozenset()   # "band_rollup", "stale_ref", "live_bias" 등
```

- `rail_match.service_minutes`는 동해선 편 매칭 내부(`match_by_time`)에서만 씁니다. 도메인의 비교·정렬·표시는 모두 `at`(datetime)으로 합니다.
- 표시는 `at`의 날짜가 기준 날짜와 다르면 "내일 00:16"처럼 씁니다.

| source | 의미 | 화면 표기 예 |
|---|---|---|
| live | 도착 캐시 ETA. 기준 시각은 `fetched_at`이고 신선도 게이트(§3.5)를 통과한 것만 씁니다 | "18:03 (실시간 · 18:01 수집)" + "N분 후" |
| schedule | 그 지점의 시간표 시각(UNIST 기점 출발, 역 시각표) | "18:15" |
| history | E단계 게이트(최근 30일·같은 요일구분·시간대 n≥4)를 통과한 이력 추정 | "약 18:40 (18:34~18:47)" |
| reference | 레거시 기록 기반 참고값(기간·n 명시) | "약 18:40 · 참고(2026년 4~6월 기록 n=87)" |
| origin | 기점 출발 시각. 보여 주기만 합니다 | "덕하 출발 17:20 · UNIST 통과 시각 아님" |
| assumed | 도보·환승 여유 설정값 | 각주 "가정값" |

### 3.2 통일 게이트 규칙 (규칙 U)

시각 추정을 두 종류로 나누고 노선에 관계없이 똑같이 적용합니다. 판단은 데이터로 합니다. 대상이 `Leg.relation == "passes"`인 승차 구간인지, 탑승 후 구간인지로 가르고, 노선 번호는 보지 않습니다.

| 종류 | 예 | 틀렸을 때 결과 | 허용 출처 |
|---|---|---|---|
| **탑승 전 통과 예측**: 내가 탈 차량이 승차·환승 지점에 언제 오는지. 기점 시각 + 기점→지점 소요 | 513이 UNIST(`196040234`)를 지나는 시각, 1224가 좋은삼정(`193030929`)을 지나는 시각, (귀가) 1224·743이 신복교차로 입구를 지나는 시각 | 차를 놓칩니다 | live > history(O-3 게이트) > **reference(B-D10 승인 시에만, 시간대 칸 n≥4, 요일 전체로 올리기 금지, `valid_until`·`review_by` 이내)** > 없음(기점 시각 라벨만 표시) |
| **탑승 후 구간 소요**: 이미 탄 차량이 하차 지점까지 걸리는 시간 | UNIST→울산역, UNIST→좋은삼정, UNIST→태화강역, 좋은삼정→노포 | 늦게 도착합니다. `hi`로 방어합니다 | live 없음. history > reference(시간대 n<4면 요일 전체로 올리고 `band_rollup` 표시, `valid_until`·`review_by` 이내) |

규칙 U를 지금 데이터에 적용한 결과는 다음과 같습니다.

- **513 덕하→UNIST**: 레거시 기록을 BIS 현행표로 매칭해 다시 계산했습니다(`r1_bands.py`, 783/792 운행 매칭). 평일·토·일 모든 시간대 칸이 n≥5입니다(평일 칸별 48~135). 따라서 B-D10을 승인하면 **PR-B에서 울산역 도착 참고 예측표를 켤 수 있습니다.**
- **1224 농소→좋은삼정**: 야간 n=3이고 주간은 측정하지 못했습니다. 게이트를 통과하지 못하므로 **루트 2는 좋은삼정 실시간 전용**이 됩니다. 시간표 기반 환승표는 P0-⑤ 표본 수집(B-D14)이나 PR-E 뒤에 데이터가 채워지면 코드 변경 없이 켜집니다.
- 같은 규칙이 513과 1224 모두에 적용되므로 v1 통합안에 있던 모순이 사라집니다. 그 모순은 "513 n=5~7은 금지하면서 1224 n=3은 허용"이었습니다.

탑승 전 참고 예측의 표시 규칙은 다음과 같습니다.

- "약 18:35 (빠르면 18:24)" 형식으로 `lo`를 함께 보여 줍니다. 승차 지점에 `lo`까지 나가 있으라는 안내입니다.
- 카운트다운("N분 후")은 붙이지 않습니다. 카운트다운은 live 전용입니다.
- 루트 간 추천 순위에 넣지 않습니다. 루트 간 추천은 E단계 전까지 전체적으로 두지 않습니다.
- `basis="stop"`, `source="reference"`로 두고, `basis="origin"` 토큰과는 구별합니다.

### 3.3 연결 판정

- **판정식**: `hi(앞 구간 도착) + 환승 여유(assumed) ≤ lo(다음 편 승차)`
  - 다음 편이 schedule(열차·동해선·1호선·UNIST 기점 출발)이면 `lo = at`입니다.
  - 다음 편이 추정(1224 통과 등)이면 `lo = p10`입니다.
  - 다음 편이 live면 `lo = at`이고 §3.5의 편향 보정을 적용합니다.
- **빠듯함**: 여유(`lo(다음) − (hi(앞) + 환승 여유)`)가 `BUSAN_TIGHT_SLACK_MIN`(제안 3분) 미만이면 **"빠듯함" 텍스트 배지**를 붙이고 그다음 편 대안을 함께 보여 줍니다. 색만으로 구분하지 않습니다.
- 화면에 보이는 "약" 시각은 중앙값입니다. 판정은 위 식으로만 합니다.
- **계산하지 않는 경우와 이유 코드**: 앞 구간 토큰이 없으면 연결을 계산하지 않습니다. 이유 코드는 `origin_only`, `ref_expired`, `ref_stale`, `tt_missing`, `rail_pending`, `metro_closed`, `live_stale`, `sample_short` 등입니다.

### 3.4 서비스일과 자정

- `service_date(now) = (now − 3h).date()`로 정의합니다.
- **다가오는 편 = ① 전날 서비스일 표 가운데 아직 남은 편 + ② 오늘 달력일 표의 편.** 두 목록을 `at`(datetime)으로 합치고 중복을 제거합니다.
  - 철도: `trains_on(store, …, service_date(now))`의 남은 편(예: 9/29 항목의 9/30 00:43 KTX)과 `trains_on(…, now.date())`를 합칩니다.
  - 동해선·1호선: 전날 서비스일의 day_type 표에서 `service_minutes ≥ 24h + 현재분`인 편을 전날 날짜로 datetime화하고, 오늘 day_type 표의 편과 합칩니다.
  - 버스: 같은 경로를 탑니다. 현재 검증기가 `hh ≤ 23`이라 ①은 사실상 비어 있습니다.
- **요일구분**: 버스·동해선·1호선 모두 **표가 속한 날짜로** 정합니다. ①은 전날, ②는 오늘입니다.
- **상태 판정 예**
  - 토요일 00:30: 금요일 서비스일에 남은 편이 없으면 상태는 "첫차 전(오늘 05:20)"입니다. "오늘 연결 끝"이 아닙니다.
  - 월요일 02:50: 일요일표에 남은 편이 없으면 월요일 평일표를 기준으로 "첫차 전"입니다.
- **막차 역산**도 같은 규칙으로 계산합니다.

### 3.5 실시간 신선도와 편향

- **게이트**: `live_max_age = max(BUSAN_LIVE_MIN_AGE_S(120), 2 × 유효 arrival 폴링 주기 + 관측 사이클 소요)`
  - 라우트가 `services/crawl_settings`의 유효 폴링 주기와 `services/arrival_status.ArrivalStatusReader`의 최근 사이클 소요를 읽어 도메인에 값으로 주입합니다. 사이클 소요를 읽지 못하면 "정류장 수 × 1.5초 + 7초"로 추정합니다.
  - 게이트를 넘으면 live 토큰을 만들지 않고 "실시간 정보가 오래되었습니다(마지막 HH:MM)"를 표시합니다. 시간표 경로는 계속 보여 줍니다.
- **기준 시각**: live 토큰의 `at`은 `fetched_at + ETA`입니다. `now + ETA`가 아닙니다.
- **편향**: `fetched_at`은 사이클 시작 시각입니다. 목록 뒤쪽 정류장의 실제 조회는 최대 사이클 소요만큼 늦게 이루어지므로 `at`이 실제보다 이르게 잡힙니다.
  - 탈 차량(다음 편)이 이르게 잡히는 것은 보수적인 방향입니다. 그대로 둡니다.
  - **앞 구간(환승 전 차량) live 토큰**은 `hi = at + 사이클 소요`로 보정하고 `live_bias` 플래그를 답니다.
  - 정류장별 조회 시각을 payload에 넣는 개선은 스키마 변경이므로 별도 소형 PR로 제안합니다(비차단).

### 3.6 실패 모드: 틀린 값 대신 "모름"을 보인다

| 입력 | 실패·이상 | 처리 |
|---|---|---|
| 도착 캐시 | 게이트 초과 또는 `fetched_at` 없음 | live 없음, "실시간 정보가 오래되었습니다(마지막 HH:MM)". 시간표 폴백은 유지합니다 |
| 도착 캐시 | `[]`. 울산 API 실패도 새 타임스탬프의 `[]`로 캐시되는 결함 X1이 있습니다 | "지금 오는 버스 정보 없음(HH:MM 수집)". "운행 없음"이라고 쓰지 않습니다 |
| 버스 시간표 | 파일 없음 / 요일 키 없음 | `tt_missing` "시간표 없음(정보 누락)". "막차 이후"와 구분합니다 |
| 버스 시간표 | `_meta.json`의 `collected_at`이 120일 경과 / 값 없음 | 경과 배너 + 수집일 / "수집일 미상". **mtime은 쓰지 않습니다** |
| 열차 trains | 그날 없음 / `suspect` | "열차 시간표 준비 중" / "평소보다 적게 조회됨". v1 동작을 유지합니다 |
| 동해선·1호선 | 역·방향·요일 항목 없음, 매칭 실패 | 그 목적지 열만 "시간표 없음" 또는 "–"로 둡니다. 보간하지 않고, 다른 열은 계속 보여 줍니다 |
| 1호선 | 환승 가능 시각이 막차보다 늦음 | 그 목적지 열을 `metro_closed` "1호선 운행 종료"로 표시합니다. 역 도착 시각은 그대로 보여 줍니다 |
| 공휴일 캐시 | 오늘이 속한 달이 캐시에 없음 | 상태 줄에 "공휴일 정보 없음 — 요일로만 판단" |
| 철도 요일 | 버스는 공휴일인데 `METRO_DAY_OVERRIDES`에 확인된 항목이 없는 대체공휴일·명절 | 상태 줄에 "동해선 편성 미확인(휴일표 적용)"을 표시합니다. 확인된 덮어쓰기가 있으면 그 값을 씁니다 |
| 1224 | 특별편 지정일 | 전용 디렉터리에서 **요청 요일 그대로** 읽습니다. 평일로 폴백하지 않습니다 |
| 노선 개편 | 참고값의 `valid_until`이 지남 | 출발 시각은 계속 보이고, 그 구간 추정만 `ref_expired` "개편 후 소요 수집 중"으로 내립니다 |
| 참고값 경과 | `review_by`가 지남 | 값은 쓰되 "오래된 참고값" 라벨(`ref_stale`)을 붙입니다. 탑승 전 예측에는 쓰지 않습니다 |

---

## 4. 아키텍처와 데이터 모델

### 4.1 계층 배치

- `Leg`는 `bushexa/data/constants.py` 안에 `typing.NamedTuple`로 정의합니다. 필드는 리터럴만 두고 Callable이나 provider는 넣지 않습니다.
  - constants가 다른 모듈을 import하지 않으므로 순환 import가 생기지 않습니다.
  - ID 단일 출처 규칙(절대 규칙 6)도 지킵니다.
- provider(시간표·철도·추정값)는 라우트가 조립해서 도메인에 **값으로** 주입합니다. domain은 `data.constants`, `data.timetable`, `time_utils`만 import합니다.
- 새 순수 모듈은 `bushexa/domain/journey_time.py`입니다. 내용은 `TimeToken`, `live_eta_token`, `segment_token`, `passing_token`(규칙 U 적용), `first_catchable`, `service_date`, `upcoming_across_midnight`입니다.

### 4.2 constants 레지스트리 (ID·문구 단일 출처)

```python
class Leg(NamedTuple):
    mode: str                       # "bus" | "rail" | "metro"
    lines: tuple[str, ...]          # 표시용 노선명(분기 금지 — 데이터 조회 키로만 사용)
    relation: str                   # "boards_at_origin" | "passes" | "scheduled_station"
    board: dict[str, str]           # 노선별 승차 정류장/역 ID
    alight: dict[str, str]          # 노선별 하차 정류장/역 ID  (1115 → 999000209, 나머지 → 193012313)
    origin_key: dict[str, str] = {} # relation="passes"일 때 시간표 기점 키(513 → "덕하", 1224 → "농소")
    route_ids: dict[str, str] = {}  # 도착 캐시 필터용 route_id

# 부산 루트 전용 버스 노선 — ROUTEID 밖. ROUTEID와 같은 4-튜플(정류장은 TAGO 2026-09-29 확인).
BUSAN_EXTRA_ROUTES = {
    "195000247": ("1224", "노포동역 방면", "농소", ["195025331", "193030929", "193030703", "140000184"]),
    "195000248": ("1224", "농소 방면", "노포동", ["140000185", "193030708", "999000065"]),  # 농소 종점 ID 미확인
}
BUSAN_EXTRA_ARRIVAL_STOPS = ["193030929"]                  # 폴러 전용. SERACH_STOPS 불변
BUSAN_EXTRA_TRACKED_STOPS = {"195000216": ["193030929"],    # govtrack 기록 필터만 확장(호출 0)
                             "195000222": ["193030929"]}
# STOP_IDS 추가: 193030929 좋은삼정병원앞, 195025331 농소공영차고지, 140000184/140000185 노포동역 (조회는 .get)

# 동해선·부산 1호선 역 — 이름 있는 상수로(위치 인덱스 금지)
METRO_TAEHWAGANG, METRO_SONGJEONG, METRO_SINHAEUNDAE = "MTRKRK6K132", "MTRKRK6K121", "MTRKRK6K120"
METRO_CENTUM, METRO_BEXCO, METRO_BUJEON = "MTRKRK6K118", "MTRKRK6K119", "MTRKRK6K110"
METRO1_BUSAN, METRO1_NOPO = "MTRBS10113", "MTRBS10134"
METRO1_NAMPO, METRO1_SEOMYEON, METRO1_BUJEON = "MTRBS10111", "MTRBS10119", "MTRBS10120"
METRO_QUERIES += [(METRO_SONGJEONG, "U"), (METRO_SINHAEUNDAE, "U"), (METRO_CENTUM, "U"),
                  (METRO1_BUSAN, "D"), (METRO1_BUSAN, "U"), (METRO1_NOPO, "U")]
METRO_SATURDAY_FALLBACK = {"MTRKRK6": "03"}   # 노선 접두 → 대체 코드. 1호선은 02가 채워져 있어 대체하지 않음
# 날짜별 철도 편성 덮어쓰기(대체공휴일·명절). confirmed=False면 상태 줄에 "편성 미확인".
METRO_DAY_OVERRIDES = {"2026-10-05": {"lines": {"MTRKRK6": "01"}, "confirmed": False,
                                      "source": "TAGO 열차 10/5=평일 집합, rail.blue 10/5 평일표(비공식)"}}
# 1호선 고정 소요(분, 방향). 출처: TAGO SubwayInfo 역 시간표 연속역 차이, 2026-09-29 확인.
METRO1_RUN_MIN = {
    (METRO1_BUSAN, METRO1_NAMPO): ("U", 4.0), (METRO1_BUSAN, METRO1_SEOMYEON): ("D", 10.5),
    (METRO1_BUSAN, METRO1_BUJEON): ("D", 12.5), (METRO1_NOPO, METRO1_BUJEON): ("U", 26.5),
    (METRO1_NOPO, METRO1_SEOMYEON): ("U", 28.0), (METRO1_NOPO, METRO1_BUSAN): ("U", 39.0),
    (METRO1_NOPO, METRO1_NAMPO): ("U", 42.5),
}
# 환승 여유(분) — 환승 지점(정류장·역 ID) 키. 모두 가정값(assumed).
TRANSFER_BUFFER_MIN = {"196015429": 10, "NAT014445": 8, "193012313": 5, "999000209": 8,
                       "193030929": 2, "140000184": 5}
BUSAN_TIGHT_SLACK_MIN = 3
BUSAN_LIVE_MIN_AGE_S = 120

BUSAN_DESTINATIONS = {   # 목적지 → 루트 옵션(한 목적지에 여러 루트). label은 i18n 키.
  "busan-stn": {"label": "busan.dest.busan_stn", "options": [{"journey": "ktx"}]},
  "nampo":     {"label": "busan.dest.nampo",     "options": [{"journey": "ktx", "onward": (METRO1_BUSAN, METRO1_NAMPO)}]},
  "seomyeon":  {"label": "busan.dest.seomyeon",  "options": [{"journey": "ktx", "onward": (METRO1_BUSAN, METRO1_SEOMYEON)},
                                                           {"journey": "nopo", "onward": (METRO1_NOPO, METRO1_SEOMYEON), "alt": True}]},
  "bujeon":    {"label": "busan.dest.bujeon",    "options": [{"journey": "ktx", "onward": (METRO1_BUSAN, METRO1_BUJEON)},
                                                           {"journey": "donghae", "alight": METRO_BUJEON}]},
  "nopo":      {"label": "busan.dest.nopo",      "options": [{"journey": "nopo"}]},
  "haeundae":  {"label": "busan.dest.haeundae",  "note": "busan.note.station_only",   # "해운대(신해운대역)"
                "options": [{"journey": "donghae", "alight": METRO_SINHAEUNDAE}]},
  "songjeong": {"label": "busan.dest.songjeong", "options": [{"journey": "donghae", "alight": METRO_SONGJEONG}]},
  "centum":    {"label": "busan.dest.centum",    "options": [{"journey": "donghae", "alight": METRO_CENTUM}]},
}
BUSAN_JOURNEYS = {   # 도메인은 순회만 한다.
  "ktx": (
    Leg("bus", ("513",), "passes", board={"513": "196040234"}, alight={"513": "196015429"},
        origin_key={"513": "덕하"}, route_ids={"513": "196000421"}),
    Leg("rail", ("KTX",), "scheduled_station", board={"KTX": RAIL_ULSAN}, alight={"KTX": RAIL_BUSAN}),
  ),
  "nopo": (
    Leg("bus", ("743", "753"), "boards_at_origin", board={"743": "196040233", "753": "196040233"},
        alight={"743": "193030929", "753": "193030929"}, origin_key={"743": "UNIST", "753": "UNIST"},
        route_ids={"743": "195000216", "753": "195000222"}),
    Leg("bus", ("1224",), "passes", board={"1224": "193030929"}, alight={"1224": "140000184"},
        origin_key={"1224": "농소"}, route_ids={"1224": "195000247"}),
  ),
  "donghae": (
    Leg("bus", ("713", "743", "753", "1115"), "boards_at_origin",
        board={b: "196040233" for b in ("713", "743", "753", "1115")},
        alight={"713": "193012313", "743": "193012313", "753": "193012313", "1115": "999000209"},
        origin_key={b: "UNIST" for b in ("713", "743", "753", "1115")}),
    Leg("metro", ("donghae",), "scheduled_station", board={"donghae": METRO_TAEHWAGANG}, alight={}),
  ),
}
```

`SEGMENT_REFERENCE`는 v1의 `BUSAN_UNIST_TO_ULSAN_STATION_MIN`과 `BUSAN_TAEHWAGANG_BUS_MIN`을 대체합니다. 구조는 다음과 같습니다.

```python
SEGMENT_REFERENCE = {
  ("196000421", "196040142", "196040234"): {           # 513 덕하 기점 → UNIST (탑승 전 통과 예측)
     "source": "logs/logs.tsv 2026-04-16~06-01, BIS 현행표 매칭(783/792)", "period": "2026-04-16~2026-06-01",
     "review_by": "2026-12-31", "valid_until": None,
     "bands": {0: {"05-07": (55.2, 49.0, 64.0, 71), "07-09": (69.2, 61.4, 74.4, 53), ...},   # (중앙, p10, p90, n)
               1: {...}, 2: {...}},
     "all": {0: (61.9, 53.6, 75.9, 553), 1: (61.7, 53.1, 68.4, 82), 2: (57.0, 50.7, 63.9, 95)}},
  ("195000216", "196040233", "193012313"): {"valid_until": "2026-10-02", ...},   # 743 가는 방향: 구영리 개편 구간 통과
  ("194000107", "196040233", "999000209"): {"valid_until": None,
     "unaffected_reason": "1115 10/3 개편 구간(명촌정문~성원상떼빌→아산로)은 태화강역광장 하류"},
  ...
}
ROUTE_CHANGE_EPOCHS = {"195000216": "2026-10-03", "195000215": "2026-10-03",    # 743 양방향
                       "194000107": "2026-10-03", "194000106": "2026-10-03"}    # 1115 양방향
```

- 키는 `(route_id, from_stop_id, to_stop_id)`입니다. from은 **항상 정류장 ID**입니다. 기점은 `196040233`(UNIST 기점), `196040142`(덕하), `195025331`(농소)처럼 씁니다. 기점 여부는 `Leg.relation`으로 표현합니다.
- 시간대는 7구간입니다: 05–07, 07–09, 09–12, 12–16, 16–19, 19–21, 21–24. 백분위는 `statistics.quantiles(method="inclusive")`로 계산합니다.
- 모든 항목에 `source`, `period`, `review_by`가 **필수**입니다. `review_by` 제안값은 2026-12-31입니다. 표본이 1학기 기록이라 2학기 말까지 유효하다고 봅니다(B-D9).
- `route_id`가 `ROUTE_CHANGE_EPOCHS`에 있는 항목에는 `valid_until` 또는 `unaffected_reason` 중 하나가 **반드시** 있어야 합니다. 테스트로 강제합니다.
- 1115 가는 방향(UNIST→태화강역광장)은 `unaffected_reason`으로 만료시키지 않습니다. 1115 귀가 방향(꽃바위→`999000077`)과 743 양방향 구간은 `valid_until: "2026-10-02"`입니다.
- `/seoul`도 513→울산역 계산을 쓰므로 **공용 함수로 추출해서 같은 PR에서 교체**합니다. 목적은 화면마다 숫자가 같게 하는 것입니다(N-10).

### 4.3 파일

| 파일 | 내용 | 쓰는 쪽 | git / 백업 | PR |
|---|---|---|---|---|
| `data/timetable/_meta.json` (신규) | `{busno: {"collected_at", "source": "ulsan_bis", "rows": {day: n}}}` | 시간표 크롤(`atomic_write_json`). 노선 파일을 쓴 직후 갱신합니다 | 노선 파일과 같은 취급(추적) | A2 |
| `data/transit/bus/1224.json` + `data/transit/bus/_meta.json` | 기존 버스 포맷 `{"0"/"1"/"2": {"농소": [...], "노포동": [...]}}` | cache-refresh transit 크롤. 최초본은 CLI로 만들어 커밋합니다 | 추적, 백업 제외 | C |
| `data/rail_timetable.json` | trains + metro(동해선 3역, 1호선 3쿼리 추가) | 기존 `locked_update_json` | ignore(기존) | B |
| `data/unist_estimates.json` | 구간 통계 절(E단계, timetable-ux와 한 파일) | 야간 잡 | **`.gitignore`에 추가**, 백업 제외 | E |
| `data/notices.json` | surface `busan` 공지 | 관리자 | 기존 정책 | A0 |

- 1224를 `data/timetable/`에 두지 않는 이유가 있습니다. 특별편 에디션에 노선 파일이 없으면 기본 디렉터리의 평일(0)로 폴백하기 때문입니다(`board_support.py:158-161`). 대신 `get_timetable(..., dir=transit_bus_dir())`로 요청 요일 그대로 읽습니다.
- `transit_bus_dir()`의 env override(`BUSHEXA_TRANSIT_DIR`)는 playbook §4 절차를 따릅니다. 모듈 캐시를 두면 같은 커밋에 테스트 리셋 훅을 넣습니다(PM-010).
- `_meta.json`을 따로 두는 이유는 노선 파일 안에 `_meta` 키를 넣으면 `validate_timetable`의 요일 키 검증과 충돌하기 때문입니다.

---

## 5. 루트별 설계

실제 시각표, 통계, 연결 계산표는 모두 `01-required-timetables.md`에 있습니다. 여기서는 계산 방식과 상태만 정합니다.

### 5.1 루트 1: 513 → 울산역 → KTX → 부산역 → 1호선

1. **UNIST 통과(탑승 전)**
   - live: `196040234` 도착 캐시에서 route_id `196000421`로 거릅니다.
   - live가 없으면 규칙 U를 적용합니다. B-D10을 승인하면 덕하 출발 + `SEGMENT_REFERENCE[513 덕하→UNIST]` 시간대 칸으로 추정합니다.
   - 둘 다 안 되면 `origin_window`(최근 1편 + 다음 2편)를 "덕하 출발 · UNIST 통과 시각 아님" 라벨로 보여 줍니다.
2. **울산역 도착(탑승 후)**: 앞 토큰에 UNIST→울산역 참고값(평일 중앙 16.0분, p10 14.1, p90 18.7, n=894)을 더합니다.
   - live 기준일 때: `hi = hi(UNIST) + p90`
   - 참고 예측일 때: 덕하→울산역 칸 값을 직접 씁니다(평일 21–24시 72.1 / p90 78.3 등).
3. **KTX**: `hi(울산역) + 10` 이후 첫 편을 잡습니다. 서비스일 규칙(§3.4)을 적용하고, 00시대 편도 포함합니다.
4. **1호선**
   - KTX 부산 도착 + 8(가정) 이후 부산역 첫 발차를 1호선 역 시간표에서 찾습니다. 서면·부전은 D, 남포는 U입니다.
   - 도착 = 그 발차 + `METRO1_RUN_MIN` 고정 소요입니다. **편별 시각 매칭은 하지 않습니다**(F6).
   - 발차가 없으면 `metro_closed`로 둡니다.
5. **예시** (평일, 참고 예측, B-D10 승인 전제)
   - 덕하 17:20 → UNIST 약 18:35(빠르면 18:24) → 울산역 약 18:52(늦으면 19:11) → KTX 19:25→19:47 → 남포 20:00 · 서면 20:06 · 부전 20:08
   - 덕하 22:00 → KTX 23:36→23:57 → **서면·부전은 1호선 운행 종료**, 남포는 내일 00:16(U 막차 00:12:30)
6. **부전**: 동해선 루트가 요금이 싸다는 대안 링크(`#route-donghae`)를 둡니다. 목적지 레지스트리에 두 루트를 모두 둡니다.
7. **B-D10을 거부하면**: 실시간이 없는 시간대에는 울산역 도착을 보여 주지 않습니다. `busan.state.ulsan_eta_pending` "울산역 도착 예측은 이력 수집 후 제공(PR-E)"을 표시하고, §2 목표 1에 "요구 미충족(PR-E까지)"을 명시합니다.

### 5.2 루트 2: 743·753 → 좋은삼정병원앞 → 1224 → 노포

1. **실시간 경로(PR-C의 주 경로)**
   - 좋은삼정 `193030929` 도착 캐시 한 번 조회로 743·753·1224 ETA를 함께 받습니다.
   - 환승 판정: `hi(743/753 live) + 2 ≤ at(1224 live)`. 앞 차량 hi에는 `live_bias`를 더합니다.
   - 대기 = 1224 at − 743 at입니다.
   - 1224가 목록에 있고 743·753이 없으면 "1224 N분 후 · 지금 UNIST에서 출발하면 연결 여부 계산 불가"로 표시합니다.
2. **시간표 경로**
   - 743·753 UNIST 출발(schedule) → 좋은삼정 도착 약(탑승 후 참고값, 평일 7구간, 743 중앙 20.2~26.3, 753 23.1~29.5)을 보여 줍니다.
   - **1224 좋은삼정 통과는 규칙 U상 현재 게이트 미통과(n=3)**입니다. 1224는 "농소 출발 HH:MM, HH:MM · 좋은삼정 통과 시각 표본 부족(`sample_short`)"으로 표시하고 연결은 계산하지 않습니다.
   - P0-⑤ 표본이나 PR-E 이력이 시간대 칸 n≥4를 채우면 같은 코드가 자동으로 연결표를 냅니다.
3. **참고 계산** (레퍼런스 문서 전용. 앱에는 게이트 통과 전 표시하지 않음. 농소+32/35/37분 가정)
   - 평일 마지막 연결: 753 22:10 → 좋은삼정 약 22:37 → 1224 22:15편(통과 약 22:50) → 노포 약 23:29
   - 이 경우 **1호선 노포 막차(23:31) 환승 불가**라서 서면은 `metro_closed`입니다.
   - 서면까지 가는 마지막 연결은 743·753 21:50 → 1224 21:55편 → 노포 약 23:09 → 1호선 23:16 → 서면 약 23:44입니다.
4. **노포 → 1호선**: 노포동역 정류장 → 노포역 여유 5분(가정) 뒤 U 첫 발차 + 고정 소요입니다(서면 28.0, 부산 39.0, 남포 42.5).
5. **귀가 안내(PR-C 표, PR-F 계산)**
   - 1224 노포 출발(`195000248`)은 좋은삼정에 서지 않습니다.
   - 울산대학교앞 `193030708`(노포 출발 +30~34분) 또는 신복교차로 입구 `999000065`(+32~36분, 이미 폴링 중)에서 743·753 UNIST 방면으로 갈아탑니다.

### 5.3 루트 3: 버스 → 태화강역 → 동해선

1. **버스 구간**
   - 713·743·753·1115의 UNIST 출발(schedule)에 태화강역 도착(탑승 후 참고값, 노선·요일·시간대 7구간)을 더합니다.
   - 하차 정류장은 `Leg.alight` 노선별 map으로 정합니다. 1115만 태화강역광장 `999000209`입니다.
   - 환승 여유는 하차 정류장 ID로 조회합니다(5분 / 8분).
2. **동해선**
   - `hi + 여유` 이후 첫 **부전행** 편을 잡습니다. 망양행은 제외합니다.
   - 도착역 열은 송정·신해운대·센텀·벡스코·부전입니다. 역별 시간표를 `metro_trips`(시각 매칭)로 붙입니다. 동해선은 배차가 15~47분이라 매칭이 성립합니다.
   - 매칭 소요가 기대값(송정 48, 신해운대 51.5, 센텀 58.5, 벡스코 55.5, 부전 76)에서 ±10분을 넘으면 테스트로 경보합니다.
3. **요일**: `metro_day_type`에 `METRO_DAY_OVERRIDES`를 먼저 적용합니다. 토요일에 02가 비면 동해선만 03으로 대체합니다.
4. **평일 마지막 연결(신해운대, BIS 현행표 + 재계산 참고값)**

   | 노선 | UNIST 출발 | 결과 |
   |---|---|---|
   | 743 | 21:50 | 태화강 늦으면 22:54 + 5 → 동해선 23:00, **빠듯함(여유 1.2분)** → 신해운대 23:51 |
   | 713 | 21:40 | 여유 11.8분 |
   | 1115 | 21:40 | 여유 19.7분 |
   | 753 | 21:25 | 여유 20.6분. 753 21:50은 연결 없음 |

   v1 통합안의 "마지막 = 753 21:25"는 틀린 값이었습니다.
5. **휴일 마지막 연결**: 713 21:40, 753 21:30, 1115 21:40, 743 21:20. 743 주말표는 BIS 현행과 4~6월 운행이 달라 미확인입니다.
6. **부전 00:16 도착**은 "내일 00:16"으로 표시합니다.

### 5.4 귀가 방향 (PR-F, 데이터 요구만 정리)

- 루트 1 귀가
  - KTX 부산→울산: `RAIL_PAIRS` 한 줄입니다.
  - 513 울산역(시내 방면) `196015414`(폴링 중) → UNIST: 참고 중앙 19.5분(p10 16.4, p90 21.6, n=913)
  - 삼남 출발 → 울산역 22.0분(p90 26.1, n=362), → UNIST 41.6분(p90 46.4, n=353)
- 루트 3 귀가
  - 동해선 D 방향 쿼리를 추가합니다.
  - 명촌 기점 + 약 7분 → 태화강역 2번 정류소 `193012314`
  - 1115 꽃바위 → 태화강역광장 오프셋은 확정하지 못했습니다(미확인).
- 루트 2 귀가: §5.2의 5번과 같습니다.

---

## 6. 수집과 호출량

| 대상 | 방법 | 호출량 변화 | PR |
|---|---|---|---|
| 기존 5개 노선 시간표 | 워커가 매일 02~03시에 재크롤합니다. P0-①에서 운영 파일 내용을 BIS와 대조합니다. 로컬은 재크롤 diff를 검토한 뒤 커밋합니다 | 0 | P0 |
| 시간표 급감 방어 | `timetable_crawl`에 새로 추가합니다. **요일·기점별 0행이거나 기존 대비 50% 미만이면 그 노선 쓰기를 보류하고 실패로 집계합니다.** 현재 코드는 "전 요일 0행"만 막습니다(`timetable_crawl.py:190-198`). 한 요일이 비면 `{"1": {}}`가 저장되어 KeyError가 납니다 | 0 | A2 |
| 동해선 송정·신해운대·센텀 | `METRO_QUERIES` 3줄 | 3역 × 3요일 = 하루 약 9건 | B |
| 1호선 부산역 D·U, 노포 U | `METRO_QUERIES` 3줄 | 하루 약 9건 | B |
| 1224 시간표 | `_busno_directions(routes=…)`, `crawl_all_timetables(..., routes=BUSAN_EXTRA_ROUTES, out_dir=transit_bus_dir())`로 인자화합니다. 기본 동작은 바뀌지 않습니다. `ulsan_bis.py` 파서가 `ROUTENAME`을 선택적으로 읽어 방향을 검증합니다("노포동역(종점) 방면" = dir 1). `cache_refresh.refresh_transit_timetables`는 격리해서 호출합니다 | 하루 약 9건 | C |
| 좋은삼정 실시간 | 폴러 기본 목록 = `SERACH_STOPS + BUSAN_EXTRA_ARRIVAL_STOPS`(순서 보존). `/stops`는 `SERACH_STOPS`만 씁니다 | 17 → 18곳, 울산 BIS **하루 약 +2.9k(+6%)** | C (P0-③ 후) |
| 743·753 좋은삼정 통과 기록 | `daemon.tracked_stops_by_route()`에서 `BUSAN_EXTRA_TRACKED_STOPS`를 합칩니다 | TAGO 0. TAGO 장애로 울산 폴백할 때의 증가분은 확인 필요 | C |
| 1224 좋은삼정 통과 표본 | P0-⑤(선택). 조사용 `sampler.py`를 며칠 실행하고 운영 코드는 바꾸지 않습니다 | 실행 중 TAGO 방향당 하루 약 +4.8k | P0 (B-D14) |
| 1224 GPS 상시 추적 | 보류(B-D2) | — | — |
| KTX 부산→울산 등 귀가 | `RAIL_PAIRS` 한 줄 | 하루 약 14건 | F |

API 일일 한도(TAGO 버스위치·열차·지하철, 울산 BIS)는 `api-usage.md` §4에 기록되어 있지 않습니다. PR-C의 폴링을 추가하기 전에 data.go.kr 마이페이지에서 확인하고 문서에 적습니다(P0-③).

---

## 7. 화면

### 7.1 원칙

- zero-JS로 완결하고, 인라인 style·script를 쓰지 않습니다.
- 문구는 모두 `t('busan.*')`로 씁니다. 버스 정류소는 `| stop`으로, 역·부산 지명·노선명은 `t('place.*')`로 씁니다.
- 1224·동해선·1호선·KTX에는 새 브랜드색을 만들지 않고 중립 route-mark와 텍스트로 구분합니다.
- 표에는 caption과 `th scope`를 붙입니다. 빠듯함·막차·운행 종료는 텍스트로 알리고 `role="status"`를 쓰며, 깜빡임은 금지합니다.
- 모바일(≤480px)에서는 표를 세로 타임라인 카드(`<ol>`)로 바꿉니다. 가로 스크롤은 `.table-scroll` 안에서만 허용하고, 터치 타깃은 44px입니다.
- **루트 간 "추천" 순위는 E단계 전까지 두지 않습니다.** 목적지마다 루트별 도착 시각을 나란히 보여 줍니다. 계산할 수 없는 루트는 숨기지 않고 "비교에서 제외" 영역에 이유 코드와 함께 둡니다.
- `Cache-Control: no-cache`를 붙입니다. 자동 갱신은 두지 않고 서버 렌더 + [새로고침]으로 갑니다. 나중에 넣게 되면 고정 컨테이너 + `innerHTML`로 하고, `POLL_SURFACES`에 등록합니다.

### 7.2 레이아웃

```
[상태 줄] 9/29(화) · 버스 평일표 · 동해선 평일표(사유) · 18:02 기준 · 실시간 18:01 수집 [새로고침]
          (해당 시) 공휴일 캐시 누락 / 시간표 수집일 경과·미상 / 동해선 편성 미확인 / 심야: 전날 운행분 표시
[공지 영역: surface busan]
어디로? [부산역][남포][서면][부전][노포][해운대(신해운대역)][송정][센텀·벡스코]   ← B: 앵커 / F: ?dest=
■ 루트 1 부산역·남포·서면·부전 — 513 → 울산역 → KTX → 1호선
  실시간 표: UNIST 도착(N분 후) | 울산역 약(범위) | KTX | 부산역 | 남포 | 서면 | 부전 (막차 후 "1호선 운행 종료")
  (실시간 없음 + B-D10 승인) 참고 예측 3편: 덕하 17:20 출발 → UNIST 약 18:35(빠르면 18:24) → …  [참고 · 2026년 4~6월 기록]
  (실시간 없음 + B-D10 거부) 덕하 출발 17:20 · 18:40 · 19:10 [UNIST 통과 시각 아님] · "울산역 도착 예측은 이력 수집 후 제공"
  ▸ 이 루트의 시간표: 513 덕하 출발(기점 라벨) / (B-D10) 울산역 도착 참고표 / KTX 울산→부산 / 1호선 부산역 운행시간·소요
  ▸ 부전은 동해선 루트가 요금이 쌀 수 있음 → #route-donghae
■ 루트 2 노포 — 743·753 → 좋은삼정병원앞(같은 정류장) → 1224
  실시간(좋은삼정): 753 N분 후 · 1224 M분 후 → 환승 대기 약 K분 (또는 빠듯함 + 다음 1224)
  시간표: 17:40 [753] UNIST → 좋은삼정 약 18:10(참고) → 1224 농소 17:35·17:50 출발편 [좋은삼정 통과 시각 표본 부족]
  ▸ 이 루트의 시간표: 743·753 UNIST 출발 / 1224 농소 출발 / 1224 노포 출발(귀가: 울산대·신복교차로 입구 환승) / 1호선 노포 운행시간
■ 루트 3 신해운대·송정(+센텀·벡스코·부전) — 버스 → 태화강역 → 동해선
  표: 버스 | UNIST 출발 | 태화강역 약(늦으면) | 동해선 | 송정 | 신해운대 | ▸ 센텀·벡스코·부전
  1115는 "태화강역광장 하차(도보 약 8분)"
  오늘 신해운대로 가는 마지막 연결: UNIST 21:50 [743] 빠듯함 / 21:40 [713] (텍스트)
  ▸ 이 루트의 시간표: 버스 4개 노선 UNIST 출발 / 동해선 태화강 출발(평일·휴일, 도착역별) / 일반열차 태화강→부전
[출처] 버스: 울산 BIS(수집 MM-DD) · 열차·동해선·1호선: TAGO(갱신 MM-DD HH:MM)
       · 소요: 2026-04~06 통과기록 중앙값·p10~p90(참고값) · 도보·환승 여유: 가정값
```

- 전체 시간표 `<details>`는 `busno._times_to_hour_rows`를 공용 헬퍼(`domain/timetable_view.hour_rows`, timetable-ux가 계획한 경로)로 추출해서 씁니다. 형식은 "HH | MM MM"입니다.
- 막차 역산은 schedule 구간과, `valid_until`·`review_by` 이내 reference 구간을 대상으로 합니다. 규칙 U에서 탑승 전 예측이 없는 루트는 대상에서 뺍니다. 남은 시간이 90분 이내면 강조합니다.
- 상태 매트릭스 키(`busan.state.*`)는 다음과 같습니다: 첫차 전 / 오늘 연결 끝(내일 첫 연결) / 시간표 없음 / 수집일 경과·미상 / 철도 suspect / 토요일 휴일표 대체 / 공휴일 / 동해선 편성 미확인 / 도착 캐시 오래됨 / 1224 파일 없음 / 개편 후 수집 중 / 오래된 참고값 / 1호선 운행 종료 / 울산역 예측 준비 중 / 표본 부족.

---

## 8. KTX/SRT 확장 지점

- 모델은 "KTX(옛 SRT 계통 포함)" 하나입니다. 등급은 API가 주는 자유 문자열(예: `KTX`, `KTX-산천(A-type)`)을 그대로 쓰고, 등급으로 분기하지 않습니다.
- 새 열차 구간은 두 가지를 추가하면 켜집니다. 수집, 급감 방어, `suspect` 표시는 기존 경로가 처리합니다.
  - `RAIL_PAIRS`에 `(출발, 도착)` 한 줄. 필요하면 `RAIL_STATIONS`·`RAIL_STOP_CANDIDATES`도 추가합니다.
  - `BUSAN_JOURNEYS`에 rail `Leg` 한 줄
- 데이터가 없으면 `reason="rail_pending"`으로 "열차 시간표 준비 중 · 울산역 도착까지만 안내"를 표시합니다. **"운행 없음"으로 표시하지 않습니다.**
- 공급자를 바꾸는 지점은 `fetch_trains(dep, arr, day) -> list[Train]`입니다. 코레일 열차운행정보(data.go.kr 15125762)나 관리자 수동 JSON을 끼울 수 있습니다. 활용신청과 필드는 미확인입니다.
- 외부 예매 링크('코레일톡/코레일+')에는 외부 링크 표시를 붙이고, URL은 constants에 둡니다.

---

## 9. 파일 변경 목록

| 파일 | 변경 | PR |
|---|---|---|
| `bushexa/services/notices.py` | `SURFACES`/`ENDPOINT_SURFACES`에 `busan`, `"busan.busan_page": "busan"` | A0 |
| `bushexa/data/constants.py` | `METRO_DAY_OVERRIDES` | A0 |
| `bushexa/data/constants.py` | `Leg`, `SEGMENT_REFERENCE`(재계산값), `ROUTE_CHANGE_EPOCHS`, 이름 있는 역 상수, 환승 여유, 임계값. v1 상수 이관 | A1 |
| `bushexa/data/constants.py` | `METRO_QUERIES` 추가, `METRO1_RUN_MIN`, `BUSAN_DESTINATIONS`, `BUSAN_JOURNEYS` | B |
| `bushexa/data/constants.py` | `BUSAN_EXTRA_*`, `STOP_IDS` | C |
| `bushexa/services/rail_timetable.py` | `metro_day_type(d, holidays, *, line, overrides)`로 확장. 노선별 토요일 대체. 확인 여부 반환 | A0·B |
| `bushexa/domain/journey_time.py` (신규) | §4.1 | A1 |
| `bushexa/domain/busan.py` | D-2~D-10 수정, 목적지 열 확장, 루트 2, 막차 역산, 전체 시간표 뷰모델, 이유 코드. 문장은 만들지 않습니다. 새 필드에는 기본값을 둡니다 | A1·B·C |
| `bushexa/domain/seoul.py` | 513→울산역 공용 함수 사용 | A1 |
| `bushexa/domain/timetable_view.py` (신규, timetable-ux 경로) | `hour_rows`, `origin_window` | B |
| `bushexa/web/routes/busan.py` | `fetched_at`·게이트 값 주입, 서비스일 두 날짜 조회, 역 상수로 조회(위치 인덱스 제거), 수집일·공휴일 커버리지·편성 확인 여부 주입. 루트 2(C)에서는 좋은삼정 조회와 1224 provider 추가 | A1·A2·B·C |
| `bushexa/crawler/timetable_crawl.py` | `_meta.json` 기록, 급감 방어 | A2 |
| `bushexa/crawler/timetable_crawl.py`, `api_clients/ulsan_bis.py` | `routes`·`out_dir` 인자화, `ROUTENAME` 검증 | C |
| `bushexa/data/timetable.py` 또는 `services/timetable_meta.py` | `_meta.json` 읽기(수집일) | A2 |
| `bushexa/services/holiday_service.py` | 읽기 전용 `holiday_cache_covers(data_dir, d) -> bool`(캐시 월 키 확인) | A2 |
| `bushexa/services/holiday_service.py` | `holiday_set_for_range` | E |
| `bushexa/services/transit_timetable.py` (신규) | `transit_bus_dir()`, 1224 로더(요청 요일 그대로), 수집일 | C |
| `bushexa/crawler/cache_refresh.py`, `bushexa/cli.py` | `refresh_transit_timetables` 격리 호출, CLI 옵션 | C |
| `bushexa/crawler/cache_refresh.py` | 구간 통계 산출 단계(실패 격리) | E |
| `bushexa/crawler/arrival_poller.py`, `crawler/daemon.py` | 추가 폴링 목록, 추가 추적 정류장 | C |
| `bushexa/web/templates/busan.html`, `macros/_journey.html` (신규), `static/css/busan.css` | §7 | A1·B·C |
| `bushexa/web/i18n.py`, `bushexa/data/stop_names.seed.json` | `busan.*`, `busan.dest.*`, `busan.state.*`, `busan.reason.*`, `place.*`(ko·en), 좋은삼정병원앞 로마자 초안 | A1·B·C |
| `bushexa/domain/travel_time.py` (신규) | 구간 통계 순수 함수(60분 간격 운행 분리, UNIST 클러스터 232·234·231, 기점 구간은 "시간표 발차 → 통과") | E |
| `bushexa/db/repo.py` | `passages(route_ids, stop_ids, since)` 읽기 메서드 | E |
| `.gitignore`, `services/backup.py` | `data/unist_estimates.json` 추가, 백업 제외 확인 | E |
| `data/timetable/*.json`, `data/timetable/_meta.json` | BIS 재크롤 반영 | P0·A2 |
| `data/transit/bus/1224.json`, `_meta.json` | 최초 수집본 | C |

**건드리지 않을 것:** `ROUTEID`, `SERACH_STOPS`, `get_busroute_info`, `info.html`

---

## 10. 단계별 작업 (PR 단위)

작업 위치는 새 worktree `../bushexa-busan-v2`(브랜치 예: `feat/busan-v2`)입니다. 기반 커밋은 **B-D6에서 오너가 정한 동기화된 master** 하나로 통일합니다. 커밋할 때는 경로를 지정해 스테이징하고, `git add -A`는 쓰지 않습니다.

### 10.1 P0 확인 체크리스트 (오너·운영 접근 필요 항목 포함)

| # | 항목 | 기한 | 완료 기준 |
|---|---|---|---|
| ① | 운영 `data/timetable/*.json` **내용**을 BIS와 대조합니다(mtime 금지). 로컬은 `crawl_all_timetables` 재크롤 diff를 검토한 뒤 커밋합니다. 대상은 513 전 요일, 753 평일, 713 토, 1115 전 요일, 743 주말입니다(BIS가 개편표인지 확인) | PR-A1 전 | 확인 메모 + 시간표 커밋 |
| ② | **10/5(월) 동해선 편성**을 코레일톡이나 역 게시 시간표로 확인합니다. 결과를 `METRO_DAY_OVERRIDES`의 `confirmed`에 반영합니다 | **10/4까지** | 오버라이드 확정 또는 삭제 |
| ③ | API 일일 한도(TAGO 버스위치·열차·지하철, 울산 BIS)를 확인하고 `api-usage.md` §4에 기록합니다 | PR-C 전 | 문서 반영 |
| ④ | 운영 `bus_timelog`의 보존 기간과 구간별 n을 서버 스냅샷(`data/debug/`)으로 집계합니다 | PR-E 전 | go/no-go 메모 |
| ⑤ | (선택, B-D14) 1224 좋은삼정 통과 표본을 수집합니다. 평일 3일 + 주말 2일, 시간대 칸 n≥4가 목표입니다 | PR-C 전 권장 | `SEGMENT_REFERENCE` 1224 항목 |
| ⑥ | 역 ID와 역명을 대조합니다. 2026-09-29 재호출로 확인한 내용을 테스트 픽스처(키 제거)로 고정합니다 | PR-B | 픽스처 커밋 |
| ⑦ | 브랜치를 정리합니다. 로컬 master를 origin/master와 동기화하고 push합니다(오너). `feat/nopo-1224-arrival` worktree는 PR-C용으로 재사용할지 폐기할지 정합니다(B-D13) | PR-A0 전 | 기반 커밋 확정 |
| ⑧ | 743 10/3 개편 이후 경유 정류장을 다시 조회합니다(좋은삼정·태화강역) | 10/3 이후(P2.5) | 참고값 유지·만료 결정 |

### 10.2 PR

| PR | 내용 | 선행 | 완료 기준 |
|---|---|---|---|
| **PR-A0 긴급** (10/3 전 권장) | ① 공지 surface `busan`(+ 743·1115 10/3 개편 공지, 동해선 편성 공지 데이터). ② `METRO_DAY_OVERRIDES` 메커니즘, 10/5 항목(`confirmed=False`), 상태 줄 "편성 미확인" | ⑦ | 10/5에 v1 페이지가 평일 동해선표(또는 미확인 표시)를 씁니다. 전체 테스트 green |
| **PR-A1 정확성** | `TimeToken`·`journey_time`. D-2(`fetched_at` 기준, 동적 게이트, 편향 보정). D-7(서비스일 두 날짜 조회). D-3(`SEGMENT_REFERENCE` 7구간, lo·hi, 재계산값). D-4(날짜 포함 표시). D-5(743 `valid_until`, 1115 가는 방향 `unaffected_reason`). D-6(범위·n·기간 라벨, 출처 푸터). D-8(역 상수). 513 공용 함수(`/seoul` 공유, 기대값 갱신). 규칙 U 구현(B-D10 결과를 설정 플래그 `BUSAN_ALLOW_REFERENCE_PASSING`로 반영) | P0-① 권장 | 틀린 연결 표시 제거. `/seoul`과 `/busan` parity. 전체 테스트 green |
| **PR-A2 데이터 신선도** | `data/timetable/_meta.json`(크롤러 기록, 읽기 헬퍼). 급감 방어. `holiday_cache_covers`. 상태 줄(수집일 경과·미상, 공휴일 커버리지) | A1 | mtime 의존 제거. 급감·부분 요일 비어 있음 테스트 |
| **PR-B 목적지 완성(루트 1·3)** | 동해선 송정·신해운대·센텀. 1호선 부산역 D·U, 노포 U 시간표 수집과 고정 소요·`metro_closed`. 노선별 토요일 대체. 목적지 앵커 칩(해운대(신해운대역) 각주). 루트별 전체 시간표 `<details>`. (B-D10 승인 시) 울산역 도착 참고표. 막차 역산. 모바일 카드 | A1, P0-⑥ | 루트 1·3 목적지 충족, "루트별 시간표" 충족 |
| **PR-C 루트 2** | 1224 크롤(인자화) → `data/transit/bus/1224.json`. 좋은삼정 폴링. 743·753 추가 추적 정류장. live 환승 판정. 1224 시간표(가는 길·귀가). (P0-⑤가 있으면) 참고 연결표. 1호선 노포 연결 | A1·B, P0-③, B-D2, B-D13 | "준비 중" 배너 제거, 노포 도착 표시(실시간·표본 충족 시) |
| **P2.5 개편 재확인** (10/3 이후) | P0-⑧. 743 참고값을 재측정할지 정합니다(B-D8). `SEGMENT_REFERENCE`·에포크 갱신 | 2026-10-03 | 743 `ref_expired` 해소 또는 유지 결정 |
| **PR-E 이력 예측** (timetable-ux E2와 합류) | `travel_time.py`, `repo.passages`, `holiday_set_for_range`, 야간 산출, `unist_estimates.json`, reference → history 승격. 이때부터 루트 간 추천을 둡니다 | P0-④ go, 표본 약 30일 | 참고값이 게이트 통과값으로 대체됨 |
| **PR-F 확장(선택)** | `?dest=` 목적지 뷰와 추천·제외 영역, 귀가 방향 전체, 관리자 편집용 `rail_day_overrides.json`, 정류장별 조회 시각 payload | 오너 결정 | — |

**병합 순서**

1. master 동기화·push(공지 포함, 10/3 전)
2. PR-A0 → PR-A1 → PR-A2 → PR-B → PR-C
3. `feat/route-map-geo-ab` rebase
4. `/info` 교차 링크

---

## 11. 테스트

모든 테스트에 자연어 의도 docstring을 붙이고, 네트워크를 쓰지 않으며(`no_network`), `FakeClock`을 씁니다. 버스 시간표 픽스처는 **BIS 재크롤본**(스크래치 `tt_live/`)으로 만듭니다.

| 파일 | 내용 |
|---|---|
| `tests/domain/test_journey_time.py` | 토큰 생성. 대역 경계(07:00·09:00). 탑승 후 구간에서 n<4 칸을 요일 전체로 올리고 `band_rollup` 표시. **탑승 전 예측에서 n<4 칸이면 토큰 없음**(513·1224 같은 규칙). `valid_until`·`review_by` 경계(10/2 23:59 대 10/3 00:00 KST). `service_date` |
| `tests/domain/test_busan.py` | ① `fetched_at`이 90초 전이면 UNIST 시각 = `fetched_at` + ETA인지 ② 게이트 초과 시 live 0행 + `live_stale` ③ 폴링 주기 300초 설정이면 게이트가 630초 이상으로 늘어나는지 ④ 753 평일 17:40이 16~19시 p90으로 판정되는지 ⑤ 여유 3분 미만이면 '빠듯함'과 다음 편 대안(743 21:50 → 23:00, 여유 1.2분) ⑥ 동해선 23:00 → 신해운대 23:51, 부전 **내일** 00:16 ⑦ **토요일 00:30 FakeClock → "첫차 전", 월요일 02:50 → "첫차 전"**, 9/30 00:30에 9/29 항목의 00:43 KTX가 보이는지 ⑧ 513 덕하·1224 농소 `origin` 토큰이 연결 입력·순위·카운트다운에 쓰이지 않는지(O-1 회귀) ⑨ 규칙 U: B-D10 플래그가 꺼져 있으면 513 참고 예측이 없고, 켜져 있으면 칸 n≥4에서만 있는지. 1224(n=3)는 두 경우 모두 없는지 ⑩ 10/3 KST 이후 743 가는 방향 참고값은 `ref_expired`, 출발 행은 유지. 1115 가는 방향은 유지 ⑪ 좋은삼정 live에 743과 1224가 함께 있으면 환승 대기 계산(앞 차량 hi에 사이클 편향), 1224만 있으면 "연결 계산 불가" ⑫ 1224 파일이 없으면 `tt_missing`이고 "막차 이후"가 아닌지 ⑬ metro 한 역이 없어도 다른 목적지는 계속 보이는지 ⑭ KTX 부산 00:05 도착이면 서면·부전 `metro_closed`, 남포는 00:12:30 U로 00:16. 1224 노포 23:29 도착이면 서면 `metro_closed` ⑮ 동해선 매칭 소요가 기대값 ±10분 안인지 ⑯ 도착 필터가 레지스트리 route_id 집합으로 동작하는지 ⑰ **`METRO_QUERIES` 순서를 섞어도 결과가 같은지** |
| `tests/domain/test_seoul.py` | 기대값 갱신(ETA 기준 변경 반영). **parity**: 같은 도착 캐시·`fetched_at`을 넣으면 `/busan` 루트 1과 `/seoul`의 UNIST 통과·울산역 도착이 같은지 |
| `tests/services/test_rail_timetable.py` | 추가 역 쿼리 병합. **노선별** 토요일 대체(동해선은 02 → 03, 1호선은 02 그대로). `METRO_DAY_OVERRIDES` 적용과 `confirmed` 전달. **공휴일 `{'20261005'}`이면 버스 weekday 2, 동해선은 덮어쓰기가 있으면 01, 없으면 03 + "편성 미확인"** |
| `tests/services/test_holiday_service.py` | `holiday_cache_covers`: 캐시 월 있음·없음 |
| `tests/services/test_transit_timetable.py` | env override(`tmp_path`). 특별편 지정일에도 요청 요일 그대로 읽는지. 캐시 리셋 훅 |
| `tests/crawler/test_timetable_crawl.py` | 인자화한 기본 동작 불변. 1224 픽스처(키 제거)로 dir 1 = 노포. `ROUTENAME` 불일치·빈 결과면 저장 안 함. **한 요일만 빈 경우와 50% 미만 급감이면 그 노선 쓰기 보류.** `_meta.json` 기록 |
| `tests/crawler/test_arrival_poller.py` | **기존 기대값 `client.calls == list(SERACH_STOPS)`(:51-56, :72, :85)를 `SERACH_STOPS + BUSAN_EXTRA_ARRIVAL_STOPS`(순서 보존)로 갱신.** `/stops` 드롭다운 불변 |
| `tests/crawler/test_daemon_tracked.py` (신규, `test_daemon.py`는 저장소에 없음) | 743·753 tracked에 `193030929` 포함. 1224는 폴링 노선에 없음. `/running` 열 불변 |
| `tests/unit/test_constants.py` | `len(ROUTEID)==10`. 1224 ∉ ROUTEID. `BUSAN_EXTRA_ARRIVAL_STOPS ∩ SERACH_STOPS = ∅`. `BUSAN_DESTINATIONS`·`BUSAN_JOURNEYS` 참조 무결성. `METRO_QUERIES` ⊆ 역 상수. **`SEGMENT_REFERENCE`의 from·to ∈ `ROUTEID[rid][3] ∪ BUSAN_EXTRA_TRACKED_STOPS[rid] ∪ BUSAN_EXTRA_ROUTES[rid][3]`.** 모든 항목에 `source`·`period`·`review_by`. `ROUTE_CHANGE_EPOCHS` 노선 항목에 `valid_until` 또는 `unaffected_reason`. **`METRO1_RUN_MIN` 일관성**: 노포>X − 노포>Y ≈ Y>X(±1분) |
| `tests/web/test_busan_route.py`, `test_routes_smoke.py`, `test_i18n.py` | 200 응답. 캐시 예외 시 error-banner + 200. `?lang=en`에서 `busan.`·`place.` 키가 노출되지 않는지. 출처 푸터에 수집일. `<details>` 시간표. 새 키의 ko·en 존재. surface `busan` 공지 렌더 |
| 실행 | `uv run --frozen python -m pytest -q` 전체. 착수 시 기준값을 다시 잽니다(통합안 보고값 697 passed, 1 skipped). `LANG=C.UTF-8`과 `en_US.UTF-8` 둘 다. 브라우저로 `/busan`, `?lang=en`을 360·480·720px에서 확인 |

---

## 12. 문서 갱신 (같은 커밋)

- `architecture.md`
  - §3 domain: `journey_time`, `travel_time`
  - §4.2 파일 표: `data/timetable/_meta.json`, `data/transit/bus/`, 구간 통계 절
  - §7 env: `BUSHEXA_TRANSIT_DIR`
  - §8: ADR-015 초안(부산 레지스트리 분리, TimeToken basis/source, 규칙 U), ADR-014 현행성 정정
- `api-usage.md`
  - §1.1 폴링 정류장 17 → 18
  - §3 호출량: 울산 +2.9k/일, 지하철 쿼리 +6(하루 약 18건), 1224 크롤 약 9건
  - §4 일일 한도
  - 역 ID 표(확인일)
- `change-playbooks.md`
  - "부산 루트 데이터 갱신" 절: 1224 재크롤, `METRO_QUERIES`·`RAIL_PAIRS` 추가, `SEGMENT_REFERENCE` 재산출과 `period`·`review_by`·`valid_until`, `METRO_DAY_OVERRIDES` 등록 절차(명절·대체공휴일마다), 동해선 개정·북울산 연장 대응
  - 공지 surface 추가 절차
- `ui-design.md`: busan 템플릿·매크로, source별 표기 규칙, 중립 route-mark, `| stop` 대 `place.*` 구분
- `pitfalls.md`
  - "부산 노선은 ROUTEID에 넣지 않는다"
  - "ETA는 fetched_at 기준, fetched_at은 사이클 시작"
  - "특별편 평일 폴백은 전용 디렉터리로 피한다"
  - "자주 다니는 노선에 편별 시각 매칭 금지"
  - "시간표 신선도에 mtime을 쓰지 않는다"
  - "00~03시는 서비스일과 달력일을 둘 다 본다"
- `README.md` 페이지 표, `data/changelog.json`(맨 뒤에 추가, 파일 끝 개행 없음), 각 문서의 `last_verified`

---

## 13. 위험과 미확인 사항

| # | 항목 | 대응 |
|---|---|---|
| R1 | 운영 이력 표본이 확인되지 않았습니다(지정 DB 16행) | reference 라벨(기간·n). P0-④, E단계 |
| R2 | 버스 시간표가 낡았습니다. 로컬 6월판이 4~6월 실제 운행과도 맞지 않습니다(513 22%). 운영 파일 상태는 미확인입니다 | P0-①, `_meta.json` 수집일, 경과·미상 배너 |
| R3 | 743 10/3 개편(좋은삼정·태화강 경유 여부, 소요). 743 주말 BIS 현행표가 4~6월과 다릅니다 | `valid_until`, P2.5, 공지 |
| R4 | 1224 주간 소요를 측정하지 못했습니다(야간 n=1~3). 노포 도착 전에 TAGO 위치가 사라집니다 | 규칙 U로 live 전용. P0-⑤(B-D14) |
| R5 | 동해선 공식 시간표 대조를 끝내지 못했습니다. 10/5 편성, 북울산 연장(2026-12 예정)이 모두 미확인입니다 | P0-②, `METRO_DAY_OVERRIDES`, 공지 |
| R6 | 1호선 역간 소요는 TAGO 시간표에서 구한 값이고, 부산교통공사 공식 자료로 대조하지 않았습니다. 부산역·노포역 환승 도보는 미확인입니다 | "약" 표기, 가정값 라벨 |
| R7 | 도보·환승 여유는 모두 가정값입니다(울산역 10, 부산역 8, 태화강 5/8, 좋은삼정 2, 노포 5) | assumed 라벨, 현장 확인 |
| R8 | 도착 캐시 `[]`의 뜻이 모호합니다(X1) | "정보 없음" 문구 + 수집 시각. X1 수정을 먼저 하도록 권장 |
| R9 | API 일일 한도가 기록되어 있지 않습니다 | P0-③ 전에는 PR-C 폴링 보류 |
| R10 | 1224 요금 차액, 입석 제한, 울산↔부산 환승할인에 공식 출처가 없습니다 | 표시하지 않음(B-D7) |
| R11 | 브랜치: 로컬 master는 7커밋 앞, 3커밋 뒤입니다. geo-ab는 옛 master 기반입니다. `feat/nopo-1224-arrival` worktree가 PR-C와 겹칩니다 | B-D6, B-D13, `info.html` 미수정 |
| R12 | 참고 예측의 시간대 p90 폭이 큽니다. 513 평일 16–19시 UNIST 통과 범위는 −11/+19분입니다 | "빠르면 HH:MM" 표시, 루트 간 추천 제외 |
| R13 | "해운대"는 신해운대역 도착까지만 안내합니다. 해수욕장까지의 거리·연계는 미확인입니다 | 라벨 "해운대(신해운대역)" + "역 도착까지만 안내" 각주 |
| R14 | 참고 백분위는 계산 방식(inclusive 대 index)에 따라 최대 약 2분 차이가 납니다. 743 21:50 연결이 바로 그 경계에 있습니다 | 방식을 constants 주석에 고정하고, 빠듯함 배지로 전달 |

---

## 14. 소유자 결정 필요

| ID | 질문 | 권장 |
|---|---|---|
| B-D1 | 탑승 후 구간 참고값(reference)을 도착 추정·연결 계산에 쓸지 | 씁니다(기간·n 라벨). 루트 간 순위·추천은 E단계까지 두지 않습니다 |
| **B-D10** | **탑승 전 통과 예측에 "참고 예측" 등급(레거시 기록, 칸 n≥4, 기간 라벨, 카운트다운·추천 제외)을 허용할지.** 허용하면 PR-B에서 루트 1 울산역 도착이 채워집니다. 거부하면 PR-E까지 요구 미충족입니다 | 허용. 513은 모든 칸이 n≥5라 적용됩니다. 1224는 n=3이라 자동으로 제외됩니다 |
| B-D11 | 규칙 U의 예외 여부. 1224(n=3)만 예외로 허용할지 | 예외 없음. P0-⑤로 표본을 채웁니다 |
| B-D2 | 좋은삼정 폴링(+2.9k/일), 743·753 통과 기록(호출 0), 1224 GPS | 한도를 확인한 뒤 앞의 두 가지만. 1224 GPS는 보류 |
| B-D3 | 1224 저장 위치 | `data/transit/bus/`, git 추적 |
| B-D4 | 목적지 ↔ 루트 묶음과 1호선 계산 범위 | 복수 루트 허용. 1호선은 PR-B에서 **역 시간표 수집 + 고정 소요**(하루 약 9건 추가) |
| B-D5 | 영문 표기: 울산역(D15), 좋은삼정병원앞, `place.*` 분리 | D15 먼저. 역·지명은 `t()`, 버스 정류소는 `| stop` |
| B-D6 | master 동기화·push와 병합 순서, 기반 커밋 | master 동기화·push(10/3 전) → A0 → A1 → A2 → B → C → geo-ab rebase |
| B-D7 | 요금·입석·환승할인 문구 | 공식 출처 전까지 노출하지 않음 |
| B-D8 | 743 개편 뒤 임시 실측으로 참고값을 갱신할지 | 1주 이상 샘플링해서 칸 n≥4일 때만 갱신 |
| B-D9 | 임계값: 신선도 게이트 하한 120초(동적), 시간표 경과 120일, 빠듯함 3분, 막차 경고 90분, 참고값 `review_by` 2026-12-31 | 제안값 그대로 |
| B-D12 | 10/5 동해선 편성 덮어쓰기. 확인 전 `confirmed=False`로 평일표를 적용할지, 휴일표 + "미확인"으로 둘지 | 평일표 + "편성 미확인" 표시. 근거는 TAGO KTX 10/5 = 평일 집합, rail.blue 평일표입니다. P0-②로 확정합니다 |
| B-D13 | `feat/nopo-1224-arrival` worktree(`edacb33`, 커밋 없음)를 PR-C에 쓸지 폐기할지 | 폐기하고 `feat/busan-v2`에서 진행합니다. 병행 작업이 있다면 알려 주세요 |
| B-D14 | P0-⑤ 1224 표본 수집(며칠 동안 TAGO 방향당 하루 약 +4.8k) | 한도 확인 뒤 평일 3일 + 주말 2일 |
| B-D15 | "해운대" 라벨과 범위 | "해운대(신해운대역)" + 역 도착까지만 안내 |
