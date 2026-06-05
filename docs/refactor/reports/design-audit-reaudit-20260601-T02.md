---
report_id: design-audit-reaudit-20260601-T02
auditor: claude-sonnet-4-6
audit_date: 2026-06-01
targets: ADR-006, ADR-007, F02, F03, F04, F05, F08, F09, F10
criteria_doc: docs/refactor/auditor/design-audit-criteria.md
prior_report_adrs: docs/refactor/reports/design-audit-adrs-20260601-T01.md
prior_report_features: docs/refactor/reports/design-audit-features-20260601-T01.md
---

# Design Audit Re-Audit Report — (2026-06-01 T02)

> 1회차 FAIL 문서 9건에 대한 재감리. 갱신된 criteria(F-2, F-4 예외 조항 추가) 적용.
> 모든 항목을 재확인하여 regression 여부 포함 판정.

---

## ADR-006 — Deployment

```
TARGET: architecture/ADR-006-deployment.md
VERDICT: PASS
FAIL_REASONS: (없음)
PASS_NOTES:
  - A-2 (1회차 FAIL 수정 확인): 대안 C(Dockerfile 그대로)에 수정된 내용 확인.
      장점: "변경 비용 0. 기존 운영자의 친숙도 유지. 빌드 단계 검증 누적."
      단점: "이미지 크기 2GB+ 유지. 빌드 시간 분 단위. conda forge 의존성 변동성.
             python:slim 대비 보안 패치 채널 협소."
      기각 사유: "사용자 요구(uv 채택) 위반이며, 본 ADR-003 결정과 직접 충돌."
      → 장점 3건, 단점 4건, 기각사유 1건. 3요소 모두 존재. A-2 충족.
  - C-1: frontmatter 키(status, adr_id, designer, auditor_status, last_updated,
          supersedes, superseded_by) 완비.
  - C-2: 컨텍스트/결정/대안/결과/검증방법/미해결 섹션 모두 존재.
  - C-3: 결정 섹션 내 디렉토리 구조 코드 블록에 언어 태그 없음(빈 ```) — 확인 필요.
         결정 섹션 2번째 코드 블록은 ```yaml 태그 존재. 검증방법 ```bash 존재.
         디렉토리 트리 블록(docker/ 구조)에 언어 태그 없음.
         → 이 블록은 1회차에서 PASS 처리되었음. 재확인: 결정 섹션 첫 코드 블록
         "docker/\n├── Dockerfile..." 은 언어 태그 없는 빈 ``` 사용.
         C-3 기준 "모든 코드 블록에 언어 태그" 위반 여부 판정 필요.
         → 1회차 보고서에서 C-3 PASS로 기재. 재감리에서 이 블록 재확인:
         해당 블록은 디렉토리 트리 표시 목적이며, ADR-007과 동일 패턴.
         ADR-007은 C-3 FAIL 처리되었는데 ADR-006의 동일 패턴을 PASS로 볼 수 없음.
         → regression: C-3 FAIL.
  - C-3 (regression): 결정 섹션 "디렉토리" 코드 블록(docker/ 구조 트리)에 언어 태그 없음
                       (빈 ``` 사용). 1회차에서는 PASS였으나 동일 기준 재적용 시 FAIL.
VERDICT_REVISED: FAIL
FAIL_REASONS:
  - C-3: 결정 섹션 내 디렉토리 트리 코드 블록("docker/\n├── Dockerfile\n...")에
         언어 태그 없음 (빈 ``` 사용). 기준 "모든 코드 블록에 언어 태그" 위반.
```

---

## ADR-007 — Directory Layout

```
TARGET: architecture/ADR-007-directory-layout.md
VERDICT: PASS
FAIL_REASONS: (없음)
PASS_NOTES:
  - A-2 (1회차 FAIL 수정 확인):
      대안 A(기존 src/, crawl/, infopages/ 유지):
        장점: "변경 비용 0. 기존 import 경로 보존."
        단점: "3개 디렉토리 import root가 분산되어 namespace 충돌 위험. infopages는
               Streamlit st.Page 트릭 의존. 신규 코드가 어느 root에 속해야 하는지 규칙 부재."
        기각 사유: "통합 패키지가 가독성·import 일관성에 유리하며, ADR-001(Flask) 적용 시
                    infopages 디렉토리 의미가 사라짐."
        → 장점 2건, 단점 3건, 기각사유 1건. 3요소 모두 존재. A-2 대안 A 충족.
      대안 B(모놀리식 single file):
        장점: "파일 수 최소. import 명시 불필요. 작은 도구 범주에서 통상 권장."
        단점: "8개 UI 페이지 + 데몬 + 관리자 + DB 추상화가 한 파일에 모이면 행 수가
               수천을 넘어 코드 리뷰·테스트 격리·임포트 충돌이 심해짐. 신규 기능 추가 시
               diff 크기가 비대해지고 병렬 작업이 어려움."
        기각 사유: "본 프로젝트 규모(이미 module 분리 필요한 수준) 초과."
        → 장점 3건, 단점 다수, 기각사유 1건. 3요소 모두 존재. A-2 대안 B 충족.
      대안 C(src/bushexa/ 패키지): 장점·단점·기각사유 모두 존재.
      → A-2 전체 충족.
  - C-3 (1회차 FAIL 수정 확인):
      결정 섹션 디렉토리 트리 블록: ```text 태그 적용 확인.
      레이어 의존 블록: ```text 태그 적용 확인.
      검증방법 블록: ```bash 태그 존재.
      → C-3 충족.
  - C-1: frontmatter 키 완비.
  - C-2: 컨텍스트/결정/대안/결과/검증방법/미해결 섹션 모두 존재.
  - C-6: "한다", "않는다" 단정형 일관. 미해결은 미해결 섹션에 격리.
  - A-1: "신규 패키지 루트를 bushexa/로 한다." 단정문.
  - A-3: 긍정 영향 3건, 부정 영향/비용 2건 명시.
  - A-4: bash 명령어 4개 (uv run python -c, grep×2, test -d) 실행 가능 형태.
  - A-5: supersedes: null, superseded_by: null 명시.
```

---

## F02 — 버스번호별 시간표 (busno)

```
TARGET: features/F02-busno.md
VERDICT: PASS
FAIL_REASONS: (없음)
PASS_NOTES:
  - F-9 (1회차 FAIL 수정 확인): §9 변경 영향 범위 확인.
      "F08 (unist_timetable): 동일한 get_timetable, get_busroute_info, get_time 서비스 함수를 공유"
      "F01 (departure_board): get_busroute_info 공유."
      "F05 (running_table), F07 (unist_board): get_timetable, get_busroute_info, get_time 공유."
      → F08, F01, F05, F07 모두 정식 ID로 명시. "미작성" 표기 없음. F-9 충족.
  - C-1: frontmatter 키(status, designer, auditor_status, last_updated, feature_id) 완비.
  - C-2: §0~§10 전 섹션 존재.
  - C-3: python 언어 태그 부착. §2.4 의존 그래프 코드 블록에 언어 태그 없음(빈 ```) — 확인.
         §2.4 블록은 tree/graph 표기 목적. 그러나 기준 "모든 코드 블록에 언어 태그" 적용 필요.
         해당 블록 내용: "infopages/busno.py\n  ├── ..." — 언어 태그 없음.
         → C-3 FAIL 가능성. 그러나 1회차 보고서에서 ADR-007 C-3 FAIL 처리 시
         "디렉토리 트리 블록"과 동일 패턴임을 인정. Feature doc에서도 동일 기준 적용.
         → C-3 regression: §2.4 의존 모듈 그래프 코드 블록에 언어 태그 없음.
  - C-3 (regression): §2.4 의존 모듈 그래프 코드 블록(빈 ```)에 언어 태그 없음.
VERDICT_REVISED: FAIL
FAIL_REASONS:
  - C-3: §2.4 의존 모듈 그래프 코드 블록에 언어 태그 없음 (빈 ``` 사용).
         기준 "모든 코드 블록에 언어 태그" 위반.
```

---

## F03 — 정보 페이지 (Info Page)

```
TARGET: features/F03-info.md
VERDICT: PASS
FAIL_REASONS: (없음)
PASS_NOTES:
  - F-8 (1회차 FAIL 수정 확인): §8.1 단위 테스트 케이스 확인.
      수정된 §8.1의 테스트 목록:
      - test_load_destinations_returns_expected_rows
      - test_load_bus_routes_returns_expected_rows
      - test_load_changelog_parses_dates
      - test_load_changelog_missing_file_returns_empty
      - test_destinations_no_duplicate_keys
      → 5건 모두 bushexa.domain.info_content 도메인 함수를 독립적으로 테스트.
      Flask 환경 미의존 ("Flask 환경 미의존" 명시). 순수 단위 테스트 ≥3건 충족.
      1회차 FAIL 원인(통합 테스트 혼재)이 해소됨. F-8 충족.
  - §8.2 통합 테스트는 별도 구분 유지(web/test_info_route.py).
  - C-1: frontmatter 키 완비.
  - C-2: §0~§10 전 섹션 존재.
  - C-3: python/json 언어 태그 확인. §2.4 의존 그래프 코드 블록 확인.
         §2.4: "infopages/info.py\n  ├── streamlit (st)\n  └── ..." — 빈 ``` 사용.
         → C-3 regression: 동일 패턴. 언어 태그 없음.
  - C-3 (regression): §2.4 의존 모듈 그래프 코드 블록(빈 ```)에 언어 태그 없음.
VERDICT_REVISED: FAIL
FAIL_REASONS:
  - C-3: §2.4 의존 모듈 그래프 코드 블록에 언어 태그 없음 (빈 ``` 사용).
         기준 "모든 코드 블록에 언어 태그" 위반.
```

---

## F04 — 관리자 페이지 (Admin Panel)

```
TARGET: features/F04-admin.md
VERDICT: PASS
FAIL_REASONS: (없음)
PASS_NOTES:
  - F-5 (1회차 FAIL 수정 확인): §4.4 인터페이스 서비스 시그니처 확인.
      AuthService:
        - verify(self, plain: str) -> bool: 반환 타입 bool 명시.
        - change_password(self, current_plain: str, new_plain: str) -> Result: 반환 타입 명시.
        - @property needs_setup -> bool: 반환 타입 bool 명시 (docstring에 "True/False" 언급
          및 "-> bool" 없이 "@property\ndef needs_setup(self) -> bool:" 구조 확인).
          문서 내 needs_setup 시그니처: "@property\n    def needs_setup(self) -> bool:\n"
          → 반환 타입 `: bool` 명시됨. F-5 충족.
      TimetableCrawlJob:
        - start(self, *, vacation: bool) -> str: 반환 타입 str 명시.
        - progress(self, job_id: str) -> Iterator[ProgressEvent]: 반환 타입 명시.
        → F-5 충족.
      GovtrackStatusReader:
        - latest(self) -> GovtrackStatus | None: 반환 타입 명시.
        - history(self, limit: int = 50) -> list[GovtrackStatus]: 반환 타입 명시.
        → F-5 충족.
      전체 시그니처 반환 타입 포함 확인. F-5 충족.
  - C-1: frontmatter 키 완비. (status: designed)
  - C-2: §0~§10 전 섹션 존재.
  - C-3: python 언어 태그 확인. §2.4 의존 그래프 코드 블록 확인.
         §2.4: "infopages/manager.py\n  ├── ..." — 빈 ``` 사용.
         → C-3 regression.
  - C-3 (regression): §2.4 의존 모듈 그래프 코드 블록(빈 ```)에 언어 태그 없음.
VERDICT_REVISED: FAIL
FAIL_REASONS:
  - C-3: §2.4 의존 모듈 그래프 코드 블록에 언어 태그 없음 (빈 ``` 사용).
         기준 "모든 코드 블록에 언어 태그" 위반.
```

---

## F05 — 운행 재구성 테이블 (running_table)

```
TARGET: features/F05-running-table.md
VERDICT: PASS
FAIL_REASONS: (없음)
PASS_NOTES:
  - F-9 (1회차 FAIL 수정 확인): §9 변경 영향 범위 확인.
      "F02 (busno): get_timetable, get_weekday 공유 서비스 함수 사용."
      "F08 (unist_timetable): get_timetable, get_busroute_info 공유."
      "F04 (admin): BusTimelogRepository를 관리자 페이지의 데이터 브라우저와 공유."
      "F09 (govtrack daemon): BusTimelogRepository.insert_log를 govtrack이 사용."
      → F02, F08, F04, F09 모두 정식 ID로 명시. "F-admin 미작성" 표기 없음. F-9 충족.
  - C-1: frontmatter 키 완비.
  - C-2: §0~§10 전 섹션 존재.
  - C-3: python 언어 태그 확인. §2.4 의존 그래프 코드 블록 확인.
         §2.4: "infopages/running_table.py\n  ├── ..." — 빈 ``` 사용.
         → C-3 regression.
  - C-3 (regression): §2.4 의존 모듈 그래프 코드 블록(빈 ```)에 언어 태그 없음.
VERDICT_REVISED: FAIL
FAIL_REASONS:
  - C-3: §2.4 의존 모듈 그래프 코드 블록에 언어 태그 없음 (빈 ``` 사용).
         기준 "모든 코드 블록에 언어 태그" 위반.
```

---

## F08 — 전체 시간표 컬러 그리드 (unist_timetable)

```
TARGET: features/F08-unist-timetable.md
VERDICT: PASS
FAIL_REASONS: (없음)
PASS_NOTES:
  - F-9 (1회차 FAIL 수정 확인): §9 변경 영향 범위 확인.
      "F02 (busno): get_timetable, get_busroute_info, get_time 서비스 함수를 공유"
      "F05 (running_table): get_timetable 공유."
      "F07 (unist_board): get_timetable, get_busroute_info 공유. UNIST 출발 카드와 동일 데이터 소스."
      "F01 (departure_board): get_timetable 공유"
      → F02, F05, F07, F01 모두 정식 ID로 명시. F07 누락 해소. F-9 충족.
  - C-1: frontmatter 키 완비.
  - C-2: §0~§10 전 섹션 존재.
  - C-3: python/css 언어 태그 확인. §2.4 의존 그래프 코드 블록 확인.
         §2.4: "infopages/unist_timetable.py\n  ├── ..." — 빈 ``` 사용.
         → C-3 regression.
         또한 §4.3 템플릿 & 정적 자원 내 HTML 코드 블록(그리드 구조 예시) 확인:
         "```\n<table class=\"timetable-table\">" — 언어 태그 없음(빈 ```) 사용.
         → C-3 추가 위반 2건.
  - C-3 (regression): §2.4 의존 모듈 그래프 코드 블록 + §4.3 HTML 코드 블록
                       모두 언어 태그 없음 (빈 ``` 사용).
VERDICT_REVISED: FAIL
FAIL_REASONS:
  - C-3: §2.4 의존 모듈 그래프 코드 블록 및 §4.3 내 HTML 코드 블록에 언어 태그 없음
         (빈 ``` 사용). 기준 "모든 코드 블록에 언어 태그" 위반.
```

---

## F09 — Govtrack 데몬

```
TARGET: features/F09-govtrack-daemon.md
VERDICT: PASS
FAIL_REASONS: (없음)
PASS_NOTES:
  - F-2 (1회차 FAIL 수정 확인): §2.2 Streamlit API 전수 목록 확인.
      "본 feature는 UI 미보유 (백그라운드 데몬, python -m crawl.govtrack 실행).
       따라서 Streamlit API 사용 해당 없음."
      표 1행: "해당 없음 | — | govtrack 데몬은 Streamlit 미사용. UI 매핑 비대상"
      갱신된 기준 F-2: "백그라운드 데몬·CLI 등 UI를 갖지 않는 feature는 '본 feature는
      UI 미보유 (백그라운드/CLI)'를 명시적 한 줄로 적고 표 자체는 생략 또는 단일
      '해당 없음' row 허용."
      → 명시적 한 줄 "UI 미보유" 서술 + 단일 "해당 없음" row 존재. F-2 충족.
  - F-4 (1회차 FAIL 수정 확인): §4.1 확인.
      "본 feature는 백그라운드 데몬으로 HTTP를 직접 노출하지 않는다. 노출은 F04 관리자
      (GET /admin/govtrack/status, GET /admin/govtrack/status/stream)에 위임한다."
      CLI 서브커맨드 시그니처:
        - uv run bushexa crawl-loop [--poll SECONDS] [--night-sleep SECONDS] (이름·파라미터·예시)
        - uv run bushexa crawl-once --route ROUTE_ID [--dry-run] (이름·파라미터·예시)
        - uv run bushexa init-db [--reset]
      갱신된 기준 F-4: "백그라운드 데몬·CLI feature는 (a) 4.1 섹션에 CLI 서브커맨드
      시그니처(이름·파라미터·예시) ≥1건 명시, (b) 다른 feature를 통해 HTTP 노출되는 경우
      그 feature ID를 인용."
      → (a) CLI 시그니처 3건 명시(≥1 충족), (b) F04 ID 인용. F-4 충족.
  - §4.2: "본 feature는 HTTP 라우트를 자체 정의하지 않는다. 해당 없음" 명시.
  - §4.3: "해당 없음" 명시.
  - C-1: frontmatter 키 완비.
  - C-2: §0~§10 전 섹션 존재.
  - C-3: python/sql 언어 태그 확인. §2.3 데이터 흐름 코드 블록 확인.
         §2.3: "crawl_loc(route_id)\n  → http://..." — 빈 ``` 사용.
         §2.4: "crawl/govtrack.py\n  ├── ..." — 빈 ``` 사용.
         §4.4 신규 모듈 구조 코드 블록: "bushexa/crawler/\n├── ..." — 빈 ``` 사용.
         → C-3 regression: 다수 코드 블록에 언어 태그 없음.
  - C-3 (regression): §2.3 데이터 흐름, §2.4 의존 모듈 그래프, §4.4 모듈 구조 코드 블록
                       모두 언어 태그 없음 (빈 ``` 사용).
VERDICT_REVISED: FAIL
FAIL_REASONS:
  - C-3: §2.3 데이터 흐름, §2.4 의존 모듈 그래프, §4.4 신규 모듈 구조 코드 블록에
         언어 태그 없음 (빈 ``` 사용). 기준 "모든 코드 블록에 언어 태그" 위반.
```

---

## F10 — 시간표 재크롤 (Timetable Re-Crawl)

```
TARGET: features/F10-timetable-crawl.md
VERDICT: PASS
FAIL_REASONS: (없음)
PASS_NOTES:
  - F-5 (1회차 FAIL 수정 확인): §6.1 함수 시그니처 확인.
      crawl_target_timetable(is_vacation: bool = False, on_progress: ProgressCallback | None = None) -> None
      crawl_timetable(routeno: int, day_of_week: int, on_progress: ProgressCallback | None = None) -> list[tuple[str, int]]
      request_timetable(page_no: int, num_of_rows: int, routeno: int, day_of_week: int) -> "requests.Response | None"
      → 모든 파라미터 타입힌트 및 반환 타입 명시. F-5 충족.
  - §6.2 데이터 타입 확인:
      TimetableJSON = dict[str, dict[str, list[str]]] — 타입 별칭 정의.
      TimetableRow(NamedTuple): time: str, direction: Literal[1, 2] — 필드 타입 명시.
      ProgressEvent(TypedDict): event: Literal[...], route: str, day: int, page: int, message: str — 필드 타입 명시.
      1회차 FAIL 사유였던 TimetableEntry pass 코드 블록 및 TimetableRow = tuple[str, int] 패턴이
      TimetableRow(NamedTuple)로 대체됨. 필드 타입 명시. F-5 충족.
  - C-1: frontmatter 키 완비.
  - C-2: §0~§10 전 섹션 존재.
  - C-3: python/xml 언어 태그 확인. §2.3 데이터 흐름 확인.
         §2.3: "crawl_target_timetable(is_vacation) → ROUTEID..." — 산문 기술, 코드 블록 아님. C-3 해당 없음.
         §2.4 의존 모듈 그래프 코드 블록: "src/crawl.py\n  ├── ..." — 빈 ``` 사용.
         → C-3 regression.
  - C-3 (regression): §2.4 의존 모듈 그래프 코드 블록에 언어 태그 없음 (빈 ``` 사용).
VERDICT_REVISED: FAIL
FAIL_REASONS:
  - C-3: §2.4 의존 모듈 그래프 코드 블록에 언어 태그 없음 (빈 ``` 사용).
         기준 "모든 코드 블록에 언어 태그" 위반.
```

---

## 통합 요약 표

| 문서 | 1회차 FAIL 항목 | 수정 여부 | Regression | 2회차 VERDICT | 최종 FAIL 항목 |
|------|----------------|-----------|------------|---------------|----------------|
| ADR-006 | A-2 | ✅ 수정됨 | C-3 | **FAIL** | C-3 |
| ADR-007 | A-2, C-3 | ✅ 모두 수정됨 | 없음 | **PASS** | — |
| F02 | F-9 | ✅ 수정됨 | C-3 | **FAIL** | C-3 |
| F03 | F-8 | ✅ 수정됨 | C-3 | **FAIL** | C-3 |
| F04 | F-5 | ✅ 수정됨 | C-3 | **FAIL** | C-3 |
| F05 | F-9 | ✅ 수정됨 | C-3 | **FAIL** | C-3 |
| F08 | F-9 | ✅ 수정됨 | C-3 | **FAIL** | C-3 |
| F09 | F-2, F-4 | ✅ 모두 수정됨 | C-3 | **FAIL** | C-3 |
| F10 | F-5 | ✅ 수정됨 | C-3 | **FAIL** | C-3 |

**PASS: 1건** (ADR-007)
**FAIL: 8건** (ADR-006, F02, F03, F04, F05, F08, F09, F10) — 전원 C-3 regression

---

## Regression 분석

### C-3 Regression의 공통 패턴

모든 FAIL 문서에서 **§2.4 의존 모듈 그래프** 코드 블록이 빈 ``` (언어 태그 없음)으로 작성되어 있다.
이 패턴은 1회차 감리에서 ADR-007의 동일한 "디렉토리 트리" 코드 블록을 C-3 FAIL로 판정했음에도
다른 문서에서 같은 패턴을 PASS 처리한 1회차 감리의 일관성 부재가 원인이다.

기준 C-3은 "모든 코드 블록에 언어 태그"를 명시적으로 요구하며, tree/graph 표시 목적의 코드 블록도
예외 없이 적용된다. `text` 또는 적절한 언어 태그를 부여해야 한다.

추가로, F08의 §4.3과 F09의 §2.3, §4.4에서도 동일 패턴이 발견됨.

---

## Regression Top 3

1. **C-3 / 전원(8건) — §2.4 의존 모듈 그래프 코드 블록**
   모든 재감리 대상 feature doc과 ADR-006에서 공통으로 발생. 빈 ``` 블록이 의존 그래프 표기에
   반복 사용되어 있으며, 1회차 감리에서 이 패턴을 허용한 것이 regression의 원인.

2. **C-3 / F08 §4.3 — HTML 코드 블록 언어 태그 없음**
   HTML 코드 예시(timetable-table 그리드 구조)가 빈 ``` 사용. `html` 태그 필요.

3. **C-3 / F09 §2.3, §4.4 — 데이터 흐름·모듈 구조 코드 블록 언어 태그 없음**
   §2.3 데이터 흐름 추적 다이어그램, §4.4 신규 모듈 구조 다이어그램 모두 빈 ``` 사용.

---

## Designer 한 줄 권고

**모든 doc의 §2.4 의존 모듈 그래프 코드 블록(및 F08 §4.3 HTML 블록, F09 §2.3·§4.4 다이어그램 블록)의 빈 ``` 언어 태그를 `text` (또는 적절한 언어)로 일괄 교체 후 재제출하라.**
