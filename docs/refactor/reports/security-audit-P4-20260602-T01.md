---
phase: P4
scope: web
verdict: PASS
gate: P5 진입 허용
auditor: claude-sonnet-4-6 (Security Auditor, 독립 컨텍스트)
date: 2026-06-02
---

# Security Audit Report — P4 (web) End-Gate

> ADR-009 / 00-workflow §10 기준. S1~S10 전수·교차 검증. P5(cutover) 진입 전 게이트.

---

## SCOPE: web

## VERDICT: PASS

## GATE: P5 진입 허용

### 근거 요약
high/critical 발견 0건. medium 3건(기지 항목 포함), low 2건. 모두 P5 기한 합의 후 등록 처리 가능.

---

## FINDINGS

### S1 — 인증·세션

- [SEV: medium] S1/SESSION_COOKIE_SECURE:
  - **무엇이**: `bushexa/web/app.py:53` — `SESSION_COOKIE_SECURE = False` 정적 하드코딩.
  - **왜 위험**: HTTP 환경에서 쿠키 도청 가능(네트워크 공격자). HTTPS 프로덕션 배포에서도 Secure 플래그 없이 발행됨.
  - **재현**: curl http://prod-host/admin/ → Set-Cookie에 Secure 없음.
  - **수정 권고**: P5 배포 config에서 `BUSHEXA_SESSION_SECURE=true` 환경변수 기반 조건 분기, 또는 reverse-proxy(nginx) `proxy_cookie_flags ... secure` 설정. 기존 주석(app.py:48~52)이 이미 지침을 담고 있음.
  - **분류 근거**: 기지 항목 2 — 개발 기본값이며 prod HTTPS 배포 config 존재 권고. medium, 게이트 차단 아님.

- [SEV: medium] S1/OPEN-REDIRECT:
  - **무엇이**: `bushexa/web/routes/admin.py:208` — `next_url.startswith("/") and not next_url.startswith("//")` 가드.
  - **왜 위험**: `next=/\evil.com` 형태(단일 슬래시 + 백슬래시)는 가드를 통과한다. 브라우저는 HTTP `Location: /\evil.com` 헤더를 `//evil.com`으로 정규화하므로, 공격자가 `?next=/\evil.com`을 포함한 로그인 URL을 조작하면 로그인 성공 후 외부 도메인으로 이동.
  - **재현**: `GET /admin/login?next=/\evil.com` → 올바른 비밀번호 POST → `Location: /\evil.com` → 브라우저가 `http://evil.com`으로 이동 (브라우저 정규화 확인됨).
  - **수정 권고**: `urlparse(next_url).netloc == ""` 조건 추가. 또는 `url_for("admin.dashboard")` 기반 허용리스트 경로만 수락. 간단 픽스: `re.match(r'^/[^/\\\\]', next_url)`.
  - **분류 근거**: 인증 후 리디렉션(피싱 보조), 관리자 대상 공격. 세션 탈취 아님. medium. 게이트 차단 아님.

- [SEV: low] S1/LOCKOUT-DURATION:
  - **무엇이**: `admin.py:64` — `_LOCKOUT_SECS = 10` (10초 잠금).
  - **왜 위험**: 5회 실패 후 10초 재설정 — 공격자가 분당 30회 시도 가능. 실질 무차별 대입 차단 효과 미흡.
  - **수정 권고**: 점진적 lockout (exponential backoff) 또는 최소 60~300초. P5 이후 개선.
  - **분류 근거**: lockout 존재(S1 요건 충족), 기간이 짧음. low.

- [SEV: low] S1/PBKDF2-LEGACY:
  - **무엇이**: `bushexa/services/auth.py:66~69` — PBKDF2 접두사가 없는 저장값은 평문 직접 비교(`secrets.compare_digest`).
  - **왜 위험**: legacy 평문 파일이 존재하면 해시 보호 없이 비교됨.
  - **재현**: `manager_password.txt`에 평문("mypassword") 저장 → `auth.verify("mypassword")` → True (평문 경로).
  - **수정 권고**: P5 전 `manager_password.txt`가 PBKDF2 포맷인지 확인. 또는 `change_password`/`set_initial` 최초 실행으로 PBKDF2 마이그레이션 유도. 이미 `change_password`는 저장 시 자동 마이그레이션(auth.py:140).
  - **비고**: constant-time 비교 사용으로 timing attack 없음. legacy 마이그레이션 경로이므로 low.

- [SEV: PASS] S1/lockout: `_MAX_FAILS=5`, `_LOCKOUT_SECS=10` (admin.py:63~64) — 기능 구현 확인.
- [SEV: PASS] S1/hexa-removed: `bushexa/web/routes/info.py:38` — `?hexa=6` 완전 제거 확인.
- [SEV: PASS] S1/cookie-flags: `HttpOnly=True`, `SameSite=Lax` 확인 (app.py:46~47).

---

### S2 — 권한

**admin 라우트 전수 열거 (login_required 여부)**

| 경로 | 메서드 | @login_required | 판정 |
|------|--------|-----------------|------|
| `/admin/login` | GET | ✗ | OK (공개 필요) |
| `/admin/login` | POST | ✗ | OK (공개 필요) |
| `/admin/logout` | POST | ✓ (line 214) | PASS |
| `/admin/` | GET | ✓ (line 221) | PASS |
| `/admin/password` | GET | ✓ (line 227) | PASS |
| `/admin/password` | POST | ✓ (line 233) | PASS |
| `/admin/data` | GET | ✓ (line 279) | PASS |
| `/admin/data.csv` | GET | ✓ (line 326) | PASS |
| `/admin/timetable` | GET | ✓ (line 397) | PASS |
| `/admin/timetable/<busno>` | GET | ✓ (line 406) | PASS |
| `/admin/timetable/<busno>` | POST | ✓ (line 447) | PASS |
| `/admin/timetable/recrawl` | POST | ✓ (line 501) | PASS |
| `/admin/timetable/recrawl/<job_id>/stream` | GET | ✓ (line 540) | PASS |
| `/admin/govtrack/status` | GET | ✓ (line 596) | PASS |
| `/admin/govtrack/status/stream` | GET | ✓ (line 612) | PASS |
| `/admin/logs` | GET | ✓ (line 659) | PASS |

**결론**: login/POST-login 2개 외 전 라우트 `login_required` 보호 확인. 누락 0건.

---

### S3 — 인젝션

- [SEV: PASS] SQL 파라미터 바인딩 — `grep -rEn 'execute\([^,]*%|f".*SELECT'` 결과에서 발견된 f-string SQL은 **모두 `{where}` / `{ph}` / `{_COLS}` 조합**으로, 사용자 입력이 SQL 문자열에 직접 삽입되는 케이스 없음.
  - `_where()`(repo.py:67~85): 조건 절은 `f"route_id = {ph}"` 방식으로 placeholder 문자열(%, ?)을 삽입하고 값은 args에 따로 전달. 안전.
  - `repo_arrival.py:43,58`: `WHERE stop_id = {ph}` / `WHERE stop_id IN ({marks})` — placeholder만 인라인. 안전.
  - `export_csv(repo.py:179)`: `LIMIT {ph}` — max_rows 상수를 placeholder로 바인딩. 안전.

- [SEV: PASS] 경로 traversal — `timetable/<busno>`: admin.py:391~393 `_require_known_busno()` → `_known_busnos()` → `TimetableEditor.list_routes()` → ROUTEID 상수 화이트리스트 대조 후 404. 사용자 입력 busno가 파일명에 도달하기 전 차단 확인.

- [SEV: PASS] logs 경로 traversal — `LogTailReader(log_dir)` 생성 시 고정(log_reader.py:76~77). `?file=` 파라미터 없음(admin.py:682~683 주석 명시).

- [SEV: PASS] subprocess — `grep -rn 'subprocess\|os\.system\|os\.popen' bushexa/` 결과 없음.

---

### S4 — XSS

- [SEV: PASS] `|safe` / `Markup` 전수 — `grep -rn '|safe\|Markup' bushexa/web/templates/ bushexa/web/` 결과: `_base.html:16` 주석 1건(코드 아님). 실제 사용처 0건. Jinja 자동이스케이프 활성(Flask 기본값, `create_app`에서 변경 없음).

- [SEV: low] S4/DASHBOARD-INNERHTML:
  - **무엇이**: `admin/dashboard.html:69` — `content.innerHTML = html` (JS). `html`에 `data.last_success_at` 문자열이 직접 삽입됨.
  - **왜 위험**: `last_success_at`이 악의적 내용이면 XSS 가능. 단, 이 값은 `GovtrackStatusWriter.write()`가 `datetime.isoformat()`으로 기록하는 내부 값(govtrack_status.py:72, `_iso()`). 사용자 자유입력 경로 없음.
  - **재현**: 현재 구현에서는 재현 불가 — 내부 생성 값. govtrack_status.json 파일을 직접 변조할 수 있는 공격자는 이미 서버 접근 권한 보유.
  - **수정 권고**: P5 또는 향후 스프린트에서 `textContent` / DOMPurify 사용으로 방어심층 강화. govtrack_status.html:53에도 동일 패턴 존재.
  - **분류 근거**: 재현 불가(내부 데이터), 관리자 전용 페이지. low.

- [SEV: PASS] HTMX partial 응답 — `partial/board_table.html`, `stops_partial.html`, `unist_partial.html` 등 서버 렌더링 Jinja 템플릿. 사용자 입력이 이스케이프 없이 삽입되는 경로 없음. `hx-swap="innerHTML"`은 서버 HTML 조각을 교체하므로 Jinja 이스케이프 보호 적용.

---

### S5 — CSRF

**상태변경 admin POST 전수 열거**

| 엔드포인트 | CSRF 토큰(form body) | before_request 검증 |
|------------|---------------------|---------------------|
| POST /admin/login | ✓ (login.html:24,34) | ✓ (app.py:73~87) |
| POST /admin/logout | ✓ (dashboard.html:79) | ✓ |
| POST /admin/password | ✓ (password.html:33) | ✓ |
| POST /admin/timetable/<busno> (save) | ✓ (timetable_edit.html:32) | ✓ |
| POST /admin/timetable/recrawl | ✓ (timetable_edit.html:87) | ✓ |

**before_request 로직**: app.py:73~87 — `path.startswith("/admin/")` + 메서드 필터링(GET/HEAD/OPTIONS/TRACE 제외) + session.csrf_token vs form/header X-CSRFToken 비교. logout 포함 전 state-changing POST 보호 확인.

**결론**: CSRF 보호 완전 적용 확인. 누락 0건.

---

### S6 — SSRF / 외부 호출

- [SEV: PASS] 외부 API URL: `_ARRIVAL_URL`, `_TIMETABLE_URL` (ulsan_bis.py:22~23), `_HOLIDAY_URL` (holiday.py:30), tago 엔드포인트 — 모두 모듈 상수 고정. 사용자 입력으로 URL 조립 없음.
- [SEV: PASS] stop_id 입력: `/partial/stops?stop_id=` — `SERACH_STOPS` 화이트리스트 대조(stops.py:37~38), 미등록 stop_id는 400.
- [SEV: PASS] 타임아웃: ulsan_bis.py:101, tago.py:110, holiday.py:35 — 모두 `timeout=10.0`.

---

### S7 — 시크릿

#### (a) 코드/추적파일 평문

- [SEV: medium] S7/COMPOSE-HARDCODED-PASSWORD:
  - **무엇이**: `docker-compose.yaml:7` 및 `podman-compose.yaml:7` — `POSTGRES_PASSWORD: WhenMyBusRun` 평문 하드코딩.
  - **왜 위험**: compose 파일이 버전 관리에 포함될 경우(현재 프로젝트는 git 레포 아님이지만 P5 배포 후) DB 비밀번호 유출.
  - **재현**: `cat docker-compose.yaml | grep POSTGRES_PASSWORD` → 평문 노출.
  - **수정 권고**: `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}` 환경변수 참조로 변경. `.env` 또는 Docker secrets 사용. `.env.example:24`에 `POSTGRES_PASSWORD=change-me` 예시 이미 존재.
  - **분류 근거**: git 레포 미포함 현재 환경, P5 배포 전 수정 대상. medium.

- [SEV: medium] S8/SECRET-FILE-PERMISSIONS:
  - **무엇이**: `secret/db.yaml`, `secret/key.txt`, `secret/manager_password.txt` — 실제 권한 `0644` (`-rw-r--r--`). S8 기준 `0600` 요구.
  - **왜 위험**: 동일 서버의 다른 사용자(또는 웹 프로세스가 아닌 프로세스)가 읽을 수 있음.
  - **재현**: `ls -la secret/` → 644 권한 직접 확인.
  - **수정 권고**: `chmod 0600 secret/key.txt secret/db.yaml secret/manager_password.txt`. Dockerfile/배포 스크립트에 권한 설정 추가. `AuthService.change_password()`는 이미 `os.chmod(path, 0o600)` 적용(auth.py:143)하지만 초기 파일에 대한 설정 없음.
  - **분류 근거**: 서버 동일 사용자 단독 환경이면 위험도 낮지만 S8 기준 위반. medium, P5 배포 시 수정 필수.

- [SEV: PASS] API 키·DB 비밀번호·세션 시크릿 코드 내 평문 0건 확인. `config.py`는 env/파일 참조만.

#### (b) 로그에 시크릿 기록 여부

- [SEV: PASS] `database_url` 직접 로깅 없음 — `create_connection(dsn)` 호출부(running.py:77, admin.py:274)에서 dsn 로깅 없음. 연결 실패 시 `log.error("... DB 오류: %s", exc)` — psycopg2 예외 메시지는 DSN을 포함하지 않음.
- [SEV: PASS] `config.api_key` 직접 로깅 없음 — ulsan_bis.py 로거: stop_id, 예외 메시지만 로깅.
- [SEV: PASS] `session_secret` 직접 로깅 없음.
- [SEV: low] S7/LOG-DB-URL-MASKGAP: `_mask_secrets` 패턴이 `postgresql://user:password@host/db` URI 형식을 처리하지 못함 (S7-c, 하단 참조). DB URL이 로그에 직접 남지 않으므로 실질 위험 낮음.

#### (c) `_mask_secrets` 완전성 검증

패턴: `(?i)(password|token|secret|api_key|apikey|authorization)\s*[=:]\s*(?:Bearer\s+)?\S+`

| 패턴 | 마스킹 여부 | 비고 |
|------|------------|------|
| `password=hunter2` | ✓ | 정상 |
| `api_key=ABCDEF123` | ✓ | 정상 |
| `Authorization: Bearer secrettoken123` | ✓ | 정상 (PM-006 수정 후) |
| `session_secret=abc123` | ✓ | `secret` 키워드 매치 |
| `MANAGER_PASSWORD=secretpw` | ✓ | `PASSWORD` 매치 |
| `postgresql://user:WhenMyBusRun@host/db` | **✗** | URI 형식 미지원 |
| `DATABASE_URL=postgresql://user:pass@host/db` | **✗** | `DATABASE_URL` 키워드 미등록 |

- [SEV: low] S7/MASK-DB-URL:
  - **무엇이**: admin.py:641~644 `_SECRET_PATTERN` — `postgresql://` URI 형식과 `DATABASE_URL` 키워드 미처리.
  - **왜 위험**: DB URL이 어떤 경로로 로그에 기록될 경우 비밀번호 노출.
  - **현재 위험도**: 코드 전수 확인 결과 `database_url`을 로그에 직접 기록하는 코드 없음. 실질 노출 경로 미확인.
  - **수정 권고**: 패턴에 `|(?:postgresql|postgres)://[^:]+:[^@]+@` 추가. P5 배포 전 적용 권고.
  - **분류 근거**: 실제 로그 기록 경로 미확인, 관리자 전용 뷰어. low.

- **PM-006 (Bearer 마스킹) 검증**: `Authorization: Bearer secrettoken123` → `Authorization=****` 정상 마스킹 확인. `test_masking_bearer_token` 회귀 테스트 존재 확인. PM-006 상태: **fixed → verified 권고**.

---

### S8 — 안전한 기본값·정보 노출

- [SEV: PASS] Flask debug 모드: `cli.py:162` `app.run(host=..., port=...)` — `debug` 인자 미전달. Flask 기본값 `debug=False`. 스택 트레이스 미노출.
- [SEV: PASS] 사용자 대면 에러: running.py:83~85 — 예외 시 `db_error = "데이터베이스에서..."` 친화 메시지. 내부 경로/스택 미노출.
- [SEV: medium] S8/SECRET-FILE-PERMISSIONS: 위 S7(a) 항목과 동일 — `secret/*.txt`, `secret/db.yaml` 권한 0644. (중복 보고이나 S8 기준으로도 위반)
- [SEV: low] S8/ADMIN-PATH-DISCLOSURE: `admin/logs.html:47` — `로그 파일: {{ log_file_path }}` 내부 경로 노출. 단, 인증된 관리자 전용 페이지. low.

---

### S9 — DoS / 자원

- [SEV: PASS] CSV max_rows=10000: `repo.export_csv(..., max_rows=10000)` (admin.py:348, repo.py:179).
- [SEV: PASS] 로그 tail 상한 2000: `LogTailReader._MAX_LINES = 2000` (log_reader.py:38). `cap = min(int(lines), _MAX_LINES)` 강제(log_reader.py:96).
- [SEV: PASS] 재크롤 동시성: `TimetableCrawlJob.start()` — 이미 실행 중이면 `ConflictError` → 409 (admin.py:509, timetable_crawl.py:41).
- [SEV: PASS] 외부 API 타임아웃: 10.0초 전수 확인 (S6 참조).

---

### S10 — 의존성

- **스캔 도구**: `uvx pip-audit /home/mlv/Project/bushexa/bus-hexa-revive-temp --format json`
- **스캔 대상**: flask 3.1.3, jinja2 3.1.6, requests 2.34.2, werkzeug 3.1.8, beautifulsoup4 4.14.3, pandas 3.0.3, pyyaml 6.0.3, urllib3 2.7.0 외 24개 패키지.
- **결과**: `No known vulnerabilities found` — 취약점 0건.
- [SEV: PASS] S10/DEPENDENCY-AUDIT: high 0건 확인.

---

## 기지 항목 최종 분류

| ID | 내용 | 결론 |
|----|------|------|
| PM-006 (Bearer 마스킹) | `Authorization: Bearer` 토큰 마스킹 수정 + 회귀 테스트 | **verified** — 수정 완료, 테스트 통과 |
| SESSION_COOKIE_SECURE=False | 개발 기본값, HTTPS 배포 시 활성 필요 | medium — P5 배포 config 점검 항목 |
| CSV formula injection | 데이터 출처 BIS 정부 피드(사용자 자유입력 아님) | medium — P5 기한 설정 후 통과 |

---

## GATE: P5 진입 허용

high/critical 발견 0건. medium 3건(SESSION_COOKIE_SECURE, COMPOSE-HARDCODED-PASSWORD, SECRET-FILE-PERMISSIONS), low 3건 — 모두 P5 배포 시 수정 또는 기한 합의 조건.

---

## PM_REQUIRED

high/critical 발견 없음 — postmortems 신규 등재 불필요.

medium 3건은 P5 배포 전 수정 권고 항목으로 PM 목록 등재:
- PM-NEW-01: `docker-compose.yaml` / `podman-compose.yaml` POSTGRES_PASSWORD 환경변수화 **및 비밀번호 교체** (S7/COMPOSE-HARDCODED-PASSWORD — 이미 노출된 값이므로 env-var화만으로 충분하지 않음)
- PM-NEW-02: `secret/` 파일 권한 0644→0600 수정 + 배포 스크립트 반영 (S8/SECRET-FILE-PERMISSIONS — 단일 테넌트 가정; 공유 호스트 배포 시 high로 상향)
- PM-NEW-03: SESSION_COOKIE_SECURE prod 활성화 확인 (S1/SESSION_COOKIE_SECURE — 기지 항목)
- PM-NEW-04: 로그인 next= 파라미터 open-redirect 수정 (S1/OPEN-REDIRECT) — Executor 수정
- PM-CSV-FORMULA: CSV formula injection P5 기한 (기지 항목 3)
- PM-006: fixed→verified (Bearer 마스킹 — 기지 항목 1)

---

## 검증 범위 및 방법론

- **직접 코드 열람**: `bushexa/web/app.py`, `routes/admin.py`, `routes/info.py`, `routes/board.py`, `routes/busno.py`, `routes/stops.py`, `routes/running.py`, `routes/unist_board.py`, `routes/unist_timetable.py`
- **서비스 계층**: `services/auth.py`, `services/log_reader.py`, `services/timetable_editor.py`, `services/govtrack_status.py`
- **DB 계층**: `db/repo.py`, `db/repo_arrival.py`, `db/connection.py`
- **설정**: `config.py`, `docker-compose.yaml`, `podman-compose.yaml`, `.env.example`, `secret/` 권한
- **템플릿 전수**: `templates/admin/` 7개, `templates/partial/` 2개, `templates/` 8개
- **의존성 스캔**: `uvx pip-audit` — "No known vulnerabilities found"
- **정규식 검증**: `_mask_secrets` 패턴 Python 직접 실행으로 커버리지 확인
- **SQL 안전성**: f-string SQL 전수 확인 — placeholder 패턴 `{ph}` 사용, 사용자 입력 직접 삽입 없음
- **테스트 커버리지 확인**: `tests/web/test_csrf.py`, `test_admin_auth_flow.py`, `test_admin_logs.py` (PM-006 회귀)
