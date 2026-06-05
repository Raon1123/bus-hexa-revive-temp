---
status: draft
phase_id: P0
designer: opus
auditor_status: pending
last_updated: YYYY-MM-DD
depends_on: []        # 다른 Phase ID 배열
---

# P0 — {{Phase Title}}

> Phase는 **그 자체가 병렬 실행 단위**이며, 내부적으로 다시 병렬 work item으로 분해된다.

## 1. 목적 (한 줄)

이 Phase가 끝나면 무엇이 가능해지는가.

## 2. 시작 조건 (Entry Criteria)

- [ ] 의존 Phase 모두 Auditor PASS
- [ ] 관련 ADR 모두 Auditor PASS
- [ ] 관련 feature doc 모두 Auditor PASS
- [ ] (해당시) 데이터 백업 / 브랜치 분기 완료

## 3. 종료 조건 (Exit Criteria — Auditor checklist)

- [ ] EC-1: ... (검증 명령: `...`)
- [ ] EC-2: ...
- [ ] EC-N: ...

## 4. Work Item 분해

> 각 work item은 **별도 Sonnet에게 단독으로 맡길 수 있는 단위**여야 한다.
> dependency가 있는 항목은 명시. dependency 없는 항목들끼리는 동시 실행 가능.

| ID | 작업 제목 | 소요 추정 | 의존 | 산출물 |
|---|---|---|---|---|
| W1 | ... | S | — | ... |
| W2 | ... | M | — | ... |
| W3 | ... | S | W1 | ... |
| W4 | ... | L | W2 | ... |

> 소요: S(≤30분), M(30분~2시간), L(>2시간 — 가능하면 더 쪼개라)

## 5. Work Item 상세

### W1 — {{제목}}

**Owner:** unassigned (Sonnet)
**Depends on:** —
**산출물:**
- `path/to/file.py` — ...
- 테스트: `tests/path/test_*.py`

**지시사항 (명령형):**
1. ...
2. ...
3. ...

**Acceptance:** (반드시 ≥2건 bullet로 분리, 각 항목에 검증 방법)
- [ ] AC-1: ... (검증: `...`)
- [ ] AC-2: ... (검증: `...`)

**테스트 케이스 (자연어 의도 동반 — P-11):**
- `test_file::test_name_1`: 무엇을 / 어떤 입력·조건에서 / 무엇이 참이어야 통과하는지 자연어 1줄.
- `test_file::test_name_2`: ...
> 감리가 이 설명만 읽고 케이스 의도를 세부 설명할 수 있어야 한다. 함수명만 나열 금지.

**검증 명령:**
```bash
uv run pytest tests/... -k ...
```

---

### W2 — {{제목}}
... (동일 구조)

## 6. 병렬화 그래프

```text
W1 ──┐
     ├──▶ W3 ──┐
W2 ──┘         ├──▶ W5
W4 ────────────┘
```

병렬 가능 그룹:
- Group A (동시): W1, W2, W4
- Group B (A 완료 후): W3
- Group C (B 완료 후): W5

## 7. 리스크 & 롤백

- 발생 가능한 리스크와 트리거
- 롤백 절차 (이 Phase만 되돌리는 방법)

## 8. Auditor 감리 포인트 (설계 단계)

이 Phase 설계 문서가 다음을 만족하는지 Auditor가 확인:

- [ ] DA-1: 각 work item이 단일 책임을 가지며 다른 work item과 명확히 분리됨
- [ ] DA-2: dependency 그래프에 사이클 없음
- [ ] DA-3: 모든 work item에 명시적 산출물 경로가 있음
- [ ] DA-4: 모든 work item에 검증 가능한 AC (자동 명령)가 있음
- [ ] DA-5: 병렬 가능 그룹이 식별됨
- [ ] DA-6: 시작/종료 조건이 객관적으로 검증 가능
- [ ] DA-7: 모든 L 크기 work item에 분해 시도 또는 분해 불가 사유 명시
- [ ] DA-8: 테스트 산출 work item의 각 test case에 자연어 검증 의도가 있어 감리가 세부 설명 가능 (P-11)
- [ ] DA-9: EC ↔ work item AC 매핑 표가 있고 모든 AC가 ≥1개 EC에 매핑 (P-12)
