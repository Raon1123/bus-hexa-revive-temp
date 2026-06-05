---
report_id: design-audit-adrs-20260601-T01
auditor: claude-sonnet-4-6
audit_date: 2026-06-01
targets: ADR-001 ~ ADR-008
criteria_doc: docs/refactor/auditor/design-audit-criteria.md
---

# Design Audit Report — ADRs (2026-06-01 T01)

## 개별 결과

---

### ADR-001

```
TARGET: architecture/ADR-001-web-framework.md
VERDICT: PASS
FAIL_REASONS: (없음)
PASS_NOTES:
  - C-1: frontmatter에 status, adr_id, designer, auditor_status, last_updated, supersedes, superseded_by 모두 존재.
  - C-2: 컨텍스트/결정/대안/결과/검증방법/미해결 섹션 전부 존재.
  - C-3: 검증 방법 코드 블록에 bash 태그 명시.
  - C-4: 경로 bushexa/web/static/vendor/htmx.min.js — 프로젝트 루트 기준 상대 경로.
  - C-5: 라인 번호 인용 없음 (해당 없음).
  - C-6: "한다", "않는다" 등 단정형 일관 사용. 추측 표현 없음 (미해결 섹션에 격리된 후속 결정 있음).
  - C-7: 혼용 개념 동일 표기 일관.
  - A-1: "웹 프레임워크는 … 한다. … 도입하지 않는다." 단정문 1-2줄 종결.
  - A-2: 대안 A/B/C 각각 장점·단점·기각사유 모두 명시.
  - A-3: 긍정 영향 4건, 부정 영향/비용 3건 모두 채워짐.
  - A-4: bash 코드 블록 3개 명령어, 모두 실행 가능한 형태.
  - A-5: supersedes: null, superseded_by: null 명시.
```

---

### ADR-002

```
TARGET: architecture/ADR-002-database.md
VERDICT: PASS
FAIL_REASONS: (없음)
PASS_NOTES:
  - C-1: frontmatter 키 완비.
  - C-2: 컨텍스트/결정/대안/결과/검증방법/미해결 섹션 전부 존재.
  - C-3: 검증 방법 bash 태그 명시.
  - C-4: 경로 bushexa/db/connection.py 등 — 프로젝트 루트 기준 상대 경로.
  - C-5: 라인 번호 인용 없음 (해당 없음).
  - C-6: "결정한다", "분리한다", "도입하지 않는다" 단정형. 미해결 Q1/Q2는 미해결 섹션에 격리.
  - C-7: Repository 패턴, BusLogRepo 등 동일 표기 일관.
  - A-1: "선택은 환경변수 DATABASE_URL 한 개로 결정한다." 단정문으로 종결.
  - A-2: 대안 A/B/C 각각 장점·단점·기각사유 모두 명시.
  - A-3: 긍정 영향 4건, 부정 영향/비용 2건 명시.
  - A-4: bash 명령어 3개, 실행 가능한 형태.
  - A-5: supersedes: null, superseded_by: null 명시.
```

---

### ADR-003

```
TARGET: architecture/ADR-003-packaging.md
VERDICT: FAIL
FAIL_REASONS:
  - A-2: 대안 A(venv+requirements.txt)에 단점이 "락파일 부재로 재현성 약함. uv 대비 느림" 으로 기재되어 있으나
         기각사유가 "사용자 선택은 uv"라는 외부 요구사항 인용만이며 자체 평가 근거가 빈약하다.
         대안 B(Poetry)에 기각사유가 "uv가 동등 이상"으로 기재되어 있으나 이는 결론 반복이지
         왜 동등 이상인지 근거 서술이 없다. 그러나 장점·단점·기각사유 3요소 자체는 모두 존재함.
         — 재검토: 3요소는 형식상 존재하므로 A-2 FAIL 근거 부족.
         → A-2 형식 충족으로 재판정.
  - C-3: 결정 섹션 내 toml 코드 블록에 언어 태그가 ```toml 으로 명시되어 있음. 확인 OK.
  - (재검토 후 FAIL 사유 없음)
VERDICT_REVISED: PASS
PASS_NOTES:
  - C-1: frontmatter 키 완비.
  - C-2: 컨텍스트/결정/대안/결과/검증방법/미해결 섹션 전부 존재.
  - C-3: toml 블록에 toml 태그, bash 블록에 bash 태그 모두 명시.
  - C-6: "한다", "커밋 대상" 등 단정형 사용. 미해결은 미해결 섹션에 격리.
  - A-1: "패키징은 pyproject.toml + uv로 한다." 단정문으로 종결.
  - A-2: 대안 A/B/C 각각 장점·단점·기각사유 3요소 존재.
  - A-3: 긍정 영향 4건, 부정 영향/비용 2건 명시.
  - A-4: bash 명령어 4개, 실행 가능한 형태.
  - A-5: supersedes: null, superseded_by: null 명시.
```

---

### ADR-004

```
TARGET: architecture/ADR-004-realtime.md
VERDICT: FAIL
FAIL_REASONS:
  - A-2: 대안 A(모든 화면 SSE)에 기각사유가 "본 앱 부하 작음, 단순 폴링이 충분."으로만 기술되어 있고,
         대안 B(모든 화면 단순 폴링)에도 단점은 명시되어 있으나 기각사유가 "데몬 status / 재크롤 로그는 SSE가
         자연스러움"으로 기술. 장점·단점·기각사유 3요소 확인:
         - 대안 A: 장점 O, 단점 O, 기각사유 O → 충족
         - 대안 B: 장점 O, 단점 O, 기각사유 O → 충족
         - 대안 C(WebSocket): 장점 O, 단점 O, 기각사유 O → 충족
         → A-2 충족. FAIL 사유 없음.
  - (검토 결과 FAIL 사유 없음)
VERDICT_REVISED: PASS
PASS_NOTES:
  - C-1: frontmatter 키 완비.
  - C-2: 컨텍스트/결정/대안/결과/검증방법/미해결 섹션 전부 존재.
  - C-3: bash 태그 명시.
  - C-6: "분리한다", "구현" 등 단정형. 미해결은 미해결 섹션에 격리.
  - A-1: 표 형태 + 구현 방법 문장이 단정형으로 기술. 2줄 이내 규범 상 표가 단정형 결정으로 기능함.
  - A-3: 긍정 영향 3건, 부정 영향/비용 2건 명시.
  - A-4: bash 명령어 3개 실행 가능 형태. grep 명령어 포함.
  - A-5: supersedes: null, superseded_by: null 명시.
```

---

### ADR-005

```
TARGET: architecture/ADR-005-secrets.md
VERDICT: FAIL
FAIL_REASONS:
  - A-2: 대안이 A, B 2건만 존재. 기준 A-2는 "대안 ≥2건"을 요구하므로 2건은 충족.
         각 대안 장점·단점·기각사유 확인:
         - 대안 A: 장점 O, 단점 O, 기각사유 O → 충족
         - 대안 B: 장점 O, 단점 O, 기각사유 O → 충족
         → A-2 충족.
  - C-4: 결정 섹션에 `docker-compose.yaml:8` 인용이 있음 (컨텍스트 섹션). 파일 경로는 있으나
         `:8`이 붙어 있어 C-5(라인 번호 인용은 `path:NN` 형식) 검토 필요.
         "docker-compose.yaml:8" → C-5 형식 `path:NN` 충족.
  - (검토 결과 FAIL 사유 없음)
VERDICT_REVISED: PASS
PASS_NOTES:
  - C-1: frontmatter 키 완비.
  - C-2: 컨텍스트/결정/대안/결과/검증방법/미해결 섹션 전부 존재.
  - C-3: bash 태그 명시.
  - C-5: docker-compose.yaml:8 → path:NN 형식 충족.
  - C-6: "로드한다", "변경", "이동" 등 단정형. 미해결은 미해결 섹션에 격리.
  - A-1: "시크릿은 환경변수 우선, 부재 시 secret/ 파일 fallback으로 로드한다." 단정문.
  - A-3: 긍정 영향 3건, 부정 영향/비용 2건 명시.
  - A-4: bash 명령어 3개, 실행 가능한 형태.
  - A-5: supersedes: null, superseded_by: null 명시.
```

---

### ADR-006

```
TARGET: architecture/ADR-006-deployment.md
VERDICT: FAIL
FAIL_REASONS:
  - A-2: 대안 C(Dockerfile 그대로)에 장점·단점이 없고 기각사유만 존재("사용자 요구(uv) 위반").
         A-2 기준은 "각 대안에 장점·단점·기각사유 모두 존재"를 요구. 대안 C에 장점·단점 미기재.
PASS_NOTES:
  - C-1: frontmatter 키 완비.
  - C-2: 컨텍스트/결정/대안/결과/검증방법/미해결 섹션 전부 존재.
  - C-3: yaml 블록에 yaml 태그, bash 블록에 bash 태그 명시.
  - C-6: "한다", "사용 불필요" 등 단정형. 미해결은 미해결 섹션에 격리.
  - A-1: "배포 구조를 다음과 같이 한다." 단정문.
  - A-3: 긍정 영향 4건, 부정 영향/비용 3건 명시.
  - A-4: bash 명령어 5개 실행 가능 형태.
  - A-5: supersedes: null, superseded_by: null 명시.
```

---

### ADR-007

```
TARGET: architecture/ADR-007-directory-layout.md
VERDICT: FAIL
FAIL_REASONS:
  - A-2: 대안 A(기존 src/crawl/infopages/ 유지)에 장점·단점이 없고 기각 선언만 존재("기각: 통합 패키지가
         가독성·import 일관성에 유리"). 대안 B(모놀리식 single file)도 장점·단점 없이 기각 선언만 존재.
         A-2 기준: 각 대안에 장점·단점·기각사유 모두 존재 요구. 대안 A·B 모두 장점·단점 미기재.
PASS_NOTES:
  - C-1: frontmatter 키 완비.
  - C-2: 컨텍스트/결정/대안/결과/검증방법/미해결 섹션 전부 존재.
  - C-3: bash 태그 명시. 디렉토리 트리는 코드 블록 내 언어 태그 없음(plain 코드 블록). 단, 언어 태그 없는
         tree 블록은 tree 표시 목적이므로 검토: 결정 섹션의 디렉토리 트리 블록과 레이어 의존 블록에
         언어 태그가 없음(빈 ``` 사용). C-3 FAIL 가능성.
         — 재검토: 디렉토리 트리 블록 ```(빈 태그)과 레이어 의존 블록 ```(빈 태그) 존재.
         C-3 기준 "모든 코드 블록에 언어 태그" 위반.
  - → C-3 추가 FAIL.
FAIL_REASONS_FINAL:
  - A-2: 대안 A, B에 장점·단점 미기재.
  - C-3: 결정 섹션 내 디렉토리 트리 코드 블록 및 레이어 의존 코드 블록에 언어 태그 없음(빈 ``` 사용).
```

---

### ADR-008

```
TARGET: architecture/ADR-008-testing-strategy.md
VERDICT: FAIL
FAIL_REASONS:
  - C-3: 결과 섹션 "따오는 작업" — 오탈자("따오는" → "따라오는") 는 C-7 대상이 아님, 스타일 트집 금지.
         코드 블록 검토: 테이블(결정 섹션 계층 표, 외부 의존 격리 규칙 텍스트 내 테이블, 회귀 보호 매트릭스)은
         마크다운 테이블이므로 코드 블록 아님. bash 코드 블록에 bash 태그 명시 확인.
         → C-3 충족.
  - A-2: 대안 A/B/C 각각 장점·단점·기각사유 존재 확인:
         - 대안 A(통합 테스트만): 장점 O, 단점 O, 기각사유 O
         - 대안 B(시뮬레이션 생략): 장점 O, 단점 O, 기각사유 O
         - 대안 C(testcontainers 미도입): 장점 O, 단점 O, 기각사유 O
         → A-2 충족.
  - A-1: "테스트는 3-계층 + 1보조 시뮬레이션 계층으로 구성한다." 단정문 — A-1 충족.
  - C-6: "결과" 섹션 제목이 "결과"이나 하위 섹션 제목이 "따오는 작업"으로 오탈자. 단, 오탈자는
         C-6(추측·미정 표현) 위반 아님. 스타일 트집 금지 원칙으로 C-6 위반 없음.
  - A-3: 결과 섹션 검토 — "따오는 작업"이 "따라오는 작업"의 오탈자로 보이나 긍정 영향 3건,
         부정 영향/비용 3건 모두 채워짐. → A-3 충족.
  - (검토 결과 FAIL 사유 없음)
VERDICT_REVISED: PASS
PASS_NOTES:
  - C-1: frontmatter 키 완비.
  - C-2: 컨텍스트/결정/대안/결과/검증방법/미해결 섹션 전부 존재.
  - C-3: bash 태그 명시.
  - A-4: bash 명령어 5개 실행 가능 형태.
  - A-5: supersedes: null, superseded_by: null 명시.
  - 특이사항: "따오는 작업"은 "따라오는 작업"의 오탈자로 보이나 criterion-id에 없는 사유로 FAIL 불가.
```

---

## 통합 요약 표

| ADR | VERDICT | FAIL criterion-id | 비고 |
|-----|---------|-------------------|------|
| ADR-001 | PASS | — | 전 항목 충족 |
| ADR-002 | PASS | — | 전 항목 충족 |
| ADR-003 | PASS | — | 전 항목 충족 |
| ADR-004 | PASS | — | 전 항목 충족 |
| ADR-005 | PASS | — | 전 항목 충족 |
| ADR-006 | **FAIL** | A-2 | 대안 C 장점·단점 미기재 |
| ADR-007 | **FAIL** | A-2, C-3 | 대안 A·B 장점·단점 미기재, 2개 코드 블록 언어 태그 없음 |
| ADR-008 | PASS | — | 전 항목 충족 (오탈자는 criterion 밖) |

**PASS: 6 / FAIL: 2**

---

## 위험도 Top 3

1. **A-2 / ADR-007**: 대안 A·B 두 건 모두 장점·단점 없이 기각만 선언. 대안 비교 근거가 없어 설계 판단 추적 불가. 가장 넓은 영향 범위(전 ADR 참조 구조).
2. **A-2 / ADR-006**: 대안 C(Dockerfile 유지)에 장점·단점 미기재. 운영 배포 결정의 기각 근거가 불완전.
3. **C-3 / ADR-007**: 결정 섹션 디렉토리 트리·레이어 의존 코드 블록에 언어 태그 없음. 문서 렌더링 일관성 저하.

---

## Designer 한 줄 권고

ADR-006 대안 C와 ADR-007 대안 A·B에 각각 장점·단점 1줄씩 추가하고, ADR-007의 빈 코드 블록에 언어 태그(예: `text`)를 부여하여 재제출하라.
