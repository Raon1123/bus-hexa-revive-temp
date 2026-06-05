---
phase: P4
scope: "W14,W16"
verdict: PASS
auditor: sonnet
date: 2026-06-02
---

# Execution Audit — P4 Chunk 3c-ii (W14 admin govtrack status+SSE + W16 admin 로그뷰어)

TARGET: P4/W14,W16
VERDICT: PASS

---

## CHECKLIST_RESULTS

### W14 — admin govtrack status + SSE (TP-011)

- **AC-1** (status JSON에 `last_success_at`·`consecutive_failures` 필드): PASS
  - 근거: `admin.py:584–592` `_status_to_dict` 함수가 두 필드를 포함해 반환.
  - `tests/web/test_admin_govtrack_status.py::test_status_json` PASS. `data["last_success_at"] == _BASE_DT.isoformat()` (구현 독립 기대값), `data["consecutive_failures"] == 0`.
- **AC-2** (SSE `text/event-stream`으로 status 이벤트 송신): PASS
  - 근거: `admin.py:628–632` Response mimetype=`text/event-stream`, `event: status\ndata: {…}\n\n` 형식.
  - `tests/web/test_admin_govtrack_status.py::test_status_sse` PASS. Content-Type 및 첫 청크 `event: status`·`data:` 확인.

### W16 — 관리자 로그 뷰어 (TP-015)

- **AC-1** (비로그인 `/admin/logs` → 302 `/admin/login`): PASS
  - 근거: `admin.py:651–652` `@bp.get("/logs") @login_required`. `login_required` 데코레이터가 세션 미인증 시 302 리다이렉트.
  - `tests/web/test_admin_logs.py::test_requires_login` PASS.
- **AC-2** (`LogTailReader.tail` 최신순·level 필터·lines≤2000·파일부재 빈목록): PASS
  - 근거: `log_reader.py:106–113` 구현 (역순, level 필터, `min(int(lines), _MAX_LINES)` 상한, FileNotFoundError → `[]`).
  - `tests/services/test_log_reader.py` 4개 테스트 모두 PASS.
- **AC-L4** (파일 부재 → 200 + "로그 파일이 아직 없습니다"): PASS
  - `tests/web/test_admin_logs.py::test_logs_missing_file_returns_empty_notice` PASS.
- **AC-L5** (path traversal 차단 — 고정 경로만 읽음): PASS
  - `admin.py:675–676` `reader = LogTailReader(config.log_dir)`, `?file=` 파라미터 무시.
  - `tests/web/test_admin_logs.py::test_uses_fixed_path` PASS (sentinel 문자열 미노출 확인).

### E-기준

- **E-1**: 모든 AC PASS.
- **E-2**: 산출물 파일 확인:
  - `bushexa/services/log_reader.py` 존재
  - `bushexa/web/routes/admin.py` W14+W16 라우트 존재
  - `bushexa/config.py` `log_dir: Path = Path("logs")` 추가됨
  - `bushexa/web/app.py` `setup_logging(level=config.log_level, log_dir=config.log_dir)` 호출 존재
  - `bushexa/web/templates/admin/govtrack_status.html` 존재
  - `bushexa/web/templates/admin/logs.html` 존재
  - `tests/services/test_log_reader.py` 존재
  - `tests/web/test_admin_govtrack_status.py` 존재
  - `tests/web/test_admin_logs.py` 존재
- **E-3**: `uv run pytest -q` 200 passed — ImportError/SyntaxError 없음.
- **E-4**: `uv run pytest -q` → **200 passed, 0 failed, 0 error** (회귀 없음).
- **E-5**: 시크릿 하드코딩 0건 확인. 테스트 fixture의 `test-api-key`/`test-secret`은 테스트 파일에만 존재.
- **E-6**: `/admin/logs/stream` SSE 미구현은 TP-015 §8에 "MVP 이후 선택" 명시. TODO/FIXME 없음.
- **E-7**:
  - **W14**: `GovtrackStatus` 실구현 필드(`cycle_started_at/total_inserts/total_errors/committed/route_breakdown/consecutive_failures/last_success_at`)가 `govtrack_status.py:24–31`에 정확히 일치. `_status_to_dict` 직렬화가 모든 7개 필드를 포함. `GovtrackStatusReader`를 `config.data_dir/"govtrack_status.json"` 경로로 사용 (`admin.py:577`).
  - **W16**: F04 §4.6 명세 `LogLine(ts, logger, level, message, raw)` 및 `LogTailReader(log_dir, filename="bushexa.log").tail(lines=200, level=None)` 시그니처와 구현(`log_reader.py:41–114`) 일치. `stream()` 미구현은 spec 명시 "선택" 항목.
- **E-8**: 10개 test case 전부 자연어 설명 아래에 기술 (TEST_CASE_EXPLANATIONS 섹션).
- **E-9**: P-11 test case 명칭과 실제 구현 일치 확인. 1건 executor-added (`test_logs_route_returns_200_with_log_file`) — PASS_NOTES 기록.
- **E-10**: W14/W16 구현 중 에러 기록 없음 (postmortems에 해당 항목 부재). 에러 미발생으로 E-10 적용 면제.
- **E-11**: 보안 항목 검사(이 청크 범위 내):
  - S2: `/admin/govtrack/status`, `/admin/govtrack/status/stream`, `/admin/logs` 모두 `@login_required` 적용 확인.
  - S3: `LogTailReader` 생성자에서 경로 고정, `?file=` 파라미터 무시 확인. traversal 차단.
  - S7: `_mask_secrets` 함수 존재 (`admin.py:646–648`), logs_view에서 표출 전 적용 (`admin.py:683–686`).
  - S9: `_MAX_LINES = 2000` 상한 존재 (`log_reader.py:38`), 테스트 검증됨.
- **E-12**:
  - TP-011: `status: implemented`, `implemented_by: P4/W14`. 라우트(`/admin/govtrack/status`, `/admin/govtrack/status/stream`), login_required, 5초 SSE, 파일부재 빈dict — 구현 일치.
  - TP-015: `status: implemented`, `implemented_by: P4/W16`. 라우트(`/admin/logs`), login_required, 고정경로, lines/level 검증, 파일부재 안내 — 구현 일치. `/admin/logs/stream` SSE는 TP-015 §8에 "MVP 이후 미구현" 명시.
- **E-13**: 아래 상세.

---

## COMMAND_OUTPUTS

- `$ uv run pytest tests/services/test_log_reader.py tests/web/test_admin_govtrack_status.py tests/web/test_admin_logs.py -v`
  ```
  tests/services/test_log_reader.py::test_tail_returns_recent_lines_last_first PASSED
  tests/services/test_log_reader.py::test_tail_filters_by_level PASSED
  tests/services/test_log_reader.py::test_tail_caps_lines_at_2000 PASSED
  tests/services/test_log_reader.py::test_missing_log_file_returns_empty PASSED
  tests/web/test_admin_govtrack_status.py::test_status_json PASSED
  tests/web/test_admin_govtrack_status.py::test_status_sse PASSED
  tests/web/test_admin_logs.py::test_requires_login PASSED
  tests/web/test_admin_logs.py::test_uses_fixed_path PASSED
  tests/web/test_admin_logs.py::test_logs_route_returns_200_with_log_file PASSED
  tests/web/test_admin_logs.py::test_logs_missing_file_returns_empty_notice PASSED
  10 passed in 0.29s
  ```

- `$ uv run pytest -q`
  ```
  200 passed in 8.97s
  ```
  (기존 190 + 신규 10 = 200, 0 fail, 0 error — 회귀 없음)

- `$ grep -rn 'streamlit' bushexa/web/` → 출력 없음 (0건 확인)

- `$ grep -rn 'datetime.now|datetime.today' bushexa/web/ bushexa/services/log_reader.py` → 출력 없음 (0건 확인)

- 시크릿 하드코딩 grep → 템플릿의 HTML form `type="password"` 필드만 (정상), 코드 내 시크릿 하드코딩 0건.

- GovtrackStatusWriter 독립 실행 검증:
  ```python
  # _BASE_DT = datetime(2026, 6, 1, 8, 0, 0, tzinfo=KST)
  # 성공 사이클 write 후 last record:
  {'cycle_started_at': '2026-06-01T08:00:00+09:00', ..., 
   'consecutive_failures': 0, 'last_success_at': '2026-06-01T08:00:00+09:00'}
  # test 기대값 _BASE_DT.isoformat() == '2026-06-01T08:00:00+09:00' — 일치, 구현 독립 확인
  ```

---

## TEST_CASE_EXPLANATIONS

- `test_log_reader.py::test_tail_returns_recent_lines_last_first`:
  임시 디렉터리에 10줄("line-0"~"line-9") 로그 파일을 테스트가 직접 기록한 뒤 `tail(lines=5)`를 호출. 반환 길이가 5이고 index 0이 "line-9"(최신), index 4가 "line-5"인지 검증한다. 기대값은 테스트가 기록한 알려진 내용에서 도출 — 구현 독립.

- `test_log_reader.py::test_tail_filters_by_level`:
  INFO 3건·ERROR 2건·CRITICAL 1건으로 구성된 알려진 시퀀스를 파일에 기록하고 `level="ERROR"`로 필터. 반환 길이 3(ERROR 이상)이고 최신순("error-5" → "crit-3" → "error-1") 순서가 맞는지 검증한다. 기대 개수·메시지는 테스트 시퀀스에서 수기 계산.

- `test_log_reader.py::test_tail_caps_lines_at_2000`:
  2050줄을 파일에 기록하고 `lines=10**6`을 요청. 반환 길이가 `_MAX_LINES`(2000) 이하이고 파일에 2050줄이 있으므로 정확히 2000임을 검증한다 — DoS/메모리 상한 회귀.

- `test_log_reader.py::test_missing_log_file_returns_empty`:
  log_dir만 생성하고 `bushexa.log`를 만들지 않은 상태에서 `tail()`를 호출. 예외 없이 빈 리스트 `[]`를 반환하는지 검증한다.

- `test_admin_govtrack_status.py::test_status_json`:
  `GovtrackStatusWriter`로 알려진 CycleStats(total_inserts=5, total_errors=0, committed=True, cycle_started_at=_BASE_DT)를 임시 status 파일에 시드한 뒤, 인증된 클라이언트로 `GET /admin/govtrack/status`를 요청. 응답 JSON에 `last_success_at == _BASE_DT.isoformat()`, `consecutive_failures == 0`이 있는지 검증한다 (W14 AC-1). 기대값은 시드 입력에서 도출 — 구현 출력 베끼기 아님.

- `test_admin_govtrack_status.py::test_status_sse`:
  동일 status_app으로 `GET /admin/govtrack/status/stream`을 요청. `Content-Type`에 `text/event-stream`이 포함되고, 첫 청크에 `event: status`와 `data:` 줄이 존재하며, data JSON에 `consecutive_failures`·`last_success_at`이 담기는지 검증한다 (W14 AC-2). 무한 루프 방지를 위해 첫 청크만 소비 후 연결 종료.

- `test_admin_logs.py::test_requires_login`:
  비인증 클라이언트로 `GET /admin/logs` 요청 시 302 리다이렉트가 발생하고 `Location`에 `/admin/login`이 포함되는지 검증한다 (W16 AC-1, F04 AC-L1).

- `test_admin_logs.py::test_uses_fixed_path`:
  인증 클라이언트로 `?file=../../secret/key.txt`를 포함해 요청. 응답이 200이고 실제 secret 파일의 sentinel 문자열(`TOP_SECRET_API_KEY_12345`)이 응답에 없는지 검증한다 (W16 AC-L5 — path traversal 차단). 고정 경로인 `config.log_dir/bushexa.log`만 읽는다는 사실을 간접 증명.

- `test_admin_logs.py::test_logs_route_returns_200_with_log_file` [**executor-added**]:
  log_dir에 알려진 로그 라인 1건을 기록하고 `GET /admin/logs` 호출 시 200이고 메시지("test message")가 HTML에 포함되는지 검증한다. P-11에 명시되지 않은 보강 smoke 테스트 — spec 테스트를 약화하지 않으므로 허용.

- `test_admin_logs.py::test_logs_missing_file_returns_empty_notice`:
  로그 파일 없이 인증 상태로 `GET /admin/logs` 요청. 500이 아닌 200을 반환하고 응답 HTML에 "로그 파일이 아직 없습니다"가 포함되는지 검증한다 (F04 AC-L4, TP-015 §9 AC-L4).

---

## FAIL_REASONS_FOR_DESIGNER

없음.

---

## PASS_NOTES

1. **govtrack_status.html HTML 렌더 라우트 미연결**: `templates/admin/govtrack_status.html`은 존재하나 HTML 렌더 라우트(`GET /admin/govtrack`)가 미구현. W14 AC는 JSON+SSE만 요구하므로 AC 위반 아님. Designer가 대시보드 카드 배선을 Chunk 4(W15 통합)로 이월 — 비차단.

2. **GovtrackStatus 필드 정정**: F04 §6는 실구현 필드에 맞게 Designer 정정됨. 구현 7개 필드 일치 확인.

3. **/admin/logs/stream SSE 미구현**: TP-015 §8 "선택(MVP 이후)" 명시. E-6 OK — 미해결 항목으로 기록됨.

4. **S7 마스킹 코드 존재, 테스트 미포함**: `_mask_secrets` 함수가 `admin.py:646–648`에 존재하고 `logs_view`에서 표출 전 적용. 단, 마스킹 회귀 테스트 없음 — Designer가 W15 통합 청크에서 추가하기로 이월. 차단 아님. 추가 주의사항: 현재 마스킹 정규식은 `value` 이후 첫 토큰만 마스킹하므로 `Authorization: Bearer <long-token>` 형태는 `<long-token>` 이후 토큰은 노출될 수 있음 — W15 마스킹 회귀 테스트 작성 시 이 케이스를 커버하도록 권장.

5. **executor-added 테스트**: `test_admin_logs.py::test_logs_route_returns_200_with_log_file` — P-11에 미포함이나 보강 smoke. spec 테스트를 약화하지 않고 기존 AC-L4/L5를 대체하지 않음 — 허용.

6. **AppConfig frozen dataclass + log_dir 기본값**: `log_dir: Path = Path("logs")`에 기본값이 지정되어 기존 테스트 파일 중 `log_dir`을 명시하지 않던 코드도 깨지지 않는 안전한 변경. 실제로는 모든 AppConfig 생성 지점(conftest, 각 web 테스트 fixture)이 이미 `log_dir=tmp_path / "logs"`를 명시하여 격리됨 — 회귀 위험 없음.

7. **전체 200 테스트 통과**: 기존 190 + 신규 10 = 200. 0 fail, 0 error — 회귀 없음 확인.
