# Design Audit — Feature Docs (F01–F10)

- **Auditor:** claude-sonnet-4-6
- **Date:** 2026-06-01
- **Criteria:** `docs/refactor/auditor/design-audit-criteria.md` (C-1~C-7, F-1~F-10)

---

## F01 — 출발 게시판 (Departure Board)

```
TARGET: docs/refactor/features/F01-departure-board.md
VERDICT: PASS
FAIL_REASONS: (없음)
PASS_NOTES:
  - frontmatter 5개 키(status, designer, auditor_status, last_updated, feature_id) 모두 존재.
  - 섹션 0~10 전부 존재. 섹션 헤더 누락 없음.
  - 코드 블록 전체 python/html 언어 태그 부착.
  - 파일 경로 전부 프로젝트 루트 기준 상대 경로(infopages/, src/, bushexa/).
  - 라인 인용은 path:NN 또는 path:NN-NN 형식 준수.
  - 결정·주장 단정형 유지. 불확실 사항은 §10 미해결 질문에 격리.
  - As-is/To-be 한 줄 요약 충실.
  - Streamlit API 전수 표: 6행, file:line 위치 및 용도 기재.
  - 외부 API 2건: URL·메서드·파라미터·응답 형식·실패 응답 모두 명시.
  - URL/핸들러 시그니처/템플릿 경로 3종 완비.
  - 도메인 서비스 함수 시그니처 타입힌트 포함(get_board_data, build_timetable_rows, merge_live_rows).
  - HTMX 폴링 간격(15s), 토픽, selector(#board-table) 명시.
  - AC 6건, 각 항목에 pytest 명령 또는 grep 검증 방법 포함.
  - 단위 테스트 6건 이름 제시(≥3 충족).
  - 영향 doc(F06, F07) 명시.
  - 결함·악취 6건 각각 단독 항목(결함 1~4, 안티패턴 1~2)으로 분리.
```

---

## F02 — 버스번호별 시간표 (busno)

```
TARGET: docs/refactor/features/F02-busno.md
VERDICT: FAIL
FAIL_REASONS:
  - F-9: §9 영향 범위에서 "F01 (departure_board, 미작성)"으로 기재함.
    F01이 실제로 작성·존재하는 문서임에도 "미작성"이라 표기하여 영향 doc ID 정보가
    부정확하다. 기준상 영향 doc ID가 나열되어야 하며 부재 사실이 아닌 잘못된 주석이
    포함된 것은 F-9 위반으로 처리한다.
PASS_NOTES:
  - frontmatter 5개 키 완비.
  - 섹션 0~10 전부 존재.
  - 코드 블록 언어 태그(python) 부착.
  - As-is/To-be 한 줄 요약 충실.
  - Streamlit API 전수 표 10행, file:line 및 용도 기재.
  - 외부 API 없음 — 해당 없음 명시.
  - URL(GET /busno)/핸들러 시그니처/템플릿 경로(busno.html) 완비.
  - 타입힌트 포함 시그니처(get_busno_page_data, get_timetable, get_busroute_info, get_time).
  - HTMX/SSE 해당 없음 명시.
  - AC 5건, 각 검증 방법 포함.
  - 단위 테스트 4건 이름 제시.
  - 결함 4건 각각 분리.
```

---

## F03 — 정보 페이지 (Info Page)

```
TARGET: docs/refactor/features/F03-info.md
VERDICT: FAIL
FAIL_REASONS:
  - F-8: §8.1 단위 테스트 케이스가 5건 제시되어 있으나,
    첫 번째 항목 `test_info_returns_200`은 Flask test_client를 사용하는 통합 테스트 성격이며
    §8.2에도 동일한 `c.get("/info") → 200` 시나리오가 중복 기재된다.
    순수 단위 테스트(도메인 함수 독립 검증)가 실질적으로 2건에 불과하다
    (`test_info_hexa_param_ignored`, `test_info_changelog_missing_fallback`).
    나머지 3건(`test_info_returns_200`, `test_info_contains_route_numbers`,
    `test_info_image_url_uses_static`)은 라우트 통합 테스트와 구분이 모호하여
    "단위 테스트 케이스 ≥3건 이름" 기준에 미달한다.
PASS_NOTES:
  - frontmatter 5개 키 완비.
  - 섹션 0~10 전부 존재.
  - 코드 블록 python/json 언어 태그 부착.
  - 경로 프로젝트 루트 기준 상대 경로(infopages/, bushexa/).
  - As-is/To-be 한 줄 요약 충실.
  - Streamlit API 전수 표 14행, file:line 및 용도 기재.
  - 외부 API 없음 — 해당 없음 명시.
  - URL(GET /info)/핸들러 시그니처/템플릿(info.html) 완비.
  - 도메인 서비스 없음 — 해당 없음 명시.
  - HTMX/SSE 해당 없음 명시.
  - AC 5건, 검증 방법 포함.
  - 영향 doc(F04) 명시.
  - 결함 2건, 악취 2건 각각 분리.
```

---

## F04 — 관리자 페이지 (Admin Panel)

```
TARGET: docs/refactor/features/F04-admin.md
VERDICT: FAIL
FAIL_REASONS:
  - F-8: §8.1 단위 테스트 파일 3개에 총 15개 이름이 제시되어 있으나,
    `test_auth_service.py` 6건, `test_timetable_editor.py` 6건,
    `test_bus_log_repo_query.py` 5건으로 분류됨.
    이는 기준 ≥3건을 충족하지만, 기준이 "단위 테스트 케이스 ≥3건 이름 제시"이므로
    PASS. (아래 별도 FAIL 없음 — F-8 자체는 통과.)
  - F-5: §6 인터페이스 계약의 `AuthService.verify`, `AuthService.needs_setup`,
    `GovtrackStatusReader.latest`, `GovtrackStatusReader.history`,
    `TimetableCrawlJob.start`, `TimetableCrawlJob.progress` 시그니처에
    반환 타입이 누락되어 있다.
    예: `def verify(self, plain: str) -> bool:` — 이 줄은 있으나
    `@property needs_setup`의 반환 타입은 `: bool`이 코드 블록에 없음.
    `TimetableCrawlJob.start` 반환 `str`은 docstring에만 기재, 시그니처 줄에 없음.
    `TimetableCrawlJob.progress` 반환 `Iterator[ProgressEvent]`도 시그니처 줄 미포함.
    타입힌트가 일부 시그니처 줄에서 누락되어 F-5 위반.
PASS_NOTES:
  - status: designed (다른 Sonnet doc은 draft). frontmatter 5개 키 완비.
  - 섹션 0~10 전부 존재.
  - 코드 블록 python 언어 태그 부착.
  - As-is/To-be 한 줄 요약 충실.
  - Streamlit API 전수 표 26행(info.py 포함), file:line 및 용도 기재.
  - 외부 API 1건(시간표 재크롤용 BIS API, F10 위임): URL 명시.
  - URL/메서드 표 14행, 핸들러 시그니처, 템플릿 경로 트리 완비.
  - HTMX hx-post 편집, SSE 재크롤·govtrack 토픽, selector 명시.
  - AC: 인증 6건, 데이터 5건, 시간표 6건, 재크롤 5건, Govtrack 3건, 비밀번호 4건.
    각 항목 검증 방법(pytest 또는 명령) 포함.
  - 영향 doc(F03, F09, F10) 명시.
  - 결함 9건(D1~D9) 각각 분리.
```

---

## F05 — 운행 재구성 테이블 (running_table)

```
TARGET: docs/refactor/features/F05-running-table.md
VERDICT: FAIL
FAIL_REASONS:
  - F-9: §9 영향 범위에서 "F-admin (미작성)"으로 기재. F04가 실제로 작성·존재하며
    정식 ID는 F04이다. 영향 받는 feature doc ID를 "F04"로 명시해야 하나
    "F-admin (미작성)"으로 잘못 표기하여 F-9 위반.
PASS_NOTES:
  - frontmatter 5개 키 완비.
  - 섹션 0~10 전부 존재.
  - 코드 블록 python 언어 태그 부착.
  - As-is/To-be 한 줄 요약 충실.
  - Streamlit API 전수 표 6행, file:line 기재.
  - 외부 API 없음 — 해당 없음 명시.
  - URL(GET /running)/핸들러 시그니처/템플릿(running.html) 완비.
  - 타입힌트 포함 시그니처(get_running_page_data, parse_timelog, parse_runs,
    parse_each_vehicle, BusTimelogRepository.get_log_by_route_id).
  - HTMX/SSE 해당 없음 명시.
  - AC 5건, 검증 방법 포함.
  - 단위 테스트 5건 이름 제시.
  - 결함 6건 각각 분리.
  - govtrack doc ID는 "govtrack 데몬 (미작성)"으로 표기되어 있으나,
    F09가 실제 작성된 문서이다. 그러나 이 항목은 "govtrack 데몬"이라는
    기능을 지칭하며 F-9 판정에서 F04 누락이 이미 FAIL 근거로 충분하므로
    추가 F-9 위반 중복 기록(F09 미표기)은 별도로 기재하지 않는다.
```

---

## F06 — 정류소별 버스 도착 정보 (Stops)

```
TARGET: docs/refactor/features/F06-stops.md
VERDICT: PASS
FAIL_REASONS: (없음)
PASS_NOTES:
  - frontmatter 5개 키 완비.
  - 섹션 0~10 전부 존재.
  - 코드 블록 python/html 언어 태그 부착.
  - As-is/To-be 한 줄 요약 충실.
  - Streamlit API 전수 표 7행, file:line 기재.
  - 외부 API(울산 BIS): URL·메서드·파라미터 표·응답 형식·실패 응답 명시.
  - URL 표(2행)/핸들러 시그니처/템플릿(stops/index.html, stops/partial.html) 완비.
  - 타입힌트 포함 시그니처(get_stop_data, filter_and_sort_arrivals, check_long_gap).
  - HTMX 폴링 간격(10s), selector(#stops-table), SSE 해당 없음 명시.
  - AC 6건, 각 검증 방법 포함.
  - 단위 테스트 6건 이름 제시.
  - 영향 doc(F01, F07) 명시.
  - 결함·악취 6건 각각 분리.
```

---

## F07 — UNIST 버스 정보 카드 (UNIST Board)

```
TARGET: docs/refactor/features/F07-unist-board.md
VERDICT: PASS
FAIL_REASONS: (없음)
PASS_NOTES:
  - frontmatter 5개 키 완비.
  - 섹션 0~10 전부 존재.
  - 코드 블록 python/html 언어 태그 부착.
  - As-is/To-be 한 줄 요약 충실.
  - Streamlit API 전수 표 9행, file:line 기재.
  - 외부 API 2건(울산 BIS, 국토부 공휴일): URL·메서드·파라미터·응답 형식·실패 응답 명시.
  - URL 표(2행)/핸들러 시그니처/템플릿(unist/index.html, unist/partial.html, unist/_card.html) 완비.
  - 타입힌트 포함 시그니처(get_unist_board_data, build_via_card, build_from_card).
  - HTMX 폴링 간격(30s), selector(#unist-grid), SSE 옵션 2차안 명시.
  - AC 6건, 각 검증 방법 포함.
  - 단위 테스트 6건 이름 제시.
  - 영향 doc(F01, F06) 명시.
  - 결함·악취 6건 각각 분리.
```

---

## F08 — 전체 시간표 컬러 그리드 (unist_timetable)

```
TARGET: docs/refactor/features/F08-unist-timetable.md
VERDICT: FAIL
FAIL_REASONS:
  - F-9: §9 영향 범위에 F02, F05가 명시되어 있으나 F07도 "공유 서비스 함수"
    (get_timetable, get_busroute_info)를 공통으로 사용한다. F07이 나열되지 않았다.
    기준 "영향 받는 다른 feature doc ID가 나열됨"에서 문서에 기재되지 않은 ID는
    FAIL 근거가 된다. 단, F09 이후도 timetable JSON을 읽으므로 누락 범위가 넓으나,
    F07의 get_timetable 공유는 §4.4(도메인 서비스 호출)에서 같은 모듈을 참조하는
    명백한 의존이다. F-9 위반.
PASS_NOTES:
  - frontmatter 5개 키 완비.
  - 섹션 0~10 전부 존재.
  - 코드 블록 python/css 언어 태그 부착.
  - As-is/To-be 한 줄 요약 충실.
  - Streamlit API 전수 표 5행, file:line 기재.
  - 외부 API 없음 — 해당 없음 명시.
  - URL(GET /timetable)/핸들러 시그니처/템플릿(timetable.html) 완비.
  - 타입힌트 포함 시그니처(get_full_timetable_data, get_timetable, get_busroute_info).
  - HTMX/SSE 해당 없음 명시.
  - AC 5건, 검증 방법 포함.
  - 단위 테스트 4건 이름 제시(≥3 충족).
  - 결함·악취 4건 각각 분리.
```

---

## F09 — Govtrack 데몬 (버스 통과 로그 수집)

```
TARGET: docs/refactor/features/F09-govtrack-daemon.md
VERDICT: FAIL
FAIL_REASONS:
  - F-2: §2.2 Streamlit API 전수 목록 표가 존재하나, 내용이
    "— | — | govtrack 데몬은 Streamlit 미사용 (clean)." 1행으로만 구성되어 있다.
    기준은 "현재 구현 분석에 Streamlit API 전수 표가 있고 각 row가 위치(file:line)와
    용도 기재"인데, 실제 Streamlit 미사용이 사실이더라도 기준은 표의 존재 + row 기재를
    요구한다. 단, Streamlit이 실제로 0개인 경우를 "해당 없음" 처리하는 명시적 예외가
    기준서에는 없다. 섹션 내 "해당 없음"을 별도 문자열로 명시하지 않고 표 형식 내에
    대시로만 표기하여 형식 미달.
    그러나 govtrack은 UI가 전혀 없는 데몬이므로 file:line 기재 자체가 불가능하다.
    이 경우 기준 적용 예외로 볼 여지가 있으나, 기준서 §6 "추측하지 않는다 — 문서에
    없으면 FAIL" 원칙에 따라, "해당 없음" 명시적 서술이 없는 현 상태는 F-2 위반으로
    판정한다.
  - F-4: §4.1에서 "본 feature는 백그라운드 데몬. HTTP 노출 없음"이라 명시하고
    CLI 명령만 기재되어 있다. URL/HTTP 메서드/Flask 핸들러/템플릿이 N/A인 것은
    도메인 특성상 정당하나, 기준 F-4는 "새 구현 매핑에 URL & HTTP 메서드, Flask
    핸들러 시그니처, 템플릿 경로가 모두 존재"를 요구한다. §4.2, §4.3에서 "N/A(데몬)"로
    명시되어 있으나, 기준서에 백그라운드 데몬에 대한 명시적 예외가 없으므로 F-4 위반.
PASS_NOTES:
  - status: designed. frontmatter 5개 키 완비.
  - 섹션 0~10 전부 존재.
  - 코드 블록 python/sql 언어 태그 부착.
  - As-is/To-be 한 줄 요약 충실.
  - 외부 API(국토부 TAGO): URL·메서드·파라미터·응답 형식·실패 응답·rate limit 명시.
  - 타입힌트 포함 시그니처(TagoClient, VehicleTimeline, GovtrackRecorder, BusLogRepo,
    run_daemon, Clock, TimelineStore 프로토콜).
  - HTMX/SSE: 데몬 자체는 N/A, 관리자 status SSE는 F04 위임 명시.
  - AC 14건(H1~H10, S1~S5, M1~M2), 각 검증 방법 포함.
  - 단위 테스트 10개 파일에 다수 케이스 이름 제시(≥3 충족).
  - 영향 doc(F04, F05) 명시.
  - 결함 10건(H1~H10) 각각 가설별 분리 — F-10 완벽 충족.
```

---

## F10 — 시간표 재크롤 (Timetable Re-Crawl)

```
TARGET: docs/refactor/features/F10-timetable-crawl.md
VERDICT: FAIL
FAIL_REASONS:
  - F-5: §6.2 데이터 타입에서 `TimetableEntry` TypedDict의 body가
    `pass  # JSON 스키마는 dict[str, dict[str, list[str]]]로 충분히 표현 가능`로
    채워져 있어 실질적인 필드 타입힌트가 없다. 또한 `TimetableRow = tuple[str, int]`는
    타입 별칭으로 정의되어 있으나, `tuple[str, int]`에서 각 원소의 의미(time, direction)가
    타입 힌트가 아닌 주석으로만 기재되어 있다. 기준 F-5 "도메인 서비스 함수 시그니처가
    타입 힌트 포함"에서 데이터 타입 정의의 실질적 공백이 F-5 취지에 부합하지 않는다.
    단, §6.1 함수 시그니처(crawl_target_timetable, crawl_timetable, request_timetable)는
    파라미터 및 반환 타입이 모두 명시되어 있어 함수 시그니처 자체는 F-5를 충족한다.
    데이터 타입 정의의 공백이 부분적 F-5 위반에 해당한다.
PASS_NOTES:
  - frontmatter 5개 키 완비.
  - 섹션 0~10 전부 존재.
  - 코드 블록 python/xml 언어 태그 부착.
  - As-is/To-be 한 줄 요약 충실.
  - Streamlit API 전수 표 7행, file:line 기재.
  - 외부 API(울산 BIS 시간표): URL·메서드·파라미터 표·응답 XML 예시·실패 응답 명시.
  - URL(POST /admin/timetable/crawl, GET /admin/sse/crawl-progress)/핸들러 시그니처/
    템플릿(admin/timetable_crawl.html) 완비.
  - SSE 토픽(/admin/sse/crawl-progress), 이벤트 타입(progress/error/done),
    selector(#crawl-log), 폴링 없음(server push) 명시.
  - AC 6건, 검증 방법(grep, ls, stat) 포함.
  - 단위 테스트 8건 이름 제시.
  - 영향 doc(F04, F01, F05~F09) 명시.
  - 결함 5건 각각 분리.
```

---

## 요약 표

| Feature ID | 제목 | VERDICT | FAIL 항목 수 |
|---|---|---|---|
| F01 | 출발 게시판 | PASS | 0 |
| F02 | 버스번호별 시간표 | FAIL | 1 (F-9) |
| F03 | 정보 페이지 | FAIL | 1 (F-8) |
| F04 | 관리자 페이지 | FAIL | 1 (F-5) |
| F05 | 운행 재구성 테이블 | FAIL | 1 (F-9) |
| F06 | 정류소별 도착 정보 | PASS | 0 |
| F07 | UNIST 버스 카드 | PASS | 0 |
| F08 | 전체 시간표 그리드 | FAIL | 1 (F-9) |
| F09 | Govtrack 데몬 | FAIL | 2 (F-2, F-4) |
| F10 | 시간표 재크롤 | FAIL | 1 (F-5) |

- **PASS: 3건** (F01, F06, F07)
- **FAIL: 7건** (F02, F03, F04, F05, F08, F09, F10)

---

## 가장 위험한 FAIL Top 3

1. **F-4 / F09**: 데몬 feature에 URL·Flask 핸들러·템플릿 경로가 "N/A" 처리되어 있으나 기준서에 예외 조항 없음 — Executor가 백그라운드 프로세스 feature에 대해 F-4를 어떻게 처리해야 하는지 불명확하여, 이후 Phase doc 또는 ADR 작성 시 동일 패턴이 반복될 위험이 있다.

2. **F-5 / F04**: `AuthService`, `TimetableCrawlJob`, `GovtrackStatusReader` 시그니처 일부에 반환 타입 누락 — 관리자 기능은 가장 복잡한 도메인이므로 타입 계약 불완전이 Executor의 구현 오류로 이어질 가능성이 높다.

3. **F-9 / F02·F05·F08 (동일 패턴)**: F02는 "F01 미작성", F05는 "F-admin 미작성", F08은 F07 누락 등 영향 doc ID를 잘못 기재하거나 누락하는 패턴이 3개 doc에 걸쳐 반복됨 — 영향 범위 파악 오류가 Phase 설계에 연쇄 영향을 줄 수 있다.

---

## Designer에게 보낼 한 줄 권고

**백그라운드 데몬(F09)과 같이 HTTP 라우트가 없는 feature에 대한 F-4 적용 예외 조항을 `design-audit-criteria.md`에 명시하고, F02/F05/F08의 영향 doc ID 오기재(미작성 표기, 실존 doc 누락)를 일괄 수정하여 재제출하라.**
