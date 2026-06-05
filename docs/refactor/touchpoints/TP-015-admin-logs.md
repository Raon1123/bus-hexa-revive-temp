---
status: implemented
touchpoint_id: TP-015
actor: 관리자
surface: admin
location: "GET /admin/logs"
related_feature: F04
auditor_status: pending
last_updated: 2026-06-02
implemented_by: P4/W16
---

# TP-015 — 관리자가 애플리케이션 로그를 브라우저에서 조회한다

> feature: F04 §4.6, phase: P4/W16 (LogTailReader 위임, depends W1/W9).

## 1. 맥락

- **누가 (actor):** 인증된 관리자
- **언제·왜:** 운영 중 오류 발생 의심 시, govtrack 데몬 하트비트·크롤러 예외 로그를 직접 확인하려 할 때.
- **위치 (surface/location):** `GET /admin/logs` + 쿼리 `?level=&lines=`
- **사전 상태 (precondition):** `login_required`. `logging_setup.setup_logging(log_dir=config.log_dir)`이 호출되어 `logs/bushexa.log`가 적재되고 있어야 함.

## 2. 인터랙션 흐름 (Happy Path)

| # | 사람의 행동 | 시스템의 정확한 반응 | 화면/상태 변화 |
|---|---|---|---|
| 1 | `/admin/logs` 접속 | `LogTailReader(config.log_dir).tail(lines=200)` 호출 후 렌더 | 최근 200줄 역순 표시 |
| 2 | `?level=ERROR` 선택 후 필터 버튼 클릭 | level="ERROR" 이상만 필터 후 재렌더 | ERROR/CRITICAL 줄만 표시 |
| 3 | `?lines=50` 입력 후 필터 적용 | tail(lines=50) 호출 (2000 상한 적용) | 최근 50줄 표시 |

## 3. 화면/상태 목업 (ASCII)

```text
┌─ 애플리케이션 로그 ──────────────────────────────────────────────────┐
│ 레벨: [INFO 이상 ▼]   줄 수: [200___]  [필터 적용]                   │
│ 로그 파일: /home/mlv/.../logs/bushexa.log | 표시: 35줄 (최신 순)      │
├──────────────────┬────────────────────┬──────┬───────────────────────┤
│ 시각             │ 로거               │ 레벨 │ 메시지                │
├──────────────────┼────────────────────┼──────┼───────────────────────┤
│ 2026-06-01T…     │ bushexa.crawler    │ INFO │ cycle started         │
│ 2026-06-01T…     │ bushexa.crawler    │ ERROR│ API timeout           │
└──────────────────┴────────────────────┴──────┴───────────────────────┘

(로그 파일 없을 때)
┌────────────────────────────────────────┐
│ 로그 파일이 아직 없습니다.             │
└────────────────────────────────────────┘
```

## 4. 입력 사양

| 입력 | 형식/제약 | 필수 | 기본값 | 검증 시점 |
|---|---|---|---|---|
| `?level` | 표준 레벨 화이트리스트(DEBUG/INFO/WARNING/ERROR/CRITICAL), 그 외 무시→None(전체) | N | None(전체) | server |
| `?lines` | 정수, 1≤lines≤2000 (LogTailReader가 상한 강제) | N | 200 | server |
| `?file` | **무시됨** — 경로 파라미터를 받지 않음 (path traversal 차단, S3) | — | — | server |

## 5. 피드백 규약

- **로딩:** 페이지 로드로 즉시 표시.
- **성공:** 로그 라인 표 (레벨별 색상 CSS 클래스).
- **에러/빈 상태:** 파일 미존재 → "로그 파일이 아직 없습니다." (500 아님).
- **시크릿 마스킹(S7):** `password=`, `token=`, `secret=`, `api_key=`, `authorization=` 패턴을 `****`로 마스킹 후 표출.

## 6. 분기 (성공/실패/엣지)

| 조건 | 시스템 반응 | 사용자에게 보이는 것 |
|---|---|---|
| 로그 파일 존재 | tail(N) 역순 파싱 후 렌더 | 최신 순 로그 표 |
| 파일 미존재 | 빈 목록 반환, 200 | "로그 파일이 아직 없습니다." |
| level 비표준값 | None으로 처리 (전체 반환) | 전체 로그 표시 |
| lines > 2000 | 2000으로 clamp | 2000줄까지만 표시 |
| ?file 주입 시도 | 무시, config.log_dir/bushexa.log만 읽음 | 공격 무시, 정상 페이지 |
| 비로그인 접근 | 302 `/admin/login` | 로그인 페이지 |

## 7. 접근성·키보드

- 필터 폼은 `<select>` + `<input>` + `<button>` — 키보드 작동.
- 테이블 헤더 `<th>` 로 스크린리더 컬럼 식별 가능.

## 8. 자동 갱신/실시간

- MVP: 자동 갱신 없음 (수동 필터 적용으로 재로드).
- 선택 (`/admin/logs/stream` SSE): MVP 이후 미구현 — **Designer 확인 필요** 항목으로 보고.

## 9. Acceptance (W16 AC 재인용)

- [ ] AC-1: 비로그인 `GET /admin/logs` → 302 `/admin/login` (검증: `tests/web/test_admin_logs.py::test_requires_login`)
- [ ] AC-2: `LogTailReader.tail`이 최신순·level 필터·`lines`≤2000·파일부재 빈목록을 만족한다 (검증: `tests/services/test_log_reader.py`)
- [ ] AC-L4: 로그 파일 부재 시 500 아닌 200 + "로그 파일이 아직 없습니다" (검증: `tests/web/test_admin_logs.py::test_logs_missing_file_returns_empty_notice`)
- [ ] AC-L5: path traversal(`?file=../../secret/key.txt`) 차단 — 고정 경로만 읽음 (검증: `tests/web/test_admin_logs.py::test_uses_fixed_path`)

## 10. 관련 touch point / feature

- feature: F04 §4.6
- 인접 TP: [[TP-011]] (govtrack status SSE), [[TP-007]] (관리자 로그인 — login_required 공유)
- 의존: W16 `bushexa/services/log_reader.py`(`LogTailReader`), `bushexa/config.py`(`log_dir` 필드)
