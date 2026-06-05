---
phase: P5
auditor: claude-sonnet-4-6 (Auditor, fresh independent context)
date: 2026-06-02
time: 11:30
verdict: PASS
scope: W1, W2, W3, W4, W5, W7, W8 (W6 DEFERRED — correctly not done)
---

# Execution Audit Report — P5 (Security Gate + Deployment + Cutover)

> Applies `execution-audit-criteria.md` E-1 ~ E-13. W6 (legacy cutover) was intentionally
> deferred per P5 plan dependency (gated on W5 operator dry-run + R1 one-week monitor) —
> this audit does NOT fail W6 absence; it verifies the absence is correct.

---

## VERDICT: PASS

**FAIL_REASONS:** none that block the phase.
**RECORDED CONDITIONS** (must be resolved before cutover):
- CONDITION-1: Operator must run `bash scripts/smoke_compose.sh` with real API key + postgres (EC-3/4/5 operator-pending).
- CONDITION-2: Operator must rotate the postgres password away from the legacy `WhenMyBusRun` value (PM-NEW-01).
- CONDITION-3: Operator must `chmod 0600 secret/*.txt secret/db.yaml` on the live host (PM-NEW-02); AuthService sets 0600 on write, but existing files need manual chmod.
- CONDITION-4 (Executor follow-up, non-blocking): `test_no_plaintext_secret` scans `docker/*.py` only — the YAML files in `docker/` are not covered. Widen `rglob("*.py")` to also cover `*.yaml`/`*.yml` so future compose changes are regression-guarded.

---

## Per Work-Item Results

### W1 — 보안 감리 게이트

**AC-1: PASS**
- Evidence: `docs/refactor/reports/security-audit-P4-20260602-T01.md` exists with `## S1` through `## S10` headers — all ten categories present.
- Command: `grep -E '^### S[0-9]+' docs/refactor/reports/security-audit-P4-20260602-T01.md` → S1, S2, S3, S4, S5, S6, S7, S8, S9, S10 all returned.

**AC-2: PASS**
- Evidence: Report front-matter `gate: P5 진입 허용`, `verdict: PASS`. Body: "high/critical 발견 0건" (line 23). Medium/low findings are all documented and none are high or critical.
- Note: The security gate report pre-dates P5 execution (audited at P4 end) — P5 W1 work sealed the medium items (SESSION_COOKIE_SECURE, CSV injection, compose password) with code changes, not just documentation.

**W1 security sealing verification:**

*CSV formula injection (`bushexa/db/repo.py`):*
- `_CSV_INJECTION_CHARS = ("=", "+", "-", "@", "\t", "\r")` defined at line 25.
- `_sanitize_csv_cell()` at lines 28–39: prepends `'` when `s[0] in _CSV_INJECTION_CHARS`. Correct.
- `export_csv()` at line 200: `",".join(_sanitize_csv_cell(v) for v in r)` — every cell in every row is sanitized. Correct.

*SESSION_COOKIE_SECURE (`bushexa/config.py` + `bushexa/web/app.py`):*
- `config.py` line 66: `session_cookie_secure: bool = False` (dataclass field with env-driven default).
- `config.py` lines 116–117: `environ.get("BUSHEXA_SESSION_COOKIE_SECURE", "").lower() in {"1", "true", "yes", "on"}`.
- `app.py` line 52: `app.config["SESSION_COOKIE_SECURE"] = config.session_cookie_secure` — NOT hardcoded False.
- Result: fully env-driven. PASS.

*Secret 0600 regression tests:*
- `tests/services/test_auth.py:257 test_set_initial_secret_file_is_0600` — PASS (run confirmed).
- `tests/services/test_auth.py:273 test_change_password_secret_file_is_0600` — PASS (run confirmed).

*No-plaintext-secret test (W1 spec `! grep -rn 'WhenMyBusRun' bushexa/ docker/`):*
- Command exit 0: no match in `bushexa/` or `docker/` directories.
- `docker/compose.yaml` uses `${POSTGRES_PASSWORD}` only (grep `PASSWORD: [^$]` exit 1).

**E-9 FINDING (test_no_plaintext_secret coverage gap):**
The P-11 intent is "코드·compose에 평문 비밀번호가 0건인지 검증 (S7)". The test docstring claims to scan `docker/` directory. However the implementation at line 41 uses `docker_dir.rglob("*.py")` — which matches **zero files** in `docker/` (which contains only `Dockerfile`, `compose.yaml`, `compose.dev.yaml`). The "compose" half of the test is currently vacuous; it would not catch a future plaintext password in `docker/compose.yaml` or `docker/compose.dev.yaml`. The current security property is verified by the independent grep command above, so the AC is met. However, the test does not reliably guard the future regression. Recorded as Condition-4 (Executor follow-up).

**Full suite:** `uv run pytest -q` → **212 passed, 0 failed, 0 errors**. Verified.

---

### W2 — docker/Dockerfile

**AC-1: PASS**
- Evidence: `docker images bushexa:test --format '{{.Size}}'` → `429MB`. Build was previously completed; the audit inspects the existing image rather than re-running the build. Dockerfile confirmed to use `python:3.12-slim-bookworm` (line 15), uv binary copied from `ghcr.io/astral-sh/uv:latest` (line 25), non-root user `app` created (line 31), `ENTRYPOINT ["uv", "run", "bushexa"]` (line 63).

**AC-2: PASS**
- Evidence: `429MB < 500MB` threshold. PASS.

**Additional checks:**
- `.dockerignore` excludes `secret/` (line 9) and `postgres-data/` (line 12). Confirmed.
- `ENV TZ=Asia/Seoul` present (line 28). PASS.
- Non-root user switched via `USER app` (line 61). PASS.

---

### W3 — docker/compose.yaml

**AC-1: PASS**
- `docker compose -f docker/compose.yaml config` → exit 0 (warnings about unset env vars are expected without a live `.env`; no parse errors).
- `grep -E 'PASSWORD: [^$]' docker/compose.yaml` → exit 1 (no matches). All password references use `${POSTGRES_PASSWORD}` interpolation. Plaintext 0건.

**AC-2: PASS**
- `grep -n 'crawl-loop\|arrival-loop' docker/compose.yaml` → line 45: `command: ["crawl-loop"]` (worker-govtrack service), line 64: `command: ["arrival-loop"]` (worker-arrival service).
- Two separate worker services per ADR-010 Q3 (independent error domains). Both present.

**Port mapping:** `8017:8000` confirmed at line 29. Host 8017 → container 8000. PASS.
**env_file:** `../.env` present in web, worker-govtrack, worker-arrival services.
**postgres healthcheck:** `pg_isready` healthcheck with interval/timeout/retries present (lines 89–93).
**restart: always:** present in web, worker-govtrack, worker-arrival, postgres services.

---

### W4 — docker/compose.dev.yaml

**AC-1: PASS**
- `docker compose -f docker/compose.yaml -f docker/compose.dev.yaml config` → exit 0.

**AC-2: PASS**
- `grep -E 'bushexa:/app|DEBUG' docker/compose.dev.yaml`:
  - `../bushexa:/app/bushexa` bind-mount present in web, worker-govtrack, worker-arrival services (3 occurrences).
  - `BUSHEXA_LOG_LEVEL: DEBUG` present in all three services.
- `DATABASE_URL: sqlite:///./data/bushexa.db` present in all three services — postgres-free dev path confirmed.

---

### W5 — scripts/smoke_compose.sh

**Deliverable checks:**
- `bash -n scripts/smoke_compose.sh` → exit 0 (syntax clean). PASS.
- `ls -la scripts/smoke_compose.sh` → `-rwxrwxr-x` — executable bit set. PASS.

**Script logic:**
1. Brings up postgres, waits for healthcheck, runs `init-db`, brings up all services.
2. Waits 15 seconds (configurable via `WAIT_SECS`).
3. `curl -sf http://localhost:${WEB_PORT}/board` for `/board` 200 check.
4. `curl -sf http://localhost:${WEB_PORT}/admin/login` for `/admin/login` 200 check.
5. Live-feed check (CycleStats + arrival upsert) gated behind `SMOKE_SKIP_FEED` env var.
6. `cleanup()` trap runs `docker compose down` on exit (both success and failure).

**AC-1 (exit 0 with /board 200) — OPERATOR-PENDING.**
**AC-2 (worker logs CycleStats + arrival) — OPERATOR-PENDING.**

Both ACs require a live stack with real `BUSHEXA_API_KEY` + postgres. Neither was claimed as locally-passed by the executor. The script explicitly documents this boundary (header comment lines 7–8, 17–19; code line 90 "OPERATOR 영역"). No fabricated green smoke was found anywhere in the report set.

---

### W6 — legacy cutover (DEFERRED — verified correct)

**Legacy files confirmed still at repo root:**
- `app.py` EXISTS
- `infopages/` EXISTS
- `src/` EXISTS
- `crawl/` EXISTS
- `docker-compose.yaml` EXISTS
- `podman-compose.yaml` EXISTS

W6 is intentionally not done. Per P5 §4/§7, W6 depends on W5 operator dry-run passing + R1 one-week monitor. These gates are not yet cleared. **Absence of W6 is correct and is NOT a failure.**

---

### W7 — README.md

**AC-1: PASS**
- `grep -c '^## ' README.md` → `8`
- Sections: `## About`, `## Quick start (uv)`, `## Configuration (.env)`, `## Local development`, `## Docker deployment (podman/docker-compose)`, `## Architecture`, `## Troubleshooting`, `## Tests`.
- All 8 required sections present. PASS.
- `uv` command count: 26 occurrences. Well exceeds ≥5 threshold. PASS.

---

### W8 — docs/refactor/migration-notes.md + .env.example

**AC-1: PASS**
- `grep -c '^## ' docs/refactor/migration-notes.md` → `5`
- Sections: `## cutover 전 백업`, `## .env 작성 가이드`, `## cutover 5단계`, `## 롤백 절차`, `## 사후 모니터 체크리스트`. All 5 required sections present. PASS.

**.env.example:**
- File exists at `/home/mlv/Project/bushexa/bus-hexa-revive-temp/.env.example`.
- `grep 'WhenMyBusRun' .env.example` → exit 1 (not found). No real password.
- All values are dummy (e.g., `POSTGRES_PASSWORD=changeme`, `BUSHEXA_API_KEY=your-public-data-api-key`). PASS.
- `BUSHEXA_SESSION_COOKIE_SECURE=false` documented with HTTPS upgrade note. PASS.

---

## EC Coverage Table

| EC | 내용 | Work Item AC | 판정 | 비고 |
|----|------|-------------|------|------|
| EC-1 | 보안 게이트 high/critical 0 | W1 AC-1, AC-2 | **PASS** | report exists, S1–S10 covered, gate 허용 |
| EC-2 | 이미지 빌드·크기 <500MB | W2 AC-1, AC-2 | **PASS** | 429MB, python:3.12-slim-bookworm |
| EC-3 | compose 기동 | W3 AC-1, AC-2 | **OPERATOR-PENDING** | compose config exit 0; live stack requires postgres |
| EC-4 | /board HTTP 200 | W5 AC-1 | **OPERATOR-PENDING** | script ready; live run requires API key + postgres |
| EC-5 | worker logs CycleStats + arrival | W3 AC-2; W5 AC-2 | **OPERATOR-PENDING** | script ready; live run requires real BIS network |
| EC-6 | legacy cutover | W6 AC-1, AC-2 | **DEFERRED (correct)** | gated on W5 dry-run + 1-week monitor |
| EC-7 | README + migration notes | W7 AC-1; W8 AC-1 | **PASS** | 8 sections README, 5 sections migration-notes |

---

## Operator-Pending Boundary — Honestly Reported? **YES**

Evidence:
1. `scripts/smoke_compose.sh` header (lines 7–8): "실시간 피드 확인(live-feed)은 실제 BUSHEXA_API_KEY + 울산 BIS 네트워크가 필요하며 SMOKE_SKIP_FEED=1 환경변수로 건너뛸 수 있다."
2. Code comment (line 90): "이 부분은 실제 BUSHEXA_API_KEY + 울산 BIS 네트워크가 필요한 OPERATOR 영역."
3. No fabricated green-smoke report found in `docs/refactor/reports/` — the executor did not claim W5 AC-1/AC-2 as locally-passed.
4. W6 absence is documented as deferred in the task list (Task #4) and no executor report claims it was completed.

---

## TEST_CASE_EXPLANATIONS (E-8, Phase P5 additions)

### `tests/security/test_security_gate.py::test_no_plaintext_secret`
**What:** Scans `bushexa/` Python source files and `docker/*.py` files for the string "WhenMyBusRun" (legacy DB plaintext password).
**Condition:** No arguments; runs at import time by traversing the file tree.
**Must be true to pass:** The list of matching files must be empty (== []).
**Independent source:** S7 requirement "코드·compose에 평문 비밀번호 0건". Expected value `[]` is not derived from running the implementation.
**E-9 gap:** `docker_dir.rglob("*.py")` returns zero files — `docker/` has only YAML and Dockerfile. The "compose" scan claimed in the docstring is vacuous. Current security state verified separately; YAML scan should be added (Condition-4).

### `tests/security/test_security_gate.py::test_admin_routes_protected`
**What:** Sends unauthenticated GET requests to protected `/admin/*` routes using Flask test client.
**Condition:** App is created via `_make_test_app(tmp_path)` with a fresh SQLite-in-memory DB and plaintext password file. No login session is active.
**Must be true to pass:** `/admin/login` returns 200 (public); all other admin routes (`/admin/`, `/admin/data`, `/admin/logs`, `/admin/govtrack/status`) return 302 or 401.
**Independent source:** F04 §7 AC-A1 and W10 AC-1 (cited in docstring). The 302/401 expected set is the spec requirement, not derived from running the route.

### `tests/security/test_security_gate.py::test_csv_formula_injection`
**What:** Verifies CSV formula injection sanitization in two parts: (a) unit test of `_sanitize_csv_cell()` helper, (b) end-to-end test of `export_csv()` with an injected stop_id.
**Condition (unit):** Calls `_sanitize_csv_cell` with eight hand-specified inputs covering all injection chars and boundary cases.
**Must be true to pass:** `_sanitize_csv_cell("=SUM(A1)") == "'=SUM(A1)"`, `"+1" == "'+1"`, `"-1" == "'-1"`, `"@FOO" == "'@FOO"`, `"\t=EXEC" == "'\t=EXEC"`, `"\r=EXEC" == "'\r=EXEC"`, `"1234" == "1234"`, `None == ""`.
**Independent source:** OWASP CSV-injection guidance; expected values are hand-specified in the test — not derived from running the implementation. E-13(b) PASS.
**Condition (e2e):** Inserts a row with `stop_id="=SUM(A1)"`, calls `export_csv()`, checks the data chunk contains `'=SUM(A1)` and does not contain unsanitized `=SUM(A1)`.

### `tests/services/test_auth.py::test_set_initial_secret_file_is_0600`
**What:** Calls `AuthService.set_initial()` with a new password and verifies the resulting secret file has mode 0o600.
**Condition:** A fresh `tmp_path` with no existing password file; `env_password=None`.
**Must be true to pass:** `result.success is True` and `stat.S_IMODE(os.stat(secret_path).st_mode) == 0o600`.
**Independent source:** S8 security requirement "secret 파일 0600"; the 0o600 bitmask is a POSIX standard, not derived from implementation output. E-13(d) PASS.

### `tests/services/test_auth.py::test_change_password_secret_file_is_0600`
**What:** Calls `AuthService.change_password()` on an existing PBKDF2-hashed file and verifies the file's permission is 0o600 after the change.
**Condition:** Pre-existing secret file with a PBKDF2-stored password; `env_password=None`.
**Must be true to pass:** `result.success is True` and `stat.S_IMODE(os.stat(secret_path).st_mode) == 0o600`.
**Independent source:** Same as above. E-13(d) PASS.

---

## E-10 — Postmortem Assessment

**Two items noted by the executor during P5 implementation:**

**Item 1: Dockerfile two-pass uv-sync (hatchling accommodation)**
The Dockerfile comment (lines 7–13) labels this as "brief-defect, reported" and explains the uv sync splitting strategy. Per 00-workflow §8.1, PM registration applies to "비자명 버그" (non-obvious bugs) or situations requiring ">30분 디버깅". The two-pass uv-sync is a known, documented hatchling/uv behavior (build system requires source tree before wheel installation). This is a build system accommodation, not a debugging session producing a new root cause. **No PM required under §8.1 exclusion ("단순 오타/컴파일 에러는 제외").** The comment in the Dockerfile is sufficient disclosure.

**Item 2: data/timetable population step**
The Dockerfile includes `COPY --chown=app:app data/timetable/*.json /app/data/timetable/` as a disclosed operational requirement. This is not an error discovered during implementation — it is a design choice to copy JSON data at build time. No PM required.

**Existing PMs from P4 (SEC medium findings now sealed):**
- PM-007 (open-redirect) was created and sealed with regression test in P4.
- PM-NEW-01, PM-NEW-02, PM-NEW-03 were listed in the security audit as follow-on items for P5 operator. These are operational deployment tasks, not implementation bugs, and are tracked as Conditions 2–3 above.

**E-10 verdict: PASS** (no unrecorded defect-class errors; acceptable items cited with §8.1 rationale).

---

## E-13 Anti-Tautology Summary

| Test | Expected value source | Tautological? |
|------|-----------------------|---------------|
| `test_no_plaintext_secret` | S7 spec ("0건") → expected `[]` | No |
| `test_admin_routes_protected` | F04 §7 AC-A1 → expected {302, 401} | No |
| `test_csv_formula_injection` | OWASP CSV-injection → hand-specified 8 input/output pairs | No |
| `test_set_initial_secret_file_is_0600` | POSIX S8 → 0o600 | No |
| `test_change_password_secret_file_is_0600` | POSIX S8 → 0o600 | No |

All P5 tests are spec-driven with independently-specified expected values. E-13(b) PASS.

---

## E-11 Security Gate

Security audit `security-audit-P4-20260602-T01.md`:
- VERDICT: PASS, GATE: P5 진입 허용
- high/critical 발견 0건
- S1–S10 all covered

E-11: PASS.

---

## CHECKLIST_RESULTS (E-1 through E-13)

| Check | Result | Evidence |
|-------|--------|----------|
| E-1 All ACs PASS | PASS (except operator-pending EC-3/4/5) | Per work-item table above |
| E-2 All artifacts at stated paths | PASS | `docker/Dockerfile`, `docker/compose.yaml`, `docker/compose.dev.yaml`, `scripts/smoke_compose.sh`, `README.md`, `docs/refactor/migration-notes.md`, `.env.example` all exist |
| E-3 SyntaxError/ImportError | PASS | `uv run pytest -q` 212 passed |
| E-4 pytest failed=0 errors=0 | PASS | 212 passed, 0 failed, 0 errors |
| E-5 No new secrets hardcoded | PASS | `grep WhenMyBusRun bushexa/ docker/` exit 1; `.env.example` has dummy values only |
| E-6 TODO/FIXME accounted for | PASS | No unresolved TODOs in new files (Dockerfile comment is a documented design note, not FIXME) |
| E-7 Domain service signatures | N/A | No domain service signatures changed in P5 |
| E-8 Test case explanations | PASS | All 5 P5 tests explained in TEST_CASE_EXPLANATIONS section |
| E-9 Test intent matches implementation | PARTIAL-PASS | 4/5 PASS; `test_no_plaintext_secret` YAML scan gap documented (Condition-4, non-blocking) |
| E-10 Postmortem for errors | PASS | Two items assessed; both excluded under §8.1; documented rationale |
| E-11 Security gate passed | PASS | `security-audit-P4-20260602-T01.md` gate=허용, high/critical 0 |
| E-12 Touch point specs | N/A | No new user-facing touch points added in P5 |
| E-13 Anti-tautology | PASS | All expected values independently sourced |

---

## FAIL_REASONS_FOR_DESIGNER

None. All buildable ACs PASS. Live-runtime ACs are correctly operator-pending.

## PASS_NOTES

1. The executor honestly bounded the operator-pending area in the smoke script, both in comments and via the `SMOKE_SKIP_FEED` mechanism. No fabrication found.
2. Docker image at 429MB is within budget; the two-pass uv-sync is a sensible hatchling accommodation and documented inline.
3. The `session_cookie_secure` migration from hardcoded `False` to env-driven config is clean and complete.
4. CSV formula injection sanitization applied at every cell in `export_csv()` — OWASP guidance followed.
5. Both secret 0600 regression tests pass; the `change_password`/`set_initial` code path was already correct, now regression-sealed.
6. **Regression risk:** `test_no_plaintext_secret` leaves `docker/*.yaml` unscanned. If `WhenMyBusRun` or another plaintext password is ever added to compose files, this test will not catch it. Recommend widening to `rglob("*.y*ml")`.

---

## Final Verdict

**VERDICT: PASS**

Buildable ACs (W1 security sealing, W2 Dockerfile, W3/W4 compose configs, W7 README, W8 migration-notes) all verified and passing. Operator-pending ACs (EC-3/4/5 live stack + EC-6 cutover) are correctly bounded and honestly reported. W6 legacy cutover correctly not done.

Conditions 1–3 must be cleared by the operator before W6 cutover proceeds. Condition 4 is an Executor follow-up (non-blocking test coverage gap).
