---
status: done (build/deploy-artifact scope) — W6 cutover + W5 runtime은 운영자 게이트
phase_id: P5
designer: opus
auditor_status: >-
  execution-pass (execution-audit-P5-20260602-1130 — W1~W5/W7/W8 PASS, 212 tests).
  빌드가능 AC 전부 PASS(이미지 429MB, compose config 무오류, 평문 0건).
  W5 라이브피드 smoke·EC-3/4/5는 운영자 영역(실 API키+postgres) OPERATOR-PENDING.
  W6 legacy cutover는 R1대로 W5 운영자 dry-run + 1주 모니터 후로 DEFERRED.
last_updated: 2026-06-02
depends_on: [P4]
---

# P5 — Security Gate + Deployment + Cutover

## 1. 목적

P4(web) 종료 후 **보안 감리 게이트**를 통과시키고, slim Python + uv 기반 `docker/` 배포 자산을 작성·검증한 뒤, 기존 Streamlit/Conda 자산을 안전하게 cutover한다.

## 2. 시작 조건 (Entry Criteria)

- [ ] P4 Auditor PASS (모든 UI·admin이 신규 스택에서 동작)
- [ ] 운영 데이터 백업(`postgres-data/`, `secret/`) 완료
- [ ] 운영자 `.env` 작성 완료 (POSTGRES_*, BUSHEXA_API_KEY, BUSHEXA_SESSION_SECRET)
- [ ] (권장) `git init` + 초기 커밋으로 롤백 지점 확보

## 3. 종료 조건 (Exit Criteria)

- [x] EC-1: 보안 감리 high/critical 0건, GATE 허용 (W1) — security-audit-P4-20260602-T01 PASS + 잔여 medium 봉인(CSV injection·SESSION_COOKIE_SECURE·secret 0600), tests/security/ 추가.
- [x] EC-2: 이미지 빌드 성공, 이미지 < 500MB (W2) — `docker build` exit 0, **429MB** (docker로 검증, podman 대체).
- [ ] EC-3: compose up으로 web/worker/postgres 기동 (W3) — **OPERATOR-PENDING** (`docker compose -f docker/compose.yaml up -d`; 실 `.env`+postgres 필요). compose config는 무오류 검증됨.
- [ ] EC-4: `curl -sf http://localhost:8017/board` HTTP 200 (W5) — **OPERATOR-PENDING** (`SMOKE_SKIP_FEED=1 bash scripts/smoke_compose.sh`).
- [ ] EC-5: worker 로그에 govtrack `CycleStats` ≥1 + arrival upsert ≥1 (W3, W5) — **OPERATOR-PENDING** (실 BUSHEXA_API_KEY + 울산 BIS 네트워크).
- [ ] EC-6: 기존 `app.py/infopages/src/crawl/*compose.yaml/runscript.sh/requirements.yaml`를 `_legacy/`로 이동 (W6) — **DEFERRED** (R1: W5 운영자 dry-run + 1주 모니터 후).
- [x] EC-7: README 최종 + migration notes 존재 (W7, W8) — README 8섹션, migration-notes 5섹션, `.env.example`(더미) 추가.

### 3.1 EC ↔ Work Item AC 매핑 (P-8 / P-12)

| EC | 검증 대상 | 충족하는 Work Item AC |
|---|---|---|
| EC-1 | 보안 게이트 | W1: AC-1, AC-2 |
| EC-2 | 이미지 빌드·크기 | W2: AC-1, AC-2 |
| EC-3 | compose 기동 | W3: AC-1, AC-2 |
| EC-4 | /board 200 | W5: AC-1 |
| EC-5 | worker 로그 | W3: AC-2; W5: AC-2 |
| EC-6 | legacy cutover | W6: AC-1, AC-2 |
| EC-7 | 문서 | W7: AC-1; W8: AC-1 |

> 모든 work item AC가 ≥1개 EC에 매핑됨. 누락 0건.

## 4. Work Item 분해

| ID | 작업 제목 | 소요 | 의존 | 산출물 |
|---|---|---|---|---|
| W1 | 보안 감리 게이트 (ADR-009) | M | (P4 완료) | reports/security-audit-*.md + (필요시) postmortems/PM-* |
| W2 | docker/Dockerfile (python:slim + uv) | M | — | docker/Dockerfile |
| W3 | docker/compose.yaml (web/worker/postgres) | M | W2 | docker/compose.yaml |
| W4 | docker/compose.dev.yaml (bind-mount override) | S | W3 | docker/compose.dev.yaml |
| W5 | dry-run smoke 스크립트 | M | W3 | scripts/smoke_compose.sh |
| W6 | legacy 자원 cutover | M | W1,W5 통과 후 | 파일 이동/삭제 |
| W7 | README 최종 | M | W3 | README.md |
| W8 | 운영 마이그레이션 노트 | S | — | docs/refactor/migration-notes.md |

## 5. Work Item 상세

### W1 — 보안 감리 게이트
**Depends:** P4 완료 **산출물:** `reports/security-audit-<ts>.md`, 발견 시 `postmortems/PM-*`

**지시사항 (명령형):**
1. 별도 Auditor 컨텍스트에서 `auditor/security-audit-criteria.md`의 S1~S10을 `bushexa/` 전체에 적용한다.
2. `/security-review` skill을 보조로 실행한다.
3. 발견을 심각도별로 `reports/security-audit-<ts>.md`에 기록한다(각 발견: `path:line` + 재현 + 수정 권고).
4. high/critical 발견은 수정하고 `postmortems/`에 PM 등재 + 보안 회귀 테스트를 추가한다.

**Acceptance:**
- [ ] AC-1: `reports/security-audit-*.md`가 생성되고 S1~S10 카테고리를 모두 다룬다 (검증: 파일 존재 + 카테고리 헤더 확인)
- [ ] AC-2: high/critical 발견이 0건이다 (잔존 시 수정·재검) (검증: 보고서 GATE='허용')

**테스트 케이스 (자연어 의도 — P-11):**
- `test_no_plaintext_secret`: 코드·compose에 평문 비밀번호/키가 0건인지 검증한다 (S7) — 발견 시 보안 회귀로 봉인.
- `test_admin_routes_protected`: 모든 `/admin/*`가 비로그인 시 302/401인지 검증한다 (S2).

**검증 명령:**
```bash
test -f docs/refactor/reports/security-audit-*.md 2>/dev/null || ls docs/refactor/reports/
! grep -rn 'WhenMyBusRun' bushexa/ docker/
uv run pytest tests/security/ -v
```

#### P4 보안게이트(security-audit-P4-20260602-T01) 잔여 항목 — P5에서 봉인 대상

> P4 게이트는 **PASS(high/critical 0, GATE 허용)**. 아래 medium/low는 게이트를 차단하지 않았으나 P5 cutover 전 처리한다(이미 OPEN-REDIRECT는 P4에서 수정·PM-007로 봉인).

- [ ] **(medium S7) compose 평문 DB 비밀번호** `docker-compose.yaml:7`·`podman-compose.yaml:7` `POSTGRES_PASSWORD: WhenMyBusRun` → 신규 `docker/compose.yaml`는 `${POSTGRES_PASSWORD}` env 참조만(W3), **비밀번호 교체**, `.env.example`만 더미. legacy compose는 W6 cutover 시 `_legacy/`로 이동. (W1 `! grep WhenMyBusRun`로 회귀 봉인)
- [ ] **(medium S1) SESSION_COOKIE_SECURE** `app.py` 정적 `False` → 운영 HTTPS 배포에서 `True`(config/env 기반 활성). W3/W8 배포 config + 마이그레이션 노트에 명시.
- [ ] **(medium S8) secret 파일 권한** `secret/*.txt`·`secret/db.yaml` 0644 → **0600** 프로비저닝(W6/배포 문서). (AuthService는 쓰기 시 이미 0600.)
- [ ] **(medium, 기지) CSV formula injection** `repo.export_csv` — 데이터 출처가 정부 BIS 피드라 medium. CSV 셀 선두 `= + - @` 위생처리(prefix `'`) 추가.
- [ ] **(low) 방어심층**: 로그인 lockout 지속(_LOCKOUT_SECS=10) 상향 검토, dashboard innerHTML(서버 내부값) 검토, `_mask_secrets` DB URL(`postgresql://user:pass@`) 형식 보강, `/admin/logs` 내부경로 노출(인증 관리자 전용) — 백로그.

---

### W2 — docker/Dockerfile
**Depends:** — **산출물:** `docker/Dockerfile`

**지시사항 (명령형):**
1. `python:3.12-slim-bookworm` 베이스, non-root user `app`을 만든다.
2. uv를 설치하고 `COPY pyproject.toml uv.lock .python-version` 후 `uv sync --frozen --no-dev --all-extras`로 의존성을 설치한다.
3. `COPY bushexa /app/bushexa`, `COPY data/timetable /app/data/timetable`(JSON만)을 복사한다. db/backup·secret은 제외(bind-mount).
4. `ENV TZ=Asia/Seoul`, `ENTRYPOINT ["uv","run","bushexa"]`를 설정한다.

**Acceptance:**
- [ ] AC-1: `podman build -t bushexa:test -f docker/Dockerfile .`가 성공한다 (검증: 빌드 exit 0)
- [ ] AC-2: 이미지 크기가 500MB 미만이다 (검증: `podman images bushexa:test --format '{{.Size}}'`)

**검증 명령:**
```bash
podman build -t bushexa:test -f docker/Dockerfile .
podman images bushexa:test --format '{{.Size}}'
```

---

### W3 — docker/compose.yaml
**Depends:** W2 **산출물:** `docker/compose.yaml`

**지시사항 (명령형):**
1. ADR-006 yaml을 기반으로 `web`(`serve`), `worker`, `postgres` 서비스를 작성한다.
2. `worker`는 govtrack(`crawl-loop`)과 arrival(`arrival-loop`)을 모두 구동한다 — 한 서비스에서 두 명령을 띄우는 진입 스크립트 또는 두 worker 서비스로 분리(ADR-010 Q3).
3. `env_file: ../.env`, postgres healthcheck, `restart: always`를 둔다.
4. 비밀번호는 `${POSTGRES_PASSWORD}` 변수 참조만 사용(평문 0건).

**Acceptance:**
- [ ] AC-1: `podman-compose -f docker/compose.yaml config`가 무오류이고 평문 비밀번호가 0건이다 (검증: `! grep -E 'PASSWORD: [^$]' docker/compose.yaml`)
- [ ] AC-2: worker 서비스가 govtrack과 arrival 두 루프를 구동하도록 정의된다 (검증: compose에 `crawl-loop`·`arrival-loop` 명시)

**검증 명령:**
```bash
podman-compose -f docker/compose.yaml config
! grep -E 'PASSWORD: [^$]' docker/compose.yaml
```

---

### W4 — docker/compose.dev.yaml
**Depends:** W3 **산출물:** `docker/compose.dev.yaml`

**지시사항 (명령형):**
1. 코드 bind-mount(`../bushexa:/app/bushexa`)와 `BUSHEXA_LOG_LEVEL=DEBUG` override를 둔다.
2. SQLite 기본(`DATABASE_URL=sqlite:///./data/bushexa.db`)으로 postgres 없이도 dev 가동 가능하게 한다.

**Acceptance:**
- [ ] AC-1: `podman-compose -f docker/compose.yaml -f docker/compose.dev.yaml config`가 무오류다 (검증: config exit 0)
- [ ] AC-2: dev override에 bind-mount와 DEBUG가 포함된다 (검증: `grep -E 'bushexa:/app|DEBUG' docker/compose.dev.yaml`)

**검증 명령:**
```bash
podman-compose -f docker/compose.yaml -f docker/compose.dev.yaml config
```

---

### W5 — dry-run smoke 스크립트
**Depends:** W3 **산출물:** `scripts/smoke_compose.sh`

**지시사항 (명령형):**
1. compose up → 15초 대기 → `/board`·`/admin/login` curl 200 확인 → worker 로그에서 `CycleStats`·arrival upsert grep → down 하는 스크립트를 작성한다.
2. 실패 시 non-zero exit로 종료한다.
3. 실행 권한을 부여한다.

**Acceptance:**
- [ ] AC-1: `scripts/smoke_compose.sh`가 exit 0으로 끝난다(`/board` 200 포함) (검증: 스크립트 실행)
- [ ] AC-2: worker 로그에서 govtrack과 arrival 활동이 확인된다 (검증: 스크립트 내 grep 통과)

**검증 명령:**
```bash
bash scripts/smoke_compose.sh
```

---

### W6 — legacy 자원 cutover
**Depends:** W1, W5 통과 후 **산출물:** 파일 이동/삭제

**지시사항 (명령형):**
1. **git 저장소가 없으므로 삭제 대신 `_legacy/`로 이동**한다(되돌리기 안전): `app.py`, `infopages/`, `src/`, `crawl/`, 루트 `Dockerfile`, `docker-compose.yaml`, `podman-compose.yaml`, `runscript.sh`, `requirements.yaml`, `run.sh`, `postgres.sh`, `podman.out`.
2. `media/`는 `bushexa/web/static/media/`로 복사 완료를 확인하고, `timetable/*.json`은 `data/timetable/`로 이전 완료를 확인한다.
3. `secret/`(gitignored), `postgres-data/`는 유지한다.
4. 신규 스택만으로 smoke가 여전히 통과하는지 재확인한다.

**Acceptance:**
- [ ] AC-1: 루트에 `app.py`·`infopages`·`src`·`crawl`·구 compose 파일이 없다 (검증: `! ls app.py infopages src crawl docker-compose.yaml 2>/dev/null`)
- [ ] AC-2: cutover 후에도 `scripts/smoke_compose.sh`가 통과한다 (검증: 재실행)

**검증 명령:**
```bash
! ls app.py infopages src crawl docker-compose.yaml podman-compose.yaml runscript.sh requirements.yaml 2>/dev/null
bash scripts/smoke_compose.sh
```

---

### W7 — README 최종
**Depends:** W3 **산출물:** `README.md`

**지시사항 (명령형):**
1. 섹션을 작성한다: About, Quick start(uv), Configuration(.env), Local development, Docker deployment(podman-compose), Architecture(docs/refactor 링크), Troubleshooting(govtrack 미동작·DB·API quota·울산 백업본), Tests.
2. uv 명령을 ≥5건 인용한다.
3. 한국어 위주로 작성하되 핵심 명령은 그대로 둔다.

**Acceptance:**
- [ ] AC-1: README에 8개 섹션 헤더가 모두 존재한다 (검증: `grep -c '^## ' README.md` ≥8)

**검증 명령:**
```bash
grep -E '^## ' README.md
```

---

### W8 — 운영 마이그레이션 노트
**Depends:** — **산출물:** `docs/refactor/migration-notes.md`

**지시사항 (명령형):**
1. 섹션을 작성한다: cutover 전 백업, `.env` 작성 가이드(`secret/db.yaml`→env 추출), cutover 5단계, 롤백 절차(`_legacy/` 복원), 사후 모니터 체크리스트(1주 govtrack/arrival 누락 점검).
2. 각 단계에 실제 명령을 인용한다.

**Acceptance:**
- [ ] AC-1: 5개 섹션이 모두 존재한다 (검증: `grep -c '^## ' docs/refactor/migration-notes.md` ≥5)

**검증 명령:**
```bash
grep -E '^## ' docs/refactor/migration-notes.md
```

## 6. 병렬화 그래프

```text
W1 (보안 게이트) ── (P4 후, 독립)
W2 ──▶ W3 ──┬──▶ W4
            ├──▶ W5
            └──▶ W7
W8 ── (독립)
W6 ── (W1 + W5 통과 후, cutover 결정 시점)
```

병렬 가능 그룹:
- **Group A (동시)**: W1, W2, W8
- **Group B (W2 후)**: W3 → (W4, W5, W7 동시)
- **Group C (게이트+smoke 통과 후)**: W6

## 7. 리스크 & 롤백

- R1: cutover 후 govtrack/arrival 실패 — W6를 W1(보안)+W5(smoke) 통과 + 1주 모니터 후로 미룬다
- R2: `.env` 누락 — `BUSHEXA_API_KEY`/`DATABASE_URL` 부재 시 컨테이너가 명시적 에러로 종료(ADR-005)
- R3: 이미지 크기 초과 — `.dockerignore` + multi-stage
- R4: git 부재로 롤백 어려움 — W6는 삭제 대신 `_legacy/` 이동, 권장: 사전 `git init`
- R5: 구현 중 발견 에러 — `postmortems/` PM 작성(00-workflow §8)

롤백: `podman-compose down` + (cutover 후) `_legacy/`에서 파일 복원 + 구 compose 재가동.

## 8. Auditor 감리 포인트 (설계 단계)

- [ ] DA-1: 8개 work item 단일 책임
- [ ] DA-2: 사이클 없음
- [ ] DA-3: 모든 work item 산출물 경로 명시
- [ ] DA-4: 모든 work item AC ≥2건(W7/W8은 단일 문서라 1 AC 허용, 검증 명령 보유) + 검증 명령
- [ ] DA-5: Group A 병렬 식별
- [ ] DA-6: EC-1~7 검증 명령 보유
- [ ] DA-7: L work item 없음
- [ ] DA-8: 테스트 동반 work item(W1)에 자연어 의도 (P-11)
- [ ] DA-9: EC↔AC 매핑 표 존재, 누락 0건 (P-12)
- [ ] DA-10: 보안 게이트(ADR-009)가 cutover 전 entry로 배치됨
