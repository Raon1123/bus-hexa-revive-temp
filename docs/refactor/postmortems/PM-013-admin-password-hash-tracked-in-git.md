---
status: fixed (부분 — 이력 정리·비밀번호 교체 미완)
postmortem_id: PM-013
severity: high
discovered: 2026-09-29
phase: 운영 (배포 번들 준비 중 수동 검토)
component: bushexa.config, .gitignore, .dockerignore
related: [ADR-005, S-카테고리 시크릿, README.txt 번들 검사]
auditor_status: pending
---

# PM-013 — 관리자 비밀번호 해시(`data/manager_password.txt`)가 git 에 추적·push 됨

> 부검(postmortem)은 **비난이 아니라 재발 방지**를 위한 기록이다. 사람이 아니라 시스템·프로세스의 결함을 본다.

## 1. 요약 (3줄)

- **증상:** 관리자 비밀번호 해시 파일이 2026-06-05 baseline 커밋부터 추적되어 원격(origin)에 push 되었다.
- **근본 원인:** 비밀번호 파일을 ignore 된 `secret/` 에서 **추적되는 콘텐츠 디렉터리 `data/`** 로 옮기면서 새 경로의 ignore 여부를 확인하지 않았다.
- **재발 방지:** 추적 해제 + `.gitignore` 등재, 배포 번들 시크릿 검사 절차(README.txt). 이력 정리와 비밀번호 교체는 남아 있다.

## 2. 영향 (Impact)

- 해시(당시 형식 PBKDF2 또는 legacy 평문 가능)가 저장소 이력에 남아 있다. 저장소 접근권이 있는 누구나 오프라인 크래킹을 시도할 수 있다.
- 기간: `f2ecd93`(2026-06-05) ~ `3372b3d`(2026-09-29). **추적 해제는 이력을 지우지 않는다.**

## 3. 타임라인

- `secret/` 가 compose 에서 `:ro` 로 마운트되어 관리자 비밀번호 변경 POST 가 실패 → `config.py` 가 비밀번호 파일 위치를 `data/manager_password.txt` 로 옮기고 `_migrate_manager_password` 로 복사.
- 당시 `.gitignore` 는 `data/bushexa.db*`, `data/timetable_backup/` 만 제외.
- 2026-09-29 배포 번들 준비 중 발견 → `3372b3d` 에서 추적 해제.

## 4. 근본 원인

- "시크릿은 `secret/` 에 있다"는 가정이 ignore 규칙의 유일한 근거였다. 시크릿이 이사하자 보호가 사라졌다.
- 시크릿 경로가 ignore 되는지 검사하는 자동 장치가 없었다. `.dockerignore` 에도 `data/manager_password.txt` 가 없다.

## 5. 재현 / 점검

```bash
git check-ignore -v data/manager_password.txt secret/key.txt .env   # 셋 다 출력되어야 함
git log --all --oneline -- data/manager_password.txt                 # 이력 잔존 확인
```

## 6. 해결

- `.gitignore` 에 `data/manager_password.txt` 추가, `git rm --cached`.
- README.txt 번들 절차: `tar tf bushexa-deploy.tar | grep -E '\.env$|secret/|password|\.db'` 출력이 없어야 함.

## 7. 재발 방지 (Prevention) — **필수**

- [ ] **운영 조치**: 관리자 비밀번호 교체(`/admin/password`). 교체하면 이력의 해시는 무의미해진다. **2026-09-29 결정: 다음 배포 단계에서 운영자가 수행**(README.txt 배포 체크리스트에 등재).
- [ ] **이력 정리**(선택): 저장소가 공개였거나 공개될 예정이면 `git filter-repo` + force-push. 파괴적 작업이므로 소유자 결정 필요.
- [ ] **회귀 테스트**: 없음. 제안 — `config.py` 가 아는 모든 시크릿 경로에 대해 `git check-ignore` 가 성공하는지 검사하는 테스트(또는 CI 단계).
- [ ] `.dockerignore` 에 `data/manager_password.txt`, `data/*.json` 런타임 파일 추가 검토.
- [x] **프로세스**: `docs/guide/pitfalls.md` §5 시크릿 항목, CLAUDE.md 절대 규칙.

## 8. 교훈

- 시크릿 파일 경로를 바꾸면 **새 경로의 ignore 상태를 같은 커밋에서 확인**한다.
- ignore 는 디렉터리 단위 가정이 아니라 파일 단위로 검증한다.
- 추적 해제 ≠ 유출 해소. 노출된 시크릿은 **교체**가 1순위다.
