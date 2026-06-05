---
report_id: design-audit-phases-20260601-T01
auditor: claude-sonnet-4-6
audit_date: 2026-06-01
target_docs:
  - docs/refactor/phases/P0-bootstrap.md
  - docs/refactor/phases/P1-data-layer.md
  - docs/refactor/phases/P2-crawler.md
  - docs/refactor/phases/P3-domain-services.md
  - docs/refactor/phases/P4-web.md
  - docs/refactor/phases/P5-deployment-cutover.md
criteria_ref: docs/refactor/auditor/design-audit-criteria.md
---

# Phase Design Audit Report — 2026-06-01-T01

## 감리 기준 적용 범위

공통 C-1 ~ C-7, Phase 전용 P-1 ~ P-10 전항목.

---

## 개별 Phase 감리 결과

---

### P0 — Bootstrap

```
TARGET: docs/refactor/phases/P0-bootstrap.md
VERDICT: FAIL
FAIL_REASONS:
  - P-4: W5(logging_setup.py) AC가 2건 중 AC-W5-2 검증 명령이 단일 `uv run python -c` 호출뿐으로
          "로그 메시지에 KST 시간 표기 (검증: pytest)"라 명시했으나 pytest 명령이 문서에 없음.
          AC는 2건이나 AC-W5-2의 검증 명령이 python 일행 명령이고 pytest 케이스 경로가 부재.
  - P-8: 종료 조건(EC-1~EC-7)이 W9(README 초안) AC(AC-W9-1, AC-W9-2)를 cover하지 않음.
          EC에 README 섹션 존재 또는 `uv` 명령 수 확인 항목이 없어 W9 AC가 Phase 종료 조건에 누락.
PASS_NOTES:
  - C-1: frontmatter 6개 키(status, phase_id, designer, auditor_status, last_updated, depends_on) 모두 보유.
  - C-2: 목적/시작조건/종료조건/Work Item 분해/상세/병렬화 그래프/리스크&롤백 섹션 모두 존재.
  - C-3: 모든 코드 블록에 bash 태그 있음.
  - C-4: 파일 경로 전부 프로젝트 루트 기준 상대 경로.
  - C-6: 결정·주장 모두 명령형/단정형.
  - P-1: Work Item 9건(W1~W9) — 기준(≥2건) 충족.
  - P-2: 각 work item에 산출물 경로 단일 또는 동일 모듈 복수 파일로 명시.
  - P-3: 모든 work item에 지시사항 ≥3 step 분해(W1=6step, W2=4step, W3=4step 등).
  - P-5: 의존 사이클 없음. W7/W8 독립, W1→W2→{W3,W4,W5,W6,W9} 일방향.
  - P-6: 병렬 가능 그룹 Group A(W1,W7,W8), Group C(W3,W4,W5,W6,W9) 식별.
  - P-7: L 크기 work item 없음(명시적 L 표기 0건). M 4건은 분해 불가 사유 또는 분해 방향 명시(W7 종류별 W7a~e 언급).
  - P-9: 시작 조건에 "의존 Phase: 없음(P0)", ADR-001~008, F01~F10 명시적 인용.
  - P-10: 리스크 R1~R3 + 롤백 절차 구체적 명령 수준으로 비공란.
```

---

### P1 — Data Layer

```
TARGET: docs/refactor/phases/P1-data-layer.md
VERDICT: FAIL
FAIL_REASONS:
  - P-3: W1(constants 이전)에 지시사항 step 분해가 없음. §5/W1 상세는 bullet 1줄
          ("현 src/constants.py를 bushexa/data/constants.py로 그대로 이동")과 단위테스트 안내
          2줄뿐. 명령형 step이 3개 미만(사실상 1~2개).
  - P-4: W1 AC가 import 성공 + 노출 항목 확인으로 단일 문장 1건. 검증 명령도
          `uv run pytest tests/unit/test_constants.py -v` 1줄만 존재. AC ≥2건이 아니라
          형식상 AC가 한 문장(조건 2가지를 AND로 묶음)으로 기술돼 분리된 2건으로 볼 수 없음.
          W5(schema.py) 및 W9(holiday.py)도 AC 목록이 bullet이 아닌 산문 1줄.
  - P-8: 종료 조건 EC-7이 "BusLogRepo가 4.4 시그니처와 일치 (F09 명세)"를 검증하지만
          W10(parsers.py) AC의 "F09 §8.1 W10 관련 parser 테스트 6건 통과" 항목이
          Phase EC에 독립 항목으로 반영되지 않음. EC-5가 parse 결과를 커버하나
          테스트 파일 경로(test_parser_bus_location.py)가 EC에 인용되지 않아 커버 여부 불명확.
PASS_NOTES:
  - C-1: frontmatter 키(status, phase_id, designer, auditor_status, last_updated, depends_on) 모두.
  - C-2: 필수 섹션 모두 존재.
  - C-3: 코드 블록에 text/bash 언어 태그.
  - P-1: Work Item 10건(W1~W10).
  - P-5: 사이클 없음. W1→{W2,W3}, W4→W5→W6, W7/W8/W9 독립, W7+W8→W10.
  - P-6: Group A = {W1,W4,W7,W8,W9} 5개 동시 가능.
  - P-7: W6(L) → W6a/W6b 분해 명시.
  - P-9: 시작 조건에 "P0 Auditor PASS", ADR-002/005/007 인용.
  - P-10: 리스크 R1~R3 + 롤백 절차 구체적으로 비공란.
```

---

### P2 — Crawler

```
TARGET: docs/refactor/phases/P2-crawler.md
VERDICT: FAIL
FAIL_REASONS:
  - P-3: W6(services/govtrack_status.py)에 지시사항 step 분해 없음. §5/W6은
          writer/reader 메서드 선언 + AC + 검증 명령만 있고 명령형 구현 step이 0건.
  - P-4: W1(state.py) AC가 "F09 §8.1 test_vehicle_timeline.py 5건 통과" 단일 문장 1건.
          2건 이상 분리된 AC bullet이 없음. W4(timetable_crawl.py) AC도
          "F10 §7 AC-1~6 모두 통과, mock UlsanBisClient로 4페이지 시뮬레이션" 1문장.
          W5, W6, W8도 동일하게 산문 1줄 AC.
  - P-8: EC-7("govtrack status 파일/테이블에 마지막 사이클 기록, F04 reader 호환")이
          W6(govtrack_status.py) AC "F04 §7 AC-G1~G3, F09 AC-M1/M2 통과"를 cover하나
          W5(TimetableCrawlJob) AC의 "F04 §7 AC-R1~R5"가 Phase EC에 독립 항목으로 존재하지 않음.
          EC-2가 폴링 시뮬레이션 임계값 통과를 기술하나 W8 AC "3개 임계 모두 충족"과
          구체적 임계 수치의 1:1 인용이 없어 완전 cover 불명확.
PASS_NOTES:
  - C-1: frontmatter 키 모두 보유.
  - C-2: 필수 섹션 모두 존재.
  - C-3: 코드 블록 bash 태그 정상.
  - P-1: Work Item 8건(W1~W8).
  - P-5: 사이클 없음. W1→W2a→W2b→W2c→{W3,W6}, W4→W5, W1+W2→W8.
  - P-6: Group A = {W1,W4} 동시 가능, Group D = W7a/b/c 병렬.
  - P-7: W2(L)→W2a/W2b/W2c, W7(L)→W7a/W7b/W7c 분해 명시.
  - P-9: 시작 조건에 P1 Auditor PASS, P1 개별 결과(W6,W7~W10), F09/F10/ADR-008 인용.
  - P-10: 리스크 R1~R3 + 롤백 절차 비공란.
```

---

### P3 — Domain Services

```
TARGET: docs/refactor/phases/P3-domain-services.md
VERDICT: FAIL
FAIL_REASONS:
  - P-3: W2(stops.py), W3(unist_board.py), W4(unist_timetable.py), W6(busno.py) 모두
          §5 상세에 명령형 지시사항 step 분해가 없음. 각 work item 상세는
          함수 시그니처 선언 + AC + 검증 명령만 있고 구현 step ≥3이 존재하지 않음.
  - P-4: W2 AC가 "F06 §7 AC 통과 (캐시 외)" 산문 1줄. W3 AC는 "F07 §7 AC 통과",
          W4는 "F08 §7 AC 통과", W6는 "F02 §7 AC 통과" 각각 1문장. 2건 이상
          분리된 bullet AC 없음.
  - P-8: EC-3("각 domain 함수가 Clock 주입받아 freezegun 테스트 가능")이
          W1(board.py) AC의 "freezegun으로 시각 고정 테스트 4건" 항목을 cover하나
          W5(running.py)의 "마지막 회차 유실 버그 수정 명시" AC가 EC에 반영되지 않음.
          EC는 general import/test/no-flask 3건이고 W5 Sonnet doc 인용 정확성 검증이 누락.
PASS_NOTES:
  - C-1: frontmatter 키 모두 보유.
  - C-2: 필수 섹션 모두 존재.
  - C-3: 코드 블록 없음(산문 위주) — 코드 블록이 없으므로 C-3 위반 없음.
  - P-1: Work Item 6건(W1~W6).
  - P-5: 사이클 없음. W1a→W1b, W5a→W5b, 나머지 독립.
  - P-6: Group A = {W1a,W2,W3,W4,W5a,W6} 6개 동시 가능.
  - P-7: W1(L)→W1a/W1b, W5(L)→W5a/W5b 분해 명시.
  - P-9: 시작 조건에 P1 PASS, F01/F05/F06/F07/F08 doc Auditor PASS 인용.
  - P-10: 리스크 R1~R2 + 롤백 절차 비공란.
```

---

### P4 — Web Layer

```
TARGET: docs/refactor/phases/P4-web.md
VERDICT: FAIL
FAIL_REASONS:
  - P-3: W2~W8(UI 라우트 7건) 상세가 §5에서 "해당 feature doc의 §4.2/§4.3 그대로 구현"
          공통 설명 1블록으로 합산 처리됨. 각 work item별 명령형 step ≥3이 개별 work item
          상세에 존재하지 않음(W2~W8은 개별 상세 섹션 자체 없음, 공통 설명에 흡수).
  - P-4: W2~W8 개별 AC가 문서 내에 없음. "각 feature §7의 AC 중 HTTP/template 관련 항목
          모두 통과"가 일괄 처리돼 work item별 ≥2건 분리 AC + 검증 명령이 부재.
          W15(smoke tests) AC도 "9건 모두 통과" 단일 문장.
  - P-8: EC-4("HTMX partial 응답이 hx-trigger='every Ns'로 자동 갱신")가 selenium
          또는 polling 시뮬레이션으로 명시되나 W4(info.py, F03)는 실시간 갱신 없으므로
          W4 AC와 EC-4의 매핑 관계가 불명확. EC-8("전체 uv run pytest 0 fail")이
          W1 AC의 test_app_factory.py 결과를 cover하는지 인용 없이 묵시적 포함에 의존.
PASS_NOTES:
  - C-1: frontmatter 키 모두 보유.
  - C-2: 필수 섹션 모두 존재.
  - C-3: W4 smoke 스크립트 코드 블록은 없으나(P5에 해당), P4 자체 코드 블록 없어 위반 없음.
  - P-1: Work Item 15건(W1~W15).
  - P-5: 사이클 없음. W1→{W2~W9,W11}, W9→{W10,W12,W13a,W14}, W13a→W13b, 모두→W15.
  - P-6: Group A = {W2,W3,W4,W5,W6,W7,W8,W9,W11} 9개 동시 가능.
  - P-7: W13(L)→W13a/W13b 분해 명시.
  - P-9: 시작 조건에 P2/P3 PASS, F01~F08 doc Auditor PASS 인용.
  - P-10: 리스크 R1~R3 + 롤백 절차 비공란.
```

---

### P5 — Deployment & Cutover

```
TARGET: docs/refactor/phases/P5-deployment-cutover.md
VERDICT: FAIL
FAIL_REASONS:
  - P-3: W3(compose.dev.yaml)에 지시사항 step이 "코드 bind-mount 옵션" + "BUSHEXA_LOG_LEVEL=DEBUG"
          기술 2줄뿐. 명령형 step ≥3 미달.
  - P-4: W3 AC가 "podman-compose ... up으로 코드 변경 즉시 반영" 1건뿐. AC ≥2건 미달.
          W7(마이그레이션 노트) AC도 "위 5개 섹션 존재" 1건 + grep 명령 1건인데
          5개 섹션 각각을 별개 AC로 명시하지 않아 단일 AC로 평가.
  - P-8: EC-8("운영자가 cutover 후 1주일 동안 govtrack 사이클 누락 없이 진행 — 사후 검증,
          본 Phase 종료 후 모니터")이 Phase 종료 조건으로 명시됐으나 검증 명령이 없는
          인간 모니터 조건임. W8(1주일 사후 검증)에 대응하는 work item이 분해 목록에 없어
          work item AC → EC cover 관계가 성립하지 않음.
PASS_NOTES:
  - C-1: frontmatter 키 모두 보유.
  - C-2: 필수 섹션 모두 존재.
  - C-3: W4 smoke 스크립트 코드 블록에 bash 태그 있음.
  - P-1: Work Item 7건(W1~W7).
  - P-5: 사이클 없음. W1→W2→{W3,W4,W6}, W7 독립, W5는 W4 후.
  - P-6: Group A = {W1,W7} 동시, Group B = {W3,W4,W6} 동시 가능.
  - P-7: L 크기 work item 없음(모두 S/M).
  - P-9: 시작 조건에 P4 PASS, 운영 데이터 백업, .env 작성 완료 명시.
  - P-10: 리스크 R1~R3 + 롤백 절차(W2/W5 단계별) 비공란.
```

---

## 요약 표

| Phase | VERDICT | FAIL criterion-ids |
|---|---|---|
| P0 Bootstrap | **FAIL** | P-4, P-8 |
| P1 Data Layer | **FAIL** | P-3, P-4, P-8 |
| P2 Crawler | **FAIL** | P-3, P-4, P-8 |
| P3 Domain Services | **FAIL** | P-3, P-4, P-8 |
| P4 Web Layer | **FAIL** | P-3, P-4, P-8 |
| P5 Deployment | **FAIL** | P-3, P-4, P-8 |

전체: **PASS 0건 / FAIL 6건**

---

## 의존성 그래프 사이클 검사

수동 트레이스:

```
P0 (depends_on: [])
P1 (depends_on: [P0])
P2 (depends_on: [P1])
P3 (depends_on: [P1])
P4 (depends_on: [P2, P3])
P5 (depends_on: [P4])
```

경로: P0 → P1 → P2 → P4 → P5  
경로: P0 → P1 → P3 → P4 → P5  
**사이클 없음 (acyclic). P-5 전 Phase PASS.**

---

## 가장 위험한 FAIL Top 3

### 1. P-3 (P1~P5 공통) — work item별 명령형 step 분해 부재

P1의 W1, P2의 W6, P3의 W2/W3/W4/W6, P4의 W2~W8, P5의 W3이 구현 step 대신 함수 선언 나열에 그침. 구현자가 방법론 없이 feature doc으로 역참조해야 하므로 실행 중 해석 불일치 발생 가능.

### 2. P-4 (P1~P5 공통) — work item별 AC가 산문 1문장으로 통합 기술

P1 W1/W5/W9, P2 W1/W4/W5/W6/W8, P3 W2~W4/W6, P4 W2~W8/W15, P5 W3/W7에서 AC가 단일 산문으로 묶여 ≥2건 분리 bullet을 충족하지 못함. 검증 명령도 일부 work item에서 부재하거나 python 일행으로만 처리. 구현 완료 판정 기준이 불명확해 Implementor와 Reviewer 간 통과/실패 판단이 불일치할 위험.

### 3. P-8 (P0, P2~P5) — 종료 조건이 일부 work item AC를 cover하지 않음

P0 W9 AC(README 섹션/uv 명령), P2 W5 AC(F04 AC-R1~R5), P3 W5의 버그 수정 검증, P4 W1 AC와 EC-8의 묵시적 포함, P5 EC-8(1주일 사후 모니터)에 대응 work item 없음. Phase 종료 선언 시 누락된 AC가 미검증 상태로 통과될 수 있어 회귀 리스크가 높음.

---

## Designer 한 줄 권고

**각 work item 상세에 명령형 step ≥3을 개별 작성하고, AC를 bullet ≥2건으로 분리한 뒤, Phase 종료 조건(EC)이 모든 work item AC를 1:1로 인용하는지 매핑 표를 추가하라.**
