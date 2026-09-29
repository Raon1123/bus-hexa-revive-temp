# Bus HeXA 시간표 표출 재설계: 전략과 실행 계획

> **개정 안내 (2026-09-29).** 오너 결정(D1 확정: 기점 출발과 UNIST 경유 시각 분리 · 실시간 우선 · 예측 게이트 30일/같은 요일군 4건, 기한형 공지 도입, 방향 일반화)을 반영한 보완안이 [03-addendum-notices-via-prediction.md](03-addendum-notices-via-prediction.md)에 있습니다. 두 문서가 다르면 **보완안이 우선**합니다. 특히 P0-9(공지 핫픽스)·P4-3은 N0로, 6.5의 513 게이트(n≥30·IQR≤15)와 6.6의 `timetable_offsets.json`은 보완안 §2로 대체됐습니다.

- 대상 화면: `/timetable`(전체 시간표), `/busno`(버스번호별 시간표). 방향·시각 규칙을 함께 쓰는 인접 화면은 `/board`, `/lite`, `/unist`입니다.
- 근거 자료: Phase 1 UX 감사(6개 관점, 적대적 검증 포함) [01-audit-findings.md](01-audit-findings.md), 세 전략안(A 방향 우선 / B 지금 우선 / C 위험 우선)과 세 심사관(사용자 가치 / 엔지니어링 / 신뢰·접근성)의 평가, 그리고 1차 계획에 대한 비평(blocker 3·major 19·minor 다수). 비평에서 다툼이 된 사실은 2026-09-29에 저장소에서 다시 확인했습니다.
- 기준 데이터: 저장소 `data/timetable/*.json`(2026-06-02 수집본). 예시 시각은 모두 이 실데이터로 다시 계산했습니다. 테스트 기대값은 E-13(테스트 기대값은 구현과 독립된 출처에서 가져온다, `docs/refactor/auditor/execution-audit-criteria.md:39`) 규율에 따라 hand-built fixture로 따로 정합니다. 실데이터 수치(예: 513 평일 28편)는 테스트 기대값으로 쓰지 않습니다.
- 표기 규칙: **[가정]** = 저장소로 확인하지 못한 전제. **[추론]** = 코드·데이터에서 유도했지만 실측하지 않은 것. **[결정 Dn]** = 오너 결정이 필요한 항목(11장).
- 시간 고정 규칙(모든 AC에 적용): 라우트는 `KSTClock().now()` = `datetime.now(tz=KST)`를 씁니다(`bushexa/time_utils.py:26-27`). 그런데 `freeze_time("2026-09-29 17:47")`는 이 값을 UTC로 해석하므로, KST로는 **2026-09-30 02:47(수)**이 됩니다. 이 문서에서 "freeze 17:47"이라고 쓴 곳은 모두 P0-1a의 `freeze_kst("2026-09-29T17:47")` 헬퍼를 뜻합니다.

---

## 0. 요약

### 문제 정의

시간표 화면의 가장 큰 결함은 레이아웃보다 **시각이 무엇을 뜻하는지가 틀려 있다**는 점입니다.

1. `/timetable`은 노선마다 `deps[0]`만 씁니다(`bushexa/domain/unist_timetable.py:82`). 그래서 513의 **덕하 기점 출발 시각**(평일 28편)이 라벨 없이 UNIST 출발 시각 사이에 섞여 나옵니다. 513 삼남 기점 방향은 아예 빠집니다(IA-1/DS-1 critical, TF-1 high).
2. `/busno`에서는 버스 칩을 누르기만 해도 Python repr이 섞인 경고가 뜹니다(`busno.html:18`, IA-4/DS-10). 출발지 선택은 JS가 있어야만 동작합니다(`busno.html:41` `onchange`, A11Y-4 WCAG 3.2.2).
3. `?day`가 붙기만 해도 특별편이 조용히 꺼집니다. 어떤 편성이 적용 중인지도 화면 어디에도 나오지 않습니다(`routes/unist_timetable.py:48-52`, `routes/busno.py:46-51`, DS-4/IA-6/TF-3).
4. '지금'을 알려 주는 표시가 없습니다. 하루치 시간표 높이는 360/375px에서 2548px(15px 스크롤바를 포함한 측정)로 약 3.4~3.8화면이고, 17시 행은 y≈1753px에 있습니다(IA-3/MR-1). 스크롤바를 숨긴 조건의 360/375 기준선은 P0-0b에서 다시 잽니다.
5. 방향과 행선지를 보여 주지 않습니다(IA-2/DS-3/CI-1). i18n이 없어서 EN 모드에서도 본문이 한국어입니다(A11Y-2/CI-3). 713·1115 배지는 대비가 AA에 못 미칩니다(4.12, 2.70; A11Y-1).
6. 날짜가 박힌 공지가 곧 낡습니다. '10월 3일부터 743번 범서중 경유'가 `i18n.py:70`, `constants.py:68`, `info.html:50,61`에 하드코딩돼 있는데, 오늘(9/29) 기준으로 4일 뒤면 과거 시점이 됩니다. 반면 `route_diagram.py:45`의 `VIA_743_BEOMSEO_FROM`에는 이미 날짜 게이트가 있어서 표면마다 문구가 어긋납니다(M-23).

### 핵심 전략

> **시간표의 1차 축을 'UNIST에서 출발 / UNIST로 도착'이라는 방향으로 바꾸고, 모든 시각이 '어느 정류장 기준인지(basis)'와 '어느 편성인지(source)'를 스스로 밝히게 합니다. 이 의미 모델을 테스트로 고정한 뒤에만 '지금·다음 출발' 같은 편의 기능을 얹습니다.**

뼈대는 전략 A(방향 우선)이고, 여기에 세 가지를 접목했습니다.

- 전략 C의 단계 규율: strict xfail 래칫, 링크 정규화 완화책, 추가형(additive) 변경, 결정 게이트.
- 전략 B의 지금·신선도 UX: `origin_window`, 'HH:MM 기준' 표기, Cache-Control, aria-live 금지.
- 심사관 must-fix 전부: 주요 경유 거점 기반 목적지 색인, 첫 뷰포트 px 예산, WCAG 2.4.11 scroll-padding, 브라우저 테스트 인프라 현실화 등.

A 원안의 **페이지 통합(`/busno` 흡수)은 채택하지 않았습니다.** 엔지니어링 심사에서 가장 큰 위험 요인으로 꼽혔기 때문입니다. 대신 **2단 구조**(방향 우선 개요 `/timetable` + 노선 상세 `/busno`)로 두고, 통합 여부는 D14로 남겼습니다.

### 단계 개요

| Phase | 이름 | 사용자 가시 변화 | 결정 의존 | 크기 |
|---|---|---|---|---|
| 0 | 안전망과 결정 없는 신뢰 핫픽스 | 칩 경고 0, select→링크, 513 각주, 오늘 칩 특별편 유지, 언어 전환 쿼리 보존, 모바일 메뉴 닫기, **743 공지 시효 핫픽스** | 없음(D13은 선택). 기존 제목 텍스트는 글자 그대로 유지 | L(작업 13개 = PR 12 + WIP 정리 1, S~M 혼재, 1인 약 2주) |
| 1 | 의미 모델과 i18n 기반 | 상태 줄(편성 사유), 표 시맨틱, EN 완성, 노선 배지 대비, 데이터 출처 푸터 | D2, D4, D12, D15 | L |
| 2 | 방향 우선 시간표와 인접 화면 정합 | 513 분리(두 방향), UNIST 도착 방향, 목적지 필터, `/busno` 방향 칩·요약·공백 행, /board·/lite·/unist 513 표기 통일 | D3, D5(P2-6b만), D6, D7, D10 | L |
| 3 | 지금 UX와 모바일 | 다음 출발, `#now`, 지난 시간 접기, sticky 바, 날짜 조회, nav 재편 | D8, D9, D11 + 데이터 신뢰 게이트 | L |
| 4 | 데이터 신뢰 확장 | 513 추정 통과 시각(승인 시), 데이터 공지 구조화, 크롤 이상 탐지 | D1(go/no-go), D12 | M~L |
| 5 | 정리와 계약 갱신 | 레거시 필드 폐기, ADR-015 확정, (선택) 통합/301 | D14 | M |

### 오너 결정이 필요한 핵심 항목

전체 목록과 각 결정이 막는 Phase, 거부했을 때 남는 상태는 11장과 12장에 있습니다.

- **D1** 513 UNIST 통과 시각. 권장: 즉시 (a) 기점 라벨 + 분리, 중기 (c) 로그 산출 → 관리자 승인 게이트.
- **D3** `day`가 오늘 요일코드와 같을 때 특별편을 유지할지, '평시 보기' 경로를 둘지.
- **D4** 노선색 대비 해결 방식. 권장: 팔레트 유지 + route-mark.
- **D5** `/board`·`/lite`에서 513 기점 행을 FIRST/SECOND 순위에서 뺄지. 기점 라벨 표기와 M-1 수정은 D5와 무관하게 P2-6a에서 진행합니다.
- **D6** 'UNIST로 도착' 방향을 `/timetable`에 넣을지.
- **D7** 목적지 거점 칩 목록과 라벨 검증.
- **D11** 3KB 이하 점진 JS 허용 여부.
- **D13** Playwright 도입 여부.

---

## 1. 현황 진단

심각도는 검증자가 **보정한 값**입니다(원래 값 → 보정 값). 반박된 TF-9(캐시 버스팅)는 결함 목록에서 뺐습니다.

### 1.1 정량 기준선

| 지표 | 현재 값 | 출처 |
|---|---|---|
| `/timetable` 평일 격자 | 18행(05–22시), 출발 배지 178개(UNIST 기점 150 + 513 덕하 28), 범례 5 | IA-3·A11Y-6 재계산, 렌더 실측 |
| 주말 배지 | 165개. 한 시 셀 최대 11개(평일은 07시 최대 13개) | A11Y-6 |
| 같은 분 중복 슬롯 | 평일 39, 토·일 42 | IA-10·MR-6 |
| 17시 행(평일) | **배지 10개**(IA-3 원문 9개는 오류). **17:47 기준 지난 편 8개**(원문 7개는 오류). 실데이터: 00-513, 05-753, 10-743, 10-1115, 20-753, 25-713, 30-513, 40-753, 55-713, 55-743 | IA-3 vnote, 2026-09-29 재계산 |
| 모바일 문서 높이 (a) | 360/375px에서 2548px, **15px 스크롤바 포함** 측정 → 2548/740≈3.44, 2548/667≈3.82 → **약 3.4~3.8화면** | MR-1 |
| 모바일 문서 높이 (b) | 414×896에서 **스크롤바 숨김** 측정 2184px → **약 2.4화면** | MR MISSED #5(method) |
| 모바일 기준선 재측정 | 스크롤바 숨김(`scrollbar-width:none`) 조건의 360/375 docH와 17시 행 y는 **아직 측정 전**. S-5·S-12의 기준선은 P0-0b에서 이 조건으로 다시 잰 값으로 바꿉니다 | MR MISSED #5 |
| 17시 행 위치 | y=1753px(375px, 스크롤바 포함 측정), 첫 데이터 행 y=316, 요일 칩 y=173 | MR-1, MR-5 |
| 가로 모드 | 812×375에서 사이드바 240px 상시 노출, docH 1960(5.2화면) | MR-7 |
| 배지 흰 글자 대비 | 513 4.98 / **713 4.12** / 743 4.60 / 753 8.20 / **1115 2.70**. 513과 713 사이 명도비 1.21 | A11Y-1(재계산 일치) |
| 비텍스트 대비 | 칩 테두리 #c5cae9 1.62:1. 제안됐던 포커스 링 #ff9800은 흰 배경 2.16:1(기각). 기존 `/board` 포커스 링(`style.css:783-784`)도 #ff9800 | A11Y-11, A11Y-10, A11Y MISSED #5 |
| 터치 타깃 | 햄버거 19×21, 언어 27×25(간격 4px), 칩 높이 30, select 34(글자 15.2px) | MR-4 |
| 방향 커버리지 | ROUTEID 10개 방향 중 `/timetable`에 5개 표시. 그중 513 덕하발 1개는 기준이 틀리게 표시됨. 513 삼남발과 도착 4방향은 없음 | TF MISSED, C 전략 |
| 페이로드 | `/timetable` HTML 25.7KB(비압축), `/busno` 약 7.3KB. htmx.min.js 48,101B를 모든 셸 페이지가 로드(`_base.html:100`). Pretendard 3종 2.34MB(font-display: swap) | TF-8, TF MISSED |
| 접근성 속성 | 공개 템플릿의 `aria-current` 0, `scope=` 0, `<caption>` 0, 인라인 핸들러 1개(`busno.html:41`) | A11Y-5, A11Y-6, TF-7 |
| 기존 테스트 | phase1 기록의 '7개 파일 43 passed'는 파일 목록이 없어 재현할 수 없음. 2026-09-29 재집계: `tests/domain/{test_unist_timetable,test_busno,test_holiday_and_special_precedence}.py` + `tests/web/{test_unist_timetable_route,test_busno_route,test_routes_smoke,test_board_support}.py` = **31 collected**. 확정 기준선은 P0-0b에서 목록과 함께 기록 | TF-5 vnote, 비평 재집계 |
| 데이터 이상 | 5개 노선 모두 `d['1']==d['2']`(토=일 완전 동일). 1115는 주말 32편이 평일 28편보다 많음 | IA-8, DS-12 |
| 공휴일 캐시 | `data/holiday_cache.json`에 `202609`(9/24–26), `202610`(10/3, **10/5**, 10/9) 두 달만 있음 | DS MISSED #6, 파일 확인 |
| 특별편 데이터 | `data/timetable/special/`가 비어 있음. 특별편 동작은 fixture로만 검증 가능 | 저장소 확인 |
| 날짜 공지 | '10/3부터' 문구가 4곳에 하드코딩됨(`i18n.py:70`, `constants.py:68`, `info.html:50,61`). 날짜 게이트는 `route_diagram.py:45`에만 있음 | TF MISSED #10, 저장소 확인 |

### 1.2 주제별 결함

#### T1. 시각 의미 오류(정확성)

| ID | 보정 심각도 | 내용 | 핵심 근거 |
|---|---|---|---|
| IA-1 / DS-1 | critical / critical | 513 덕하 기점 시각 28편(평일)이 UNIST 출발처럼 섞여 나오고, 삼남 방향은 빠짐 | `domain/unist_timetable.py:82`, `data/timetable.py:104-116`(ROUTEID 삽입 순서), `constants.py:37-40` |
| TF-1 | critical→high | 방향·승차 기준 모델이 없고 dict 삽입 순서에 의존함 | 같음 |
| DS-2 | high→high | `/board`·`/lite`·`/unist`도 513 기점 시각으로 정렬·순위·만료를 처리함 | `domain/board.py:155-166`, `merge_live_rows` `:312-325`, `board_lite.html:21,25` |
| CI-10 | medium | 513 문구가 화면마다 다름: '덕하 출발 예정'(`/board`), 'HH:MM 출발 예정'(`/unist`), 표기 없음(시간표) | `board.py:163`, `unist_board.py:95` |
| DS-11 | medium→low | 승차 정류소가 셋인데 구분 없이 섞임: 196040233 'UNIST (기점)', 196040234 '울산과학기술원 (경유)', 그리고 **196040231 '울산과학기술원정문 (시내)'**. 231은 513(양방향 모두 234 다음)과 713/743/753(233 다음)이 함께 서는 공용 정류장 | `constants.py:38,40,42` 등 ROUTEID stops, STOP_IDS |
| TF-2 | high | 513의 UNIST 통과 시각은 저장소 데이터로 결정론적으로 구할 수 없음. validator가 요일 외 키를 거부하고 `hh≤23`를 강제함 | `data/timetable.py:131-133,143-144` |
| M-1 | (MISSED) | `/unist` 513 via 카드는 기점명 없이 'HH:MM 출발 예정'을 쓰고, `_is_future`가 기점 시각으로 거름. 막 출발해 UNIST로 오는 중인 편이 사라짐 | `unist_board.py:45,89-95` |

참고 수치(로그 재계산): 덕하→UNIST 약 59분, 삼남→UNIST 약 42~45분(`data/logs.tsv`). 이 값은 **phase1 감사 시점 표본 n≈5~6(11~16시에 몰림)**에서 나왔습니다. `data/logs.tsv`는 현재 1,095행이고 계속 늘고 있어 다시 집계할 수 있습니다. 명촌→UNIST 약 78~81분(n=13)은 전략 A의 재계산이라 독립 검증을 거치지 않았습니다. 첨두 시간대 근거로는 부족합니다(IA MISSED #5). 재집계는 P4-0에서 합니다.

#### T2. 방향·명명·과업 적합성

| ID | 보정 | 내용 | 근거 |
|---|---|---|---|
| IA-2 | high | 행선지 대신 노선번호와 기점명만 보여 줌 | `timetable.py:104-116`(terminal 버림), `busno.html:40-45`, `unist_timetable.html:22-26` |
| DS-3 | high | '출발지' 라벨이 모호함. 513 사용자가 울산역으로 가려면 반대쪽 지명인 '덕하'를 골라야 함 | `busno.html:40`, `constants.py:37` |
| CI-1 | high | 같은 513 편을 기점(`/busno`)과 방면(`/board`·`/unist`)이라는 반대 기준으로 부름 | `board_table.html:35` |
| IA-5 | high | 'UNIST로 오는' 과업이 `/timetable` 범위 밖이라 `/busno`에서 노선 3개를 오가야 함 | `unist_timetable.py:82` |
| IA-11 | medium | `/busno` 기본값이 513/덕하(ROUTEID 순서) | `domain/busno.py:99,113` |
| M-5 | (MISSED, medium) | info의 '513번은 앞쪽이 시내, 뒤쪽이 삼남'은 가리키는 대상이 없는 레거시 문구 | `info.html:45-47` |
| M-6 | (MISSED, medium) | `VIA_STOPS`의 키는 **종점**이고 `dep`는 **기점**. dep로 조회하면 반대 방향 경유지가 나옴 | `constants.py:59-` VIA_STOPS |

#### T3. 편성 출처와 상태의 투명성

| ID | 보정 | 내용 | 근거 |
|---|---|---|---|
| DS-4 / IA-6 | high→medium / high→medium | `?day`가 붙기만 해도 특별편이 조용히 꺼지고 편성이 표시되지 않음. '기존 동작 유지'라는 주석으로 보아 의도된 설계 | `routes/unist_timetable.py:48-52`, `routes/busno.py:46-51`, 모든 템플릿 칩에 `day=` |
| TF-3 | high | `timetable_provider_for`가 Callable만 반환해서 edition 정보가 클로저 밖으로 나오지 않음 | `services/board_support.py:103-168` |
| IA-7 / DS-7 / CI-2 | medium / medium / high→medium | '현재 시각: HH:MM (요일)'의 요일이 오늘이 아니라 선택한 탭의 요일임. 레거시보다 퇴행 | `unist_timetable.py:66`, `busno.py:124` |
| DS-6 | medium | 공휴일로 자동 선택된 이유를 보여 주지 않음 | `time_utils.py:53-54` |
| DS-5 | medium→low | 특별편 FileNotFoundError 폴백이 요청 요일과 무관하게 weekday 0으로 감(테스트로 고정됨) | `board_support.py:153-161`, `tests/web/test_board_support.py:134~` |
| DS-8 / IA-14 / CI-13 | medium / low / low | 수집일·학기/방학·기점 기준 같은 데이터 출처를 표시하지 않음. 6월 수집본이 가을학기에 그대로 나감 | `crawler/timetable_crawl.py:123,151-153` |
| M-4 | (MISSED) | 공휴일 캐시가 두 달뿐이라, 갱신 워커가 멈추면 11월 이후 공휴일에 조용히 평일 편성이 나감 | `holiday_service.py:51-65`(캐시 보존 범위 `upcoming_months(count=2)`), `:129-136`(읽기 경로 `read_effective_holidays`) |

#### T4. 조작과 오류 피드백

| ID | 보정 | 내용 | 근거 |
|---|---|---|---|
| IA-4 / DS-10 | high / medium | 칩 href가 이전 dep를 그대로 넘겨 정상 조작에서도 경고가 뜸. **기점 집합이 다른 노선 사이를 전환할 때** 발생: 513(덕하/삼남)↔나머지, 명촌 기점(713/743/753)↔1115(꽃바위). 713↔743↔753 사이 전환만 경고가 없음 | `busno.html:18,28`, `domain/busno.py:108-112` |
| CI-5 / A11Y-14 | high→medium / low | 경고에 repr(`&#39;덕하&#39;`)과 예외 원문이 노출되고 문장이 이어 붙음 | `domain/busno.py:98,112,122` |
| A11Y-4 / MR-10 / CI-12 | high / low / low | select `onchange` 자동 제출, 제출 버튼 없음. JS 없이는 방향을 바꿀 수 없고 iOS에서 자동 확대됨 | `busno.html:37-48` |
| CI-4 / A11Y-12 | high→medium / low | 언어 전환 링크가 쿼리를 버림 | `_base.html:69,72` |
| M-11 | (MISSED, low) | 범위 밖 `day`는 안내 없이 0으로 바뀜. 숫자가 아닌 `day`는 라우트가 조용히 0으로 바꾸므로 도메인은 원래 입력이 잘못됐는지 모름 | `domain/busno.py:104-105`, `routes/busno.py:27-29`, `routes/unist_timetable.py:40-43` |

#### T5. 지금·스캔 효율·모바일

| ID | 보정 | 내용 | 근거 |
|---|---|---|---|
| IA-3 / MR-1 | high / critical→high | now 앵커, 다음 편, 지난 편 구분이 없음. 3.4~3.8화면(스크롤바 포함 측정) | `unist_timetable.html:41-51` |
| TF-4 | high→medium | is_today 판정에 필요한 입력은 라우트에 이미 있음(`raw_day is None`, `get_weekday`) | `routes/unist_timetable.py:24-52` |
| MR-2 | high | 모바일 사이드바를 닫을 수 없음. box-shadow 오버레이가 탭을 흡수하지 않음 | `style.css:192-202` |
| MR-3 | high→medium | ≤480px에서 `/busno` 표가 무너짐. 특이도 충돌로 해당 규칙이 무효 | `style.css:706-708` vs `:917-919` |
| MR-4 | high→medium | 터치 타깃이 작음(2.5.8 AA는 통과, 44px 권장치 미달) | `style.css:802-811` |
| MR-5 | medium | sticky 요소 없음 | `style.css:157-164`, `timetable.css:24-27` |
| MR-6 / IA-10 | medium / medium | 배지 벽. 범례는 조작할 수 없는 장식이고 노선 필터가 없음 | `unist_timetable.html:22-26` |
| IA-13 / DS-13 | low / low | `/busno`에서 빈 시간대 행이 사라지고 첫차·막차·공백이 안 보임(513 평일 13시 행 없음) | `domain/busno.py:45-56` |
| IA-8 / DS-12 | medium / low | 날짜 기반 계획을 지원하지 않음. 토·일 동일 | 라우트는 `day`만 받음 |
| IA-9 | medium | 내비게이션이 구현 단위로 나뉨. 🕒 중복, 교차 링크 없음 | `_base.html:28-37,66` |
| MR-7 / MR-8 / MR-11 / MR-12 | low | 가로 모드, 갱신 전략 없음, 폰트 덮어쓰기(`timetable.css:11`), hover 전용 | 각 vnote |
| M-8 | (MISSED) | 운행 종료·첫차 전 상태 안내가 없음(`/unist`에는 '운행 종료 또는 정보 없음'이 있음, `unist_partial.html:17`) | IA MISSED #6 |

#### T6. 접근성·i18n·일관성

| ID | 보정 | 내용 | 근거 |
|---|---|---|---|
| A11Y-1 | high | 713(4.12)·1115(2.70) 대비 불합격(SC 1.4.3) | `timetable.css:44-59` |
| A11Y-2 / CI-3 | high / high | EN 모드인데 본문이 한국어(SC 3.1.1), 병기 헤더. KO 모드의 영어 라벨에는 lang 표기가 없음(SC 3.1.2) | 두 템플릿 하드코딩, `busno.py:42`, `constants.py:20-24` |
| A11Y-3 | high | 키보드로 메뉴를 열 수 없고, 화면 밖 링크가 포커스를 받음 | `style.css:172,192-205`, `_base.html:65` |
| A11Y-5 | medium | aria-current 없음(사이드바·칩·언어), 레이블 없는 nav 여러 개 | grep 0건 |
| A11Y-6 | medium | th scope와 caption 없음, 배지가 맥락 없이 연속 낭독됨 | `unist_timetable.html:33-53` |
| A11Y-13 | medium | `/board` `.tag-first` 무한 깜빡임(SC 2.2.2 A 위반) | `style.css:551-553,683-686` |
| A11Y-7~12 | low | now 텍스트 부재, 이모지 aria-hidden 없음, h1과 skip link 없음, 포커스 링, 비텍스트 대비, 언어 링크 | 각 vnote |
| CI-6 / CI-8 / CI-11 | medium | 한 페이지에 이름이 셋(nav/title/topbar), 요일 라벨 출처가 둘, 팔레트가 세 곳에 중복 | `i18n.py:43`, `busno.py:42`, `timetable.css:55-59`·`style.css:545-549`·`route_diagram.py:36-42`(작업 트리 기준, HEAD에서는 `:32` 부근) |
| TF-5 / TF-6 / TF-10 / TF-11 | medium | 테스트 결합(kwargs dataclass, 정확한 문자열, patch 경로), 도메인이 문구를 직접 생성, 토큰이 단일 소스가 아님, 헬퍼 사본 4벌 | 각 vnote |
| M-13 | (MISSED) | `/unist` 카드 헤더(`style.css:958-965`)와 `/board` `c-route` 글자색(`:537-549`, FIRST 배경 #fff8e1 `:585` 위에서는 더 낮음)도 대비 불합격 | A11Y MISSED #1·#2 |
| M-15 | (MISSED) | 1280px를 200% 확대하면 CSS 폭 640px가 되어 모바일 셸이 적용되고, 저시력 사용자가 A11Y-3을 그대로 겪음 | A11Y MISSED #3 |

### 1.3 변경을 막는 제약(비협상)

- 인라인 `style="color:` 금지. 노선색은 `.bus-N`·`.route-N` 클래스로만 씁니다(`tests/web/test_unist_timetable_route.py:107-110`).
- 테스트 마커 유지:
  - `timetable-grid`, `bus-713`(`test_unist_timetable_route.py:80,103`)
  - 정확한 문자열 `class="timetable"`(`test_busno_route.py:81`)과 **렌더 HTML 안의 `"20, 40"`**(`test_busno_route.py:83`)
  - mock `timetable_rows`의 '07'·'08' 렌더(`test_unist_timetable_route.py:77-79`)
  - `warning-banner`와 '유효하지 않은 버스번호'(`test_busno_route.py:104-105`)
  - KO `<title>`의 '전체 시간표'·'버스번호별 시간표'(`test_routes_smoke.py:162-163,185-189`)
  - `translate('nav.board','ko')=='Departure Board'`(`test_i18n.py:23`)
  - `tests/domain/test_busno.py::test_invalid_dep_fallback`의 `warning is not None`
- frozen dataclass를 kwargs로 생성하는 fixture가 있습니다(`test_routes_smoke.py:58-107`, `test_busno_route.py:24-51`, `test_unist_timetable_route.py:28-50`). 따라서 새 필드는 반드시 기본값을 가져야 하고, 템플릿은 새 필드가 비어 있으면 레거시 필드로 렌더해야 합니다(N-8).
- `get_busroute_info`는 admin 5곳(`admin.py:1014,1032,1097,1174,1253`)과 `timetable_editor.py:90`이 씁니다. **변경 금지**입니다.
- 읽기 경로에서 외부 API를 호출하지 않습니다(ADR-010). 권위 소스는 ROUTEID입니다(ADR-011). JSON 쓰기는 `atomic_write_json`을 씁니다(ADR-012). gunicorn은 다중 워커입니다(`bushexa/cli.py:313`, `BUSHEXA_WEB_WORKERS` 기본 `'2'`. phase1의 `cli.py:223` 인용은 TF-8 verifier가 정정함). 다중 워커 캐시 일관성의 선례는 `data/timetable.py:49-101`(mtime·size 서명 캐시)입니다.
- `/lite`는 style 0, JS 0, 웹폰트 0입니다(`board_lite.html:1-5`). CDN은 쓰지 않습니다. admin이 `_base.html`을 extends합니다.
- 특별편은 공휴일보다 우선합니다(`tests/domain/test_holiday_and_special_precedence.py`). 특별편 폴백 규칙은 `test_board_support.py`로 고정되어 있습니다.
- 표·배지 레거시 HEX는 고정합니다(`docs/refactor/legacy-ui-reference.md:89`의 레거시 HEX 고정 규칙).
- 테스트 데이터 경로: 시간표는 `config.data_dir`이 아니라 `timetable_dir()`(env `BUSHEXA_TIMETABLE_DIR`, 기본은 저장소 `data/timetable`)에서 읽고, 경로별 모듈 전역 `_cache`가 있습니다(`data/timetable.py:55-67`). 특별편 배정 맵은 `config.data_dir/special_timetables.json`, 에디션 파일은 `timetable_dir()/special/<id>/`에 있어 두 곳으로 나뉩니다(`board_support.py:136-146`). 계약 테스트는 P0-1a의 `tt_env`로만 이 배선을 다룹니다.
- 작업 트리 현황(git status로 확인한 사실): 수정된 파일은 `bushexa/data/constants.py`(VIA_STOPS 1115 '태화강역광장' 등), `bushexa/web/route_diagram.py`, `bushexa/web/static/css/info.css`, `bushexa/web/templates/info.html`, `tests/web/test_route_diagram.py`, `data/changelog.json`입니다. untracked 런타임 파일은 `data/arrival_status.json`, `data/govtrack_state.json`, `data/govtrack_status.json`, `data/holiday_cache.json`입니다. **선행 작업 P0-0a**에서 코드·템플릿·테스트 변경만 커밋하고 런타임 파일은 제외합니다(7장). 이 계획의 거점 색인은 수정본(1115는 태화강역 정류소에 서지 않음)을 기준으로 삼았습니다.

---

## 2. 사용자·과업 모델

### 2.1 페르소나

| ID | 페르소나 | 맥락 | 주요 제약 |
|---|---|---|---|
| P1 | UNIST 정류장의 재학생 | 모바일, 한 손, 서 있음, 몇 초 안에 판단 | 첫 뷰포트, 한 손 도달, 햇빛 아래 대비 |
| P2 | 계획하는 사람 | 데스크톱이나 모바일, 내일·주말·공휴일 계획 | 편성 출처를 신뢰할 수 있어야 함 |
| P3 | 신입생·방문자 | 노선 지식 없음, 목적지로만 생각함 | 노선번호를 외워야 하는 부담, 어느 정류장에 서야 하는지 |
| P4 | 시내에서 UNIST로 오는 사람 | 명촌·꽃바위 기점 또는 중간 정류장(삼산·공업탑) | 기점 시각은 중간 정류장 이용자에게 맞지 않음 |
| P5 | 유학생(EN 모드) | 공유 링크를 열고 EN으로 전환 | 한국어가 섞이면 안 됨, 쿼리 보존 |
| P6 | 저시력·키보드·스크린리더 사용자 | 200% 확대 시 모바일 셸 진입 | 키보드 메뉴, 표 구조, 텍스트 상태 |
| P7 | 운영자 | 특별편·공휴일 적용과 데이터 기준일 검증 | 화면에 적힌 기준으로 문의에 답해야 함 |

### 2.2 핵심 과업(빈도×위험 순)

**[가정]** 빈도는 추정입니다. 실제 유입 시간대, 기기 비율, 실시간 화면과의 이동 경로는 **P0-0b**에서 access log 기준선으로 확인합니다(9장 I-1). 사용자 가치 심사관은 "정류장에서 다음 버스를 보는 과업이 시간표 페이지에서 일어난다"는 가정 자체를 검증하라고 요구했습니다. 그 결과에 따라 Phase 3 안의 우선순위(다음 출발 대 날짜 조회)가 바뀔 수 있습니다.

| 순위 | 과업 | 페르소나 | 현재 | 목표(성공 정의) | 달성 Phase |
|---|---|---|---|---|---|
| T1 | UNIST에서 시내로 가는 다음 버스 2~3편과 남은 분 | P1, P6 | 격자에서 17시 행(y≈1753, 스크롤바 포함)을 찾아 암산. 513 오답 포함 | 375×667(스크롤바 숨김)에서 **탭 0회, 스크롤 0회**, 첫 항목 bottom ≤ 600px. 복도 테스트 중앙값 ≤ 5초, 오답 0. 전후 비교는 P0-0b의 스크롤바 숨김 기준선으로 함 | 3 |
| T2 | UNIST에서 울산역(KTX)으로 가는 513을 언제 탈 수 있나 | P1, P3 | 덕하 기점 시각을 UNIST 시각으로 오독. /busno에서는 '덕하'를 골라야 함 | 기점 시각이 기점 시각으로 표기되고, '최근 기점 출발 1편 + 다음 2편'과 실시간 링크가 1탭 거리. 오답 0. 정답률 ≥ 90%(D1 (b)/(c) 승인 후에는 '약 HH:MM(추정)') | 2(라벨), 4(추정) |
| T3 | 목적지(삼산·공업탑·울산대·동구·울산역)로 가려면 몇 번을 타나 | P3 | info 표를 외워야 함 | '어디로?' 거점 칩 1탭으로 해당 노선만 필터. 칩에 노선번호 표시 | 2 |
| T4 | 내일·토요일·대체공휴일(10/5)의 첫차와 적용 편성 | P2, P7 | 요일 라벨이 틀림, 편성 사유 미표시 | 날짜 칩 1탭 또는 날짜 폼 1회 제출. 상태 줄에 사유 문장 100% | 1(사유), 3(날짜) |
| T5 | 명촌에서 UNIST로 가는 다음 차나 막차 | P4 | /busno에서 노선 3개를 오감 | '도착' 방향 + 출발지 '명촌' 2탭으로 713·743·753을 합친 기점 출발 시각. 중간 정류장 이용자는 실시간 `/stops`로 1탭 | 2 |
| T6 | 공유 링크를 열고 EN으로 전환해 T1~T5 수행 | P5 | 선택 초기화, 한국어 잔존 | 쿼리 보존 100%(다중 값 포함). `[lang=ko]` 밖 한글 0자(sr-only와 속성 포함) | 0(쿼리), 1(본문) |
| T7 | 특별편 날에 편성 확인, 탭을 다시 눌러도 유지 | P7, P2 | 탭 재클릭 시 특별편 해제 | 상태 줄 표기 100%, 오늘 칩 재클릭 후 유지 100% | 0(링크), 2(규칙) |
| T8 | 키보드만으로 메뉴 열기·닫기와 모든 칩 조작(200% 확대) | P6 | 불가 | 가능. 포커스가 sticky 바에 가려지지 않음(SC 2.4.11) | 0, 3 |

---

## 3. 설계 원칙

각 원칙에는 검증 방법을 붙였습니다. **N**은 비협상 원칙, **G**는 지침입니다.

| # | 원칙 | 검증 |
|---|---|---|
| N-1 **정확성이 편의보다 먼저** | 화면의 모든 시각 토큰은 `basis ∈ {unist, origin, estimated}`를 데이터로 가지고, 템플릿은 그 기준을 텍스트로 드러냅니다. `basis≠unist`인 토큰에는 카운트다운('N분 후'), FIRST/SECOND 순위, next 강조를 적용하지 않습니다. 예외는 승인된 `estimated`로, '약' 접두어를 붙입니다. | 속성 테스트: 전 요일 × 전 노선에서 `basis=='origin'` 토큰은 `minutes_until is None`이고 state가 next가 아님. 렌더 HTML에서 `data-basis="origin"` 요소 안에 '분 후'·'min' 0건 |
| N-2 **방향이 1급 개념** | 첫 선택은 'UNIST에서 출발 / UNIST로 도착'입니다. 칩·배지·범례의 주 텍스트는 행선이나 방면이고 기점은 보조입니다. 명명 규칙은 하나입니다: `[기점] → [행선] 방면`, 513은 `[기점] → UNIST 경유 → [행선]`. '출발지: 덕하'처럼 기점만 단독으로 쓰는 라벨은 금지합니다(P0-2부터 적용). | 템플릿 grep '출발지:' 0. DirectionSpec 10개 hand-built 기대값 테스트 |
| N-3 **상태를 숨기지 않는다** | 오늘 날짜, 적용 편성(평시·공휴일·특별편)과 사유, 보고 있는 편성이 오늘과 같은지, 공휴일 데이터 범위, 데이터 경과일을 상태 줄에 항상 텍스트로 보여 줍니다. 조용한 폴백은 금지합니다. | 5.6 상태 매트릭스 × 언어 계약 테스트(8.1) |
| N-4 **zero-JS 완결성과 점진 향상** | 방향·목적지·노선·요일·날짜 선택과 다음 편 확인까지 모든 과업이 서버 렌더와 GET 링크(또는 제출 버튼이 있는 GET 폼)만으로 가능해야 합니다. JS는 분 단위 재계산과 스크롤 편의만 맡고, 페이지 전용 파일 1개, 비압축 3KB 이하, storage 미사용입니다. | test client 렌더에 `on[a-z]+=` 속성 0, `<select` 0(자동 제출). JS 파일 크기 CI 단언. JS 비활성 수동/E2E 체크리스트 |
| N-5 **인라인 style 0, 인라인 script 0** | 노선색은 클래스로만 씁니다. | 공개 템플릿 렌더에서 `style="` 0, 인라인 `<script>` 본문 0 |
| N-6 **모든 문구는 `t()`로, 언어 경계는 lang으로** | 도메인은 문장을 만들지 않고 코드(`(code, params)`)만 반환합니다. 한 화면은 한 언어로만 표기하고 병기는 금지합니다. **EN 렌더**: 번역되지 않은 한국어 고유명사만 `<span lang="ko">`로 감쌉니다. **KO 렌더(대칭 규칙)**: 브랜드·약어 허용 목록(`UNIST`, `KTX`, `Bus HeXA`, `BIS`, 노선번호 숫자, `HH:MM`)을 뺀 라틴 단어 연속 토큰은 `[lang=en]` 조상 안에만 있어야 합니다(SC 3.1.2). nav, `<title>`, topbar, h1은 같은 키를 씁니다. | 키 커버리지 테스트(동적 접두사 허용 목록 포함, 8.1). EN 렌더에서 `[lang=ko]` 밖 한글 0자. KO 렌더에서 허용 목록 밖 라틴 토큰이 `[lang=en]` 밖에 0개. 스캔 대상은 텍스트 노드, `aria-label`, `title` 속성, `<title>`, `caption`, sr-only |
| N-7 **WCAG 2.2 AA** | 텍스트 대비 ≥ 4.5, 비텍스트 ≥ 3. 선택 칩에 `aria-current="true"`, 사이드바 현재 링크에 `aria-current="page"`, 모든 `<nav>`에 접근 가능한 이름. 표에 caption과 th scope. 현재/다음/지남은 텍스트로도 전달합니다. 무한 애니메이션은 금지합니다. sticky 요소가 있으면 `scroll-padding-top`과 `scroll-margin-top`으로 포커스와 앵커가 가려지지 않게 합니다(SC 2.4.11). | CSS 파싱 대비 테스트, 칩 그룹당 aria-current 정확히 1개, 사이드바 aria-current=page 정확히 1개, 수동 SR 점검(8장) |
| N-8 **추가형 스키마와 템플릿 폴백** | 새 dataclass 필드는 전부 기본값을 가집니다. 기존 필드(`minutes: str`, `warning`, `timetable_rows`, `bus_legend`), 클래스 마커, KO title 마커, `get_busroute_info`, 라우트 모듈의 patch 대상 심볼은 유지합니다. **템플릿 폴백 규칙**: `grid_groups`/`hour_groups`가 비어 있으면 `timetable_rows`로 렌더하고, `notices`가 비어 있으면 레거시 `warning`을 렌더합니다. | "레거시 모양 fixture로 렌더 → 200이고, fixture의 hour·minute 값(예: '07', '20, 40')이 렌더됨" 테스트. 기존 테스트는 수정 없이 통과하며, 의도된 이관은 PR 본문에 목록화 |
| N-9 **링크가 곧 상태** | 같은 URL은 사용자와 무관하게 같은 화면을 렌더합니다. 예외는 lang 쿠키 하나이고, 기본 방향이나 노선에 쿠키를 쓰지 않습니다. 알 수 없는 파라미터는 200으로 정규화하고 안내 코드를 남깁니다. 정상 조작에서는 경고도 notice도 뜨지 않습니다. | 링크 크롤 테스트: `/busno` 5×2×3 조합의 모든 칩 href → 200, `.warning-banner` 0, notice 0 |
| N-10 **표면 간 단일 규칙** | `/timetable`, `/busno`, `/board`, `/lite`, `/unist`는 같은 `DirectionSpec`과 `effective_unist_time()`으로 방향·기준·정렬을 정합니다. 날짜가 걸린 공지는 하나의 날짜 상수로 게이트합니다(P0-9). | `unist_board`·`board` 방향 판정과의 동치성 테스트(P1-1). 5개 화면 513 표기 교차 테스트 |
| N-11 **추정은 승인 후에만** | 오프셋 추정은 `approved_by`가 있고 품질 게이트(첨두 포함 시간대별 n, IQR)를 통과한 시간대에만 보여 줍니다. 표기는 '약'과 범위이고 점선 표식을 붙입니다. 파일이 없거나 파손되면 (a)로 폴백합니다. | Phase 4 테스트 |
| N-12 **신선도 표기** | 서버가 렌더한 상대 시각은 항상 절대 시각과 'HH:MM 기준' 옆에 둡니다. 시간 의존 공개 응답에는 `Cache-Control: no-cache`와 `Vary: Cookie`를 붙입니다. | 응답 헤더 단언. 상대 시각 요소의 조상에 기준 시각 텍스트 존재 |
| G-1 모바일 첫 화면 답 | 375×667에서 컴포넌트별 px 예산을 지킵니다(5.2절). 칩 라벨 길이 상한은 KO 10자, EN 16자, 한 줄입니다. | 헤드리스 측정(선택 게이트) |
| G-2 색은 보조 식별자 | 노선번호 텍스트가 1차 정보이고, 노선색은 좌측 바나 테두리로 씁니다. 노선번호 텍스트는 색과 무관하게 **모든 토큰에 항상 표시**합니다(현재 `/timetable`의 '(513)' 텍스트가 하는 색각 대체 역할을 유지, CI MISSED #7). 색 토큰은 단일 소스이고 parity 테스트를 둡니다. | parity 테스트, "모든 `li.dep`에 노선번호 텍스트 존재" 단언 |
| G-3 되돌릴 수 있는 작은 PR | 한 PR에 한 관심사만 담고, 의존 순서를 명시하며, git revert로 되돌릴 수 있게 합니다. 이중 템플릿(`?layout=v2`)은 쓰지 않습니다(엔지니어링 심사 지적). | PR 체크리스트 |

---

## 4. 목표 정보구조(IA)와 URL 계약

### 4.1 페이지 체계(2단 구조)

| 페이지 | 정체성 | 역할 |
|---|---|---|
| `/timetable` | **UNIST 전체 시간표** [D2] | 방향 우선 개요. `dir=out`(기본)은 UNIST에서 타는 모든 버스로, UNIST 기점 4개 노선은 격자, 513은 '경유 노선' 패널. `dir=in`은 UNIST로 오는 버스의 기점 출발 시각 [D6] |
| `/busno` | **노선별 시간표** | 한 노선 한 방향의 상세: 첫차·막차·최장 간격·공백 행·경유지·승차 정류소·공지 |
| `/unist`, `/stops`, `/board`, `/lite` | 실시간 | 역할은 그대로 두고, 시간표로 채운 행에 같은 basis 규칙과 문구를 적용 |
| `/info` | 노선 정보 | 목적지→노선 표의 각 행에서 `/timetable?hub=…`로 교차 링크. '앞쪽/뒤쪽' 문구는 방향 명명 규칙으로 교체 |

두 시간표 페이지를 합치는 A 원안은 D14(Phase 5)로 미뤘습니다. 이유는 세 가지입니다. URL 상태 조합이 폭증합니다. `get_full_timetable_data`·`get_busno_page_data`를 patch하는 테스트의 대량 이관이 한 Phase에 몰립니다. 기존 `/busno` 사용자의 인지 부하가 커집니다. 두 페이지는 `macros/_timetable.html` 컴포넌트와 `timetable_view` 도메인을 공유하므로 나중에 합쳐도 비용이 적습니다.

### 4.2 `/timetable` 쿼리 계약(모두 선택, GET)

| 파라미터 | 값 | 도입 | 규칙 |
|---|---|---|---|
| `dir` | `out` \| `in` | P2 | 기본 `out`. **쿠키로 기억하지 않음**(N-9). 알 수 없는 값이면 `out` + notice `invalid_dir` |
| `hub` | 거점 키, 쉼표 구분(4.5절) | P2 | `dir=out`에서만 의미가 있음. 지정한 거점을 지나는 노선만 표시. 알 수 없는 키는 무시 + notice `invalid_hub`. `dir=in`과 함께 오면 무시 + notice `param_ignored{param:'hub'}` |
| `origin` | `myeongchon` \| `kkotbawi` \| `deokha` \| `samnam` | P2 | `dir=in`에서만 의미가 있음(A의 대칭 `place` 키 대신 방향별로 분리해 의미가 뒤집힐 위험을 없앰). `dir=out`과 함께 오면 무시 + notice `param_ignored{param:'origin'}` |
| `routes` | `513,713,743,753,1115`의 부분집합(쉼표 구분 또는 반복 파라미터) | P3 | 노선 필터. 범례가 GET 토글이 됨. 알 수 없는 값은 버리고 notice `invalid_routes`. 유효 값이 0개면 필터 없음으로 취급 |
| `day` | `0`\|`1`\|`2` | 기존 | 범위 밖이거나 숫자가 아니면 0으로 보정 + notice `invalid_day`(P1부터, 라우트가 `day_invalid`를 넘김). P0: 요일 칩 규칙 ①·버스 칩 규칙 ②(P0-4). P2(D3 승인 시): `day==오늘 코드`이면 오늘 날짜로 취급해 특별편 유지 |
| `date` | `YYYY-MM-DD` | P3 | `day`보다 우선. 허용 범위는 오늘−7일 ~ +90일이고, 벗어나면 오늘로 두고 notice `date_out_of_range`. 서버가 날짜를 요일 유형·공휴일·특별편으로 한 번에 해석. 과거 날짜는 상태 줄 `tt.status.past_date` |
| `edition` | `base` | P2(D3) | 특별편 날에 평시 시간표를 명시적으로 보는 경로. 상태 줄에 '평시 시간표를 보고 있습니다 · 오늘 특별 시간표로' |
| `lang` | `ko`\|`en` | 기존 | `lang_url(code)`가 나머지 쿼리를 보존(4.8절) |
| 앵커 | `#now`, `#via-513`, `#hHH`, `#next` | P2~3 | |

### 4.3 `/busno` 쿼리 계약

| 파라미터 | 값 | 규칙 |
|---|---|---|
| `bus` | 5개 노선 | 기존. 잘못된 값이면 기본 노선 + **warning-banner**(TP-002 계약, '유효하지 않은 버스번호' 유지) |
| `to` | `downtown` \| `unist` \| `ulsan-station` | 신규(P2). `DirectionSpec.slug`. 713/743/753/1115는 UNIST 기점이 `downtown`, 명촌·꽃바위 기점이 `unist`. 513은 삼남 기점(덕하(시내) 방면)이 `downtown`, 덕하 기점(삼남(울산역) 방면)이 `ulsan-station` |
| `dep` | 기점명(레거시) | 계속 받음. 서버가 `DirectionSpec.origin_ko`로 `to`에 매핑하고 `<link rel=canonical>`로 새 URL을 알림. **VIA_STOPS 키로 조회하지 않음**(M-6) |
| `day`, `date`, `edition`, `lang` | `/timetable`과 같음 | |

버스 칩 규칙: href에는 `dep`를 **절대 넣지 않습니다**. 같은 `to` 슬러그가 새 노선에도 있으면 `to`를 유지하고(713 `downtown` → 513 `downtown`), 없으면 `to`를 생략해 새 노선의 기본 방향을 씁니다. `to`를 생략한 것은 정상 조작이므로 **notice를 띄우지 않습니다**(N-9). 방향이 바뀌었다는 사실은 방향 칩의 `aria-current`와 기준 안내 줄로 이미 보입니다.

오류와 안내의 구분:

- 어떤 노선의 유효한 기점명이지만 이 노선에는 없는 조합(예: 공유된 `bus=713&dep=덕하`): **notice** `dir_not_available`. `role=status`이고 경고 스타일이 아닙니다. 칩 링크로는 이 조합이 만들어지지 않습니다.
- 어떤 노선에도 없는 값(예: `dep=xx`, `bus=999`): **warning-banner**.

### 4.4 레거시 URL 매핑(리다이렉트 없음, 같은 화면 200 + canonical, 테스트 표로 고정)

| 요청 | 렌더 결과 | canonical |
|---|---|---|
| `/timetable` | 오늘, `dir=out` | `/timetable` |
| `/timetable?day=N`(N==오늘 코드) | P0~P1: 대표 편성(특별편 미적용, 칩은 day 생략). P2(D3): 오늘과 같음 | `/timetable` |
| `/timetable?day=N`(N≠오늘 코드) | 대표 편성 보기, 상태 줄에 '오늘 시간표로' | 같음 |
| `/busno` | 기본 노선 [D10], 권장은 데이터 규칙 | — |
| `/busno?bus=713&dep=UNIST` (743·753·1115 동일) | `to=downtown` | `/busno?bus=713&to=downtown` |
| `/busno?bus=713&dep=명촌` (743·753 동일), `bus=1115&dep=꽃바위` | `to=unist` | 해당 |
| `/busno?bus=513&dep=덕하` | `to=ulsan-station` | 해당 |
| `/busno?bus=513&dep=삼남` | `to=downtown` | 해당 |
| `/busno?bus=713&dep=덕하` | 기본 방향 + notice `dir_not_available` | `/busno?bus=713` |
| `/busno?bus=513&dep=UNIST` | 기본 방향 + notice | `/busno?bus=513` |
| `/busno?bus=999` | 기본 노선 + warning-banner | `/busno` |
| `/busno?bus=713&dep=xx` | 기본 방향 + warning-banner(값은 이스케이프, repr 없음) | `/busno?bus=713` |

### 4.5 목적지 거점 색인(`DESTINATION_HUBS`, D7)

사용자 가치 심사관의 must-fix를 반영했습니다. A의 **종점 기반** 칩은 1115(시내 경유)와 513 삼남발(공업탑·시청 경유)을 빠뜨립니다. 그래서 거점 칩은 **주요 경유 거점 → 노선·방향** 색인에서 만듭니다. 아래 표는 `VIA_STOPS`(작업 트리 수정본), ROUTEID 정류소 ID, `info.html` 목적지 표에서 유도한 것이며, **라벨과 묶음은 운영자 검증이 필요합니다(D7)**.

| 키 | KO 라벨(10자 이내) | EN 라벨 | 해당 방향(`dir=out`) | 근거(VIA_STOPS / ROUTEID 정류소 ID) |
|---|---|---|---|---|
| `ulsan-station` | 울산역(KTX) | Ulsan Stn (KTX) | 513 덕하발(경유) | '울산역 - 삼남신화' |
| `samsan` | 삼산·태화강역 | Samsan · Taehwagang | 713, 743, 753, 1115(태화강역광장) | 713/743/753 '삼산 - 태화강역', 1115 '삼산동 - 태화강역광장' |
| `myeongchon` | 명촌 | Myeongchon | 713, 743, 753 | 종점 |
| `gongeoptap` | 공업탑 | Gongeoptap | 743, 753, 513 삼남발(경유) | 743·753·513 삼남발 문자열 |
| `ulsan-univ` | 울산대학교 | Univ. of Ulsan | 743, 753 | 해당 문자열 |
| `city-hall` | 시청 | City Hall | 1115, 513 삼남발(경유) | 시청앞 193031109가 1115(`constants.py:54`)와 513 삼남발(`:40`) UNIST 이후 구간에 있음. `info.html:38` '시청 (City hall) → 513, 1115'와 일치 |
| `dong-gu` | 동구·꽃바위 | Dong-gu · Kkotbawi | 1115 | 남목·현대중공업·일산·꽃바위 |

규칙:

- 색인은 상수로 두고 테스트 두 개를 붙입니다. (1) 각 (거점, 노선) 쌍의 키워드가 해당 `VIA_STOPS` 문자열에 실제로 있는지. (2) 정류소 ID가 있는 거점(예: `city-hall` → 193031109/193031110)은 해당 방향 ROUTEID stops의 **UNIST 이후 구간**에 그 ID가 있는지 교차 검증합니다. VIA_STOPS나 ROUTEID가 바뀌면 테스트가 깨지도록 하기 위해서입니다. 713은 시청앞을 지나지 않으므로(`195000178` stops에 193031109 없음) `city-hall`에서 뺐습니다.
- 713·1115의 '태화루'를 별도 거점 `taehwaru`로 둘지는 D7에서 정합니다. 기본값은 두지 않음입니다.
- '태화강역'과 '태화강역광장'은 서로 다른 정류장입니다(작업 트리 info.html의 '(역 정류소 미정차)'). 1115를 `samsan`에 넣는 것이 타당한지도 D7에서 확인합니다.
- 513 방향이 속한 거점 칩에는 '경유' 표식을 붙입니다. 513 토큰은 선택된 거점과 관계없이 **격자에 섞이지 않고** 경유 패널에만 나옵니다(N-1).

`dir=in` 출발지 칩은 `명촌에서`(713·743·753), `꽃바위에서`(1115), `덕하에서`(513, UNIST 경유 → 울산역), `삼남·울산역에서`(513, UNIST 경유 → 덕하)입니다. 모두 basis=origin입니다.

### 4.6 내비게이션(D9)

| 그룹(KO / EN) | 항목 |
|---|---|
| 실시간 / Live | UNIST 출발 `/unist`, UNIST 도착 `/stops`, 출발 게시판 `/board` |
| 시간표 / Timetables | UNIST 전체 시간표 `/timetable`, 노선별 시간표 `/busno`, 운행 기록 `/running` |
| 정보 / Info | 노선 정보 `/info` |

- 아이콘은 `aria-hidden="true"`로 처리하고 🕒 중복을 없앱니다(A11Y-8, P0-7b).
- 사이드바 현재 링크에 `aria-current="page"`, 사이드바·언어 선택·칩 영역의 각 `<nav>`에 `aria-label="{{ t('nav.label.main') }}"` 등 접근 가능한 이름을 붙입니다(P0-7b). 칩 그룹의 `<nav>` 남용은 P1-4에서 `role=group`으로 바꿉니다.
- nav 라벨, page_title, `<title>`('… · Bus HeXA'), h1은 같은 키 `page.<id>.title`을 씁니다(CI-6). 새 명칭 적용은 D2 이후 P1-3에서 합니다. P0-7b는 기존 제목 텍스트를 글자 그대로 씁니다.
- KO title에는 스모크 마커 '전체 시간표'와 '버스번호별 시간표'를 Phase 5까지 포함합니다. 예: `<title>UNIST 전체 시간표 · Bus HeXA</title>`, `/busno`는 `713번 시간표 — 버스번호별 시간표 · Bus HeXA`.
- KO nav 라벨을 한국어로 바꾸면 `test_i18n.py:23`이 깨집니다. **D9 결정과 함께 해당 테스트를 개정하는 PR로 묶습니다.** D9가 거부되면 P3-5는 'KO nav의 영문 라벨에 `lang="en"` 부여'로 대체합니다(N-6 대칭 규칙 충족).

### 4.7 교차 링크(IA-9)

- `/timetable?dir=out` 상단에 '실시간 출발 보기 → /unist', `dir=in` 상단에 '실시간 도착 보기 → /stops'를 둡니다. 중간 정류장 이용자에게는 이쪽이 1차 답입니다.
- 격자 토큰과 경유 패널 행에서 `/busno?bus=N&to=…#hHH`로 가는 딥링크를 둡니다.
- `/board`·`/unist` 카드의 노선번호에 `/busno?bus=N&to=…` 링크를 둡니다(P3-5). 링크를 따라가도 경고가 0건이어야 합니다.
- 상태 줄에 '오늘 시간표로'(파라미터 없는 URL)를 둡니다.

### 4.8 언어 전환

- context processor `lang_url(code)`를 추가합니다. 구현은 다음과 같습니다.

  ```python
  def lang_url(code):
      if request.endpoint is None:
          return f"{request.path}?lang={code}"
      args = request.args.to_dict(flat=False)   # 다중 값(routes= 반복 등) 보존
      args.pop('lang', None)
      for k in (request.view_args or {}):        # view_args와 쿼리 키 충돌 시 view_args 우선
          args.pop(k, None)
      return url_for(request.endpoint, **(request.view_args or {}), **args, lang=code)
  ```
- 링크에 `lang`, `hreflang`을 붙이고, 현재 언어에는 `aria-current="true"`를 붙입니다(A11Y-12).
- 한글 쿼리 값은 `url_for`가 인코딩합니다(CI-4).
- 언어 버튼 '한'은 `<span lang="ko">한</span>`으로 감쌉니다(자기 언어로 이름을 쓰는 방식). 그룹 aria-label은 `t('lang.switcher')`입니다.

---

## 5. 화면 설계 명세

### 5.1 공통 컴포넌트(`bushexa/web/templates/macros/_timetable.html`, 신규)

| ID | 컴포넌트 | 명세 |
|---|---|---|
| C1 | `tt_status(status)` 상태 줄 | `<p class="tt-status">`. 오늘 날짜, 적용 편성과 사유, 기준 시각을 담습니다. 편성 경고(폴백, 캐시 범위 밖, 데이터 경과)가 있을 때만 `<div class="info-banner" role="status">`를 추가합니다. 오늘 날짜와 보고 있는 편성은 **항상 분리**해서 표기합니다 |
| C2 | `chip_group(label_key, items)` | `<div role="group" aria-labelledby>`(현재의 `<nav>` 남용 해소). 항목은 `<a class="chip …">`이고, 현재 항목에 `aria-current="true"`를 줍니다. ≤480px에서 min-height 44px, 간격 8px 이상. 비활성 테두리 #7986cb(≥3:1) |
| C3 | 방향 세그먼트 | `chip_group`의 2항목 변형이고 전체 폭을 씁니다. KO 'UNIST에서 출발' / 'UNIST로 도착', EN 'From UNIST' / 'To UNIST' |
| C4 | `route_mark(busno, basis)` | D4 권장안 (a): 흰 배경(`--surface`) + 4px 좌측 바(`--route-N`) + 번호 글자 #1b1b1b(흰 배경에서 16:1 이상) + 1px 테두리 #767676(4.54:1). `basis=estimated`는 점선 테두리. 클래스 `bus-N`을 유지합니다(테스트 마커). D4가 (b)이면 `--route-N-ink` 배경에 흰 글자(513 #C62828 5.62, 713 #2E7D32 5.13, 743 #1565C0 5.75, 753 #7B1FA2 8.20, 1115 #B34700 5.50, 모두 검증값) |
| C5 | `dep_token(dep)` | `<li class="dep" data-state="past|next|upcoming|neutral" data-basis="unist|origin|estimated">`. 보이는 텍스트는 분 숫자(tabular-nums)와 route-mark이고, **노선번호 텍스트는 색과 무관하게 항상 표시**합니다(G-2). sr-only로 '17시 55분 713번 명촌 방면'(EN 'Route 713 to Myeongchon at 17:55')을 넣습니다. next는 텍스트 배지 '다음' + 2px 테두리(≥3:1). past는 글자 #595959(7.0:1) + sr-only '지난 편'이고, 취소선이나 불투명도는 쓰지 않습니다. 같은 분의 다노선 토큰은 한 토큰으로 묶습니다('55 · 713 743'). 실데이터에서 평일 17:55에 713과 743이 동시 출발합니다. `/busno`와 `/timetable`은 이 한 표기 규칙을 공유합니다(현재 'MM, MM'과 'MM (513)' 두 체계, CI MISSED #7) |
| C6 | `hour_grid` | `<table class="timetable-grid">`에 `<caption>`, `<th scope="col">`, 시 셀 `<th scope="row" id="hHH">`, 분 셀 `<ul class="dep-list">`. 현재 시 행은 `id="now"`, `class="is-now"`, th 안에 텍스트 '지금'. `grid_groups`가 비어 있으면 `timetable_rows`로 렌더(N-8) |
| C7 | `next_departures(items)` | `<section id="next" aria-labelledby>`, h2 '다음 출발 · HH:MM 기준', `<ol>`. 항목 형식은 `<time>17:55</time> [713] 명촌 방면 · 8분 후`(C4, C5 규칙). 오늘 남은 편이 N개 미만이면 내일 첫차 1편을 '내일' 표기와 함께 붙입니다(5.6) |
| C8 | `via_panel(sections)` | `<section id="via-513">`. 513 두 방향을 두 블록(모바일)이나 두 열(데스크톱)로 보여 줍니다. 각 블록에 기점 출발 시각임을 명시합니다. 블록 구성: (1) `origin_window` 요약(최근 기점 출발 1편 + 다음 2편), (2) `<details><summary>{origin} 출발 전체 시각({n}편)</summary><ul class="dep-list">…</ul></details>`로 그날 기점 시각 전체(JS 불필요). 최근 편이 없으면(첫 기점 출발 전) '첫 {origin} 출발 HH:MM', 그날 513이 없으면(특별편) '오늘 513 운행 정보 없음' |
| C9 | `notice(code, params)` / `warning(code, params)` | `role="status"`. 제목 `<strong>`. 문장은 `t()`로 만들고 값은 이스케이프합니다. repr과 예외 원문은 로그로만 보냅니다. 렌더 우선순위: `notices`가 있으면 코드로 렌더, 없으면 레거시 `warning` 문자열(N-8) |
| C10 | `source_footer(meta)` | `_meta.json`이 있을 때만: '울산 BIS 기점 출발 시간표 · 2026-06-02 수집 · 학기 편성' |

CSS 토큰은 `style.css :root`에 둡니다(파일 경로 `bushexa/web/static/style.css`).

- `--route-{N}`: 식별색. 레거시 hex를 유지합니다(`legacy-ui-reference.md:89`).
- `--route-{N}-ink`: 텍스트용(D4).
- `--focus-ring: 2px solid #1a237e`: offset 2px, 흰 배경에서 3:1 이상.
- `--tt-controls-h: 52px`.

`.bus-N`과 `.route-N`은 `var()`만 참조하고, `route_diagram.COLORS`와의 parity 테스트를 둡니다. `timetable.css:11`의 `font-family: sans-serif`는 제거합니다. hover 규칙은 `@media (hover:hover)` 안으로 옮깁니다.

### 5.2 `/timetable` 모바일(360~414px), `dir=out`, 오늘

평일 17:47 실데이터 예시입니다(P2 이후 모습이므로 17시 행에 513은 없습니다).

```
┌──────────────────────────────────────┐ ← topbar ≤48px
│ ☰(44×44)  UNIST 전체 시간표   한|EN  │   (h1 = topbar 제목)
├──────────────────────────────────────┤
│ 오늘 9/29(화) · 평일 시간표 · 17:47 기준 [새로고침] │ ← 상태 줄 ≤44px(최대 2줄)
├══════════════ sticky ≤52px ══════════┤
│ [ UNIST에서 출발 ✓ ][ UNIST로 도착 ]  │ ← 방향 세그먼트 44px
├──────────────────────────────────────┤
│ ▸ 목적지·요일·노선으로 좁히기          │ ← <details> summary 44px
├──────────────────────────────────────┤
│ 다음 출발 · 17:47 기준  (UNIST(기점)) │ ← h2 ≈32px
│ 17:55 [713] 명촌 방면 · 8분 후  다음  │
│ 17:55 [743] 명촌 방면 · 8분 후        │   44px × 3 = 132px
│ 18:10 [1115] 꽃바위 방면 · 23분 후    │
│ 18:15 [753] 명촌 방면 · 28분 후       │
│ 18:25 [713] 명촌 방면 · 38분 후       │
│ 실시간 출발 보기 →                    │
├──────────────────────────────────────┤
│ 513 · 울산과학기술원(경유) · 기점 출발 시각 │
│ 울산역(KTX) 방면 · 덕하 출발           │
│   최근 17:30 · 다음 18:30, 19:00      │
│   ▸ 덕하 출발 전체 시각(28편)          │
│ 덕하(시내) 방면 · 삼남 출발            │
│   최근 17:20 · 다음 17:50, 18:30      │
│   ▸ 삼남 출발 전체 시각(28편)          │
│ UNIST 통과는 기점 출발보다 늦습니다. 실시간 위치 보기 → │
├──────────────────────────────────────┤
│ 지금으로 이동(#now)                   │
│ ▸ 지난 시간 05–16시 펼치기 (N편)       │ ← <details>(JS 불필요)
│ 17시  지금                            │ ← id=now
│  05 753 · 10 743 1115 · 20 753 ...    │
│ 18시 ...                              │
├──────────────────────────────────────┤
│ 울산 BIS 기점 출발 시간표 · 2026-06-02 수집 · 학기 편성 │
└──────────────────────────────────────┘
```

**첫 뷰포트 예산(375×667, 스크롤바 숨김)** [가정: 폰트와 행 높이는 현재 셸 기준 추정. Phase 3에서 측정으로 확정]

| 요소 | 상한 | 누적 |
|---|---|---|
| topbar | 48 | 48 |
| 상태 줄(최대 2줄) + 여백 | 56 | 104 |
| sticky 방향 세그먼트 | 52 | 156 |
| 좁히기 `<details>` summary(닫힘) | 44 + 8 | 208 |
| '다음 출발' h2 | 40 | 248 |
| 다음 출발 3행 | 3 × 44 | 380 |
| 여유 | ≤ 220 | **≤ 600** |

- 목적지 거점 칩 7개는 **기본으로 접습니다**(`<details>`). 펼쳤을 때만 줄바꿈을 허용합니다. 이렇게 해서 A의 과밀 문제를 해소합니다.
- 칩 라벨 상한은 KO 10자, EN 16자(4.5절)이고, 360px에서도 한 줄이어야 합니다.
- EN 상태 줄('Today Tue 9/29 · Weekday timetable · as of 17:47')이 360px에서 2줄을 넘지 않는지 검증합니다.
- `html { scroll-padding-top: var(--tt-controls-h) }`, `[id] { scroll-margin-top: calc(var(--tt-controls-h) + 8px) }`(SC 2.4.11).
- 격자는 모바일에서 시간대 목록 레이아웃(`ul` 기반), 데스크톱에서 `table.timetable-grid`입니다. 두 레이아웃 모두 같은 마크업 클래스(`timetable-grid`)를 유지합니다. **[가정]** 한 마크업에 CSS 레이아웃만 전환하는 방식을 우선하고, 불가능하면 표를 유지한 채 행 높이만 줄입니다.

### 5.3 `/timetable` 데스크톱(721px 이상)

- 사이드바를 상시 노출하고 main은 max-width 900px입니다(확장은 D17에서 범위 밖으로 권장). 컨트롤은 일반 흐름이고 sticky가 아닙니다.
- '다음 출발'은 격자 위 가로 5칸 카드, 513 경유 패널은 2열입니다.
- 격자 토큰에 행선 소표기를 붙입니다('55 · 713 743 명촌').
- 목적지 거점 칩과 노선 칩은 펼친 상태로 둡니다.

### 5.4 `/timetable?dir=in`

평일 17시 실데이터 예시입니다.

```
┌ 상태 줄 ─ 오늘 9/29(화) · 평일 시간표 · 17:47 기준 ┐
│ [ UNIST에서 출발 ][ UNIST로 도착 ✓ ]              │
│ 어디서? [명촌에서 713 743 753][꽃바위에서 1115]     │
│         [덕하에서 513 경유][삼남·울산역에서 513 경유]│
│ ⓘ 아래 시각은 각 기점의 출발 시각입니다. UNIST 도착은 이보다 늦습니다. │
│   중간 정류장(삼산·공업탑 등)에서 타신다면 실시간 도착 보기 → /stops   │
│ caption: 평일 · UNIST로 도착 · 기점 출발 시각       │
│ 17시 | 명촌에서: 00 743 · 05 713 753 · 25 753 · 40 713 753 · 50 743 | 꽃바위에서: 30 1115 │
└──────────────────────────────────────────────────┘
```

- **다음 출발 섹션과 카운트다운을 렌더하지 않습니다.** 모든 토큰이 basis=origin이기 때문입니다(N-1, 신뢰 심사관 must-fix). B의 "기점 탑승자에게는 카운트다운 허용"은 D6의 하위 선택지로 남깁니다.
- 첫차 전과 운행 종료에는 `tt.in.before_first`/`tt.in.end_of_day` 문구를 씁니다(5.6).
- D1 (b)/(c) 승인 후에는 caption에 'UNIST 도착 예상은 약 N분 뒤(추정)'를 추가할 수 있습니다(Phase 4).

### 5.5 `/busno` 모바일

```
┌ topbar: 노선별 시간표 ─────────────────────┐
│ 상태 줄                                    │
│ 노선 [513 울산역/덕하][713 명촌✓][743 명촌][753 명촌][1115 꽃바위] │ ← href에 dep 없음
│ 방향 [ UNIST → 명촌(시내) 방면 ✓ ][ 명촌 → UNIST 방면 ] │ ← 칩 2개, select 폐지
│ 요일 [평일✓ 오늘][토][일·공휴일]            │
│ 승차: UNIST(기점) 정류장 · 기준: 이 정류장 출발 시각 │
│   정문(시내) 정류장에서도 탑승 가능 · 표시 시각은 UNIST(기점) 기준 │ ← also_stops_at, [가정] 운영자 확인
│ 다음 17:55 · 8분 후 · 그다음 18:25, 18:45    │ ← 오늘 + basis=unist일 때만
│ 첫차 05:00 · 막차 22:45 · 평일 42편 · 가장 긴 간격 40분 │
│ caption: 713 · UNIST → 명촌(시내) 방면 · 평일 │
│ 05시 │ 00 · 30 ...                          │ ← <table class="timetable"> 정확한 속성 유지
│ ...  │                                      │
│ 17시 지금 │ 25(지난 편) · 55 다음             │
│ 경유: 천상 - 구영리 - … - 명촌 (VIA_STOPS['713']['명촌']) │
│ 실시간 도착 보기 →                           │
└───────────────────────────────────────────┘
```

513 `to=ulsan-station`(덕하 기점, 평일 실데이터):

- 방향 칩: '덕하 → UNIST 경유 → 삼남(울산역)' / '삼남 → UNIST 경유 → 덕하(시내)'.
- 기준 안내: '덕하 기점 출발 시각 · UNIST(울산과학기술원 경유)는 8번째 정류장 · 통과 시각은 이보다 늦습니다'.
- 다음 편 표기: '다음 기점 출발 18:30'. 카운트다운 없음.
- 요약: '첫차 05:20 · 막차 22:00 · 28편 · 가장 긴 간격 90분(08:20–09:50)'. **동률 규칙은 첫 발생 채택**이고(6.1 `summarize`), 실데이터에는 08:20–09:50과 12:40–14:10 두 개의 90분 간격이 있습니다. 동률이 있으면 요약 뒤에 '외 1회'를 붙입니다(`tt.summary_ties`). 표에는 '13시 · 운행 없음(다음 편까지 90분)' 행을 둡니다(12:40→14:10 공백으로 13시 행이 없음. 08:20→09:50은 09시에 09:50이 있으므로 빈 행이 생기지 않음).
- 삼남 기점: UNIST는 4번째 정류장, 가장 긴 간격 90분(06:00–07:30, 첫 발생. 10:30–12:00과 동률 → '외 1회'), 11시 행 없음 → '운행 없음' 행.

그 밖의 규칙:

- ≤480px에서는 `table.timetable`을 가로 스크롤 규칙에서 빼고 폭 100%로 둡니다. 특이도 충돌(`style.css:917` vs `:706`)도 해소합니다(MR-3). 추가 클래스는 감싸는 div에 줍니다.
- 경유지는 `DirectionSpec.terminal_key`로 조회합니다(M-6).

### 5.6 상태 매트릭스

각 행은 8.1의 '상태 매트릭스 × 언어' 계약 테스트의 한 케이스입니다. fixture ID는 `tests/fixtures/timetable/states.py`에 둡니다(P1-3에서 뼈대, 이후 Phase마다 추가).

| 상태 | 판정 | `/timetable` | `/busno` | i18n 키 · fixture | 도입 |
|---|---|---|---|---|---|
| 오늘(기본) | `is_today` | 다음 출발(dir=out), `#now`, past/next, 'HH:MM 기준' | 다음 편 카드(basis=unist), `#now` | `tt.status.today` · `F-today-1747` | P1(상태 줄), P3(다음) |
| 다음 출발 부족 | 오늘 & 남은 편 < N(5) (예: 22:30) | 남은 편 + **내일 첫차 1편**('내일 05:00' 표기, 카운트다운 없음) | 남은 편 + '내일 첫차 HH:MM' | `tt.next.tomorrow` · `F-2230` | P3 |
| 다른 날 또는 대표 편성 | `day≠오늘 코드` 또는 `date≠오늘` | 다음 출발 없음, `id=now` 0개, 모든 토큰 neutral, 상태 줄 '…을 보고 있습니다 · 오늘 시간표로' | 같음 | `tt.status.viewing_other` · `F-other-day` | P0(분리), P1 |
| 과거 날짜 조회 | `date` ∈ [오늘−7, 오늘−1] | '{date} 편성(지난 날짜)을 보고 있습니다 · 오늘 시간표로'. 모든 토큰 neutral | 같음 | `tt.status.past_date` · `F-date-past` | P3 |
| 첫차 전 | 오늘 & now < 당일 첫 편 | '첫차 05:00(713·753·1115 명촌/꽃바위 방면)까지 N분' + 첫 3편 | '첫차 HH:MM까지 N분' | `tt.before_first` · `F-0430` | P3 |
| 운행 종료 | 오늘 & now > 당일 마지막 편(평일 UNIST 기점 22:50 1115) | '오늘 UNIST 출발 버스는 끝났습니다 · 내일 {date} 첫차 05:00 · [내일 시간표]'(P3 전에는 `day=내일 코드`, 이후 `date=내일`). 격자는 접지 않고 모두 past. 513 패널은 '마지막 기점 출발 22:00(덕하) · 실시간 위치 보기'를 유지(M-1 원칙) | 같은 방식 | `tt.end_of_day` · `F-2255` | P3 |
| 513 경유 패널: 최근 편 없음 | 오늘 & now < 방향별 첫 기점 출발(예: 05:10) | 해당 블록에 '첫 덕하 출발 05:20' + 다음 2편 | 513 방향에서 '첫 기점 출발 HH:MM' | `tt.via.first` · `F-0510` | P2 |
| 513 경유 패널: 그날 513 없음 | 특별편에 513 파일·키 없음, 폴백도 0편 | '오늘 513 운행 정보 없음 · 실시간 위치 보기'(빈 블록을 조용히 숨기지 않음) | `tt.no_service` | `tt.via.no_service` · `F-special-no513` | P2 |
| `dir=in` 첫차 전 / 운행 종료 | 오늘 & 기점 첫 편 전 / 마지막 편 후 | '명촌 첫 출발 05:00까지 N분' / '오늘 UNIST로 오는 버스의 기점 출발은 끝났습니다 · 내일 첫 출발 HH:MM'. 카운트다운은 첫차 전 문장의 N분만(기점 기준임을 명시) | — | `tt.in.before_first`, `tt.in.end_of_day` · `F-in-0430`, `F-in-2330` | P2 |
| 필터 결과 0편 | `hub`/`routes`/`origin` 적용 뒤 0편(예: 특정 거점 + 주말 미운행 fixture) | '선택한 조건에 맞는 버스가 없습니다 · [필터 해제]'(필터 파라미터를 뺀 URL 링크). 격자 자리에 빈 상태 1개 | — | `tt.filter.empty` · `F-hub-empty` | P2(hub), P3(routes) |
| 알 수 없는 필터 값 | `routes=999`, `routes=`(빈 값), `hub=xx` | 알 수 없는 값은 버리고 notice 1건. 유효 값이 없으면 필터 없음 | — | `notice.invalid_routes`, `notice.invalid_hub` · `F-bad-filter` | P2, P3 |
| 파라미터 교차 오용 | `dir=in&hub=…` 또는 `dir=out&origin=…` | 해당 파라미터를 무시 + notice 1건 | — | `notice.param_ignored` · `F-cross` | P2 |
| 특별편 적용 | `source.reason=='special'` | 상태 줄 '오늘 특별 시간표 적용 중({edition_label})'. 폴백 노선이 있으면 '· {routes}는 평시 평일 시간표로 표시'(DS-5). D3 이후 '[평시 시간표 보기]'(`edition=base`) | 같음 | `tt.status.special`, `tt.status.special_fallback` · `F-special`, `F-special-partial` | P1 |
| 공휴일 | `reason=='holiday'` | '오늘 10/5(월)은 공휴일이라 일요일·공휴일 시간표를 적용합니다'(이름은 저장하지 않으므로 쓰지 않음, D12) | 같음 | `tt.status.holiday` · `F-holiday-1005` | P1 |
| 공휴일 캐시 범위 밖 | `holiday_known==False` | info-banner '공휴일 정보가 아직 없어 요일 기준으로 표시합니다' | 같음 | `tt.status.holiday_unknown` · `F-cache-gap` | P1 |
| 데이터 경과·학사 모드 불일치 | `today − crawled_at > N일`(N은 D12, 권장 120) 또는 `_meta.vacation`과 운영자가 admin에 입력한 현재 학사 모드(D12) 불일치 | info-banner '시간표 수집일({date})로부터 {n}일이 지났습니다 · 학기/방학 편성이 바뀌었을 수 있습니다'. `_meta.json`이 없으면 배너 없음 | 같음 | `tt.status.stale`, `tt.status.mode_mismatch` · `F-stale`, `F-mode-mismatch` | P3 |
| 토·일 동일 | 전 노선 `d['1']==d['2']` | 탭은 유지하고 칩 아래 '현재 데이터상 토요일과 일·공휴일 시간표가 같습니다'(D8) | 같음 | `tt.status.sat_eq_sun` · `F-sat-eq-sun` | P3 |
| 노선 데이터 누락 | `missing_routes` | 해당 위치와 범례에 '743 시간표를 불러오지 못했습니다(운행 여부와 무관)'. 범례에서 조용히 빼지 않음(DS-14) | 표 자리에 같은 문구 | `tt.route_missing` · `F-missing-743` | P1 |
| 전체 비어 있음 | 모든 노선 실패 | '시간표 데이터를 불러오지 못했습니다. 실시간 출발 게시판을 확인하세요 →' / 'No timetable data available.'(F08 AC-5) | 같음 | `tt.empty` · `F-empty` | P1 |
| 해당 날짜 미운행 | 편성 0(현재 데이터에는 없음, 특별편에서 가능) | '이 노선은 {날짜}에 운행하지 않습니다' | 같음 | `tt.no_service` · `F-no-service` | P1 |
| 방향 없음(레거시 조합) | notice `dir_not_available` | — | '713번에는 덕하 출발편이 없어 UNIST 출발 시간표를 표시합니다'(role=status) | `notice.dir_not_available` · `F-legacy-dep` | P2 |
| 잘못된 요일 | `day=9`, `day=abc` | 평일 + notice | 같음 | `notice.invalid_day` · `F-bad-day` | P1 |
| 잘못된 파라미터 | warning | '요청한 값을 알 수 없어 기본 화면을 표시합니다' | '유효하지 않은 버스번호입니다: 999 — 기본 노선을 표시합니다' | `warn.invalid_bus`, `warn.invalid_dep` · `F-bad-param` | P0 |
| JS 꺼짐 | — | 서버 렌더값 + 'HH:MM 기준 [새로고침]'. 모든 조작 가능, 지난 시간은 `<details>` | 같음 | — · `F-nojs`(기본 test client) | P3 |
| JS 켜짐(D11) | `[data-now-root]` | 다음 분 경계에 맞춘 setTimeout으로 state/ETA 재계산, 'HH:MM · 자동 갱신'. aria-live 없음. `pageshow(persisted)`·`visibilitychange`에서 즉시 재계산. 서버 epoch로 시계 오차 보정. KST 날짜가 바뀌면 '시간표가 바뀌었을 수 있습니다 · 새로고침' 배너 | 같음 | `tt.auto_refresh`, `tt.day_changed` · 수동 | P3(선택) |

### 5.7 문구 표(i18n 키, ko / en)

| 키 | ko | en |
|---|---|---|
| `page.timetable.title` | UNIST 전체 시간표 | UNIST Timetable |
| `page.busno.title` | 노선별 시간표(`<title>`에는 '버스번호별 시간표' 마커 병기) | Timetable by Route |
| `lang.switcher` | 언어 선택 | Language |
| `nav.label.main` / `nav.menu_open` / `nav.menu_close` / `nav.skip` | 주 메뉴 / 메뉴 열기 / 메뉴 닫기 / 본문으로 건너뛰기 | Main menu / Open menu / Close menu / Skip to content |
| `tt.dir.out` / `tt.dir.in` | UNIST에서 출발 / UNIST로 도착 | From UNIST / To UNIST |
| `tt.dir.group` | 방향 | Direction |
| `tt.hub.q` / `tt.origin.q` | 어디로? / 어디서? | Where to? / From where? |
| `tt.status.today` | 오늘 {date} · {edition} · {time} 기준 | Today {date} · {edition} · as of {time} |
| `tt.status.viewing_other` | {edition}을 보고 있습니다 · 오늘 시간표로 | Viewing the {edition} · Back to today |
| `tt.status.past_date` | {date} 편성(지난 날짜)을 보고 있습니다 · 오늘 시간표로 | Viewing a past date ({date}) · Back to today |
| `tt.status.holiday` | 오늘 {date}은 공휴일이라 일요일·공휴일 시간표를 적용합니다 | Today ({date}) is a public holiday — showing the Sunday/holiday timetable |
| `tt.status.special` | 오늘 특별 시간표 적용 중({label}) | Special timetable in effect today ({label}) |
| `tt.status.special_fallback` | {routes}는 평시 평일 시간표로 표시합니다 | {routes}: shown with the regular weekday timetable |
| `tt.status.base_view` | 평시 시간표를 보고 있습니다 · 오늘 특별 시간표로 | Viewing the regular timetable · Back to today's special timetable |
| `tt.status.holiday_unknown` | 공휴일 정보가 아직 없어 요일 기준으로 표시합니다 | Holiday data unavailable — showing by day of week |
| `tt.status.stale` | 시간표 수집일({date})로부터 {n}일이 지났습니다 · 학기/방학 편성이 바뀌었을 수 있습니다 | Timetable collected {n} days ago ({date}) — term/vacation schedules may have changed |
| `tt.status.mode_mismatch` | 현재 {mode} 편성으로 수집된 시간표입니다 · 실제 운행과 다를 수 있습니다 | This timetable was collected for the {mode} schedule and may differ from current service |
| `tt.status.sat_eq_sun` | 현재 데이터상 토요일과 일·공휴일 시간표가 같습니다 | Saturday and Sunday/holiday timetables are currently identical |
| `day.0.long` / `day.1.long` / `day.2.long` | 평일 시간표 / 토요일 시간표 / 일요일·공휴일 시간표 | Weekday / Saturday / Sunday & holiday timetable |
| `day.0.short` … | 평일 / 토 / 일·공휴일 | Weekday / Sat / Sun·Hol |
| `dow.0` … `dow.6` | 월 … 일 | Mon … Sun |
| `fmt.date_short` | {m}/{d}({dow}) | {dow} {m}/{d} |
| `tt.next.heading` | 다음 출발 · {time} 기준 | Next departures · as of {time} |
| `tt.next.tomorrow` | 내일 {time} | Tomorrow {time} |
| `tt.eta.soon` / `tt.eta.min` / `tt.eta.hm` | 곧 출발 / {n}분 후 / {h}시간 {m}분 후 | Departing now / in {n} min / in {h} h {m} min |
| `tt.state.next` / `tt.state.past` / `tt.now_tag` | 다음 / 지난 편 / 지금 | Next / Departed / Now |
| `tt.sr.token` | {h}시 {m}분 {bus}번 {dest} 방면 | Route {bus} to {dest} at {h}:{m} |
| `tt.dir.towards` | {stop} 방면 | To {stop} |
| `tt.dir.pair` / `tt.dir.via` | {origin} → {dest} 방면 / {origin} → UNIST 경유 → {dest} | {origin} → {dest} / {origin} → via UNIST → {dest} |
| `tt.basis.unist` | UNIST(기점) 정류장 출발 시각 | Departure times at UNIST (terminus) |
| `tt.basis.origin` | {origin} 기점 출발 시각 · UNIST 통과(도착)는 이보다 늦습니다 | Departure times from {origin} · reaches UNIST later |
| `tt.basis.estimated` | 약 {time} UNIST 통과(추정) | approx. {time} at UNIST (estimated) |
| `tt.boarding.also` | {stop} 정류장에서도 탑승 가능 · 표시 시각은 {basis_stop} 기준 | You can also board at {stop} · times shown are for {basis_stop} |
| `tt.via.recent` | 최근 {origin} {time} 출발 | Last left {origin} at {time} |
| `tt.via.first` | 첫 {origin} 출발 {time} | First departure from {origin} at {time} |
| `tt.via.all` | {origin} 출발 전체 시각({n}편) | All departures from {origin} ({n}) |
| `tt.via.no_service` | 오늘 513 운행 정보 없음 | No route 513 service data today |
| `tt.via.hint` | UNIST 통과 여부는 실시간 위치에서 확인하세요 → | Check live positions for when it reaches UNIST → |
| `unist.via.origin_dep` | {origin} {time} 출발 | Leaves {origin} at {time} |
| `tt.before_first` | 첫차 {time}까지 {n}분 | First bus at {time} (in {n} min) |
| `tt.end_of_day` | 오늘 UNIST 출발 버스는 끝났습니다 · 내일 {date} 첫차 {time} | No more departures today · First bus tomorrow ({date}) at {time} |
| `tt.in.before_first` | {origin} 첫 출발 {time}까지 {n}분(기점 기준) | First departure from {origin} at {time} (in {n} min, at origin) |
| `tt.in.end_of_day` | 오늘 UNIST로 오는 버스의 기점 출발은 끝났습니다 · 내일 첫 출발 {time} | No more departures towards UNIST today · First tomorrow at {time} |
| `tt.filter.empty` / `tt.filter.clear` | 선택한 조건에 맞는 버스가 없습니다 / 필터 해제 | No buses match your filters / Clear filters |
| `tt.past.expand` | 지난 시간 {from}–{to}시 펼치기({n}편) | Show earlier hours {from}–{to} ({n}) |
| `tt.gap_row` | 운행 없음(다음 편까지 {n}분) | No service (next in {n} min) |
| `tt.summary` | 첫차 {first} · 막차 {last} · {count}편 · 가장 긴 간격 {gap}분({from}–{to}) | First {first} · Last {last} · {count} trips · Longest gap {gap} min ({from}–{to}) |
| `tt.summary_ties` | 외 {n}회 | and {n} more |
| `tt.route_missing` | {bus} 시간표를 불러오지 못했습니다(운행 여부와 무관) | Couldn't load the {bus} timetable (not a service change) |
| `tt.no_service` | 이 노선은 {date}에 운행하지 않습니다 | No service on {date} |
| `tt.empty` | 시간표 데이터를 불러오지 못했습니다. 실시간 출발 게시판을 확인하세요 | No timetable data available. |
| `notice.dir_not_available` | {bus}번에는 이 방향이 없어 {dir} 시간표를 표시합니다 | Route {bus} has no such direction — showing {dir} |
| `notice.invalid_day` | 요일 값이 올바르지 않아 평일 시간표를 표시합니다 | Invalid day — showing the weekday timetable |
| `notice.invalid_dir` / `notice.invalid_hub` / `notice.invalid_routes` | 알 수 없는 방향/목적지/노선 값을 무시했습니다 | Ignored an unknown direction/destination/route value |
| `notice.param_ignored` | 이 방향에서는 '{param}' 조건을 쓰지 않아 무시했습니다 | '{param}' doesn't apply to this direction and was ignored |
| `notice.date_out_of_range` | 조회할 수 없는 날짜라 오늘 시간표를 표시합니다 | Date out of range — showing today |
| `warn.invalid_bus` | 유효하지 않은 버스번호입니다: {value} — 기본 노선을 표시합니다 | Unknown route {value} — showing the default route |
| `warn.invalid_dep` | 알 수 없는 출발지입니다: {value} — 기본 방향을 표시합니다 | Unknown origin {value} — showing the default direction |
| `warn.data_error` | 실시간 정보를 일시적으로 가져오지 못했습니다 | Live data is temporarily unavailable |
| `board.notice.743.upcoming` / `board.notice.743.active` | 10월 3일부터 743번은 구영리에서 범서중학교를 경유합니다 (…) / 743번은 구영리에서 범서중학교를 경유합니다 (…) | From Oct 3, bus 743 passes … / Bus 743 passes Beomseo Middle School … |
| `tt.footer.source` | 울산 BIS 기점 출발 시간표 · {date} 수집 · {mode} 편성 | Ulsan BIS origin departure timetable · collected {date} · {mode} schedule |
| `tt.link.live_out` / `tt.link.live_in` | 실시간 출발 보기 / 실시간 도착 보기 | Live departures / Live arrivals |

지명 EN 표기는 ADR-014(draft) RR 규칙을 따릅니다: Deokha, Samnam, Myeongchon, Kkotbawi, UNIST, 울산역은 'Ulsan Station (KTX)'(D15). 사전이 구현되기 전에는 `place.*` 임시 키를 쓰고, 번역이 없으면 `<span lang="ko">`로 폴백합니다.

---

## 6. 도메인·데이터 설계

### 6.1 신규 순수 모듈 `bushexa/domain/timetable_view.py`

외부 I/O는 없고 Clock을 주입받습니다. `get_busroute_info`는 건드리지 않습니다.

```python
Basis = Literal['unist', 'origin', 'estimated']
UnistRelation = Literal['departs', 'passes', 'arrives']
DirSlug = Literal['downtown', 'unist', 'ulsan-station']

@dataclass(frozen=True)
class DirectionSpec:
    route_id: str; busno: str
    origin_ko: str               # ROUTEID[2] '덕하'
    terminal_ko: str             # ROUTEID[1] '삼남 (울산역) 방면'
    terminal_key: str            # VIA_STOPS 조회 키('삼남'). dep 키 역전 방지(M-6)
    slug: DirSlug                # /busno ?to=
    unist_relation: UnistRelation
    view: Literal['out', 'in', 'both']   # 513은 'both'(경유)
    boarding_stop_id: str | None # '196040233'(기점) | '196040234'(경유) | None(in)
    also_stops_at: tuple[str, ...] = ()  # UNIST 권역의 추가 승차 정류장. 예: ('196040231',) 정문(시내)
    unist_stop_index: int | None = None  # 513 덕하=7(8번째), 삼남=3(4번째), 0-based
    basis: Basis = 'origin'      # departs → 'unist', 그 외 → 'origin'

def direction_specs() -> tuple[DirectionSpec, ...]
    # ROUTEID.items()에서 **데이터로** 판정한다(순서 의존 제거):
    #  stops[0]=='196040233' → departs/out/unist
    #  stops[-1]=='999000145' → arrives/in/origin
    #  UNIST_VIA_STOP_ID in stops[1:-1] → passes/both/origin
    #  also_stops_at: boarding 이후 UNIST 권역 정류장(196040231) 중 stops에 있는 것
def spec_for(busno, *, to=None, dep=None) -> tuple[DirectionSpec, list[NoticeCode]]
def default_spec(busno) -> DirectionSpec    # D10 규칙을 명시

@dataclass(frozen=True)
class Departure:
    time: str; minute_of_day: int; busno: str; route_id: str
    slug: DirSlug; basis: Basis; origin_ko: str
    state: Literal['past', 'next', 'upcoming', 'neutral'] = 'neutral'
    minutes_until: int | None = None
    merged_busnos: tuple[str, ...] = ()
    is_tomorrow: bool = False
    est_unist_time: str | None = None        # Phase 4, 승인 시에만

@dataclass(frozen=True)
class HourGroup:
    hour: int; departures: tuple[Departure, ...]
    is_current: bool = False; is_gap: bool = False; gap_minutes: int | None = None

@dataclass(frozen=True)
class ServiceSummary:
    first: str | None; last: str | None; count: int
    max_gap_min: int | None; gap_from: str | None; gap_to: str | None
    gap_ties: int = 0            # 같은 최대 간격의 추가 발생 수(첫 발생을 gap_from/to로 채택)

NoticeCode = tuple[str, dict]   # ('invalid_bus', {'value': '999'}) 등. 도메인은 문장을 만들지 않음
NOTICE_CODES: frozenset[str]    # 도메인이 낼 수 있는 모든 코드. TRANSLATIONS의 notice.*/warn.*와 1:1 대조(8.1)

# 순수 헬퍼. board.py:125 _hhmm_to_minutes, unist_board.py:45 _is_future 등 사본 4벌을 여기로 수렴(TF-11)
def hhmm_to_min(t) -> int
def classify_now(deps, now_min, *, is_today) -> tuple[Departure, ...]
    # is_today가 False면 모두 neutral. next와 minutes_until은 basis∈{unist, 승인된 estimated}만 계산
def next_n(deps, now_min, n=5, *, tomorrow_first: Departure | None = None) -> tuple[Departure, ...]
    # 남은 편이 n 미만이면 tomorrow_first를 is_tomorrow=True, minutes_until=None으로 1편 덧붙인다
def origin_window(deps, now_min, *, recent=1, upcoming=2) -> tuple[Departure, ...]
    # 기점 시각 > now 필터로 '막 떠난 편'을 숨기지 않는다(M-1, 신뢰 심사 must-fix)
def group_by_hour(deps, *, fill_gaps: bool, span=(5, 22), gap_threshold=45) -> tuple[HourGroup, ...]
def summarize(times) -> ServiceSummary
    # 최대 간격 동률: 시간순 첫 발생을 채택하고 나머지 수를 gap_ties에 기록(결정론적)
def effective_unist_time(spec, t, offsets) -> tuple[str | None, Basis]
    # unist → (t, 'unist'); origin + 승인 오프셋 → (t+Δ, 'estimated'), 단 23:59를 넘으면 (None, 'origin');
    # 그 외 → (None, 'origin')
DESTINATION_HUBS: Mapping[str, HubDef]   # 4.5절. 키 → (label_key, ((busno, slug), ...), stop_ids)
```

`origin_window`는 **도착했다고 주장하지 않습니다**. 표시는 '최근 {origin} {time} 출발'과 실시간 링크뿐입니다. 창의 폭(recent=1편)은 오프셋 데이터 없이도 성립하는 규칙이라 N-1과 충돌하지 않습니다.

### 6.2 편성 출처 `bushexa/services/board_support.py`

```python
class FallbackLog:
    """요청 범위의 가변 수집기. provider가 폴백할 때 노선을 기록한다. 요청마다 새로 만든다."""
    def __init__(self): self.routes: list[str] = []
    def record(self, busno: str) -> None: ...

@dataclass(frozen=True)
class TimetableSource:
    provider: Callable
    fallback_log: FallbackLog                  # provider와 같은 요청 범위 인스턴스
    target_date: date | None; today_code: int; day_code: int; is_today: bool
    reason: Literal['weekday', 'saturday', 'sunday', 'holiday', 'special', 'representative', 'base']
    edition_id: str | None = None; edition_label: str | None = None
    holiday_known: bool = True                 # 대상 월이 holiday_cache 또는 admin 지정 범위 안인가

def resolve_timetable_source(config, today, holiday_set, *,
                             requested_day: int | None,
                             requested_date: date | None = None,
                             force_base: bool = False) -> TimetableSource
```

- 폴백 노선 수집: 어떤 노선이 폴백됐는지는 도메인이 provider를 호출한 **뒤에야** 알 수 있습니다. 그래서 frozen 필드가 아니라 `FallbackLog`에 기록합니다. 라우트는 도메인 호출이 끝난 뒤 `ScheduleStatus(fallback_routes=tuple(source.fallback_log.routes), …)`를 만들어 템플릿에 넘깁니다. 클로저 공유 상태나 모듈 전역은 금지합니다(요청마다 새 인스턴스, 스레드 안전).
- 기존 `timetable_provider_for(...)`는 `resolve_timetable_source(...).provider`를 반환하는 얇은 래퍼로 남깁니다. `test_board_support.py`와 `/board` 경로는 영향을 받지 않습니다. 폴백 규칙(weekday 0) 자체는 바꾸지 않고 표시만 합니다. 규칙 변경은 D3-ii(P4-5)에서 정합니다.
- 특별편 규칙: P0~P1에서는 기존 규칙(`requested_day is None`일 때만)을 그대로 두고, **링크 정규화**(P0-4)로 완화합니다. P2에서는 ADR-015/D3 승인 시 `requested_day == today_code`일 때도 특별편을 적용합니다. `test_holiday_and_special_precedence`의 '특별편 > 공휴일' 우선순위는 바뀌지 않습니다.
- `edition_label`: 에디션 ID 형식은 `special_timetable.py:39`의 `_EDITION_ID_RE = ^[A-Za-z0-9_-]{1,64}$`로 **ASCII 슬러그**입니다. 그래서 `edition_label=edition_id`이면 KO 화면에도 `chuseok-2026` 같은 슬러그가 그대로 보입니다. D3(iii)의 사람이 읽을 라벨(`_edition.json {label_ko, label_en}`)이 필요한 이유이고, 라벨이 없으면 '특별 시간표'로만 표기하고 슬러그는 `<code>`로 보조 표기합니다.
- `holiday_known`: 대상 날짜의 `YYYYMM` 키가 `holiday_cache.json`에 있는지 검사합니다. 현재 `read_effective_holidays`/`HolidayCache.load()`는 날짜 set만 돌려주므로(`holiday_service.py:128-135`), `services/holiday_service.py`에 `cached_months(data_dir) -> set[str]`를 추가합니다(P1-2). 없으면 상태 줄 경고와 admin 대시보드 경고를 냅니다.

### 6.3 스냅샷의 추가형 확장(모두 기본값)

- `FullTimetableSnapshot +=` `status: ScheduleStatus | None = None`, `view: str = 'out'`, `grid_groups: tuple[HourGroup, ...] = ()`, `via_sections: tuple[ViaSection, ...] = ()`, `next_departures: tuple[Departure, ...] = ()`, `service_state: str = 'n/a'`, `first_of_next_day: Departure | None = None`, `missing_routes: tuple[str, ...] = ()`, `notices: tuple[NoticeCode, ...] = ()`, `hubs: tuple = ()`, `sat_eq_sun: bool = False`, `data_meta: dict | None = None`.
  - 기존 `timetable_rows`와 `bus_legend`는 계속 채웁니다. 템플릿은 `grid_groups`가 비어 있으면 `timetable_rows`로 렌더합니다(N-8, `test_unist_timetable_route.py:77-79`의 '07'·'08' 보존).
  - P2부터 `timetable_rows`에서 513을 빼고 `via_sections`로 옮깁니다. 격자 단언은 `'bus-713'`뿐이라(grep 확인) 기존 테스트와 충돌하지 않습니다. `deps[0]`을 전제한 fixture 주석은 같은 PR에서 갱신합니다.
- `BusnoTimetable +=` `status=None`, `selected_spec: DirectionSpec | None = None`, `direction_options: tuple[tuple[str, str], ...] = ()`(P0-2, `(dep, label)`), `hour_groups: tuple = ()`, `summary: ServiceSummary | None = None`, `next_items: tuple = ()`, `notices: tuple = ()`, `canonical_url: str | None = None`, `today_code: int | None = None`(P0-4).
  - `minutes: str`('00, 30')과 `warning: str | None`은 유지합니다. `warning`에는 사용자 입력 오류만 repr 없는 KO 호환 문구로 채웁니다('유효하지 않은 버스번호' 포함).
  - 템플릿 폴백: `direction_options`가 비어 있으면 `terminals`의 기점명을 라벨로 씁니다. `hour_groups`가 비어 있으면 `timetable_rows`로 렌더합니다.
- `ScheduleStatus`(뷰용): `today`, `now_hhmm`, `today_code`, `selected_day`, `is_today_view`, `reason`, `edition_id`, `edition_label`, `holiday_known`, `fallback_routes`, `sat_eq_sun`, `stale_days: int | None = None`, `mode_mismatch: bool = False`.
- `WEEKDAY_STR`와 `_DAY_OPTIONS`는 KO 폴백 상수로만 남기고, 템플릿은 `t('day.N.*')`를 씁니다. `weekday_str` 필드는 '선택한 요일'이라는 의미로 유지하되 '현재 시각' 옆에서는 쓰지 않습니다.

### 6.4 라우트

- 두 라우트 모두 `resolve_timetable_source`를 한 번만 호출하고, `today_code = get_weekday(today, holiday_set)`를 계산해 도메인에 키워드 인자(기본값 None)로 넘깁니다(P0-4).
- 숫자가 아닌 `day`는 라우트가 0으로 바꾸기 전에 `day_invalid=True`를 기록해 도메인에 넘깁니다(P1-7).
- 새 인자는 전부 키워드 인자이고 기본값을 둡니다. 모듈 수준 `get_full_timetable_data`·`get_busno_page_data` 심볼은 patch 대상이므로 유지합니다.
- 응답 헤더에 `Cache-Control: no-cache`, `Vary: Cookie`를 붙입니다. 현재 공개 라우트에는 Cache-Control이 없습니다(`admin.py:733,799`에만 있음).
- 라우트가 `KSTClock()`을 직접 생성하므로(`routes/unist_timetable.py`, `routes/busno.py`), 테스트는 `freeze_kst`와 `tt_env` fixture를 씁니다(7장 P0-1a).

### 6.5 513 UNIST 시각 처리 결정지(D1)

| 옵션 | 내용 | 데이터·운영 요구 | 장점 | 위험 |
|---|---|---|---|---|
| **(a) 기점 라벨+분리** | basis=origin. 격자·카운트다운·FIRST에서 빼고 경유 패널에 두 방향 모두 표시. `origin_window` + 실시간 링크 | 없음 | 거짓 정보 0, 영구 운영 가능 | T2의 '언제 지나가나'에 직접 답하지 못함 |
| (b) 관리자 고정 오프셋 | `timetable_offsets.json`에 route_id별 분 값, '약 HH:MM(추정)' | admin 폼, 백업 등록 | 단순 | 첨두·계절 편차 미반영. phase1 감사 시점 근거(n≈5~6, 11~16시)로는 부족 |
| **(c) 운행 이력 산출** | 야간 워커가 `bus_timelog`에서 요일 유형 × 시간대별 중앙값·IQR·n 산출 → 제안값 → 관리자 승인 | 운영 DB 보존 기간·표본 확인(**go/no-go 선행 조건**), recorder의 present_stop 의미 확인 | 실측 기반 | 로그 기점 목격 시각이 시간표와 어긋난 사례가 있음(DS MISSED #1: 덕하 13:10 목격이 12:40→14:10 공백 안) |
| (d) BIS 경유 시각 API 조사 | 경유 정류소 기준 시각표가 있으면 (a)~(c)를 대체 | 조사 1회 | 권위 소스 | 존재 여부 미확인 |

**권장:**

- P1~P3은 (a)로 운영합니다. (a)만으로도 **영구 운영이 가능해야** 합니다(엔지니어링 심사의 운영자 부담 상한).
- P4 착수 여부는 go/no-go로 정합니다. 운영 `bus_timelog`와 저장소 `data/logs.tsv`(현재 1,095행) 재집계에서 방향 × 시간대(첨두 07–09·17–19 **필수** 포함)별 n ≥ 30, IQR ≤ 15분을 확인합니다. B의 n≥30을 채택했고 C의 n≥20보다 보수적이며, 수치는 D1에서 확정합니다. 현재 참고값은 덕하 방향 약 59분, 삼남 방향 약 42~45분입니다.
- 통과하면 (c) 제안 → 관리자 승인(`approved_by`) → '약 18:25~18:40' 범위 표기와 점선 route-mark로 격자와 다음 출발에 합류합니다.
- 게이트에 못 미치는 시간대는 자동으로 (a)로 되돌립니다. 오프셋을 더해 23:59를 넘는 편은 제외합니다(`hh≤23` 제약).
- 같은 결정지를 `dir=in` 전 노선에도 적용합니다.
- no-go면 TF-2는 'WND by design'으로 닫고 (a)를 영구 운영합니다(12장).

### 6.6 사이드카 데이터

| 파일 | 내용 | 쓰기 | 백업 | Phase |
|---|---|---|---|---|
| `data/timetable/_meta.json` | `{crawled_at, vacation, source:'ulsan-bis', crawled_by}` | 크롤러가 `{busno}.json`과 함께 `atomic_write_json`. get_timetable 경로와 충돌 없음(glob 코드 없음 확인) | **제외**. 크롤 산출물이고 평면 `timetable/*.json`도 백업 대상이 아님(`backup.py:28-35` `_FLAT_FILES`는 data_dir 평면 파일만, `:44-67` `_is_safe_path`는 `timetable/special/` 접두어만 허용). 엔지니어링 심사 must-fix | 1 |
| `data/notices.json` | `[{id, routes, start, end, ko, en}]`. 기간 게이트 적용 | admin 편집, atomic | `_FLAT_FILES`에 추가 + 복구 라운드트립 테스트 | 4 |
| `data/timetable_offsets.json` | `{version, updated_at, entries:[{route_id, to_stop, band, minutes, n, iqr, source, approved_by}]}` | admin 승인 폼, 워커 제안 | `_FLAT_FILES`에 추가 + 라운드트립 | 4 |
| `special/{edition}/_edition.json` | `{label_ko, label_en}`(선택) | admin | **포함 확인됨**: `_is_safe_path`는 `timetable/special/<edition>/<*.json>` 깊이 4를 허용하고(`backup.py:61-65`), `create_backup_zip`은 `special_dir.rglob("*.json")`(`:105`)을 씀. 노선 파일 오인 없음: `list_editions`(`special_timetable.py:117-125`)는 디렉터리만 세고, `get_timetable`은 `{busno}.json`만 읽으며, admin·서비스에 에디션 디렉터리 안 파일을 나열하는 코드가 없음(grep 확인). 이후 나열 코드가 생기면 `_` 접두 파일을 제외한다는 규칙을 둠. 대안: 특별편 맵 JSON에 label 필드 | 2(선택) |

- 로더는 기존 timetable 캐시처럼 mtime·size 서명으로 재검증하고(`data/timetable.py:49-101`) 가변 전역 상태는 두지 않습니다(다중 워커, `cli.py:313`).
- 파일이 없거나 파손되면 기능을 생략(graceful)하거나 (a)로 폴백합니다(ADR-013). 500은 금지입니다.
- 날짜 공지: 시효 문제는 **P0-9에서 먼저** 날짜 게이트로 고칩니다(`i18n.py:70`, `constants.py:68`, `info.html:50,61`). P4-3은 이를 `notices.json`으로 구조화 이관하는 일만 맡습니다.

### 6.7 색 토큰 단일 소스와 parity 테스트

- `style.css :root`에 `--route-513: #D32F2F; --route-713: #388E3C; --route-743: #1976D2; --route-753: #7B1FA2; --route-1115: #F57C00`를 둡니다(`legacy-ui-reference.md:89`의 레거시 HEX 고정 규칙 유지). `--route-N-ink`(D4 (b)일 때 또는 `/board` `c-route` 글자색용)도 여기에 둡니다.
- `timetable.css .bus-N`과 `style.css .route-N`은 `var()`만 참조합니다.
- 테스트 1: CSS를 파싱해 `route_diagram.COLORS`(`route_diagram.py:36-42`)와 식별색이 같은지 단언합니다.
- 테스트 2: 실제로 쓰는 텍스트/배경 쌍의 WCAG 대비를 계산해 단언합니다. 대상은 다음과 같습니다.
  - C4의 #1b1b1b/흰색, ink/흰색(≥4.5).
  - (P3-5) `/unist` `.bus-card-header` 교체 후 쌍(≥4.5). `.bus-card.last-bus` 텍스트 #595959/흰색이며, opacity는 쓰지 않아야 합니다(≥4.5).
  - (P3-5) `/board` `span.c-route` 글자색이 흰 배경과 FIRST 행 배경 #fff8e1 위 두 경우 모두 ≥4.5.
  - (P0-7b) `/board` 포커스 링(`style.css:783-784` 교체값)이 인접 배경 대비 ≥3.
- 인접 화면의 `/unist` `.bus-card-header`(`style.css:958-965`)와 `/board` `span.c-route`(`:537-549`)는 같은 토큰 체계로 교체합니다(M-13, P3-5).

---

## 7. 단계별 실행 계획

크기 기준: **S** ≤ 반나절~1일, **M** 2~4일, **L** 1주 이상(1인 기준 **[가정]**). PR마다 "변경된 기존 단언 목록"을 본문에 적습니다.

### Phase 0: 안전망과 결정 없는 신뢰 핫픽스

- 목표: 오너 결정 없이 확정할 수 있는 것만 담습니다. 데이터 의미 규칙은 바꾸지 않습니다. **제목 텍스트도 바꾸지 않습니다**(KO '전체 시간표', '버스번호별 시간표' 그대로. 새 명칭은 D2 이후 P1-3).
- 선행 작업: P0-0a(사용자 WIP 정리). 긴급 작업: P0-9는 **10/3 이전 배포**가 목표이므로 다른 PR을 기다리지 않습니다.

| PR | 작업 | 주요 파일 | 크기 | 의존 |
|---|---|---|---|---|
| P0-0a | **사용자 WIP 정리(선행, 오너 확인).** 별도 브랜치에서 코드·템플릿·테스트 변경 6개 파일(`constants.py`, `route_diagram.py`, `info.css`, `info.html`, `test_route_diagram.py`, `changelog.json`)만 커밋·병합. untracked 런타임 파일(`data/arrival_status.json`, `data/govtrack_state.json`, `data/govtrack_status.json`, `data/holiday_cache.json`)은 커밋하지 않고 `.gitignore`에 추가(오너 확인) | git | S | 없음 |
| P0-0b | **기준선 측정.** (1) I-1 접근 로그 집계 스크립트 `scripts/metrics/access_summary.py`(경로·쿼리 키·시간대·모바일 여부만, IP 미사용). **[가정]** gunicorn access log가 켜져 있음. 꺼져 있으면 이 PR에서 accesslog 설정을 추가. (2) 헤드리스 측정 스크립트 `scripts/metrics/measure_viewport.sh`(`google-chrome --headless=new`, `scrollbar-width:none` 주입, 360/375/414 × 17:47 fixture 서버에서 docH·17시 행 y 측정). (3) 복도 테스트 5인 기준선(T1·T2·T3·T5 시간·정답률) 기록. (4) 테스트 기준선 `pytest --collect-only -q <목록>` 결과를 파일 목록과 함께 기록. 산출물: `docs/refactor/metrics/timetable-baseline.json` | `scripts/metrics/`, `docs/refactor/metrics/` | S~M | P0-0a |
| P0-1a | **fixture 팩토리(프로덕션 diff 0, 이후 데이터 의존 AC를 가진 PR을 모두 막음).** `tests/fixtures/timetable/conftest` 수준 fixture: (1) `freeze_kst("2026-09-29T17:47")` 헬퍼. 내부는 `freeze_time("2026-09-29 17:47:00+09:00")`이고, 자체 단위 테스트로 `KSTClock().now()`가 2026-09-29 17:47 화요일 KST인지 확인. (2) `tt_env`: `monkeypatch.setenv('BUSHEXA_TIMETABLE_DIR', tmp/'timetable')`, 5개 노선 × 3요일 × 모든 기점 hand-built JSON 기록, 테스트 앞뒤로 `bushexa.data.timetable._clear_cache()` 호출, `app_config_test.data_dir`과 연결. (3) `make_special(date, edition, routes=…)`: 배정 맵(`config.data_dir/special_timetables.json`)과 에디션 디렉터리(`timetable_dir()/special/<id>/`)를 한 번에 생성. (4) `make_holidays(admin=…, cache={'202610': ['20261005']})`: `holidays.json`·`holiday_cache.json` 기록(값은 **문자열** 'YYYYMMDD'). (5) 레거시 모양 스냅샷 팩토리. (6) **도메인 golden**: `get_full_timetable_data`·`get_busno_page_data` 결과 dataclass를 JSON으로 직렬화한 스냅샷(핵심 조합 소수, `@pytest.mark.characterization`). HTML golden은 P1-4 이후로 미룸 | `tests/fixtures/timetable/`, `tests/conftest.py` 확장 | M | 없음 |
| P0-1b | **strict xfail 계약과 키 커버리지(막지 않음).** 아래 판정 계약 표대로 finding별 파일에 strict xfail 작성. pytest 마커 `contract`, `timetable`, `characterization` 등록. 템플릿 `t()` 키 커버리지 테스트(동적 접두사 허용 목록 포함, 8.1) | `tests/web/test_contract_*.py`, `tests/web/test_i18n_coverage.py`, `pyproject.toml`(markers) | S~M | P0-1a |
| P0-2 | **`/busno` 칩과 방향.** 버스·요일 칩 href를 `url_for`로 생성하고 버스 칩에서 `dep` 제거. 출발지 select를 GET 링크 칩 2개로 교체. 도메인 `BusnoTimetable`에 `direction_options: tuple[tuple[str, str], ...] = ()` 추가: 라벨은 ROUTEID terminal과 경유 여부로 만듦('UNIST → 명촌(시내) 방면', '덕하 → UNIST 경유 → 삼남(울산역)'). 경유 판정은 P1-1 이전이므로 도메인에서 `UNIST_VIA_STOP_ID in stops[1:-1]`로 계산하고, ROUTEID는 `get_busroute_info`를 건드리지 않고 직접 읽음. 템플릿은 `direction_options`가 비면 `terminals` 기점명으로 폴백(레거시 fixture `test_busno_route.py:24-51`, `test_routes_smoke.py:58-`). 그룹 라벨 '출발지:' → '방향'. `onchange` 제거. `dep` 파라미터는 그대로 쓰고 `to`는 P2에서 도입 | `templates/busno.html`, `domain/busno.py` | S~M | P0-1a |
| P0-3 | **경고 문구와 I-2 카운터.** 도메인이 `notices`(코드)를 추가로 반환하고 `warning`에는 repr 없는 KO 호환 문구를 계속 채움(`test_invalid_dep_fallback`의 `warning is not None` 유지). 템플릿 렌더 우선순위: `notices`가 있으면 `t()`로, 없으면 레거시 `warning`(patch fixture `test_invalid_bus_warns` 보존). repr과 예외 원문은 `log.warning`으로만. '유효하지 않은 버스번호' KO 문구 유지. `translate(key, lang, **kwargs)` 확장(누락 파라미터는 원문 템플릿으로 안전 폴백, KeyError 금지) + context processor `t`가 kwargs 통과. `fmt.date_short`·`dow.N` 키 추가. **I-2**: notice·warning 코드가 렌더될 때 `log.info("tt.notice code=%s page=%s", code, endpoint)` | `domain/busno.py`, `web/i18n.py`, `web/app.py:113`, `busno.html` | S | P0-1a |
| P0-4 | **오늘 링크 정규화와 상태 줄 분리.** 규칙 ① 요일 칩: 대상 day == today_code이면 href에서 `day` 생략. 규칙 ② 버스·방향 칩: selected_day == today_code이면 `day` 생략, 아니면 유지(라우트의 특별편 규칙은 불변). 두 라우트가 `today_code = get_weekday(today, holiday_set)`를 계산해 도메인에 keyword 인자(기본 None)로 넘김. `/busno` 도메인이 내부에서 `get_weekday`를 부르던 경로(`domain/busno.py:103`)는 인자가 None일 때만 유지. '현재 시각' 줄을 `t('fmt.date_short', m=, d=, dow=t('dow.N'))` 기반 '오늘 9/29(화) 17:47 기준'과, 다를 때만 '{요일} 시간표를 보고 있습니다 · 오늘 시간표로'로 분리 | `unist_timetable.html`, `busno.html`, 두 라우트, 두 도메인(필드 추가) | S | P0-3 |
| P0-5 | **513 정직성 응급조치.** (1) `/timetable` 513 토큰에 텍스트 표식 '덕하발', caption과 범례 각주 '513은 덕하 기점 출발 시각입니다. UNIST 통과는 이보다 늦습니다. 삼남 출발 방향은 노선별 시간표에서 확인하세요'. (2) `/unist` via 카드(`domain/unist_board.py:95` `_build_via_card`의 timetable 채움 줄**만**): `CardEntry`에 기본값 필드 `kind: str | None = None`, `params: dict = {}` 추가. via 시간표 항목은 `kind='via_origin'`, `params={'origin':…, 'time':…}`이고, 템플릿은 `kind`가 있으면 `t('unist.via.origin_dep', **params)`('덕하 17:30 출발'), 없으면 `text`를 렌더. `text`는 KO 폴백으로 `'{origin} {t} 출발'`을 채워 `HH:MM` 부분 문자열을 유지. `:120`(`_build_from_card`, UNIST 기점 713/743/753/1115의 '출발 예정')은 **건드리지 않음**. 필터 로직은 P2-6a. (3) `info.html:45-47` '앞쪽/뒤쪽' → '덕하 출발 → UNIST 경유 → 울산역 / 삼남 출발 → UNIST 경유 → 덕하(시내)' | `unist_timetable.html`, `domain/unist_board.py:95`, `unist_partial.html`, `info.html` | S | P0-1a, P0-0a |
| P0-6 | **`lang_url`.** 4.8절 구현(다중 값 보존, view_args None 방어, endpoint None이면 path 폴백)으로 `_base.html:69,72` 교체. `lang`·`hreflang`·`aria-current` 부여 | `web/app.py`, `_base.html` | S | — |
| P0-7a | **모바일 셸: 열기·닫기.** 햄버거 44×44 label(aria-label `t('nav.menu_open')`), `label.nav-backdrop`(fixed inset 0), 사이드바 × 닫기 label, 닫힌 사이드바 `visibility:hidden`, 체크박스 sr-only로 포커스 가능 + `autocomplete="off"`(M-14), 열린 동안 `overscroll-behavior:contain`으로 배경 스크롤 체이닝 방지(MR MISSED #6) | `_base.html`, `style.css`, admin 스모크 | S~M | — |
| P0-7b | **셸 시맨틱.** skip link(`t('nav.skip')`). 페이지별 `page_title` 블록 재정의 + topbar를 h1으로(본문 h2 중복 제거). **제목 텍스트는 기존 글자 그대로**, `<title>`에 ' · Bus HeXA' 접미사만 복원(KO 마커 유지). 이모지 `aria-hidden`, 🕒 중복 해소. 사이드바 현재 링크 `aria-current="page"`, 모든 `<nav>`에 `aria-label`(`t('nav.label.*')`), 언어 선택 aria-label을 `t('lang.switcher')`로. `:focus-visible` 링 #1a237e 2px + offset 2px. `/board` 기존 포커스 링 `style.css:783-784`(#ff9800)도 같은 토큰으로 교체(A11Y MISSED #5). 칩 그룹의 nav 남용은 P1-4에서 `role=group`으로 | `_base.html`, 각 공개 템플릿의 `page_title` 블록, `style.css` | S~M | P0-7a |
| P0-8 | **작은 CSS 수정.** `.tag-first`를 최대 3회로 제한 + `prefers-reduced-motion: reduce`에서 `animation:none`(A11Y-13). ≤480px에서 `.day-btn/.bus-btn/.lang-btn/.nav-toggle-btn` min-height 44px, 간격 8px. `table.timetable` 폭 붕괴 수정(MR-3) | `style.css` | S | — |
| P0-9 | **날짜 공지 시효 핫픽스(긴급, 10/3 이전 배포).** 단일 날짜 상수(`route_diagram.VIA_743_BEOMSEO_FROM`, 필요하면 `data/constants.py`로 옮기고 route_diagram이 import)로 게이트. (1) `board.notice.743`을 `board.notice.743.upcoming`('10월 3일부터 …')과 `.active`('743번은 구영리에서 범서중학교를 경유합니다 …')로 나누고, `board.html:19`와 `unist_board.html:8`이 날짜로 선택. (2) `VIA_STOPS['743']['명촌']`(`constants.py:68`)은 평서형 '구영리(범서중학교)'로 바꾸고, 10/3 전에는 `board._via_for`가 '(10/3부터)'를 덧붙임(override > 상수 우선순위 불변). (3) `info.html:50,61`: info 라우트가 `beomseo_active` bool을 넘기고, 10/3 이후에는 '2026년 10월 3일부터' → 평서형 '743번은 구영리에서 513번과 같이 범서중학교를 경유하며 …', 표의 '(범서중학교, 10/3부터)' → '(범서중학교)'. 테스트는 P0-1a를 기다리지 않고 `freeze_time('2026-10-02 12:00:00+09:00')`을 직접 사용 | `web/i18n.py:70`, `data/constants.py:68`, `domain/board.py`(`_via_for`), `web/routes/info.py`, `templates/info.html`, `board.html`, `unist_board.html` | S | P0-0a |

**P0-1b xfail 판정 계약 표**(선택자는 bs4 `select` 문법. 각 xfail의 reason에 finding ID를 적습니다)

| # | finding | 대상 URL(fixture) | 선택자·판정 | 기대값 | 파일 |
|---|---|---|---|---|---|
| ① | IA-4 | `/busno` 30조합 칩 href 크롤(`tt_env`) | `.warning-banner` | 모든 응답에서 0개 | `test_contract_busno_links.py` |
| ② | TF MISSED 커버리지 | `/timetable`, (P2) `/timetable?dir=in`, `/busno` 방향 칩 | `[data-route-id]` 속성값 합집합 | ROUTEID 10개와 같음 | `test_contract_coverage.py` |
| ③ | DS-1 | `/timetable?day=0`(`tt_env`) | `.timetable-grid .bus-513` 각 요소 텍스트 | fixture에 넣은 513 토큰 N개 전부에 '덕하' 포함(N/N). P2에서 계약을 '0개'로 교체 | `test_contract_basis.py` |
| ④ | DS-4 | `make_special(오늘)` 날 `/timetable` | `nav.day-selector a.day-btn.active`(P1-4 후 `[role=group] [aria-current=true]`)의 href를 따라간 응답 | 에디션 전용 시각 문자열 존재 | `test_contract_special.py` |
| ⑤ | A11Y-2 | `/timetable?lang=en`, `/busno?lang=en` 5×2 | 텍스트 노드·`aria-label`·`title` 속성·`<title>`·`caption`·`.sr-only` 중 `[lang=ko]` 조상 밖 | `[가-힣]` 0자 | `test_contract_i18n.py` |
| ⑥ | A11Y-4 | 공개 페이지 전부 | 모든 요소의 `on[a-z]+` 속성, `select` | 0개 | `test_contract_nojs.py` |
| ⑦ | A11Y-1 | CSS 정적 | `timetable.css`·`style.css`에서 `.bus-N`/`.route-mark`의 (color, background) 쌍 파싱 | 대비 ≥ 4.5(모든 N) | `test_contract_contrast.py` |
| ⑧ | A11Y-5 | `/timetable`, `/busno` | `soup.select('[role=group]')` 각각의 `[aria-current=true]` | 그룹마다 정확히 1개, 그룹 ≥ 2개 | `test_contract_a11y.py` |
| ⑨ | CI-4 | `/busno?bus=743&day=1&dep=명촌` | `a[hreflang=en]`의 href 쿼리 | bus=743, day=1, dep(인코딩), lang=en 모두 존재 | `test_contract_i18n.py` |
| ⑩ | A11Y-6 | `/timetable`, `/busno` | 모든 `table`의 `caption`, `tbody th[scope=row]` | table마다 caption 1개, 모든 시 셀이 `th[scope=row]` | `test_contract_a11y.py` |

**Phase 0 수용 기준**(모두 Flask test client + `bs4.BeautifulSoup(html, 'html.parser')`로 CI 자동화. 시각 고정은 `freeze_kst`, 데이터는 `tt_env`)

1. xfail ①④⑥⑨가 pass로 바뀌고 strict 목록에서 빠집니다. ③은 '덕하발' 표식으로 통과합니다(fixture 513 토큰 N/N).
2. 링크 크롤(`tt_env`): `/busno` 30개 조합(5 노선 × 2 방향 × 3 요일)의 모든 칩 href → 200, `.warning-banner` 0.
3. patch 없이 실제 도메인 + `tt_env`로 `/busno?bus=999` → 200, `.warning-banner` 안에 '유효하지 않은 버스번호'가 있고 'KeyError', 'FileNotFoundError', `&#39;`는 0(검사 범위는 `.warning-banner` 내부로 한정. EN의 정상 아포스트로피 오탐 방지). patch 경로의 기존 `test_invalid_bus_warns`도 수정 없이 통과.
4. `freeze_kst("2026-09-29T17:47")` 자체 테스트: `KSTClock().now()`가 2026-09-29 17:47, weekday()==1(화). 같은 시각 `/busno?bus=713&day=1` → '오늘 9/29(화)' 포함, '현재 시각: 17:47 (토요일' 미포함.
5. `make_special(2026-09-29)` 날 `/timetable` → 오늘 칩 href에 `day=` 없음. 그 링크의 렌더에 에디션 시각이 있음. 버스 칩: `/busno`(오늘)에서 버스 칩 href에 `day=` 없음. `/busno?day=1`(오늘 아님)에서는 `day=1` 유지.
6. `lang_url`: `/busno?bus=743&day=1&dep=명촌`의 EN 링크에 bus=743, day=1, dep(인코딩), lang=en이 모두 있음. 다중 값 `?routes=713&routes=743`이 두 값 모두 보존됨. view_args가 있는 admin 경로 1개에서 TypeError 없이 렌더됨.
7. 공개 템플릿 렌더에서 `onchange=` 0, `<select` 0(busno), `style="` 0, '출발지:' 0.
8. 기존 테스트 전량 통과. 마커 `timetable-grid`, `class="timetable"`, `"20, 40"`, `bus-713`, '전체 시간표', '버스번호별 시간표' 유지. admin 스모크 통과.
9. 수동 또는 헤드리스(D13) 체크리스트: 375×667에서 메뉴 열기 → backdrop 탭으로 닫힘, 본문 링크는 눌리지 않음. 닫힌 상태에서 Tab이 사이드바 링크로 가지 않음. 1280px 200% 확대에서도 같음. 메뉴가 열린 동안 사이드바 안 스와이프가 배경을 스크롤하지 않음.
10. CSS 파싱: `.tag-first` 반복 ≤ 3, reduce 규칙 존재, `outline: 2px solid #ff9800` 0.
11. (P0-0b) `docs/refactor/metrics/timetable-baseline.json`에 360/375/414 스크롤바 숨김 docH와 17시 행 y, 테스트 파일 목록과 collected 수, 복도 테스트 기준선이 기록됨. 스크립트 두 개가 저장소에 있음.
12. (P0-3) `caplog`: `/busno?bus=999` 렌더 시 `tt.notice code=invalid_bus` 로그 1줄.
13. (P0-5) `/unist` fixture(513 via 카드가 시간표로 채워지는 상황)에서 via 카드 문구에 기점명('덕하' 또는 '삼남')이 포함됨. 713 from 카드 문구는 불변('출발 예정'). `tests/domain/test_unist_fixes.py`는 수정 없이 통과('16:10' 등 `HH:MM` 부분 문자열 유지). `/info` 렌더에 '앞쪽'·'뒤쪽' 0.
14. (P0-7b) 공개 페이지마다 사이드바에 `[aria-current=page]`가 정확히 1개. 모든 `<nav>`에 `aria-label` 또는 `aria-labelledby`가 있음. KO `<title>`의 본문 텍스트가 기존 문자열과 글자 그대로 같고 ' · Bus HeXA'로 끝남.
15. (P0-9) `freeze_time('2026-10-02 12:00:00+09:00')`: `/board`, `/unist` 배너에 '10월 3일부터', `/board` 743 경유에 '(10/3부터)', `/info`에 '10월 3일부터'. `freeze_time('2026-10-04 12:00:00+09:00')`: 네 표면 모두 '부터'·'10/3부터' 0, '범서중학교' 포함. EN도 같은 두 시점에서 'From Oct 3' 유무를 단언.

- 해소 finding: IA-4, DS-10, CI-5, A11Y-14, A11Y-4, MR-10, CI-12, IA-7, DS-7(부분), CI-2, CI-4, A11Y-12, IA-6(완화), DS-4(완화), IA-1(응급), DS-1(응급), CI-10(부분), MR-2, A11Y-3, A11Y-5(사이드바·nav 이름·언어), A11Y-8, A11Y-9, A11Y-10, CI-6(부분), A11Y-13, MR-3, MR-4, A11Y-11(크기), TF-5(안전망), TF-14, M-5, M-14, M-15(셸 부분), M-16, M-23(시효), M-31, M-32.
- 선택(D13): Playwright + axe를 dev 의존성으로 도입합니다(우선 CI 비필수). 현재 저장소 dev 의존성 그룹은 `pytest`, `pytest-mock`, `responses`, `freezegun`입니다(`pyproject.toml` `[dependency-groups]`). HTML 파서는 기존 런타임 의존성 `beautifulsoup4>=4.12`(`pyproject.toml:10`) + `html.parser`를 씁니다. 대안은 P0-0b의 헤드리스 Chrome 측정 스크립트를 수동 게이트로 쓰는 것입니다.

### Phase 1: 의미 모델과 i18n 기반

| PR | 작업 | 주요 파일 | 크기 | 의존 |
|---|---|---|---|---|
| P1-1 | `timetable_view.py`: DirectionSpec(`also_stops_at` 포함), `direction_specs`, `spec_for`, 헬퍼(`hhmm_to_min`, `classify_now`, `group_by_hour`, `summarize` 동률 규칙, `origin_window`, `next_n`), `effective_unist_time`(오프셋 없음 = (a)), `NOTICE_CODES`. 단위 테스트는 ROUTEID 10개 스펙의 slug·relation·basis·unist_stop_index·also_stops_at(713/743/753 UNIST 기점과 513 양방향에 196040231 포함)을 hand-built 기대값으로. **동치성 테스트**: (1) 모든 ROUTEID 항목에 대해 `unist_board`의 분류(`unist_board.py:53-71`: `departure=='UNIST'`→from, `UNIST_VIA_STOP_ID in stops`→via, 그 외→제외) == `spec.unist_relation`(departs→from, passes→via, arrives→제외). (2) `board.py`가 행을 만드는 route_id 집합(`board.py:151-166` 부근 행 생성 루프에서 추출하는 헬퍼로 비교) == `{s.route_id for s in specs if s.view in ('out','both')}` | 신규 모듈, `tests/domain/test_timetable_view.py` | M | P0-1a |
| P1-2 | `resolve_timetable_source` + `TimetableSource` + `FallbackLog` + `ScheduleStatus`. `timetable_provider_for` 래퍼화. `holiday_service.cached_months(data_dir) -> set[str]` 추가와 `holiday_known`. 라우트가 도메인 호출 뒤 `ScheduleStatus(fallback_routes=tuple(log.routes))`를 만들어 템플릿에 전달. 상태 줄에 reason·edition·holiday·fallback·캐시 범위 밖 반영(규칙 불변). admin 대시보드에 `.admin-alert[data-code=holiday_cache_gap]` | `services/board_support.py`, `services/holiday_service.py`, 두 라우트, 두 도메인, admin 대시보드 템플릿 | M | P0-1a(P1-1과 병렬) |
| P1-3 | **i18n 전량.** 두 시간표 페이지, 매크로, **`_base.html`**의 모든 리터럴을 `t()`로(`aria-label="언어 선택"` → `t('lang.switcher')`, '한' 버튼은 `<span lang="ko">한</span>`). 병기 제거, `day.N.*` 단일 출처, `fmt.date_short`, sr-only와 aria-label 키화, `place.*` 임시 키(D15), 번역 없는 고유명사는 `lang=ko` span. KO 모드의 비허용 라틴 토큰에는 `lang=en`. 제목은 D2 값으로 `page.*.title`(KO 값에는 스모크 마커 문자열 포함). 새 문구는 모두 ko/en 쌍. **상태 매트릭스 × 언어 계약 테스트 뼈대**(8.1)를 이 PR에서 만들고 P1 상태 행을 등록 | `web/i18n.py`, 두 템플릿, `_base.html`, `domain/busno.py`(코드 반환), `tests/web/test_contract_states.py` | M | P0-3 |
| P1-4 | **표 시맨틱.** `macros/_timetable.html` 신설(C2, C5, C6, C9). caption, th scope, sr-only 맥락 문장, 칩 그룹 `role=group`·`aria-labelledby`·`aria-current`. `/timetable`은 `ul.dep-list`로 전환하되 `grid_groups`가 비면 `timetable_rows`로 렌더. `/busno` 분 셀은 이 PR에서 **쉼표 문자열(`row.minutes`)을 그대로 유지**하고 caption·scope만 추가(`test_busno_route.py:83` "20, 40" 보존). 분 토큰화는 P2-4. `class="timetable"` 속성 문자열은 정확히 유지. HTML golden(핵심 조합 소수)을 이 PR 이후 도입 | 매크로, 두 템플릿, `timetable.css` | M | P1-3 |
| P1-5 | **색 토큰과 route-mark(D4).** `:root` 토큰, `.bus-N`·`.route-N`을 var 참조로, C4, parity와 대비 테스트, `timetable.css:11` 폰트 덮어쓰기 제거, tabular-nums | `style.css`, `timetable.css`, `tests/web/test_route_tokens.py` | S~M | D4, P0-0a(`route_diagram.COLORS` 안정화) |
| P1-6 | **데이터 출처.** 크롤러가 `_meta.json` 기록, 로더(mtime 서명), 푸터 C10(파일이 없으면 생략), admin 대시보드에 공휴일 캐시 범위 경고 | `crawler/timetable_crawl.py`, `data/timetable.py`, 템플릿, admin | S~M | D12 |
| P1-7 | **누락 노선과 잘못된 요일 표시.** `missing_routes`를 범례와 해당 위치에 표시(DS-14). 빈 상태 문구를 F08 AC-5와 i18n으로 양립. `invalid_day` notice(M-11): 두 라우트가 `ValueError`로 0 보정할 때 `day_invalid=True`를 도메인에 넘기고, 도메인은 범위 밖 정수와 함께 notice 코드를 냄 | `domain/unist_timetable.py:83-86`, `domain/busno.py:104-105`, `routes/busno.py:27-29`, `routes/unist_timetable.py:40-43`, 템플릿 | S | P1-3 |

**Phase 1 수용 기준**

1. DirectionSpec 10개 기대값 테스트와 P1-1의 두 동치성 테스트 통과. `get_busroute_info` 반환값 불변(admin 테스트 전량과 `tests/services/test_timetable_editor.py` 통과).
2. `make_holidays(cache={'202610': ['20261005']})` + `freeze_kst("2026-10-05T09:00")`(월) 기본 진입 → 상태 줄에 사유 문장, `reason=='holiday'`, 선택 day=2. 10/5는 실제 `data/holiday_cache.json` '202610'에도 있습니다. 직접 인자를 쓰는 단위 테스트는 `holiday_set={'20261005'}`(문자열)입니다.
3. `make_special` fixture → 상태 줄에 에디션 표식. 부분 편성 fixture(에디션에 713만) → `FallbackLog`에 나머지 노선이 기록되고 폴백 노선명이 렌더됨.
4. 캐시 범위 밖 fixture(대상 월 키 없음) → `tt.status.holiday_unknown` 렌더. admin 로그인 fixture로 GET 대시보드 → `.admin-alert[data-code=holiday_cache_gap]` 정확히 1개.
5. xfail ⑤ pass: `/timetable`, `/busno`(5 노선 × 2 방향)의 `?lang=en` 렌더에서 `[lang=ko]` 밖 한글(가-힣) 0자. 스캔 대상은 텍스트 노드, `aria-label`, `title` 속성, **`<title>` 요소**, `<caption>`, sr-only. `<html lang="en">`. EN `<title>`은 `t('page.*.title')`의 en 값 + ' · Bus HeXA'. **KO 쪽 대칭 단언**: 같은 페이지 KO 렌더에서 허용 목록(UNIST, KTX, Bus HeXA, BIS, 노선번호, HH:MM) 밖의 라틴 단어 연속 토큰이 `[lang=en]` 조상 밖에 0개. KO `<title>`에는 '전체 시간표'와 '버스번호별 시간표' 유지.
6. KO 렌더에 '(Hour)', '(Saturday)', '(working day)' 같은 병기 0. 키 커버리지에서 누락 0, 미사용 `tt.*` 0(동적 접두사 허용 목록 적용). `NOTICE_CODES` ↔ TRANSLATIONS `notice.*`/`warn.*` 1:1. 템플릿 `t()` 인자가 문자열 리터럴이나 `'prefix.' ~ var` 형태뿐임(lint 테스트).
7. xfail ⑦ pass(D4 반영). ⑧ pass: 칩 그룹마다 `aria-current="true"` 정확히 1. ⑩ pass: 모든 표에 caption, 시 셀은 `th[scope=row]`.
8. `_meta.json`이 없으면 푸터 요소 0이고 오류도 없음. 있으면 수집일과 편성 모드가 렌더됨. **백업 테스트는 `_meta.json`을 포함하지 않음**을 단언.
9. 레거시 모양 fixture(새 필드 없음)로 두 페이지 렌더 → 200이고 **fixture의 hour·minute 값이 렌더됨**(`/timetable` '07'·'08', `/busno` '07'·'20, 40').
10. 상태 매트릭스 × 언어 계약 테스트에 P1 행(오늘, 다른 날, 특별편, 특별편 폴백, 공휴일, 캐시 범위 밖, 노선 누락, 전체 비어 있음, 미운행, 잘못된 요일)이 등록되고 KO/EN 모두 통과.
11. `/busno?day=abc`와 `/timetable?day=9` → 평일 + `notice.invalid_day` 1건, `.warning-banner` 0.

- 해소: TF-1(모델), TF-3, TF-6, TF-10, TF-11(헬퍼), IA-6(표시), DS-6, DS-5(표시), CI-13, A11Y-2, CI-3, IA-12, MR-9, CI-8, A11Y-1, CI-11, A11Y-5(칩 그룹), A11Y-6, A11Y-7(텍스트 라벨 기반), DS-8, IA-14, TF-12, DS-14, CI-9, MR-11, M-4, M-11, M-20, M-26.

### Phase 2: 방향 우선 시간표와 인접 화면 정합

| PR | 작업 | 주요 파일 | 크기 | 의존 |
|---|---|---|---|---|
| P2-1 | **513 분리.** `/timetable` 격자는 basis=unist만. 513 두 방향을 `#via-513` 패널(C8: `origin_window` 요약 + `<details>` 전체 기점 시각)로 옮기고 실시간 링크 추가(삼남 방향 복구). 승차 정류소를 열 머리에 명시: 'UNIST(기점)' / '울산과학기술원(경유)' + `also_stops_at`이 있으면 `tt.boarding.also`('정문(시내) 정류장에서도 탑승 가능 · 표시 시각은 {기점} 기준') + `/info` 노선도 링크(사용자 가치 심사 must-fix: 물리적 승차 위치). **[가정]** 세 정류소의 물리적 위치 관계와 문구는 저장소로 확인할 수 없으므로 운영자가 D7과 함께 확인. 첫 기점 출발 전·513 미운행 상태(5.6) | `domain/unist_timetable.py`, 매크로 C8 | M | P1-1, P1-4 |
| P2-2 | **`dir=in` 뷰(D6).** 출발지 칩(`origin`), 기점 출발 caption, 카운트다운 없음, `/stops` 링크, 첫차 전·운행 종료 문구, `hub` 교차 오용 notice | 라우트, 도메인, 템플릿 | M | P2-1, D6 |
| P2-3 | **목적지 거점 필터(D7).** `DESTINATION_HUBS` 상수 + VIA_STOPS·정류소 ID 교차 검증 테스트, `hub=` 파라미터, `<details>` 칩 그룹, 필터 결과 0편 빈 상태, `invalid_hub`·`origin` 교차 오용 notice | `timetable_view.py`, 템플릿 | M | P2-1, D7 |
| P2-4 | **`/busno` 방향 모델.** `to` 파라미터, 레거시 `dep` 매핑, `<link rel=canonical>`, 버스 칩의 `to` 유지 규칙(생략 시 notice 없음), `dir_not_available` notice, 기준 안내 한 줄, `also_stops_at` 안내, 경유지는 `terminal_key`로 조회, 요약(ServiceSummary, 동률 규칙), `group_by_hour(fill_gaps=True)`로 '운행 없음' 행, 분 개별 토큰(C5, 기존 `minutes` 문자열 필드 유지), 기본 노선 규칙(D10). **테스트 이관(PR 본문 명시)**: `test_busno_route.py::test_valid`의 `"20, 40" in html`을 구조 단언(`[li.dep 텍스트] == ['20','40']`, 행 hour '07')으로 교체. 레거시 fixture(`hour_groups=()`)에서는 `timetable_rows` 폴백이 쉼표 문자열을 렌더하므로 기존 단언도 계속 성립(이관은 새 fixture 경로에 한정) | `routes/busno.py`, `domain/busno.py`, `busno.html`, `tests/web/test_busno_route.py` | L | P1-1, P1-4, D10 |
| P2-5 | **특별편 규칙 변경(D3).** ADR 기록 `docs/refactor/architecture/ADR-015-timetable-edition-today-semantics.md`(템플릿 `docs/refactor/templates/adr-template.md`) → `requested_day == today_code`면 특별편 적용, `edition=base` 경로와 상태 문구, 공유된 `?day=N` URL의 날짜 의존 의미를 상태 줄에 설명. `test_holiday_and_special_precedence.py`에 케이스 추가(우선순위 불변) | `board_support.py`, 두 라우트, ADR-015 | S~M | P1-2, D3 |
| P2-6a | **인접 화면 정합: 결정 무관 부분.** (1) `/unist` via 카드를 `origin_window`로 교체(`_is_future` 기점 필터 결함 수정, M-1). `unist_board.py:45` `_is_future`를 `timetable_view.hhmm_to_min`으로 수렴. (2) `/board`·`/lite` 513 시간표 파생 행에 `effective_unist_time` 적용해 '{기점} HH:MM 출발' 표기(CI-10 완결). 순위는 이 PR에서 바꾸지 않음. `/lite`는 텍스트만 변경(style·script 0 유지). (3) **오류 원문 제거(M-12)**: `board.html:21-22`의 `({{ snapshot.error }})`와 `board_lite.html:18`의 `{{ snapshot.error }}`를 제거하고 `t('warn.data_error')` 코드 기반 문구로 교체. 원문은 `log.warning`으로만. **영향 테스트 목록(사전 작성)**: `tests/domain/test_board.py`, `test_board_merge.py`, `test_board_cleanup.py`, `test_unist_board.py`, `test_unist_fixes.py`, `tests/web/test_board_lite.py`, `test_board_route.py`, `test_unist_board_route.py` | `domain/board.py`, `domain/unist_board.py`, `board.html`, `board_lite.html` | M | P1-1 |
| P2-6b | **인접 화면 정합: D5 의존 부분.** 513 origin 행을 `/board`·`/lite`의 FIRST/SECOND 순위와 `tag-first`에서 제외(`board.py:151-166`, `merge_live_rows` `:312-325`). changelog 공지 | `domain/board.py`, `data/changelog.json` | S | P2-6a, D5 |
| P2-7 | **캐시 헤더.** 두 시간표 라우트에 `Cache-Control: no-cache`, `Vary: Cookie` | 라우트 | S | — |

`/board` live 과잉 대체(`board.py:257-262`)는 **이 계획 범위 밖의 별도 버그 PR**로 다룹니다. 회귀 원인이 섞이지 않게 하기 위해서입니다(D16).

**Phase 2 수용 기준**

1. xfail ② pass: `/timetable?dir=out`와 `dir=in` 렌더의 `[data-route-id]` 합집합 = ROUTEID 10개. D6이 거부되면 `/timetable`(out) ∪ `/busno` 방향 칩 합집합으로 대체.
2. 속성 테스트(`tt_env`): 전 요일(0/1/2) × 전 노선에서 `.timetable-grid` 안 토큰의 `data-basis`가 모두 `unist`이고 bus-513은 0(③ 계약 교체). `#via-513`: 방향별 `origin_window` 요약이 최대 3편(최근 1 + 다음 2), `<details>` 전체 목록에 fixture에 넣은 513 시각이 방향별로 N/N. 각 블록 제목에 '덕하 출발'·'삼남 출발'.
3. 시각 기준 불변식: `basis!='unist'`인 Departure는 `minutes_until is None`이고 state≠next(단위 테스트, 전 조합). 렌더에서 `data-basis="origin"` 요소 안 '분 후' 0.
4. `origin_window` 테스트: `freeze_kst("2026-09-29T17:47")` 평일 fixture(실데이터와 같은 모양의 hand-built)에서 덕하 방향이 '최근 17:30 · 다음 18:30, 19:00', 삼남 방향이 '최근 17:20 · 다음 17:50, 18:30'. `/unist` via 카드에도 최근 기점 출발 1편이 남아 있음(17:30 편이 사라지지 않음).
5. 레거시 매핑 표(4.4절 12행) 전부 200, 기대한 canonical, 정상 매핑 행은 warning-banner 0. 칩 크롤을 `to` 체계로 반복 → 경고 0, notice 0.
6. 버스 전환: `713 to=downtown`에서 513 칩 href = `to=downtown`(삼남 기점). `713 to=unist`에서 513 칩 href에 `to` 없음. 그 링크 렌더 시 notice 0, `.warning-banner` 0.
7. `/busno?bus=513&to=ulsan-station&day=0`(fixture는 실데이터 덕하 평일 목록을 옮긴 hand-built): 05~22시 18행, 13시 '운행 없음', 요약 '가장 긴 간격 90분(08:20–09:50) 외 1회'. 삼남 방향은 '90분(06:00–07:30) 외 1회', 11시 '운행 없음'. `class="timetable"` 정확 문자열과 `minutes` 필드 유지. 레거시 fixture 경로에서 `"20, 40"` 계속 렌더.
8. 거점 색인 테스트: 모든 (hub, busno) 쌍의 키워드가 VIA_STOPS 문자열에 존재. `city-hall`의 정류소 ID 193031109가 1115·513 삼남발 UNIST 이후 구간에 있고 713에는 없음. `hub=gongeoptap` 렌더에 743·753 토큰과 513 삼남발 패널만 있음.
9. (D3 승인 시) 특별편 fixture에서 `/timetable`, `/timetable?day=<오늘 코드>`, `/busno?day=<오늘 코드>` 모두 에디션 적용. `edition=base`는 평시 데이터와 '평시 시간표를 보고 있습니다'. 우선순위 테스트 불변.
10. (P2-6a) freeze 17:47 `/lite` 시각 칸에 '덕하 17:30' 형식, `/board` 513 timetable 행에 '덕하 17:30 출발' 형식. `/lite` 응답에 `<style>`, `<script>`, 웹폰트 참조 0.
11. (P2-6a, M-12) `snapshot.error`에 `KeyError("x")`·Traceback 문자열을 넣은 fixture로 `/board`, `/lite` 렌더 → 응답에 예외 클래스명·'Traceback'·repr 따옴표 0, `warn.data_error` 문구 1건. `/lite` style·script 0 유지.
12. (P2-6b, D5 승인 시) freeze 17:47 `/board` fixture에서 513 timetable 행에 `tag-first` 없음.
13. 응답 헤더 `Cache-Control: no-cache`, `Vary`에 Cookie 포함.
14. 상태 매트릭스 × 언어 계약 테스트에 P2 행(via 최근 편 없음, 513 미운행, dir=in 첫차 전·종료, 필터 결과 0(hub), 알 수 없는 hub, 교차 오용, 방향 없음 레거시 조합)이 추가되고 KO/EN 모두 통과(누락 키 0, EN 한글 0, notice·warning 개수 일치).

- 해소: IA-1, DS-1, TF-1(완결), DS-11, IA-2, DS-3, CI-1, IA-5, IA-4(근본), IA-6/DS-4(규칙), DS-2(D5 승인 시 완결), CI-10, IA-13, DS-13, IA-11, M-1, M-2, M-6, M-7, M-9, M-12, M-24, M-25, M-29.

### Phase 3: 지금 UX, 모바일, 날짜, 내비게이션

**진입 게이트(신뢰 심사 must-fix):**

- (1) P1-6 `_meta.json` 푸터가 운영에 반영되어 있어야 합니다.
- (2) 운영자가 BIS 원본과 현재 시간표를 1회 대조하고 결과를 기록해야 합니다(토=일 동일이 크롤 이상인지 포함, DS-12·M-27). 대조 결과 불일치가 나오면 재크롤을 먼저 합니다.

| PR | 작업 | 주요 파일 | 크기 | 의존 |
|---|---|---|---|---|
| P3-1 | **다음 출발과 now.** `classify_now`, C7(`dir=out`, basis=unist, 최대 5개, 같은 분 병합, 부족하면 내일 첫차 1편), `id=now` + th '지금', past/next 텍스트 라벨, 첫차 전·운행 종료 문구 + 내일 링크, '지금으로 이동' 링크 | 도메인, 매크로 | M | P2-1, 게이트 |
| P3-2 | **모바일 레이아웃.** sticky 방향 바(≤52px, 불투명 배경, z-index), `scroll-padding-top`/`scroll-margin-top`, 지난 시간 `<details class="tt-past">`(JS 불필요), 모바일 시간대 목록, 44px 토큰, 가로 모드 `@media (max-width:720px), (max-height:500px)`로 사이드바 오버레이 + `100dvh`, `@media (hover:hover)`, `:active`. **[가정]** 조상 요소에 `overflow`가 있으면 sticky가 동작하지 않을 수 있으므로 `style.css .layout/.content` 확인이 선행 작업 | `style.css`, `timetable.css` | M | P3-1 |
| P3-3 | **날짜 조회와 신선도.** `date=` 파라미터 해석(`resolve_timetable_source(requested_date=)`), 날짜 칩 '오늘 {m/d}' · '내일 {m/d}' · '평일' · '토' · '일·공휴일'(D8: 3탭 유지 + 동일 안내), `<details>` 안의 `<form method=get>`(`input type=date` 16px 이상 + hidden `dir/hub/routes` + 제출 버튼 '보기'), 범위 밖이면 notice, 과거 날짜 상태 줄, 운행 종료 링크를 `date=내일`로 교체. 데이터 경과·학사 모드 불일치 info-banner(D12 임계값) | 라우트, 도메인, 템플릿 | M | P1-2, P1-6 |
| P3-4 | **노선 필터.** `routes=` GET 토글(쉼표·반복 파라미터 모두 수용), 범례가 칩 그룹이 됨, 알 수 없는 값은 notice, 필터 결과 0편 빈 상태 | 템플릿, 라우트 | S | P1-4 |
| P3-5 | **내비게이션과 인접 표면(D9).** 4.6절 재편, KO 라벨 한국어화 시 `test_i18n.py:23` 개정(D9 거부 시: KO nav 영문 라벨에 `lang="en"` 부여로 대체). 교차 링크 4.7절, `/unist`·`/board` 카드 → `/busno?bus=N&to=…` 딥링크. `/unist` 카드 헤더와 `/board` `c-route`를 토큰으로(M-13). `/unist` `.bus-card.last-bus { opacity:0.6 }`(`style.css:957`) → opacity 제거, 텍스트 라벨 '막차' + 글자 #595959(M-30). `/board` 템플릿의 한국어 하드코딩 aria-label과 열 헤더(`board_table.html:17-20,34` '시각/노선/행선/현재 위치', '행선 및 경유 열기', `board.html:12-13` '표시 스타일')를 `t()`로 이관(M-28) | `_base.html`, `i18n.py`, `board_table.html`, `board.html`, `unist_partial.html`, `style.css`, `tests/web/test_i18n.py` | M | D9 |
| P3-6 | **(선택, D11) `static/js/timetable-now.js`.** ≤3KB(비압축), `[data-now-root]`가 있을 때만 활성, 외부 의존과 storage 없음, 분 경계 재계산, 예비 편 승격(서버가 hidden으로 3편 추가 렌더), 서버 epoch 보정, `pageshow`/`visibilitychange`, 날짜 경계 배너, aria-live 없음. `{% block extra_scripts %}`로 두 페이지에만 로드. **`boardclock.js`를 일반화하지 않고 새 파일을 두는 이유**: boardclock.js는 `#dboard-time`에 하드와이어돼 있어, 일반화하면 `/board` 회귀 범위가 이 PR로 들어옴(MR-8 권고와 다른 선택, 12장 비고). `htmx.min.js`는 `extra_scripts`로 옮겨 시간표 페이지에서 로드하지 않음(M-10). 이 부분은 JS 도입과 무관하게 수행. **기존 JS 방어 보강(TF-13)**: `splitflap.js:33-35,243`의 `localStorage` 접근을 try/catch로 감싸고 실패 시 기본 'table' | `static/js/`, `_base.html:100`, `static/js/splitflap.js` | M | P3-1 |

**Phase 3 수용 기준**

1. `freeze_kst("2026-09-29T17:47")` 평일, hand-built fixture(실데이터와 같은 모양)에서 `/timetable` `#next` 첫 항목이 '17:55'이고 713과 743이 병합 또는 인접 표기됨. 5개 항목, 513 0. 실데이터 교차 검증 스냅샷에서도 17:55 → 17:55 → 18:10(1115) → 18:15(753) → 18:25(713) 순서.
2. 같은 시각에 `id="now"` 행이 정확히 1개이고 그 th 텍스트는 '17시'와 '지금'을 포함. past 토큰은 모두 sr-only '지난 편'을 포함하고 글자 대비 ≥ 4.5.
3. `?day=1`(오늘 아님)이면 `data-state="next"` 0, `id="now"` 0, `#next` 없음, '오늘 시간표로' 링크 있음.
4. `freeze_kst("2026-09-29T22:55")` → `tt.end_of_day`와 내일 첫차 05:00, 513 패널에 '마지막 기점 출발'. `freeze_kst("2026-09-29T04:30")` → '첫차 05:00까지 30분'. `freeze_kst("2026-09-29T22:30")` → `#next`에 남은 편 + '내일' 표기 1편, 내일 편에는 '분 후' 없음.
5. `/timetable?date=2026-10-05`(`make_holidays`) → reason=holiday, day=2 데이터. `date=`특별편 fixture 날짜 → 에디션. 형식 오류나 범위 밖 → 오늘 + notice 1. `date=2026-09-25`(과거) → `tt.status.past_date`, 모든 토큰 neutral.
6. 토·일 동일 fixture → 안내 문구 1. 다른 fixture → 0. 탭 수는 항상 3.
7. JS 없는 렌더에서 `on*` 속성 0, 인라인 script 0. `timetable-now.js`(도입 시) ≤ 3072B. 시간표 페이지 HTML에 `htmx.min.js` 참조 0.
8. 성능 예산: `/timetable` HTML gzip ≤ 12KB(현재 비압축 25.7KB), 새 웹폰트 0.
9. (헤드리스 또는 수동, D13) 스크롤바 숨김 조건. (a) **freeze 05:00~22:00 매시 정각 18회 × 375×667/360×640 × KO/EN**에서 `#next` 첫 항목(첫차 전·운행 종료 시각에는 해당 안내 블록) bottom ≤ 600px(375) / ≤ 640px(360, 첫 3행). (b) `docH(17:47, 375)` ≤ P0-0b 스크롤바 숨김 기준선의 60%(S-12). 참고로 스크롤바 포함 기준선은 2548px, 414 숨김은 2184px입니다. (c) 1500px 스크롤 뒤 `.tt-controls` top = 0, 높이 ≤ 52. (d) Tab 순회 중 포커스 요소의 bounding box가 sticky 바와 겹치지 않음. (e) `#now` 이동 뒤 현재 시 행 top ≥ 컨트롤 바 bottom. D13을 도입하지 않으면 (a)~(e)를 수동 게이트 체크리스트에 같은 항목으로 넣습니다(P0-0b 측정 스크립트 사용).
10. (D11 도입 시, 수동 또는 JS 러너) 3분 진행 → '8분 후'가 '5분 후'로 바뀌고, 지난 항목은 목록에서 빠지며, 예비 편이 올라옴. 30분 숨긴 뒤 `visibilitychange` → 1초 안에 재계산. 로컬 시계를 +7분 틀어도 서버 기준 ETA 유지. `localStorage` 접근이 예외를 던지도록 스텁한 환경에서도 `/board` 표시 전환이 기본 'table'로 동작(splitflap.js 보강).
11. (P3-4) `/timetable?routes=713,743` 렌더에 `bus-513`·`bus-753`·`bus-1115` 토큰 0. 범례 칩 그룹에서 713·743에 `aria-current="true"`, 나머지 없음. `routes=999` → notice `invalid_routes` 1건 + 필터 없음. `routes=` 빈 값 → 필터 없음, 경고 0.
12. (P3-5) 공개 페이지마다 사이드바 `[aria-current=page]` 정확히 1. `/board`·`/unist` fixture의 모든 `/busno` 딥링크를 크롤 → 200, `.warning-banner` 0, notice 0. CSS 대비 테스트: `.bus-card-header` 교체 쌍, `span.c-route`가 흰 배경과 #fff8e1 FIRST 배경 모두에서 ≥ 4.5. `.bus-card.last-bus`에 `opacity` 0, '막차' 텍스트 존재. `/board?lang=en` 렌더에서 `board_table.html`·`board.html` 유래 한글 aria-label·th 0.
13. 상태 매트릭스 × 언어 계약 테스트에 P3 행(다음 출발 부족, 과거 날짜, 첫차 전, 운행 종료, 데이터 경과, 학사 모드 불일치, 토·일 동일, 필터 결과 0(routes), 알 수 없는 routes)이 추가되고 KO/EN 모두 통과.

- 해소: IA-3, MR-1, TF-4, A11Y-7, MR-5, MR-6, IA-10, IA-8, DS-12(표시), DS-8(경과 경고), MR-7, MR-8, MR-12, TF-7, TF-8, TF-13, IA-9, CI-7(D9 승인 시), M-8, M-10, M-13, M-15(완결), M-28, M-30, CI-6(완결).

### Phase 4: 데이터 신뢰 확장(결정 의존)

| PR | 작업 | 크기 | 의존 |
|---|---|---|---|
| P4-0 | **go/no-go 조사.** 운영 `bus_timelog`의 보존 기간, 방향 × 시간대 표본 수, recorder present_stop 의미를 확인하고 저장소 `data/logs.tsv`(현재 1,095행)를 다시 집계해 보고서를 씀. 게이트 미달이면 P4-1~2는 하지 않고 (a)를 영구 운영(TF-2 WND by design) | S | D1 |
| P4-1 | 야간 워커 산출(중앙값/IQR/n, 요일 유형 × 시간대) → 제안값. n이 기준 미만이면 제안하지 않음 | M | P4-0 go |
| P4-2 | `timetable_offsets.json` 로더(mtime), admin 편집·승인 폼, `_FLAT_FILES` 등록 + 라운드트립, `effective_unist_time` 승인값 적용, 격자·다음 출발 합류('약'과 범위, 점선), `dir=in` 보조 표기, 5개 화면 동시 적용 | L | P4-1 |
| P4-3 | **공지 구조화 이관(범위 축소).** P0-9에서 날짜 게이트로 고친 743 공지와 경유 문구를 `notices.json` + 기간 게이트 + admin 편집으로 옮김. route focus·거점 칩·`/board`에 같은 문구. 시효 자체는 P0-9에서 이미 해결됨 | M | D12, P0-9 |
| P4-4 | 크롤 sanity check(토==일 전 노선 일치, 노선별 편수 ±30% 이상 급변)를 admin 보고에 추가 | S | — |
| P4-5 | (D3-ii) 특별편 FileNotFoundError 폴백을 '기본 시간표의 요청 요일'로 변경 + `test_board_support.py` 계약 개정 | S | D3 |

**수용 기준**

1. `approved_by`가 없는 항목은 어떤 화면에도 추정 시각을 만들지 않음.
2. 승인된 fixture(196000421 +60, n·IQR 통과) → 덕하 17:30 편이 18시 행에 '약 18:30'으로 표시되고 `data-basis="estimated"`, sr-only에 '추정'. 게이트 미달 시간대(fixture n=5)에서는 '약' 0.
3. 오프셋 파일이 없거나 파손되면 (a)로 폴백, 오류 로그 1건, 500 없음. 23:59를 넘는 편은 제외.
4. 백업 화이트리스트 테스트에 `notices.json`과 `timetable_offsets.json`이 포함되고 `_is_safe_path` 통과, 복구 라운드트립 성공.
5. notices: `end` 다음 날 freeze → 렌더 0, `start` 전 → 0, KO와 EN 모두 렌더. P0-9의 10/2·10/4 단언이 notices.json 경로로도 같은 결과.
6. (P4-4) 토==일 전 노선 일치 fixture → admin 보고 항목 1건. 한 노선의 평일 편수가 직전 수집본 대비 ±30% 이상 변한 fixture → 1건. 정상 fixture → 0건.
7. (P4-5) 에디션에 노선 JSON이 없는 FileNotFoundError fixture에서 `day=1` 요청 → 기본 시간표의 **요일 1** 편성 반환(현행은 0). PR 본문에 `test_board_support.py` 개정 diff(기존 weekday 0 단언 → 요청 day 단언)를 명시.
8. 상태 매트릭스 × 언어 계약 테스트에 P4 행(추정 시각 표시, 추정 게이트 미달, notices 기간 안/밖)이 추가되고 KO/EN 모두 통과.

- 해소: TF-2(go 시 해소, no-go 시 WND by design), IA-1(완결), DS-1(완결), DS-2(완결), DS-9, DS-12(탐지), DS-5, M-19(데이터 재검증), M-22, M-23(구조화), M-27.

### Phase 5: 정리와 계약 갱신

| PR | 작업 | 크기 |
|---|---|---|
| P5-1 | 테스트 계약 개정: KO title 마커를 새 명칭으로 바꿀지 결정(D2). `class="timetable"` 정확 일치를 파서 기반 구조 단언으로 대체 | S |
| P5-2 | 참조 0 확인 뒤 `WEEKDAY_STR` 병기 문자열, `_DAY_OPTIONS`, 스냅샷의 레거시 필드(`timetable_rows` 등)를 폐기하고 fixture 이관 | M |
| P5-3 | ADR-015(`docs/refactor/architecture/ADR-015-timetable-edition-today-semantics.md`) 확정, F08(`:291` 미결 → 해결), F02, TP-002, TP-005 갱신 | S |
| P5-4 | (D14) 페이지 통합 또는 `/busno` 301. 4주 이상 로그(I-1)로 유입 비율을 확인한 뒤에만 | M~L |
| P5-5 | (선택, 성능) 폰트 서브셋, static 장기 캐시와 버전 쿼리(TF-9는 결함이 아니라 성능 과제) | M |

**수용 기준:** 레거시 심볼 grep 0이고 전체 테스트 통과. ADR-015가 병합됨. 301을 도입한다면 모든 레거시 매핑 URL이 1홉에 canonical로 가고 쿼리 손실이 없음.

### 의존 그래프(요약)

```
P0-0a ─┬─ P0-0b ; P0-9(긴급, 10/3 이전) ; P0-5 ; P1-5(D4)
       │
P0-1a ─┬─ P0-1b ; P0-2 ; P0-3 ─ P0-4 ; P0-5
       ├─ P1-1 ─┬─ P2-1 ─┬─ P2-2(D6), P2-3(D7) ─ P3-1(게이트) ─ P3-2, P3-6(D11)
       │        │        └─ (via 패널)
       │        ├─ P2-6a ─ P2-6b(D5)
       │        └─ P2-4(D10)
       └─ P1-2 ─┬─ P2-5(D3) ─ P4-5(D3-ii)
                └─ P3-3
P0-3 ─ P1-3 ─ P1-4 ─ P1-7, P3-4, (P2-1, P2-4)
(P0-6, P0-7a ─ P0-7b, P0-8 독립)
P1-6(D12) ─ [Phase 3 게이트], P3-3 ; P4-0(D1) ─ P4-1 ─ P4-2 ; P0-9 ─ P4-3(D12)
```

---

## 8. 검증 전략

### 8.1 테스트 계층

| 계층 | 도구 | CI 필수 | 내용 |
|---|---|---|---|
| 도메인 단위 | pytest, freezegun(`freeze_kst` 헬퍼), hand-built fixture(E-13; 모듈마다 freezegun 1회 이상 EC-3) | 예 | DirectionSpec 10개, 헬퍼, `classify_now` 불변식, `origin_window`, `summarize`(동률 규칙), 거점 색인과 VIA_STOPS·정류소 ID 검증, `resolve_timetable_source` 전 분기, `FallbackLog`, `cached_months` |
| characterization | 도메인 golden(dataclass→JSON, P0-1a), HTML golden(P1-4 이후), `@pytest.mark.characterization` | 예 | P0에서 현재 동작을 고정하고, 의도된 변경은 PR diff 요약으로 설명. Phase 0 동안 마크업이 계속 바뀌므로 HTML golden은 P1-4 이후에만 둠 |
| 계약 | Flask test client + `bs4.BeautifulSoup(html, 'html.parser')`(기존 런타임 의존성 `beautifulsoup4>=4.12`) + `tt_env` | 예 | 링크 크롤(경고 0), 레거시 매핑 12행, 커버리지 불변식, 마커 보존, aria-current 개수, th scope/caption, `on*`·`style=`·인라인 script 0, 캐시 헤더, 레거시 fixture 렌더(값 렌더 확인) |
| strict xfail 래칫 | pytest `xfail(strict=True, reason="IA-4 …")`, P0-1b 판정 계약 표 | 예 | Phase마다 수가 줄어야 하고 Phase 3 종료 시 0. 파일을 finding 묶음별로 나눠 병렬 PR의 머지 충돌을 막음 |
| i18n 완결성 | 키 커버리지 테스트 + 양방향 lang 스캔 | 예 | (1) 템플릿 `t('…')` 정적 추출 ↔ TRANSLATIONS(누락 0, 미사용 `tt.*` 0). **동적 접두사 허용 목록** `notice.*`, `warn.*`, `day.[0-2].*`, `dow.[0-6]`, `place.*`, `page.*.title`은 개별 키 대신 접두사 존재로 판정. (2) `NOTICE_CODES` ↔ TRANSLATIONS `notice.*`/`warn.*` 1:1 대조. (3) lint: 템플릿 `t()` 인자는 문자열 리터럴이나 `'prefix.' ~ var` 형태만 허용. (4) EN 렌더 스캔: 텍스트 노드, `aria-label`, `title` 속성, `<title>`, `alt`, `<caption>`, `.sr-only`에서 `[lang=ko]` 조상 밖 `[가-힣]` 0. (5) **KO 렌더 대칭 스캔**: 허용 목록(UNIST, KTX, Bus HeXA, BIS, 노선번호, HH:MM)을 뺀 라틴 단어 연속 토큰이 `[lang=en]` 조상 밖에 0. (6) 누락 키가 그대로 노출된 문자열(`tt.`·`notice.`·`warn.` 접두 텍스트) 0 |
| **상태 매트릭스 × 언어** | `tests/web/test_contract_states.py`, `pytest.mark.parametrize(state, lang)` | 예 | 5.6절 각 행마다 fixture 1개(`tests/fixtures/timetable/states.py`), KO/EN 두 번 렌더. 단언: (1) 누락 키 문자열(`tt.`·`notice.`·`warn.` 접두) 0, (2) EN 렌더 한글 0(`[lang=ko]` 밖), KO 렌더 비허용 라틴 0(`[lang=en]` 밖), (3) `.warning-banner`·`[role=status]` notice 개수가 행별 기대값과 같음, (4) 행별 핵심 i18n 키의 렌더 문구 존재. P1-3에서 뼈대를 만들고, **P2·P3·P4의 새 상태 행 추가는 각 Phase AC의 필수 항목**입니다 |
| CSS 정적 | 간단한 CSS 파서(정규식 수준) | 예 | 토큰 parity, 대비 ≥ 4.5(6.7 테스트 2의 인접 화면 쌍 포함), 비텍스트 ≥ 3(포커스 링), 칩 min-height 44px(≤480), `.tag-first` 반복 ≤ 3, reduce 규칙, `.bus-card.last-bus` opacity 0 |
| 인접 회귀 | 기존 `test_board*.py`, `test_unist_board*.py`, `test_unist_fixes.py`, `test_board_lite.py`, `test_board_route.py`, `test_board_cleanup.py` | 예 | P0-5·P2-6a·P2-6b의 이관 목록을 사전 작성 |
| 반응형·시각 | P0-0b 헤드리스 Chrome 스크립트(`google-chrome --headless=new`) 또는 Playwright(D13) | 선택 게이트 | 360×640, 375×667, 414×896, 768×1024, 1280×800, 가로 812×375, 1280 200%(=640). 모두 `scrollbar-width:none` 기준(MR 방법론 정정). 좌표 AC(5.2절 예산, 18시각 × 2폭 × 2언어, sticky, 2.4.11 겹침, docH 60%) |
| 접근성 자동 | axe-core(D13 도입 시) | 선택 → 도입 후 필수 | 시간표 두 페이지 × KO/EN × 360/1280 × 200%에서 serious/critical 0 |
| 접근성 수동 | 체크리스트 | 릴리스 전 | ① VoiceOver(iOS Safari)와 TalkBack(Android Chrome)으로 헤딩을 탐색해 '다음 출발'에 도달하고, 토큰이 '17시 55분 713번 명촌 방면'처럼 읽힘 ② NVDA+Firefox로 표를 탐색할 때 행과 열 머리가 낭독됨 ③ 키보드만으로 메뉴 열기·닫기, 모든 칩 조작, 날짜 폼 제출 ④ 200% 확대에서 화면 밖 포커스 0 ⑤ EN 모드에서 한국어 고유명사 발음이 lang=ko로 처리되고, KO 모드 영문 라벨이 lang=en으로 처리됨 ⑥ reduced-motion |
| JS | (D11 도입 시) 수동 체크리스트 또는 경량 러너 | 선택 | fake timer 시나리오(Phase 3 AC 10). 러너를 도입하지 않으면 수동으로 강등(엔지니어링 심사: 인프라 비용 명시) |
| 사용성 | 복도 테스트 5인(P1 3, P3 2), 375px 실기기 | 릴리스 판단 | T1, T2, T3, T5 과업 시간·정답률. **기준선은 P0-0b에서 측정**, P3 후에 재측정 |

### 8.2 회귀 실행 명령

CI(`.github/workflows/ci.yml`)는 `uv sync --frozen` 뒤 `uv run --frozen --with pytest-cov pytest -q`를 실행합니다. 기본 명령은 CI와 같은 경로로 맞춥니다.

```bash
# 전체(CI와 동일 경로. 배포 전 게이트도 이 명령)
uv sync --frozen
uv run --frozen pytest -q
# 로컬 대안: .venv/bin/python -m pytest -q

# 시간표 핵심 묶음(P0 시점에 존재하는 파일만)
uv run --frozen pytest -q tests/domain/test_unist_timetable.py tests/domain/test_busno.py \
  tests/domain/test_holiday_and_special_precedence.py tests/domain/test_unist_fixes.py \
  tests/web/test_unist_timetable_route.py tests/web/test_busno_route.py tests/web/test_routes_smoke.py \
  tests/web/test_board_support.py tests/web/test_i18n.py tests/services/test_timetable_editor.py

# 새 계약·도메인 테스트(P0-1b에서 마커 등록 뒤, 파일 추가와 무관하게 동작)
uv run --frozen pytest -q -m "contract or timetable or characterization"

# 인접 화면(P0-5, P2-6a, P2-6b, P3-5)
uv run --frozen pytest -q tests/domain/test_board.py tests/domain/test_board_merge.py \
  tests/domain/test_board_cleanup.py tests/domain/test_unist_board.py tests/domain/test_unist_fixes.py \
  tests/web/test_board_lite.py tests/web/test_board_route.py tests/web/test_unist_board_route.py

# admin 회귀(셸 변경 PR)
uv run --frozen pytest -q tests/web -k admin

# 기준선 기록(P0-0b)
uv run --frozen pytest --collect-only -q <위 핵심 묶음 목록> | tail -1
```

새 테스트 파일(`tests/domain/test_timetable_view.py`, `tests/web/test_contract_*.py` 등)은 **그 파일을 만드는 PR부터** 경로 목록에 넣습니다. 그 전까지는 마커 명령으로만 실행해 'file not found'(종료 코드 4)를 피합니다.

---

## 9. 성공 지표와 측정 방법

| # | 지표 | 기준선(현재) | 목표 | 측정(수행 PR) |
|---|---|---|---|---|
| S-1 | 기준 불명 시각의 혼입 | 평일 513 덕하 기점 28편이 라벨 없이 격자에 있음 | 0(전 요일 × 전 노선) | 속성 테스트(P2-1, P2 AC 2·3) |
| S-2 | 방향 커버리지 | 10개 중 5개(1개는 기준 오표기) | 10/10 | 커버리지 불변식(P0-1b ②, P2 AC 1) |
| S-3 | 정상 조작 경고 | 기점 집합이 다른 노선 사이 전환(513↔나머지, 명촌 기점↔1115)에서 발생 | 0(30조합 크롤) | 계약 테스트(P0-2, P0 AC 2). 운영 로그 `tt.notice` 카운터(I-2, P0-3)로 배포 2주 뒤 ≈ 0 |
| S-4 | 편성 투명성 | 상태 줄 없음, 오늘 칩 재클릭 시 특별편 유지 0% | 특별편·공휴일·캐시 범위 밖 fixture에서 상태 줄 100%, 재클릭 후 유지 100% | 계약 테스트(P0-4, P1-2, 상태 매트릭스) |
| S-5 | T1 첫 화면 답 | 17시 행 y≈1753px(375, 스크롤바 포함). 스크롤바 숨김 기준선은 P0-0b 측정값으로 대체 | 첫 항목 bottom ≤ 600px, 스크롤 0. 복도 테스트 중앙값 ≤ 5초, 오답 0 | 헤드리스 측정(05~22시 정시 freeze 18회 × 360/375 × KO/EN, P0-0b 스크립트, P3 AC 9), 복도 테스트(P0-0b 기준선 → P3 후) |
| S-6 | T2 정답률 | 구조적으로 오답 유도 | ≥ 90%(P3 페르소나 5인) | 복도 테스트(P0-0b → P2·P3 후) |
| S-7 | T3·T5 탭 수 | /busno 노선 3개 × 전환 + 암산 | T3 ≤ 2탭(좁히기 펼침 + 거점), T5 ≤ 2탭 | 과업 분석 + 복도 테스트(P0-0b → P2 후) |
| S-8 | 노선 텍스트 대비 최소값 | 2.70:1 | ≥ 4.5:1(전 노선, 인접 화면 포함) | CSS 대비 테스트(P1-5, P3-5, 6.7 테스트 2) |
| S-9 | 접근성 속성 | aria-current 0, scope 0, caption 0, onchange 1 | 칩 그룹당 aria-current 1, 사이드바 aria-current=page 1, 모든 nav에 이름, 표마다 caption과 scope, onchange 0 | 계약 테스트(P0-2, P0-7b, P1-4). axe serious/critical 0(D13) |
| S-10 | i18n | EN 렌더 본문에 한국어 수십 자, 전환 시 쿼리 손실 | EN `[lang=ko]` 밖 한글 0자(속성·sr-only·`<title>` 포함), KO 비허용 라틴 `[lang=en]` 밖 0, 쿼리 보존 100%(다중 값 포함), 상태 매트릭스 전 행 KO/EN 통과 | i18n 스캔, 상태 매트릭스 × 언어(P0-6, P1-3, P2~P4 AC) |
| S-11 | 성능 | HTML 25.7KB 비압축, htmx 48KB를 모든 페이지에서 로드 | HTML gzip ≤ 12KB, 시간표 페이지 JS ≤ 3KB, htmx 0, 새 폰트 0 | 빌드 없는 크기 테스트, 응답 검사(P3-6, P3 AC 7·8) |
| S-12 | 문서 높이(모바일, 오늘 17:47) | 2548px(360/375, 스크롤바 포함) / 2184px(414, 숨김). 360/375 숨김 기준선은 P0-0b | P0-0b 스크롤바 숨김 기준선의 60% 이하(≥ 40% 감소) | 헤드리스 측정(P0-0b 스크립트, P3 AC 9(b)) |
| S-13 | 회귀 안전 | — | Phase마다 기존 테스트 100% 통과(의도된 이관은 목록화), strict xfail 수 단조 감소 → P3 종료 시 0 | CI(모든 PR) |
| S-14 | 운영 감지 | 공휴일 캐시 공백과 크롤 이상은 사용자 문의로 인지 | 발생 당일 admin 경고 | admin 테스트(P1-2, P4-4) |
| S-15 | 날짜 공지 정합 | 4개 표면 중 1개만 날짜 게이트 | 10/3 전후 모든 표면 문구 일치 | freezegun 두 시점 테스트(P0-9) |

### 계측(프라이버시 보존) 선택지

- **I-1 접근 로그 집계(권장, 기준선은 P0-0b에서 측정).** 기존 서버 접근 로그에서 경로, 쿼리 **키**(값 중에서는 `bus`, `dir`, `day`, `date` 유무만), 시간대, User-Agent의 모바일 여부만 일 단위로 집계하는 스크립트 `scripts/metrics/access_summary.py`를 둡니다. IP는 집계에 쓰지 않고 새로 보존하지도 않습니다. 측정 항목은 `/timetable`·`/busno` 시간대 분포, 모바일 비율, `/busno` 직접 유입 비율(D14 근거), `dir=in` 사용률(D6 검증), `date=` 사용률입니다.
- **I-2 서버 측 카운터 로그(P0-3).** warning·notice 코드가 렌더될 때 `log.info("tt.notice code=%s page=%s", code, endpoint)` 한 줄을 남깁니다. PII는 없습니다. `caplog` 테스트로 형식을 고정합니다.
- **I-3 이동 경로(쿠키 없음).** 교차 링크에 `?from=tt`처럼 출처 표식만 붙여 `/timetable → /unist` 이동률을 봅니다. 사용자 식별자는 없습니다. **[가정]** 쿼리 표식이 canonical·캐시에 영향을 주지 않도록 해당 키는 렌더에서 무시합니다.
- 제3자 분석 스크립트는 도입하지 않습니다(CDN 금지, zero-JS 원칙).

---

## 10. 리스크와 완화, 롤백

| # | 리스크 | 가능성/영향 | 완화 | 롤백 |
|---|---|---|---|---|
| R-1 | 추정 시각이 틀려 버스를 놓치게 함 | 중/고 | (a)를 기본으로 영구 운영 가능하게. go/no-go, 첨두 포함 n·IQR 게이트, 승인 게이트, 범위 표기, 실시간 링크 병치 | 오프셋 파일 삭제 → 자동으로 (a) |
| R-2 | 513이 두 방향에 모두 나와 혼란 | 중/중 | '경유' 표식, 승차 정류소 명시, 행선 언어를 1차 텍스트로. 복도 테스트 T2 ≥ 90% | 문구 조정 |
| R-3 | 모바일 컨트롤 과밀로 첫 화면 초과 | 중/중 | 방향만 상시 노출하고 나머지는 `<details>`. px 예산, 라벨 길이 상한, KO·EN 18시각 측정 | CSS revert |
| R-4 | 테스트 계약 대량 파손 | 중/중 | 추가형 필드, 템플릿 폴백 규칙, 마커 보존, PR마다 이관 목록(`test_valid` "20, 40" 등 명시), P0 안전망 | PR 단위 revert |
| R-5 | 북마크와 공유 링크 회귀 | 저/중 | 리다이렉트 대신 같은 화면 + canonical, 매핑 표 테스트, dep는 `DirectionSpec.origin_ko`로만 매핑 | — |
| R-6 | 특별편 규칙 변경으로 같은 URL의 의미가 날짜에 따라 바뀜 | 중/중 | P0은 링크 정규화만. 규칙은 ADR-015/D3 이후. `edition=base` 경로와 상태 줄 설명 | P2-5 단독 revert(링크 정규화는 유지) |
| R-7 | 공휴일 캐시 공백 | 중/고 | `holiday_known` 경고, admin 경보, 운영 절차에 워커 점검 추가 | — |
| R-8 | 인접 화면 순위 변경의 체감 변화(513이 FIRST에서 빠짐) | 중/저 | D5 승인, changelog 공지, 문구에 기점 표기. 표기(P2-6a)와 순위(P2-6b)를 분리 | P2-6b 단독 revert(표기는 유지) |
| R-9 | `legacy-ui-reference.md:89`의 레거시 HEX 고정 규칙과 충돌 | 저/중 | 권장안 (a)는 팔레트를 유지하므로 규칙 개정 불필요 | 토큰 값만 되돌림 |
| R-10 | 셸 변경이 admin에 회귀 | 중/중 | P0-7을 a/b로 나누고 각각 admin 스모크 포함, 사이드바 체크리스트 | P0-7a 또는 P0-7b 단독 revert |
| R-11 | zero-JS 원칙 침식, JS 비대화 | 저/중 | 3KB CI 단언, JS 없이 서버만으로 과업이 완결되는지 계약 테스트, `/lite` 불변 | JS 파일 제거(서버 렌더만으로 완결) |
| R-12 | 데이터 자체의 신뢰성(토=일 동일, 로그 불일치, 오래된 수집본) | 중/고 | Phase 3 진입 게이트(BIS 원본 대조 + `_meta` 공개), 데이터 경과 배너(P3-3), 크롤 이상 탐지(P4-4), 안내 문구는 '현재 데이터상 동일' | — |
| R-13 | sticky가 포커스를 가림(2.4.11) | 중/중 | scroll-padding/margin, 겹침 측정 AC | sticky 해제(CSS) |
| R-14 | 오래된 탭이나 bfcache에서 상대 시각이 틀림 | 중/중 | 절대 시각 병기, 'HH:MM 기준', no-cache, (D11) pageshow 재계산과 날짜 경계 배너 | — |
| R-15 | i18n 키 누락으로 키 문자열이 화면에 노출 | 중/저 | 키 커버리지 CI 필수(동적 접두사 포함), 상태 매트릭스 × 언어 테스트를 Phase마다 확장 | — |
| R-16 | 다중 워커에서 사이드카 캐시 불일치(`cli.py:313`, 기본 워커 2) | 저/중 | mtime·size 서명 재검증(`data/timetable.py:49-101` 선례), 가변 전역 상태 금지 | — |
| R-17 | 거점 라벨 오류(예: 태화강역 vs 태화강역광장, 시청 vs 태화루) | 중/중 | D7 운영자 검증, VIA_STOPS·정류소 ID 교차 검증 테스트 | 상수 수정 |
| R-18 | 운영자 유지 표면 증가 | 중/중 | (a) 영구 운영 가능, Phase 4는 go/no-go 뒤. notices와 오프셋 외 admin 기능 추가 금지 | 기능 비활성 |
| R-19 | 시각 고정 테스트가 UTC로 해석되어 틀린 날짜·시각을 검증 | 고/중 | `freeze_kst` 헬퍼와 자체 테스트를 P0-1a에 두고, 모든 시각 AC가 헬퍼를 쓰게 함 | — |
| R-20 | 날짜 공지가 시효를 넘겨 과거 '부터' 문구가 노출 | 고/저(10/3에 확정 발생) | P0-9를 다른 PR과 독립적으로 10/3 이전에 배포, 단일 날짜 상수 게이트 | P0-9 revert 시 기존 문구로 돌아감(시효 문제 재발) |

**롤백 원칙:**

- 모든 PR은 한 관심사만 담고 개별 revert가 가능해야 합니다.
- 데이터 스키마는 사이드카 추가만 합니다(시간표 JSON 불변). 따라서 코드 revert만으로 되돌아갑니다.
- 사이드카가 없거나 파손되면 graceful로 동작합니다.
- `?layout=v2` 같은 이중 템플릿은 쓰지 않습니다.
- 배포 전에 CI와 같은 명령 `uv sync --frozen && uv run --frozen pytest -q` 전량이 통과해야 합니다. 배포 뒤 24시간 동안 I-2 `tt.notice` 카운터와 5xx를 확인합니다.

---

## 11. 결정 필요 사항

| ID | 결정 | 선택지 | 권장 | 각 선택의 결과 | 막는 작업 |
|---|---|---|---|---|---|
| D1 | 513(과 도착 방향) UNIST 시각 | (a) 라벨+분리 / (b) 관리자 고정 오프셋 / (c) 로그 산출 + 승인 / (d) BIS API 조사 | (a) 즉시, P4-0 go/no-go 뒤 (c)→승인. 게이트 기본값은 방향 × 시간대(첨두 포함) n ≥ 30, IQR ≤ 15분 | (a) 거짓 정보 0, T2는 간접 답. (b) 단순하지만 근거가 약함. (c) 운영 부담이 있으나 실측 기반. (d) 성공하면 모두 대체. no-go이면 TF-2는 WND by design, (a) 영구 | P4-0~P4-2 |
| D2 | 페이지 정체성과 제목 | 'UNIST 전체 시간표'(out 기본 + in 보조) / 'UNIST 출발 전체 시간표'(out만) | 'UNIST 전체 시간표'. KO `<title>` 마커 '전체 시간표'는 P5까지 유지. P0에서는 기존 제목을 글자 그대로 유지 | 이름에 따라 `page.*.title` 키 값과 스모크 마커 개정 시점이 달라짐 | P1-3(값), P5-1 |
| D3 | 특별편 규칙 | (i) `day==오늘 코드`이면 특별편 유지 + `edition=base` / (ii) 폴백을 '요청 요일'로 변경 / (iii) `_edition.json` 라벨 | (i) 채택, (iii) 채택 권장(에디션 ID가 ASCII 슬러그라 KO 화면에 그대로 노출되기 때문), (ii)는 P4에서 별도 판단 | (i) 공유된 `?day=N`의 의미가 날짜에 따라 바뀜(상태 줄로 설명). 거부하면 P0 링크 정규화 + P1 표시까지만 유지. (ii)는 테스트 계약 변경. (iii)을 거부하면 슬러그 대신 '특별 시간표'로만 표기 | P2-5, P4-5 |
| D4 | 노선색 대비 | (a) 팔레트 유지 + route-mark / (b) ink 팔레트로 교체(713 #2E7D32, 1115 #B34700 등) | (a) | (a) 레거시 HEX 고정 규칙(`legacy-ui-reference.md:89`) 유지, 시각 정체성 보존. (b) 그 규칙의 개정과 `route_diagram`·`/board`·SVG 동기화, 전후 스크린샷 승인 필요 | P1-5, P3-5(인접 토큰) |
| D5 | `/board`·`/lite`의 513 시간표 파생 행 **순위** | 순위에서 제외 / 목록에서 제거 / 현행 유지 | 순위 제외. 기점 표기와 `/unist` M-1 수정은 D5와 무관하게 P2-6a에서 진행 | 제외하면 게시판 '다음 버스' 체감이 바뀜(changelog 공지). 현행 유지는 DS-2가 부분 잔존(라벨은 적용, 순위 혼입은 남음) | P2-6b |
| D6 | 'UNIST로 도착'(`dir=in`)을 `/timetable`에 포함할지 | 포함(기점 출발 시각, 카운트다운 없음) / `/busno`와 `/stops`에 맡김 / 포함하되 기점 탑승자에게 카운트다운 허용 | 포함, 카운트다운 없음 | 포함하면 T5가 2탭. 제외하면 IA-5는 `/busno` 방향 칩으로 대체하고 커버리지 불변식을 `/busno`로 대체. 카운트다운을 허용하면 중간 정류장 오독 위험 | P2-2 |
| D7 | 목적지 거점 칩 목록과 라벨, 승차 정류소 문구 | 4.5절 7개(검증 후) / 축소(시내·울산역·동구 3개) / 도입 안 함. `taehwaru` 별도 거점 여부. 정문(231) 탑승 안내 문구 | 4.5절 목록을 운영자가 검증(특히 1115와 태화강역광장, 태화루 분리 여부). 231 안내 문구 확인 | 축소하면 모바일은 간결하지만 공업탑·울산대 탐색이 약해짐. 도입하지 않으면 T3 미지원(IA-2는 방향 칩으로 부분 해소) | P2-1(문구), P2-3 |
| D8 | 토·일 탭 | 3탭 유지 + '현재 데이터상 동일' 안내 / 동일할 때 동적 병합 | 3탭 유지 + 안내. BIS 원본 대조 선행 | 병합은 크롤 이상을 숨길 수 있음 | P3-3 |
| D9 | nav 언어와 구조 | KO 한국어화 + 4.6절 재편 / 영어 브랜딩 유지 | 한국어화 + 재편. `test_i18n.py:23` 개정 동반 | 유지하면 CI-7이 남고, P3-5는 'KO nav 영문 라벨에 `lang="en"` 부여'로 대체(A11Y-2의 SC 3.1.2 절반 충족) | P3-5 |
| D10 | `/busno` 기본 진입값 | 현행 513/덕하 / 편수가 가장 많은 UNIST 기점 노선(753 평일 50편, `to=downtown`) / 713/UNIST / 마지막 선택 쿠키 | 데이터 규칙(753 downtown). 쿠키는 쓰지 않음(N-9) | 쿠키는 공유 URL과 캐시 결정성을 해침. 현행 유지면 IA-11·M-24 잔존 | P2-4 |
| D11 | 점진 JS | 3KB 이하 `timetable-now.js` 허용 / 서버 렌더 + '기준 HH:MM' + 새로고침만 | 허용(선택 PR). zero-JS 적용 범위는 `/lite` 전체와 시간표의 '과업 완결성' | 거부해도 모든 과업은 가능하고 신선도만 수동(MR-8 부분 잔존). htmx 제외와 splitflap.js 보강은 D11과 무관하게 진행 | P3-6(JS 부분) |
| D12 | 데이터 메타·공지·공휴일 이름·경과 임계값·학사 모드 | `_meta.json` 푸터 / `notices.json` + admin / holiday 캐시에 이름 추가 / 데이터 경과 경고 임계값 N일 / admin의 현재 학사 모드 입력 | 앞의 둘 승인, 이름 저장은 보류, N=120일, 학사 모드는 admin 수동 입력(단일 값) | 푸터 공개는 수집일이 오래됐을 때 신뢰 판단에 도움. 거부하면 DS-8·CI-13·IA-14 잔존, 경과 배너 없음 | P1-6, P3-3(경과), P4-3 |
| D13 | 브라우저 테스트 인프라 | Playwright + axe를 dev 의존성으로 도입(처음엔 CI 선택) / 헤드리스 Chrome 수동 스크립트 + 체크리스트 | P0-0b 수동 스크립트로 시작, Phase 3 전에 Playwright 도입 여부 재판단 | 도입하면 좌표·확대·JS-off E2E 자동화, uv 의존성과 브라우저 바이너리·CI 시간 비용. 미도입이면 좌표 AC는 수동 게이트 | P0(선택), P3 AC 9·10 |
| D14 | 페이지 통합 / `/busno` 301 | 2단 영구 유지 / `/timetable` route focus로 통합(별칭 렌더) / 통합 후 301 | 2단 유지. I-1 로그로 4주 이상 관찰한 뒤 재검토 | 통합하면 URL 상태 조합과 테스트 이관 비용 증가 | P5-4 |
| D15 | EN 지명 표기 | '울산역' → 'Ulsan Station (KTX)' / RR 'Ulsanyeok'. ADR-014(draft) 전에는 `place.*` 임시 키 사용 | 'Ulsan Station (KTX)', 임시 키 허용 | ADR-014 확정 시 키 교체 | P1-3 |
| D16 | `/board` live 과잉 대체(`board.py:257-262`) 처리 | 이번 계획에 포함 / 별도 버그 | 별도 버그 PR | 포함하면 회귀 원인이 섞임 | — |
| D17 | main max-width 확장, 다크 모드 | 이번 범위 포함 / 제외 | 둘 다 제외(토큰화로 다크 모드 준비만) | 포함하면 셸 전체 회귀 범위 확대 | — |

**Phase별 차단 요약**

- Phase 0: 차단 없음(D13은 선택). P0-0a는 오너 확인만 필요.
- Phase 1: D4(P1-5), D12(P1-6), D15(P1-3 값), D2(title 값).
- Phase 2: D3(P2-5), D5(P2-6b만), D6(P2-2), D7(P2-3, P2-1 문구), D10(P2-4). P2-1, P2-6a, P2-7은 결정 없이 진행.
- Phase 3: 데이터 신뢰 게이트(운영 작업), D8(P3-3), D9(P3-5), D11(P3-6의 JS 부분), D12(경과 임계값).
- Phase 4: D1(P4-0 go/no-go), D12(P4-3), D3-ii(P4-5).
- Phase 5: D2(P5-1), D14(P5-4).

---

## 12. 부록: finding → Phase 추적 매트릭스

표기: P0~P5 = 해소 Phase(괄호 = 부분 또는 완화). **WND** = won't do, 사유 병기. '결정 거부 시 잔존' 열은 해당 결정이 거부되거나 no-go일 때 그 finding이 어떤 상태로 남는지 적습니다(— = 결정 의존 없음).

### IA(과업 효율)

| ID | 보정 심각도 | Phase | 결정 거부 시 잔존 | 비고 |
|---|---|---|---|---|
| IA-1 | critical | (P0) → P2 → (P4 추정) | D1 no-go: P2 (a)로 해소 완료, 추정 합류만 없음 | P0 각주, P2 분리, P4 승인 시 추정 합류 |
| IA-2 | high | P2 | D7 거부: 방향 칩·행선 표기로 해소, 거점 탐색 없음 | 방향 칩, 행선 표기, 거점 |
| IA-3 | high | P3 | — | 다음 출발, `#now` |
| IA-4 | high | P0 → P2(근본) | — | |
| IA-5 | high | P2 | D6 거부: `/busno` 방향 칩과 `/stops` 링크로 대체(T5 탭 수 증가) | `dir=in`(D6) |
| IA-6 | medium | (P0) → P1(표시) → P2(규칙, D3) | D3 거부: P0 링크 정규화 + P1 표시까지만. `?day=N` 특별편 해제는 표시된 채 잔존 | |
| IA-7 | medium | P0 | — | |
| IA-8 | medium | P3 | — | `date=` |
| IA-9 | medium | P3 | D9 거부: 교차 링크·아이콘은 해소, nav 재편 없음 | nav, 교차 링크 |
| IA-10 | medium | P3 | — | `routes=`, 같은 분 병합 |
| IA-11 | medium | P2 | D10 현행 유지: 잔존 | |
| IA-12 | medium | P0(쿼리) → P1 | — | |
| IA-13 | low | P2 | — | 공백 행, 요약 |
| IA-14 | low | P1(출처) → P4(공지) | D12 거부: 잔존 | |

### DS(데이터 의미)

| ID | 보정 | Phase | 결정 거부 시 잔존 | 비고 |
|---|---|---|---|---|
| DS-1 | critical | (P0) → P2 → (P4) | D1 no-go: (a)로 해소 완료 | |
| DS-2 | high | P2-6a(라벨) → P2-6b(순위) → (P4) | D5 거부: 부분 잔존(라벨은 적용, `/board`·`/lite` 순위 혼입 남음) | |
| DS-3 | high | P2 | — | |
| DS-4 | medium | (P0) → P2 | D3 거부: P0 완화 + P1 표시까지 | |
| DS-5 | low | P1(표시) → P4 | D3-ii 거부: 표시만(폴백 규칙 잔존) | |
| DS-6 | medium | P1 | — | |
| DS-7 | medium | P0 → P3(신선도) | — | |
| DS-8 | medium | P1(푸터) → P3(경과 경고) | D12 거부: 잔존 | |
| DS-9 | low | P4 | D12 거부: P0-9의 날짜 게이트까지만 | notices |
| DS-10 | medium | P0 | — | |
| DS-11 | low | P2 | — | 승차 정류소 표기(233/234/231) |
| DS-12 | low | P3(표시) → P4(탐지) | — | 병합 안 함(D8) |
| DS-13 | low | P2 | — | |
| DS-14 | low | P1 | — | |

### MR(모바일)

| ID | 보정 | Phase | 결정 거부 시 잔존 |
|---|---|---|---|
| MR-1 | high | P3 | — |
| MR-2 | high | P0(P0-7a) | — |
| MR-3 | medium | P0 | — |
| MR-4 | medium | P0 | — |
| MR-5 | medium | P3 | — |
| MR-6 | medium | P3 | — |
| MR-7 | low | P3 | — |
| MR-8 | low | P3(D11, 서버 'HH:MM 기준'은 P0). boardclock.js 일반화 대신 신규 파일(하드와이어 `#dboard-time` 결합 회피) | D11 거부: 서버 'HH:MM 기준' + 새로고침만(부분 잔존) |
| MR-9 | low | P1 | — |
| MR-10 | low | P0 | — |
| MR-11 | low | P1(덮어쓰기 제거). 폰트 서브셋은 P5 선택 | — |
| MR-12 | low | P3 | — |

### A11Y(접근성)

| ID | 보정 | Phase | 결정 거부 시 잔존 |
|---|---|---|---|
| A11Y-1 | high | P1(D4) | D4 어느 쪽이든 해소 |
| A11Y-2 | high | P1(EN 본문 + KO 대칭 lang) | D9 거부: P3-5를 KO nav 영문 라벨 `lang="en"`으로 대체해 해소 |
| A11Y-3 | high | P0(P0-7a) | — |
| A11Y-4 | high | P0 | — |
| A11Y-5 | medium | P0(P0-7b 사이드바 aria-current=page·nav 이름, P0-6 언어 aria-current) → P1(P1-4 칩 그룹 role=group·aria-current) | — |
| A11Y-6 | medium | P1 | — |
| A11Y-7 | low | P1(텍스트 라벨 원칙) → P3 | — |
| A11Y-8 | low | P0 | — |
| A11Y-9 | low | P0 | — |
| A11Y-10 | low | P0(#1a237e, #ff9800 기각, `/board` 기존 링 교체) | — |
| A11Y-11 | low | P0(크기) → P1(칩 테두리 #7986cb) | — |
| A11Y-12 | low | P0 | — |
| A11Y-13 | medium | P0 | — |
| A11Y-14 | low | P0 | — |

### CI(일관성·i18n·문구)

| ID | 보정 | Phase | 결정 거부 시 잔존 |
|---|---|---|---|
| CI-1 | high | P2 | — |
| CI-2 | medium | P0 | — |
| CI-3 | high | P1 | — |
| CI-4 | medium | P0 | — |
| CI-5 | medium | P0 | — |
| CI-6 | medium | (P0) → P1(키) → P3 | D9 거부: 페이지 이름 일치는 해소, nav 언어만 영어 |
| CI-7 | low | P3(D9) | D9 거부: 잔존(lang="en"으로 접근성만 보완) |
| CI-8 | medium | P1 | — |
| CI-9 | low | P1(누락·빈 상태) → P3(운행 종료) | — |
| CI-10 | medium | (P0) → P2-6a | — |
| CI-11 | medium | P1 | — |
| CI-12 | low | P0 | — |
| CI-13 | low | P1 | D12 거부: 잔존 |

### TF(기술 타당성)

| ID | 보정 | Phase | 결정 거부 시 잔존 | 비고 |
|---|---|---|---|---|
| TF-1 | high | P1(모델) → P2(적용) | — | |
| TF-2 | high | P4(D1) | D1 no-go: **WND by design**, (a) 영구 운영 | (a)는 P2에서 운영 |
| TF-3 | high | P1 | — | `FallbackLog`로 폴백 노선 노출 |
| TF-4 | medium | P3 | — | |
| TF-5 | medium | P0(안전망) → P5(완결) | — | |
| TF-6 | medium | P0(kwargs, CardEntry kind/params) → P1 | — | |
| TF-7 | medium | P0(select 제거) → P3 | — | |
| TF-8 | low | P3(htmx 제외, 예산) → P5(폰트) | — | |
| TF-9 | refuted | **WND(결함 아님)** | — | Flask가 static을 `no-cache`+ETag로 제공하므로 캐시 혼합 위험 없음. 재검증 왕복 제거는 P5 선택 성능 과제 |
| TF-10 | medium | P1 | — | |
| TF-11 | medium | P1(헬퍼) → P2-6a(인접 사본 수렴) | — | |
| TF-12 | low | P1 | — | |
| TF-13 | low | P3(P3-6: timetable-now.js 신규 파일, splitflap.js try/catch 보강) | D11 거부: splitflap.js 보강과 htmx 제외는 그대로 수행 | boardclock.js 일반화 대신 신규 파일(하드와이어 결합 회피, `/board` 회귀 범위 분리) |
| TF-14 | medium | P0 | — | 단계 분리 자체 |

### MISSED 항목(검증된 추가 발견)

출처 표기: `IA#n`은 digest IA 렌즈 MISSED의 n번째 항목입니다(구분자 ' | ' 기준. DS·MR·A11Y·CI·TF도 같음).

| ID | 내용 | 출처(렌즈 MISSED #n) | 근거 | Phase |
|---|---|---|---|---|
| M-1 | `/unist` via 카드가 기점명 없이 표기하고 `_is_future`가 막 떠난 편을 숨김 | IA#1, DS#4 | `unist_board.py:45,89-95` | P0(문구, P0-5) → P2-6a(`origin_window`, D5 무관) |
| M-2 | `/board`가 513 기점 행을 UNIST 행과 섞어 정렬(약 1시간 어긋남 [추론]) | IA#2, TF#9 | `board.py:151-166` | P2-6a(표기) → P2-6b(순위, D5) |
| M-3 | `/board` live 과잉 대체 | DS#5 | `board.py:257-262` | **WND(이 계획)**: 별도 버그 PR(D16) |
| M-4 | 공휴일 캐시 두 달 | DS#6 | `holiday_service.py:51-65`(보존 범위), `:129-136`(읽기 경로) | P1 |
| M-5 | info '앞쪽/뒤쪽' 문구 | DS#2, CI#3 | `info.html:45-47` | P0 |
| M-6 | VIA_STOPS 종점 키 역전 함정 | CI#4 | `constants.py` VIA_STOPS | P2(`terminal_key`) |
| M-7 | `/timetable` 513 삼남 방향 누락, 방향 혼합 표 | TF#1, MR#3, CI#1, A11Y#8 | `unist_timetable.py:82` | P0(각주) → P2 |
| M-8 | 운행 종료·첫차 전 안내 없음 | IA#6 | `unist_partial.html:17` 대비 | P3 |
| M-9 | 승차 정류소(196040233/234/231) 미표기 | IA#3 | `constants.py:38,40,42` ROUTEID stops, STOP_IDS | P2-1(`also_stops_at`, D7 문구) |
| M-10 | htmx를 모든 셸 페이지에서 로드 | TF#2 | `_base.html:100` | P3 |
| M-11 | 범위 밖·숫자 아닌 `day`를 조용히 보정 | CI#5 | `domain/busno.py:104-105`, `routes/busno.py:27-29`, `routes/unist_timetable.py:40-43` | P1-7 |
| M-12 | `/board`·`/lite` 오류 배너에 내부 오류 원문 | CI#6 | `board.html:21-22`, `board_lite.html:18` | P2-6a(작업 (3), P2 AC 11) |
| M-13 | `/unist` 카드 헤더, `/board` `c-route` 대비(흰 배경·#fff8e1) | A11Y#1, A11Y#2 | `style.css:537-549,585,958-965` | P3-5 |
| M-14 | nav 체크박스 bfcache 복원 | MR#4 | `_base.html:13` | P0-7a |
| M-15 | 200% 확대 시 모바일 셸 진입 | A11Y#3 | `style.css` ≤720px 규칙 | P0(셸) → P3(검증) |
| M-16 | 접근성 회귀 테스트 부재 | A11Y#9 | `test_unist_timetable_route.py:103` | P0-1b |
| M-17 | `/board` `td role=button` | A11Y#7 | `board_table.html:34` | **WND(이 계획)**: 시간표 재설계는 셀 상호작용을 쓰지 않음. `/board` 접근성 백로그로 이관 |
| M-18 | 자동 갱신 영역에 일시정지 없음(`/board` 15s 등) | A11Y#6 | `board.html:32` 등 | **WND(이 계획)**: 인접 실시간 화면 고유 이슈. 시간표는 aria-live·폴링을 도입하지 않음. 백로그 |
| M-19 | 로그 기점 목격 시각과 시간표 불일치, 로그 표본 부족 | DS#1, IA#5(후반) | `data/logs.tsv`, `513.json` | P3 게이트(BIS 대조) → P4-0(logs.tsv 재집계) |
| M-20 | `/unist` 방향 규칙과의 동치성 | TF#6 | `unist_board.py:53-71` | P1-1 |
| M-21 | `get_busroute_info` admin 사용 | TF#7 | `admin.py` 5곳, `timetable_editor.py:90` | 전 Phase 제약(변경 금지) |
| M-22 | 백업 화이트리스트 | TF#8 | `backup.py:28-35`(`_FLAT_FILES`), `:44-67`(`_is_safe_path`) | P4(offsets, notices만. `_meta`는 제외, `_edition.json`은 자동 포함) |
| M-23 | 하드코딩된 날짜 공지의 시효 | TF#10 | `i18n.py:70`, `constants.py:68`, `info.html:50,61`, `route_diagram.py:45`(게이트 선례) | **P0-9(시효 핫픽스)** → P4-3(구조화) |
| M-24 | `/busno` 기본값 513/덕하 | TF#11 | `domain/busno.py:99,113` | P2(D10) |
| M-25 | 시각 비교 사본 4벌 | TF#5 | `board.py:125`, `unist_board.py:45` 등 | P1 → P2-6a |
| M-26 | 시간표 폰트 덮어쓰기 | TF#3 | `timetable.css:11` | P1 |
| M-27 | 토=일 완전 동일이 크롤 이상일 가능성 | DS-12 vnote(MISSED 아님) | `data/timetable/*.json` | P3 게이트 → P4-4 |
| M-28 | `/board` 한국어 하드코딩 aria-label과 열 헤더 | CI#9 | `board_table.html:17-20,34`, `board.html:12-13` | P3-5(t() 이관, P3 AC 12) |
| M-29 | 두 표기 체계('MM, MM' vs 'MM (513)')와 '(513)' 텍스트의 색각 대체 역할 | CI#7 | `domain/busno.py:55`, `unist_timetable.html:47` | P1-4(C5 공통 규칙) → P2-4(`/busno` 토큰화). G-2 '노선번호 텍스트 항상 표시' 단언 |
| M-30 | `/unist` `.bus-card.last-bus { opacity:0.6 }`이 대비를 추가로 낮춤 | A11Y#1(후반) | `style.css:957` | P3-5(opacity 제거, '막차' 텍스트 + #595959) |
| M-31 | 기존 `/board` 포커스 링 #ff9800(2.16:1) | A11Y#5 | `style.css:783-784` | P0-7b(`--focus-ring`으로 교체) |
| M-32 | 메뉴가 열린 동안 배경 스크롤 체이닝 | MR#6 | `style.css:192-202` | P0-7a(`overscroll-behavior:contain`) |
| M-33 | 측정 방법론: 스크롤바 15px 포함 측정 → 기준선 재측정 필요 | MR#5 | MR-1 측정 방식 | P0-0b(스크롤바 숨김 기준선) |

**기존 finding으로 흡수된 digest MISSED**(1:1 대응 완결용)

| 출처 | 내용 요지 | 흡수처 |
|---|---|---|
| IA#4 | 배지 대비 수치(1115 2.70, 713 4.12) | A11Y-1(P1-5) |
| IA#5(전반) | 17시 행 배지 10개·지난 편 8개 정정 | 1.1 기준선 표에 반영 |
| DS#3 | 513 출발지 선택의 역직관성 | DS-3(P0-2 방향 칩 → P2-4) |
| DS#7 | 시간표 두 페이지 i18n 부재 | A11Y-2/CI-3(P1-3) |
| MR#1 | 노선 칩의 dep 전달로 경고 | IA-4(P0-2) |
| MR#2 | day 명시로 특별편 해제 | DS-4/IA-6(P0-4 → P2-5) |
| MR#7 | 출발지 select가 기점명을 보여 줌 | DS-3/IA-2(P0-2 → P2-4) |
| A11Y#4 | box-shadow 오버레이가 탭을 흡수하지 않음 | MR-2(P0-7a backdrop) |
| CI#2 | EN 모드 `lang="en"`인데 본문 한국어 | A11Y-2(P1-3, 양방향 lang 규칙) |
| CI#8 | 🕒 아이콘 중복 | A11Y-8(P0-7b) |
| TF#4 | static no-cache 재검증 왕복 | TF-9 재분류(P5-5 선택) |

critical, high, medium 심각도의 검증된 finding은 모두 **실행 PR과 수용 기준이 있는 Phase**에 배정했습니다. 예를 들어 A11Y-5는 P0-7b·P0-6·P1-4와 P0 AC 14·P1 AC 7에, M-12는 P2-6a와 P2 AC 11에, M-23은 P0-9와 P0 AC 15에 배정돼 있습니다. 결정 의존 항목이 결정 거부나 no-go로 남기는 잔존 상태는 각 표의 '결정 거부 시 잔존' 열에 적었습니다. WND는 반박된 TF-9와 인접 화면 고유의 M-3·M-17·M-18, 그리고 D1 no-go 시의 TF-2(by design)뿐이며, 모두 사유와 이관처를 적었습니다.