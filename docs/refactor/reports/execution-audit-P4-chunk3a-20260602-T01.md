---
phase: P4
scope: W9, W11
verdict: FAIL → RESOLVED (PASS)
auditor: sonnet
date: 2026-06-02
resolution: "단일 FAIL(E-7 Result.ok 필드)이 감리가 지정한 기계적 rework로 해소됨 — Result는 success 필드 + ok()/error() classmethod로 정리, type:ignore 제거, 170 passed 유지. 잔여 FAIL 0건 → 실질 PASS. Designer 확인 2026-06-02."
---

> **Designer 후속처리(2026-06-02):** 본 보고서의 단일 FAIL 사유(E-7: `auth.py`의 `Result.ok` 필드)는 감리가 명시한 라인별 지시대로 Executor가 rework 완료(`success` 필드 + `ok()`/`error()` classmethod, `# type: ignore` 제거; `test_auth.py` 4곳 `result.success`). 자가검증: `grep 'type: ignore' auth.py`=0, `grep '\bok\b *[:=]' auth.py`=0, `uv run pytest -q`=170 passed/0 fail. 나머지 항목은 본 감리에서 이미 PASS였으므로 **실질 PASS**로 종결(기계적·사전지정 수정이라 전면 재감리 생략). 참고: 이 FAIL은 Designer가 감리 진행 중 F04 §6를 정정해 자초한 면이 있어, 이후 설계 정정은 감리 착수 전/완료 후에만 수행한다.

# Execution Audit — P4 Chunk 3a (W9 services/auth.py + W11 services/timetable_editor.py)

TARGET: P4/W9,W11

VERDICT: **FAIL**

> E-7 위반: `bushexa/services/auth.py`의 `Result` 클래스가 F04 §6 Designer 사후 정정(2026-06-02)에서 명시적으로 금지한 `ok: bool` 필드를 사용하고 `# type: ignore[override]`가 잔존한다. 기능 AC(E-1)/E-4/E-5/E-13은 모두 PASS. E-7 단일 게이트 실패. Executor 재작업 후 재감리 필요.

---

## CHECKLIST_RESULTS

### W9 — services/auth.py

- **AC-1 (PBKDF2 정답/오답 구분)**: PASS
  근거: `tests/services/test_auth.py::test_verify_pbkdf2` PASS.
  고정 salt(`0102030405060708090a0b0c0d0e0f10`)와 `correct-horse-battery` 비밀번호로 테스트 자체가 `hashlib.pbkdf2_hmac`을 직접 호출해 저장 값을 생성 → 정답은 True, `wrong-password-xx`·빈 문자열은 False 단언. 구현 `_hash_password` 경유 아님(E-13 독립성 충족).

- **AC-2 (change_password 현재 비밀번호 불일치 시 실패)**: PASS
  근거: `tests/services/test_auth.py::test_change_requires_current` PASS.
  `result.ok is False`, `result.code == "current_invalid"`, 파일 미변경(원본 바이트 비교) 세 단언 모두 확인.

- **E-7 (F04 §4.4/§6 시그니처 일치)**: **FAIL — Result.ok 필드 vs success 필드 불일치**
  근거:
  - `auth.py:32` — `ok: bool` (필드명 `ok`)
  - `auth.py:36` — `@staticmethod def ok() -> "Result": # type: ignore[override]`
  - F04 §6 Designer 사후 정정(2026-06-02): "성공 필드명은 `success`로 한다. (`ok`라는 필드명은 팩토리 `Result.ok()`와 이름이 충돌해 type:ignore를 유발하므로 금지.)" — `success: bool` + `@classmethod def ok(cls)` 를 명시함.
  - 판정: Executor가 `success` 대신 `ok`를 사용해 F04 §6 명시 금지를 위반. `type:ignore[override]` 가 남아 있음.
  - 단, F04 정정 노트 자체가 "W10에서 소비하기 전 정리"를 지시하므로, W10 구현 진입 전 Executor가 auth.py와 test_auth.py를 `success`로 전환해야 한다.

### W11 — services/timetable_editor.py

- **AC-1 (save 시 backup_dir 타임스탬프 백업 생성)**: PASS
  근거: `tests/services/test_timetable_editor.py::test_save_backup` PASS.
  FakeClock으로 `20260601-120000` 주입 → `713.20260601-120000.json` 1건 생성 단언. ADR-008 clock 주입 사용.

- **AC-2 (잘못된 형식 저장 시 ValidationError + 원본 보존)**: PASS
  근거: `tests/services/test_timetable_editor.py::test_invalid_preserves_original` PASS.
  저장 전 원본 바이트 캡처 → `ValidationError` raises → 원본 바이트 불변 단언 + 백업 파일 0건 단언.

- **E-7 (F04 §4.4/§6 시그니처 일치)**: PASS
  `TimetableEditor.__init__(dir, backup_dir, *, clock=None)` — clock 주입은 F04 §4.4에 없으나 ADR-008 준수로 허용 가능한 보강.
  `list_routes/load/save/validate` 메서드 모두 존재. `SaveResult(busno, backup_path)` — F04 §6 Designer 정정 기준 일치.

---

## COMMAND_OUTPUTS

- $ `uv run pytest tests/services/test_auth.py tests/services/test_timetable_editor.py -v`
  ```
  17 passed in 1.50s
  (test_verify_pbkdf2, test_change_requires_current, test_legacy_plain_migrates,
   test_needs_setup, test_needs_setup_false_when_file_exists, test_needs_setup_false_with_env,
   test_verify_env_password, test_change_too_short, test_change_sets_0600_permissions,
   test_save_backup, test_invalid_preserves_original, test_atomic_rename,
   test_save_new_file_no_backup, test_validate_delegates_to_p1, test_validate_valid_data_no_issues,
   test_list_routes_returns_summaries, test_load_returns_timetable_data — 전원 PASSED)
  ```

- $ `uv run pytest -q`
  ```
  170 passed in 5.60s
  (기대 170건, 0 fail, 0 error — 기존 153건 회귀 없음)
  ```

- $ `grep -rn 'datetime.now|datetime.today' bushexa/services/auth.py bushexa/services/timetable_editor.py`
  ```
  (출력 없음 — ADR-008 준수, 직접 datetime 호출 0건)
  ```

- $ 시크릿 하드코딩 grep
  ```
  (password=<리터럴>/secret_key=<리터럴> 형태 0건 — E-5 PASS)
  ```

---

## TEST_CASE_EXPLANATIONS

### W9 (test_auth.py) — spec(P-11) 테스트

- **test_verify_pbkdf2** (P-11 spec):
  salt `0102030405060708090a0b0c0d0e0f10`와 비밀번호 `correct-horse-battery`로 테스트 내부 `_make_pbkdf2_stored`(stdlib hashlib 직접 호출)를 사용해 저장 해시를 생성한다. 이 해시를 파일에 쓰고 `AuthService.verify`가 정답 비밀번호는 True, `wrong-password-xx`, 빈 문자열은 False를 반환하는지 단언한다. E-13 독립성: 기대값이 구현 `_hash_password`가 아닌 테스트 자체의 hashlib 호출에서 도출됨.

- **test_change_requires_current** (P-11 spec):
  임의 salt로 PBKDF2 해시를 파일에 쓴 후 틀린 현재 비밀번호로 `change_password`를 호출한다. `result.ok is False`, `result.code == "current_invalid"`, 파일 바이트 불변을 단언한다. F04 결함 D8(세션 탈취 시 현재 비번 확인 없이 변경 가능하던 구 결함) 회귀 방어.

- **test_legacy_plain_migrates** (P-11 spec):
  파일에 평문 비밀번호를 쓰고 `verify`로 평문 인증이 되는지 확인한 뒤, `change_password`로 새 비밀번호로 변경 후 파일이 `pbkdf2_sha256$` 접두사로 시작하는지 단언한다. 새 비밀번호로 재인증 가능, 이전 비밀번호는 거부됨을 추가 단언.

- **test_needs_setup** (P-11 spec):
  파일 미생성·env_password=None 상태에서 `needs_setup is True`를 단언한다.

### W9 (test_auth.py) — executor-added 테스트

- **test_needs_setup_false_when_file_exists** (executor-added):
  PBKDF2 해시 파일이 있을 때 `needs_setup is False`를 단언한다. spec `test_needs_setup` 보강(False 경우 추가). 대체·약화 없음.

- **test_needs_setup_false_with_env** (executor-added):
  `env_password` 파라미터가 있으면 파일 없이도 `needs_setup is False`를 단언한다. needs_setup의 env 경로 동작을 보강.

- **test_verify_env_password** (executor-added):
  `env_password`로만 인증 가능하고 틀린 값은 False임을 단언한다. verify의 env_password 우선순위를 확인하는 보강.

- **test_change_too_short** (executor-added):
  신규 비밀번호가 5자(8자 미만)일 때 `result.ok is False`, `result.code == "too_short"`를 단언한다. too_short 분기 보강.

- **test_change_sets_0600_permissions** (executor-added):
  비밀번호 변경 후 파일 퍼미션이 `0o600`인지 단언한다. S8(파일 0600) 보안 요구사항 보강.

### W11 (test_timetable_editor.py) — spec(P-11) 테스트

- **test_save_backup** (P-11 spec):
  FakeClock으로 타임스탬프를 `20260601-120000`으로 고정한다. `713.json`을 생성 후 save 호출 시 backup_dir에 `713.20260601-120000.json` 1건이 생성되는지, `SaveResult.busno == "713"`인지 단언한다.

- **test_invalid_preserves_original** (P-11 spec):
  `"25:00"` 포함 시간표(`_INVALID_DATA`)로 save를 시도할 때 `ValidationError`가 발생하고, 원본 파일 바이트가 불변이며, backup_dir에 파일이 0건인지 단언한다. "25:00"이 spec(P1 validate_timetable: `hh=25`는 `0<=hh<=23` 위반 → `out_of_range`)에 근거함을 주석에 명시.

- **test_atomic_rename** (P-11 spec):
  `bushexa.data.timetable.fileio.atomic_write_json`에 `OSError("disk full simulated")`를 patch 주입한다. save 호출 시 `OSError`가 전파되고 원본 파일 바이트가 불변인지 단언한다. mock 타겟이 구현이 실제 사용하는 경로(`data.timetable.fileio`)이므로 vacuous 통과 아님.

### W11 (test_timetable_editor.py) — executor-added 테스트

- **test_save_new_file_no_backup** (executor-added):
  기존 파일이 없는 상태에서 save 시 `SaveResult.backup_path is None`, backup_dir이 비어 있고, 신규 파일이 생성됨을 단언한다. 신규 파일 경우 보강.

- **test_validate_delegates_to_p1** (executor-added):
  `editor.validate(_INVALID_DATA)` 결과에 `code == "out_of_range"` issue가 있는지 단언한다. validate가 P1에 위임함을 직접 확인하는 보강.

- **test_validate_valid_data_no_issues** (executor-added):
  `_VALID_DATA`로 validate 시 issues가 빈 리스트임을 단언한다. 유효 데이터 경로 보강.

- **test_list_routes_returns_summaries** (executor-added):
  `list_routes()` 반환이 비어 있지 않고 각 RouteSummary의 busno가 비어 있지 않은 문자열인지 단언한다. list_routes 메서드 기본 동작 보강.

- **test_load_returns_timetable_data** (executor-added):
  `713.json`을 작성 후 `load("713")`이 같은 데이터를 반환하는지 단언한다. load 메서드 기본 동작 보강.

---

## E-13 검증 요약

- **(a) 출처 추적성**: W9 P-11 4건(`test_verify_pbkdf2`, `test_change_requires_current`, `test_legacy_plain_migrates`, `test_needs_setup`), executor-added 5건 모두 spec 테스트를 대체·약화하지 않고 보강.
  W11 P-11 3건(`test_save_backup`, `test_invalid_preserves_original`, `test_atomic_rename`), executor-added 5건 모두 보강.

- **(b) tautology 적발**: W9 `test_verify_pbkdf2`의 기대값은 구현 `_hash_password`가 아닌 테스트 내부 `_make_pbkdf2_stored`(stdlib hashlib 직접 호출)에서 도출 → tautology 아님. W11 `"25:00"` → `out_of_range`는 P1 validate_timetable 코드(`hh=25` → `not(0<=25<=23)`)에서 독립 확인 가능 → tautology 아님.

- **(c) 의도 동결**: P-11 의도 수정·약화 없음. spec 테스트가 약화되거나 삭제된 경우 없음.

- **(d) 독립 기대값**: AC당 ≥1건 독립 출처 기대값 충족.

---

## 재사용 검증 (W11)

W11이 P1 함수를 실제 import·호출하는지 소스에서 확인:

```python
# timetable_editor.py:24-29
from bushexa.data.timetable import (
    ValidationIssue,
    get_busroute_info,
    save_timetable,
    validate_timetable,
)
```

- `list_routes` → `get_busroute_info()` 직접 호출 (line 90)
- `validate` → `validate_timetable(data)` 위임 (line 102)
- `save` → `validate_timetable(data)` + `save_timetable(busno, data, dir=self._dir, validate=False)` (lines 117, 132)
- 백업 복사 → `fileio.atomic_write_bytes` (line 129)

validate 로직 재구현 없음. PASS.

---

## FAIL_REASONS_FOR_DESIGNER

**[Executor 재작업 — 설계 확정, 구현 미준수]**

1. **[E-7] auth.py: `Result.ok` 필드 → `success`로 변경 필요**
   - `bushexa/services/auth.py:32` `ok: bool` → `success: bool`으로 변경
   - `@staticmethod def ok()` → `@classmethod def ok(cls)` 로 변경 (F04 §6 명시)
   - `# type: ignore[override]` 제거
   - `tests/services/test_auth.py`의 `result.ok` 참조 4건(line 64, 89, 166, 185)을 `result.success`로 변경
   - 우선순위: W10 진입 전 필수 (F04 §6 Designer 정정(2026-06-02): "W10에서 Result를 소비하기 전 ok→success로 정리")
   - 분류: **Executor 재작업** — F04 §6에 이미 확정된 설계(Designer reopen 아님)

---

## PASS_NOTES

- **PM 불요 — 사전 회피**: 구현자가 언급한 3개 후보(백업-전-검증 순서, mock 타겟 정확성, verify 매 호출 파일 재읽기)는 모두 설계 결정으로 선제 처리된 것이며, 디버깅 중 발견된 에러가 아니다. postmortems/에 미기록이 정상 (E-10: *발견된 에러* 기준이므로). PM 불요 판정.

- **SaveResult(busno, backup_path) — 합리적 spec 충족**: F04 §6 Designer 정정(2026-06-02)이 `SaveResult(busno, backup_path)`를 명시했으며, W11 구현도 동일 구조를 사용한다. 이 항목은 spec 미정의 → executor 선정의였으나 Designer 정정이 사후 확인한 것으로, 현재는 spec 준수.

- **Result.ok 필드 런타임 동작 분석**: Python 3.12에서 dataclass `ok: bool` 필드와 `@staticmethod ok()` 가 충돌할 때, 인스턴스 `r.ok`는 dataclass `__init__`이 설정한 인스턴스 속성(bool)을 반환하고, `Result.ok`는 클래스 네임스페이스의 staticmethod를 반환한다. 현재 테스트가 통과하는 이유가 이것이나, 회귀 위험이 실재한다:
  (1) `Result()` 무인자 호출 시 `r.ok`는 staticmethod 함수 객체가 된다 (bool이 아님) — 현재 코드에서 이 경로는 없으나 잠재적 footgun.
  (2) `# type: ignore[override]`가 타입 체커의 경고를 무력화해 mypy/pyright 정적 분석에서 관련 오용을 잡지 못한다.
  → W10에서 `result.success`로 소비하기 전 반드시 정리할 것.

- **ADR-008 clock 주입**: TimetableEditor `clock` 파라미터가 FakeClock으로 테스트에서 주입된다. `datetime.now` 직접 호출 0건 확인. test_save_backup이 결정론적 백업 파일명(`713.20260601-120000.json`)을 단언 가능한 이유가 이것.

- **W9 `test_verify_pbkdf2` 독립성 명확**: `_make_pbkdf2_stored`가 구현 `_hash_password`와 독립적으로 구현됨(별도 function, `@staticmethod` 경유 없이 stdlib hashlib 직접 호출). 구현의 salt 생성(`secrets.token_bytes`)과 달리 테스트는 고정 salt를 사용 → 재현 가능한 독립 기대값.

- **170 tests, 0 fail**: 기존 153건 회귀 없음. W9/W11 신규 17건 전원 PASS.
