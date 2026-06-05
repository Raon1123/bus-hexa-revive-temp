# Execution Audit Criteria

> Auditor는 Executor (Sonnet)가 끝낸 작업의 **결과물**이 해당 Phase / Work Item 의 Acceptance Checklist를 모두 충족하는지 확인한다.

## 0. 진입

```
audit-execution --phase {P0|P1|...} --work-item {W1|W2|...|all}
```

응답 양식:

```
TARGET: P{N}/{W{M}|all}
VERDICT: PASS | FAIL
CHECKLIST_RESULTS:
  - AC-1: PASS | FAIL (근거: <파일:라인 또는 명령 출력 인용>)
  - AC-2: ...
COMMAND_OUTPUTS:
  - $ <명령>
    <stdout/stderr 인용 핵심 부분>
TEST_CASE_EXPLANATIONS:
  - <test_file::test_name>: <이 테스트가 무엇을, 어떤 입력/조건에서, 무엇이 참이어야 통과하는지 자연어 2-3줄>
  - ... (해당 Phase/work item이 추가·변경한 모든 test case)
FAIL_REASONS_FOR_DESIGNER:
  - <Executor에게 재작업 지시할 구체 항목 또는 Designer에게 설계 보강 요청 항목>
PASS_NOTES:
  - <긍정 신호, 회귀 위험 코멘트>
```

## 1. 절차 (Auditor가 따라야 할 순서)

1. **AC 인벤토리** — Phase doc과 모든 work item 의 AC를 모아 unique 리스트로 정렬
2. **자동 검증 실행** — 각 AC의 "검증 명령"을 실제로 실행, 출력 캡처
3. **소스 검사** — 명령으로 확인 불가한 AC (예: "X 함수가 Y 시그니처를 가진다")는 grep/Read로 직접 확인
4. **부수 효과 확인** — 산출물 파일이 명시된 경로에 존재하고 정상 import 가능한지
5. **회귀 검사** — Phase 진입 전에 통과하던 다른 테스트들이 여전히 PASS인지 (`uv run pytest`)
6. **테스트 케이스 자연어 설명** — 해당 Phase/work item이 추가·변경한 각 test case의 본문·docstring·assert를 읽고, `TEST_CASE_EXPLANATIONS`에 "무엇을 / 어떤 입력·조건에서 / 무엇이 참이어야 통과"를 자연어로 기술. 설계 단계 의도(P-11)와 실제 검증 내용이 다르면 적발한다.
7. **테스트 출처·반정당화 검증 (E-13)** — 각 테스트의 기대값이 *구현과 독립된 출처*에서 왔는지 확인한다. (a) P-11에 없는 Executor 추가 테스트를 "executor-added"로 분류, (b) 구현 출력을 그대로 베낀 tautological 테스트 적발, (c) 설계 문서의 AC·P-11 의도가 Executor에 의해 약화 수정됐는지 git/diff로 확인. "테스트가 통과한다"는 사실 자체가 구현 정당성을 보장하지 않는다 — 무엇과 비교해 통과하는지를 본다.
8. **판정**

## 2. 판정 기준

- [ ] **E-1**: 모든 AC가 PASS (부분 통과 금지)
- [ ] **E-2**: 모든 산출물 파일이 명시된 경로에 존재
- [ ] **E-3**: 변경된 코드가 import 시 SyntaxError/ImportError 없음
- [ ] **E-4**: 전체 `pytest` 결과: failed=0, errors=0 (skip 허용, 단 신규 skip은 사유 명시 필요)
- [ ] **E-5**: 신규 시크릿·키·DB 비밀번호가 코드/문서에 하드코딩되지 않음 (grep `password|secret_key`)
- [ ] **E-6**: 신규 파일에 TODO/FIXME가 남아있다면 work item의 미해결 항목으로 기록되어 있음
- [ ] **E-7**: 코드 변경이 작성된 doc의 "도메인 서비스 시그니처"와 일치
- [ ] **E-8**: 해당 Phase/work item이 추가·변경한 **모든 test case**에 대해, Auditor가 `TEST_CASE_EXPLANATIONS` 섹션에서 검증 의도를 자연어로 세부 설명한다. 테스트 본문(또는 docstring/주석)을 읽어도 "무엇을 검증하는지" 설명 불가능한 케이스가 1건이라도 있으면 그 케이스는 FAIL 사유로 기록한다 (의도 불명 테스트 = 회귀 보호 가치 없음)
- [ ] **E-9**: Phase doc의 테스트 관련 AC가 명시한 케이스 이름이 실제 코드의 test 함수와 1:1 대응하고, 각 케이스의 자연어 의도(설계 단계 P-11)와 실제 구현이 일치한다 (의도와 다른 것을 검증하는 테스트 적발)
- [ ] **E-10**: 해당 Phase 구현·디버깅 중 발견된 에러가 `docs/refactor/postmortems/`에 부검으로 기록되었고, 각 부검의 "재발 방지" 회귀 테스트가 실재하며 통과한다 (00-workflow §8). 미기록 에러나 재발 방지 없는 부검은 FAIL 사유
- [ ] **E-11**: (web/보안 관련 Phase) 보안 감리(`security-audit-criteria.md`) 게이트를 통과했고 high/critical 발견이 0건이다. 미통과 시 P5 진입 차단 (00-workflow §10, ADR-009)
- [ ] **E-12**: 사람 touch point를 추가·변경한 Phase는 대응 `touchpoints/TP-*.md`가 존재하고 구현이 그 인터랙션 명세(단계·분기·피드백)와 일치한다 (00-workflow §9)
- [ ] **E-13**: **테스트 출처·반(反)정당화 무결성** — Executor(Sonnet)는 자신의 구현을 정당화하는 수단으로 테스트를 제안할 수 있으므로, Auditor는 다음을 적발한다:
  - **(a) 출처 추적성**: 모든 테스트는 설계 문서의 자연어 의도(P-11)에 1:1 추적되어야 한다. P-11에 없는 Executor 추가 테스트는 `PASS_NOTES`에 **"executor-added"로 명시**하고, 그것이 spec 테스트를 대체·약화하지 않는지 확인한다(보강은 허용, 대체는 금지).
  - **(b) tautology 적발**: 기대값이 "구현이 내놓는 값"을 그대로 베낀(change-detector) 테스트 — 즉 **스펙이 위반돼도 통과**할 테스트 — 는 FAIL. 판별법: 각 AC에서 기대값이 *구현과 독립된 출처*(설계 명세·fixture의 알려진 정답·수기 계산·legacy 동등성)에서 도출됐는지 확인. 단지 `assert f(x) == <현재 f(x)>` 형태면 적발.
  - **(c) 의도 동결**: Executor가 자기 구현을 통과시키려 설계의 AC·P-11 의도를 수정·약화하면 FAIL. 구현이 spec 테스트를 못 통과하면 그것은 *구현* 결함(재작업) 또는 Designer reopen이지 *테스트* 완화가 아니다. 설계 문서의 test 의도 diff가 있으면 Designer 승인 여부를 확인한다.
  - **(d) 독립 기대값**: AC당 최소 1개 기대값이 구현 출력이 아닌 외부 출처에서 와야 한다(예: parser는 fixture 원문에서 직접 센 개수, time_utils는 달력상 요일).

## 3. FAIL 시 처리

- FAIL은 두 종류:
  - **Executor 실수** — 지시 명확, 결과 미달 → 동일 work item으로 재할당
  - **Designer 결함** — 지시 모호·누락·내부 모순 → Designer에게 reopen 요청

Auditor는 FAIL_REASONS_FOR_DESIGNER 섹션에서 둘 중 어느 쪽인지 명시한다.

## 4. Auditor가 절대 하지 않는 것

- 코드 수정 / 파일 편집 (Auditor는 read-only)
- 명령을 임의로 변경 실행 (지정된 검증 명령 외에 추가 명령 금지, 단 무해한 확인 명령(`ls`, `grep`, `cat -n` via Read)은 허용)
- 무한 retry — 동일 명령이 flaky하면 ≤3회 시도 후 FAIL 보고
- "거의 통과"로 PASS 부여

## 5. 회귀 가드

- 기존 통과하던 테스트가 깨졌다면, 그 테스트도 FAIL 사유로 포함한다 — 신규 AC 통과만으로 PASS 불가
- `pytest --collect-only` 결과의 테스트 수가 줄었다면 사유 확인 (삭제된 테스트 정당성)
