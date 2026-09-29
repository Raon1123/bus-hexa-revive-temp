# Refactor Workflow

> 본 프로젝트의 대규모 리팩토링은 **세 가지 역할**과 **두 종류의 감리 루프**로 운영된다.

## 1. 역할 정의

| 역할 | 모델 | 책임 |
|---|---|---|
| **Designer** | Opus 4.7 | 모든 문서 골격·템플릿·아키텍처 결정·Phase 분해·세부 work item 정의 |
| **Executor** | Sonnet 4.6 | Designer가 만든 매뉴얼/체크리스트를 그대로 수행 (feature doc 채우기, 코드 작성, 테스트 작성) |
| **Auditor** | Sonnet 4.6 (별도 컨텍스트) | Designer 산출물의 granularity 감리 + Executor 결과의 checklist 충족 여부 감리 |

> **불변 규칙**
> - Executor는 Designer 매뉴얼에 명시되지 않은 의사결정을 하지 않는다. 모호한 부분은 보고만 한다.
> - Auditor는 산출물 외 정보를 가정하지 않는다. checklist만으로 판정한다.
> - Designer가 자기 산출물을 직접 감리하지 않는다 (반드시 별도 Auditor 컨텍스트).

## 2. 두 감리 루프

### Loop A — 설계 감리 (Design Audit)

```text
Opus Designer ──작성──▶  설계 문서 (feature/ADR/phase)
                              │
                              ▼
                       Auditor (design 모드)
                              │
              ┌──────PASS─────┴──────FAIL──────┐
              ▼                                  ▼
        Loop B 진입                       Designer 재작업
                                          (Auditor 지적 반영)
```

판정 기준: `docs/refactor/auditor/design-audit-criteria.md`

### Loop B — 실행 감리 (Execution Audit)

```text
Sonnet Executor ──구현──▶  코드/테스트/문서 업데이트
                              │
                              ▼
                       Auditor (execution 모드)
                              │
              ┌──────PASS─────┴──────FAIL──────┐
              ▼                                  ▼
       다음 Phase 진입                    Executor 재작업
                                          (남은 checklist 항목)
```

판정 기준: `docs/refactor/auditor/execution-audit-criteria.md`

## 3. 단계 흐름 (전체 리팩토링)

```text
Stage 0  Feature 문서화 (Loop A → Loop B with Sonnet writers)
   │
   ▼
Stage 1  아키텍처 결정 (ADR) — Designer only, Auditor 감리
   │
   ▼
Stage 2  Phase 설계 — Designer 분해, Auditor가 granularity/병렬성 감리 (Loop A)
   │
   ▼
Stage 3  Phase 병렬 실행 — Sonnet 다수가 work item 분담, Auditor가 phase 종료시 감리 (Loop B)
   │     (Phase 간 dependency가 허용하는 한 동시 진행)
   ▼
Stage 4  통합 검증 — 전체 E2E, podman-compose 배포 dry-run
```

## 4. 산출물 디렉토리 레이아웃

```text
docs/refactor/
├── 00-workflow.md                # 본 파일
├── 01-overview.md                # 리팩토링 범위·제약·목표
├── templates/
│   ├── feature-template.md       # Sonnet이 채우는 feature doc 슬롯
│   ├── adr-template.md           # 아키텍처 결정 기록 양식
│   └── phase-template.md         # Phase 분해 양식
├── features/
│   ├── F01-departure-board.md
│   ├── F02-busno.md
│   ├── ...                       # 페이지/백그라운드 컴포넌트별 1파일
├── architecture/
│   ├── ADR-001-web-framework.md
│   ├── ADR-002-database.md
│   ├── ADR-003-packaging.md
│   ├── ADR-004-realtime.md
│   ├── ADR-005-secrets.md
│   ├── ADR-006-deployment.md
│   └── ADR-007-directory-layout.md
├── phases/
│   ├── P0-bootstrap.md
│   ├── P1-data-layer.md
│   ├── ...
├── auditor/
│   ├── design-audit-criteria.md
│   └── execution-audit-criteria.md
└── reports/                       # Auditor 결과물 (자동 생성)
    ├── design-audit-<phase>-<ts>.md
    └── execution-audit-<phase>-<ts>.md
```

## 5. 파일/문서 명명 규칙

- Feature doc: `F{NN}-{kebab-name}.md` — NN은 2자리 zero-pad (앱 라우팅 순서와 무관, 신규 추가는 NN++)
- ADR: `ADR-{NNN}-{kebab-name}.md` — NNN은 3자리, 한 번 부여하면 변경 불가
- Phase: `P{N}-{kebab-name}.md` — N은 1자리, P0부터 시작
- Audit report: `{design|execution}-audit-{target}-{YYYYMMDD-HHMM}.md`

## 6. 상태 추적

- 각 문서 상단에 frontmatter 형식 메타 블록을 둔다:
  ```yaml
  ---
  status: draft | designed | audited | executing | done
  designer: opus
  auditor_status: pending | pass | fail
  last_updated: YYYY-MM-DD
  ---
  ```
- Auditor 결과는 `reports/`에 timestamp 파일로 누적, 본 문서는 `auditor_status`만 갱신.

## 7. 통신 규약 (Designer ↔ Executor ↔ Auditor)

- Designer는 항상 **명령형 체크리스트**로 지시한다. (예: "X 파일에 Y 함수를 작성하라. 시그니처: Z")
- Executor는 항상 **체크리스트 형식 보고**로 응답한다. ✅/❌ + 한 줄 근거.
- Auditor는 항상 **개별 항목에 대한 PASS/FAIL + 근거 인용**으로 응답한다.

이 규약 위반은 곧바로 Loop 재시작 사유다.

## 8. 에러·부검(Postmortem) 규약

구현·디버깅·운영 중 **에러를 발견하면 반드시 부검 보고서를 남긴다.** 같은 실수를 두 번 하지 않기 위한 제도다.

### 8.1 트리거 (언제 작성하는가)

다음 중 하나라도 해당하면 `docs/refactor/postmortems/PM-{NNN}-{slug}.md`를 작성한다.

- 운영에서 관찰된 오작동 (예: "버스 통과 로그가 안 남는다")
- 구현 중 발견한 비자명 버그 (단순 오타/컴파일 에러는 제외)
- 테스트가 잡지 못했던 회귀
- 데이터 손상·오염, 보안 약점
- "왜 이렇게 동작하지?"로 30분 이상 소비한 모든 디버깅

### 8.2 절차

1. `templates/postmortem-template.md`를 복사해 `postmortems/PM-{NNN}-{slug}.md` 생성 (NNN은 3자리 일련번호).
2. 근본 원인(Root Cause)과 **재발 방지(Prevention)** 섹션을 반드시 채운다. 재발 방지가 비면 부검 미완료다.
3. 재발 방지의 회귀 테스트는 ADR-008 규약(자연어 의도 1줄)을 따른다.
4. 해당 결함이 일반적 패턴이면 `ADR-008` 회귀 매트릭스 또는 감리 기준에 반영한다.
5. `postmortems/INDEX.md`에 한 줄 추가 (PM-ID, 제목, 심각도, 상태).
6. 일반화 가능한 교훈은 `docs/guide/pitfalls.md` 해당 절에 "규칙 — 왜 — 근거(PM 링크)" 한 줄로 추가한다. 다른 AI 세션은 PM 전문보다 이 요약을 먼저 읽는다.

### 8.3 감리 연계

- Auditor(실행 감리)는 해당 Phase에서 발견된 에러가 부검으로 기록되었는지, 재발 방지 테스트가 실재하는지 확인한다 (execution-audit-criteria E-10).
- 미기록 에러를 발견하면 그 자체가 FAIL 사유다.

### 8.4 명명·상태

- 파일: `PM-{NNN}-{kebab-slug}.md`
- severity: low / medium / high / critical
- status: draft → fixed → verified (회귀 테스트 통과 + Auditor 확인)

## 9. Touch Point 인터랙션 디자인 규약

사람과 시스템이 만나는 모든 지점(화면 로드, 폼 제출, 버튼/링크, 관리자 액션, CLI 명령)은 **"정확히 어떻게 동작하는가"**를 별도 디자인 문서로 남긴다.

- 위치: `docs/refactor/touchpoints/TP-{NNN}-{slug}.md`, 템플릿 `templates/touchpoint-template.md`.
- 내용: actor·트리거·단계별 인터랙션(사람 행동↔시스템 반응)·입력 검증·피드백(로딩/성공/에러)·분기·접근성·자동갱신.
- feature doc은 §1에 자신의 touch point를 TP-ID로 나열·링크한다.
- 각 Phase(특히 P4 web)는 해당 화면/액션의 TP 문서를 산출물에 포함한다.
- `touchpoints/INDEX.md`에 한 줄 등재.
- 설계 감리: feature/Phase가 사람 touch point를 가지면 대응 TP 문서가 존재하고, 단계별 반응·분기·피드백이 명세되었는지 확인(design-audit F-11 / DA-10).

## 10. 보안 감리 규약

구현(특히 web) 후 **보안 위협 감리**를 전용 단계로 수행한다 (ADR-009).

- 기준: `auditor/security-audit-criteria.md` (위협 카테고리 S1~S10).
- 시점: P4 종료 후·P5(cutover) 전 게이트. high/critical 0건이어야 P5 진입.
- 수행: 별도 Auditor 컨텍스트 + `/security-review` 보조.
- 발견 결함: `postmortems/`에 PM 등재 + 보안 회귀 테스트로 봉인(§8 연계).
- 실행 감리(execution-audit E-11)에서 보안 게이트 통과 여부를 확인한다.
