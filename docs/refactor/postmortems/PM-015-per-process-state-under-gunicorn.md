---
status: verified
postmortem_id: PM-015
severity: medium
discovered: 2026-06-05
phase: 코드리뷰 (#6, #7, #9)
component: bushexa.web.routes.admin, bushexa.services.recrawl_job, bushexa.services.audit_log, bushexa.fileio
related: [review #6 #7 #9, ADR-012, "tests/web/test_admin_lockout_cross_worker.py", "tests/web/test_admin_recrawl_sse.py", "tests/services/test_recrawl_job.py", "tests/services/test_audit_log.py"]
auditor_status: pass (6114da3)
---

# PM-015 — gunicorn 멀티 워커에서 프로세스 로컬 상태가 어긋남 (recrawl SSE 404, lockout ×워커, audit 유실)

> 부검(postmortem)은 **비난이 아니라 재발 방지**를 위한 기록이다. 사람이 아니라 시스템·프로세스의 결함을 본다.

## 1. 요약 (3줄)

- **증상:** (#6) 시간표 재크롤 SSE 가 다른 워커로 가면 404. (#9) 로그인 lockout 이 워커별이라 실제 허용 횟수가 워커 수 × 5. (#7) 동시 편집 시 audit 로그 항목 유실.
- **근본 원인:** 개발 서버(단일 프로세스) 기준으로 상태를 `current_app.config`·모듈 전역에 두었다. atomic write 만으로 read-modify-write 경합(lost update)을 막을 수 있다고 가정했다.
- **재발 방지:** 공유 상태는 파일 + `fileio.locked_update_json`(fcntl)으로 옮기고 크로스 워커 테스트를 추가했다.

## 2. 영향

- 관리자 기능 오작동(재크롤 진행률), 보안 통제 약화(lockout), 감사 기록 유실.

## 4. 근본 원인

- `BUSHEXA_WEB_WORKERS` 기본 2. 테스트는 앱 인스턴스 하나로만 돌았다.
- `atomic_write_json` 은 파일이 깨지지 않게 할 뿐, 두 프로세스가 같은 파일을 읽고-고치고-쓰면 한쪽 변경이 사라진다.

## 6. 해결

- `bushexa/fileio.py` `locked_update_json` — 형제 `<file>.lock` 에 `fcntl.flock`(Linux 전용).
- `admin_lockout.json`, `audit_log.json`, `timetable_crawl_job.json` + 진행 jsonl 로 이전.
- 재크롤 잡은 heartbeat(120초 초과 시 재시작 허용), 손상 메타는 idle 처리.

## 7. 재발 방지 (Prevention) — **필수**

- [x] **회귀 테스트**: `tests/web/test_admin_lockout_cross_worker.py::test_lockout_shared_across_app_instances`, `tests/web/test_admin_recrawl_sse.py::test_cross_worker_sse_via_http`, `tests/services/test_recrawl_job.py::test_cross_worker_progress`, `tests/services/test_audit_log.py`.
- [x] **프로세스**: `docs/guide/architecture.md` 불변식 I-2·I-3, `pitfalls.md` §2.

## 8. 교훈

- 웹 상태를 만들 때 "워커가 2개 이상이면?"을 먼저 묻는다. 요청 간 공유 상태는 DB 또는 잠금 파일.
- atomic ≠ isolated. 쓰기 원자성과 read-modify-write 직렬화는 다른 문제다.
- 크로스 워커 테스트 패턴: 같은 설정으로 앱 인스턴스 2개를 만들고 교차 요청.
