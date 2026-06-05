---
phase: P4
scope: "W13a,W13b"
verdict: PASS
auditor: sonnet
date: 2026-06-02
---

# Execution Audit — P4 Chunk 3c-i (W13a admin 시간표 편집 UI + W13b admin 재크롤 SSE)

## TARGET
P4 / W13a (admin timetable editor), W13b (admin recrawl SSE)

## VERDICT
**PASS**

> E-12 부분 편차(TP-009 §2#3 HTMX partial 미구현)가 있으나, spec 내부 불일치(W13a AC 범위 vs TP-009 §2#3)에 해당하여 Designer reopen 으로 처리. 감리 대상 AC(W13a AC-1/2, W13b AC-1/2)는 전부 PASS.

---

## CHECKLIST_RESULTS

### W13a — 시간표 편집 UI (TP-009)

- **AC-1**: PASS (`test_edit_view` PASS — `GET /admin/timetable/713` → 200, HTML에 "평일"/"토요일"/"일·공휴일" 3개 탭 라벨 + `role="tab"` 3개 확인. `admin.py:399-415`, `timetable_edit.html:38-48`)
- **AC-2**: PASS (`test_save` PASS — POST 후 디스크 713.json 내용 변경 + `tmp_path/timetable_backup/713.*.json` 1건 이상 생성, 백업 내용 == 저장 전 원본. `admin.py:440-459`, `timetable_editor.py:104-134`)
- **AC-3 (invalid weekday 422 + 원본 보존)**: PASS (`test_invalid_save_422` PASS — weekday 키 "월요일" POST → 422, 디스크 바이트 무변경. `timetable_editor.py:117-119`, `validate_timetable._VALID_WEEKDAYS={"0","1","2"}`)

### W13b — 재크롤 SSE (TP-010)

- **AC-1**: PASS (`test_stream` PASS — recrawl POST → 200 + job_id JSON; SSE 소비 시 `event: progress` ≥1건 후 `event: done`, mimetype `text/event-stream`. `admin.py:494-560`)
- **AC-2**: PASS (`test_conflict` PASS — `_MockConflictJob.start` ConflictError 발생 시 409 + JSON 오류 응답. `admin.py:500-503`)

### 공통 검사

- **E-1 모든 AC PASS**: PASS (5개 테스트 모두 PASS)
- **E-2 산출물 파일 존재**: PASS (`bushexa/web/routes/admin.py`(확장), `templates/admin/timetable_index.html`, `templates/admin/timetable_edit.html`, `bushexa/services/timetable_editor.py`, `bushexa/services/timetable_crawl.py`, `tests/web/test_admin_timetable_edit.py`, `tests/web/test_admin_recrawl_sse.py` — 전부 존재 확인)
- **E-3 SyntaxError/ImportError**: PASS (`uv run python -c "from bushexa.web.routes.admin import timetable_edit, timetable_save, timetable_recrawl, timetable_recrawl_stream; from bushexa.services.timetable_editor import TimetableEditor; from bushexa.services.timetable_crawl import TimetableCrawlJob"` → 오류 없음)
- **E-4 전체 pytest 0 fail**: PASS (`uv run pytest -q` → 190 passed, 0 fail, 0 error. 기존 185 + 신규 5 = 190, 회귀 없음)
- **E-5 시크릿 하드코딩**: PASS (`grep -rn 'SECRET\s*=\|API_KEY\s*=' bushexa/web/` → 0건. 테스트 `session_secret="test-secret"`은 test fixture 한정, 운영 코드 하드코딩 없음)
- **E-6 미해결 TODO/FIXME**: PASS (admin.py, timetable_editor.py, timetable_crawl.py, 템플릿 — TODO/FIXME 0건)
- **E-7 도메인 서비스 시그니처 일치**: PASS (주요 일치 + 함수명 편차 1건 PASS_NOTES 참조)
  - `TimetableEditor.save(busno, data)` 위임: `admin.py:447-449` `editor.save(busno, data)` ✓
  - `TimetableCrawlJob.start(vacation=...)` / `.progress(job_id)`: `admin.py:501,540` ✓
  - `ConflictError → 409`: `admin.py:502-503` ✓
  - SSE `text/event-stream`: `admin.py:556` ✓
  - F04 §4.2 함수명 편차: `timetable_recrawl_start` → `timetable_recrawl`. URL `/admin/timetable/recrawl`은 동일, 기능 동일. PASS_NOTES로 기록.
- **E-8 테스트 의도 설명 가능**: PASS (TEST_CASE_EXPLANATIONS 섹션 참조, 5건 전부 설명 가능)
- **E-9 테스트 의도 일치**: PASS (P-11 자연어 의도: `test_edit_view`/`test_save`/`test_invalid_save_422`/`test_stream`/`test_conflict` 모두 W13a/W13b P-11과 1:1 대응)
- **E-10 부검 기록**: PASS (W13a/W13b 구현 중 별도 에러 미발생, 신규 PM 없음. PM-005는 W10 lockout 건으로 선행 처리됨)
- **E-11 보안 감리**: PASS (이 scope 내 항목 — S2/S5/S3 확인 완료. 전체 보안 감리는 P4 종료 후 별도)
- **E-12 TP 일치**: **PARTIAL** — TP-009 §2#3 HTMX partial 편차 있음. 상세는 FAIL_REASONS_FOR_DESIGNER.
- **E-13 테스트 출처 무결성**: PASS (상세는 TEST_CASE_EXPLANATIONS)
- **streamlit 0**: PASS (`grep -rn 'streamlit' bushexa/web/` → 0건)
- **datetime.now/today 0**: PASS (`grep -rn 'datetime\.now\|datetime\.today' bushexa/web/` → 0건. `timetable_editor.py`는 `KSTClock().now()` 사용 — ADR-008 준수)
- **네트워크 호출 격리**: PASS (테스트에서 `app.config["_TIMETABLE_CRAWL_JOB"]` mock 주입 → `_get_crawl_job()` `config.get()` 로 mock 우선 반환. `_make_crawl_fn()` 은 mock이 아닐 때만 호출되며, UlsanBisClient/crawl_all_timetables는 그 closure 내부에서 import → 테스트 시 실제 네트워크 호출 0)

### 보안 (S2/S5/S3)

- **S2 login_required 전 admin 라우트**: PASS
  - `GET /timetable` → `@login_required` ✓ (`admin.py:391`)
  - `GET /timetable/<busno>` → `@login_required` ✓ (`admin.py:400`)
  - `POST /timetable/<busno>` → `@login_required` ✓ (`admin.py:441`)
  - `POST /timetable/recrawl` → `@login_required` ✓ (`admin.py:495`)
  - `GET /timetable/recrawl/<job_id>/stream` → `@login_required` ✓ (`admin.py:534`)
- **S5 CSRF — timetable save/recrawl POST**: PASS — `app.py:68-83` `before_request` `_csrf_protect`가 `/admin/` 하위 모든 POST에 토큰 검증. 템플릿에 `<input type="hidden" name="csrf_token" value="{{ session['csrf_token'] }}">` 포함 (`timetable_edit.html:32,87`)
- **S3 busno traversal 차단**: PASS — `_require_known_busno(busno)` → `_known_busnos()`(whitelist) → 미존재 시 `abort(404)` (`admin.py:380-388`)

---

## COMMAND_OUTPUTS

- `$ uv run pytest tests/web/test_admin_timetable_edit.py tests/web/test_admin_recrawl_sse.py -v`
  ```
  tests/web/test_admin_timetable_edit.py::test_edit_view PASSED            [ 20%]
  tests/web/test_admin_timetable_edit.py::test_save PASSED                 [ 40%]
  tests/web/test_admin_timetable_edit.py::test_invalid_save_422 PASSED     [ 60%]
  tests/web/test_admin_recrawl_sse.py::test_stream PASSED                  [ 80%]
  tests/web/test_admin_recrawl_sse.py::test_conflict PASSED                [100%]
  5 passed in 0.23s
  ```

- `$ uv run pytest -q`
  ```
  190 passed in 8.51s
  ```
  (기존 185 + 신규 5 = 190. 0 fail / 0 error. 기존 회귀 없음)

- `$ grep -rn 'streamlit' bushexa/web/`
  ```
  (출력 없음 — 0건)
  ```

- `$ grep -rn 'datetime\.now\|datetime\.today' bushexa/web/`
  ```
  (출력 없음 — 0건)
  ```

---

## TEST_CASE_EXPLANATIONS

- `test_admin_timetable_edit.py::test_edit_view`:
  로그인된 test_client로 `GET /admin/timetable/713`을 요청했을 때 200이 반환되고, 응답 HTML에 weekday 탭 라벨 "평일"/"토요일"/"일·공휴일" 3개와 `role="tab"` 속성이 정확히 3개 포함되는지를 검증한다. 독립 출처: TP-009 §2 #2 "3개 weekday 탭(평일/토/일·공휴일)". SEED 데이터(`_SEED_713`)는 weekday 키 "0"/"1"/"2"를 모두 포함해 탭이 모두 렌더되도록 한다.

- `test_admin_timetable_edit.py::test_save`:
  시드된 713.json을 디스크에 두고 시간 1건(13:00)을 추가하는 POST를 전송했을 때, (a) 응답 200/302, (b) 디스크 713.json이 시드와 달라지고 "13:00"이 `["0"]["명촌"]`에 포함되며, (c) `timetable_backup/713.*.json`이 1개 이상 생성되고 백업 내용이 저장 전 원본과 동일한지를 검증한다. 독립 출처: TP-009 §2 #4("저장 후 디스크 JSON 변경+백업"), AC-2 spec. 기대값(`_SEED_713`, 추가 시각 "13:00")은 fixture에서 직접 결정됨.

- `test_admin_timetable_edit.py::test_invalid_save_422`:
  유효하지 않은 weekday 키("월요일")를 포함한 POST를 전송했을 때 422가 반환되고, 디스크의 713.json 바이트가 요청 전후로 동일한지(원본 보존)를 검증한다. 독립 출처: TP-009 §6 "잘못된 weekday 키 → 422", `validate_timetable._VALID_WEEKDAYS={"0","1","2"}` 계약(P1 독립 명세). "월요일"이 숫자 집합에 없다는 사실은 구현 출력과 무관하게 자명하다.

- `test_admin_recrawl_sse.py::test_stream`:
  `_MockStreamJob`(progress 1건 후 done yield)을 app.config에 주입한 후 recrawl POST → job_id 획득 → SSE 소비 시, (a) POST 200 + job_id == "job-abc", (b) SSE mimetype `text/event-stream`, (c) 본문에 "event: progress"가 존재하고 "event: done"이 존재하며, (d) progress가 done보다 먼저 오는지를 검증한다. 독립 출처: TP-010 §2/§6 "progress ≥1회 후 done으로 스트림 종료", AC-1 spec.

- `test_admin_recrawl_sse.py::test_conflict`:
  `_MockConflictJob`(start 시 ConflictError 발생)을 app.config에 주입한 후 recrawl POST가 409를 반환하는지를 검증한다. 독립 출처: TP-010 §6 "진행 중 재시작 시도 → 409 Conflict", AC-2 spec, F04 AC-R5.

---

## E-13 테스트 출처·반정당화 무결성

### (a) 출처 추적성

| 테스트 | P-11 근거 | 분류 |
|---|---|---|
| `test_edit_view` | W13a P-11 `test_edit_view` ✓ | spec-backed |
| `test_save` | W13a P-11 `test_save` ✓ | spec-backed |
| `test_invalid_save_422` | W13a P-11 `test_invalid_save_422` ✓ | spec-backed |
| `test_stream` | W13b P-11 `test_stream` ✓ | spec-backed |
| `test_conflict` | W13b P-11 `test_conflict` ✓ | spec-backed |

executor-added 테스트 0건. P-11에 없는 추가 테스트 없음.

### (b) tautology 적발

- `test_edit_view` 기대값("평일"/"토요일"/"일·공휴일", `role="tab"` ×3): TP-009 §2 탭 라벨에서 독립 도출. 구현이 다른 라벨을 쓰면 fail.
- `test_save` 기대값(`_SEED_713` 정의, "13:00" 추가): fixture가 선행 정의됨. 구현이 저장하지 않으면 fail.
- `test_invalid_save_422` 기대값(422, 디스크 무변경): `_VALID_WEEKDAYS` 계약(P1 독립 구현)에서 "월요일" 거부는 자명. 구현이 통과시키면 fail.
- `test_stream` 기대값(progress 전 done 없음, `text/event-stream`): TP-010 §8 형식 명세에서 독립 도출.
- `test_conflict` 기대값(409): TP-010 §6 명세에서 독립 도출.

tautological 테스트 0건.

### (c) 의도 동결

P-11에서 설계의 AC/의도가 수정·약화된 증거 없음. `test_invalid_save_422`는 W13a P-11에 명시됨(TP-009 §6 근거). TP-009 §4의 weekday 키 사후 정정(2026-06-02, Designer)이 구현(숫자 키)과 일치함 — 의도 약화 없음.

### (d) 독립 기대값

각 AC당 fixture/spec 출처에서 독립 기대값 확인. 기대값이 "구현이 내놓는 값을 읽어서 넣은" 형태 없음.

---

## E-12 TP 일치 상세 (편차 기록)

### TP-009 — 구현 일치 항목

| TP 단계/절 | 구현 확인 | 판정 |
|---|---|---|
| §1 `login_required` + busno whitelist | `admin.py:400,403` | ✓ |
| §2 #1 GET /admin/timetable 목록 200 | `admin.py:390-396` | ✓ |
| §2 #2 GET /admin/timetable/713 → 200 + 3탭 | `test_edit_view` PASS | ✓ |
| §2 #4 POST 저장 → TimetableEditor.save (검증→백업→atomic) | `admin.py:447`, `timetable_editor.py:104-134` | ✓ |
| §4 weekday 키 "0"/"1"/"2" 숫자 문자열 | `admin.py:361-364`, `timetable_edit.html:34` | ✓ |
| §4 잘못된 weekday → 422 + 원본 보존 | `test_invalid_save_422` PASS | ✓ |
| §4 `<busno>` whitelist traversal 차단 | `admin.py:380-388` | ✓ |
| §4 CSRF token hidden + 검증 | `timetable_edit.html:32`, `app.py:68-83` | ✓ |
| §5 성공 flash "저장됨 (백업 생성됨)" | `admin.py:458` | ✓ |
| §5 에러 422 + 폼 상단 errors 표시 | `timetable_edit.html:21-29`, `admin.py:452-457` | ✓ |
| §6 분기(비로그인→302, CSRF불일치→400) | `before_request`, `login_required` | ✓ |

### TP-009 §2#3 편차 (Designer reopen)

TP-009 §2#3 및 §5 지정:
> "시간 추가·삭제는 HTMX `hx-post` partial로 해당 weekday 패널만 갱신(**전체 리로드 없음**). `hx-indicator`로 미세 표시."

**구현 실제**: `timetable_edit.html`에 `hx-*` 속성 없음, 추가/삭제 버튼 없음. 시간 편집은 weekday별 `<textarea>`에서 일괄 배치 편집 후 단일 저장 POST. 이 방식은 TP-009 §5가 요구하는 개별 항목 partial 갱신(전체 리로드 없음)과 다르다.

**그러나**: F04 §4.1 AC-T6("HTMX 부분 갱신: 시간 1건 추가 POST → 해당 panel HTML만 응답")은 존재하지만, W13a P-11 내 `test_edit_view`/`test_save`/`test_invalid_save_422` 외에 partial HTMX 테스트는 지정되지 않았고, **EC-4(HTMX partial)는 W13a에 매핑되지 않았다**(EC-4는 W2/W5/W6만). 또한 Executor가 결정한 "textarea 배치 편집" wire format은 별도 기록 대상(PASS_NOTES: executor-decided wire format)으로 Designer가 수용 가능 범위로 판단함. 이는 **spec 내부 불일치**(TP-009 §2#3 vs W13a AC 범위 + EC-4 매핑)이므로 **Executor 실수가 아닌 Designer reopen** 처리.

### TP-010 — 구현 일치 항목

| TP 단계/절 | 구현 확인 | 판정 |
|---|---|---|
| §1 `login_required` | `admin.py:495,534` | ✓ |
| §1 시작 POST CSRF 필요 | `app.py:68-83`, `timetable_edit.html:87` | ✓ |
| §2 #1 POST → job_id JSON | `admin.py:494-504` | ✓ |
| §2 #2 `/recrawl/<job_id>/stream` SSE | `admin.py:533-560` | ✓ |
| §2 #3 done 이벤트 후 스트림 종료 | `admin.py:525-530` | ✓ |
| §4 `<job_id>` 미존재 → 404 | `admin.py:540-543` | ✓ |
| §5 SSE `event: progress\ndata: {}\n\n` 형식 | `admin.py:514-522` | ✓ |
| §6 progress → done 순서 | `test_stream` assert | ✓ |
| §6 진행 중 2번째 → 409 | `test_conflict` PASS | ✓ |
| §8 SSE `text/event-stream`, `event: <type>\ndata: <json>\n\n` | `admin.py:556`, `_format_sse` | ✓ |

TP-010 편차 없음.

---

## FAIL_REASONS_FOR_DESIGNER

- **Designer reopen (설계 내부 불일치)**: TP-009 §2#3/§3/§5는 시간 추가/삭제를 HTMX `hx-post` partial(전체 리로드 없음, hx-indicator 포함, `[+추가]/[x삭제]` 버튼)로 명세하지만, W13a의 Acceptance Checklist(AC-1/AC-2)에는 이 항목이 없고 EC-4도 W13a를 포함하지 않는다. Executor는 "textarea 배치 편집" 방식을 결정했는데, 이는 TP-009 §2#3과 다른 UX이다. **Designer가 다음 중 하나를 결정해야 한다:**
  1. W13a에 HTMX partial을 실제 요구한다면: AC-T6 및 대응 테스트를 W13a/W13a-htmx로 분리하고 Executor 재작업을 지시한다.
  2. textarea 배치 편집을 수용한다면: TP-009 §2#3을 수정하고 §5 hx-indicator를 제거한다. 현재 구현은 그 상태로 PASS 처리.
  - EC-4 미매핑 + W13a AC 미포함이므로 **현 감리 scope에서는 Executor 결함으로 처리하지 않는다**.

---

## PASS_NOTES

- **190/185 회귀**: 기존 185 + 신규 5 = 190, 0 fail / 0 error. 회귀 없음.
- **executor-decided wire format**: `weekdays`/`departures__<wd>`/`times__<wd>__<dep>` 폼 필드 구조는 TP-009 §4에 미명세로 Executor가 결정. 기능적으로 합리적이며 테스트가 동일 형식을 독립 사용하므로 차단 아님. "executor-decided wire format, 미명시분"으로 기록.
- **timetable_recrawl_start → timetable_recrawl 함수명 편차**: F04 §4.2 지정 함수명은 `timetable_recrawl_start`이나 구현은 `timetable_recrawl`. URL `/admin/timetable/recrawl`과 반환 시그니처 `-> Response`는 동일. Blueprint endpoint명이 `admin.timetable_recrawl`로 변경됨. 영향 없음 (테스트는 URL 직접 사용). PASS_NOTE로 기록.
- **네트워크 격리 확인**: `_get_crawl_job()` → `config.get("_TIMETABLE_CRAWL_JOB")` mock 우선; `_make_crawl_fn()` 내 UlsanBisClient/crawl_all_timetables import는 closure 실행 시에만 발생. 테스트에서 실제 네트워크 호출 없음.
- **S5 CSRF 배선**: `timetable_edit.html`에 두 개의 CSRF hidden(`csrf_token`) 포함 — 시간표 저장 폼(line 32)과 재크롤 폼(line 87). before_request에서 전부 커버.
- **Designer 정정(TP-009 §4 weekday 키)**: 숫자 키 `"0"/"1"/"2"` 구현이 2026-06-02 사후 정정과 일치. `_WEEKDAY_TABS = [("0","평일"),("1","토요일"),("2","일·공휴일")]` 확인.
