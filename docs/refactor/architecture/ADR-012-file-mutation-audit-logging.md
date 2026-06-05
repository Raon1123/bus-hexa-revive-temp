---
status: designed
adr_id: ADR-012
designer: opus
auditor_status: pending
last_updated: 2026-06-01
supersedes: null
superseded_by: null
---

# ADR-012 — 파일 생성·수정은 단일 쓰기 choke-point를 거쳐 반드시 감사 로그를 남긴다

## 컨텍스트

- **사용자 지시:** "로그에는 파일을 생성하거나 수정한다면 반드시 기록할 수 있도록 한다."
- 본 시스템이 디스크에 파일을 쓰는 지점: ① 시간표 JSON 저장(`init_timetable`, 크롤 결과 `timetable/{busno}.json`), ② 공휴일 캐시(`secret/holiday_{year}.json`), ③ (P4) 관리자 시간표 직접 편집 저장, ④ (P4/F05) CSV 디스크 내보내기 등.
- 이 쓰기들이 흩어진 `open(..., "w")` / `json.dump`로 구현되면 (a) 누가 언제 무엇을 바꿨는지 관찰 불가, (b) ADR-010·F04 §4.6의 **관리자 로그 뷰어가 보여줄 기록이 비어** 있고, (c) 시간표가 잘못 덮어써졌을 때 추적 불가.
- 사용자는 **"생성"과 "수정"을 구분**해 말했다("생성하거나 수정") — 로그도 두 동작을 구분해야 한다.
- 관련: F04 §4.6(관리자 로그 뷰어), P0 `logging_setup.py`(`logs/bushexa.log` KST RotatingFileHandler), W3(`init_timetable`), F10(시간표 크롤), TP-009(관리자 편집).

## 결정

애플리케이션의 **모든 파일 쓰기를 단일 헬퍼 `bushexa/fileio.py`로 강제**하고, 그 헬퍼가 감사 로그를 남긴다.

1. **유일한 합법 쓰기 경로:** `bushexa/fileio.py`의 `atomic_write_bytes/atomic_write_text/atomic_write_json(path, data, *, logger=None)`. `bushexa/` 내 코드에서 디스크 파일을 쓸 때 **직접 `open(...,"w")`/`json.dump(...,파일)`/`Path.write_*` 사용 금지**(감리에서 grep 검출).
2. **원자적 쓰기:** 임시파일(`{path}.tmp.{pid}`)에 기록 → `flush`+`os.fsync` → `os.replace`(원자적 rename). 부분 쓰기로 인한 손상 방지(시간표가 깨진 채 남지 않음).
3. **생성/수정 구분:** 쓰기 **직전** `path.exists()`로 판정해 동사를 정한다 — 없으면 `created`, 있으면 `modified`.
4. **감사 로그:** `bushexa.*` 로거로 **INFO** 한 줄 — 예: `file created: <abs_path> (<bytes>B)` / `file modified: <abs_path> (<bytes>B)`. 호출자가 `logger`를 주지 않으면 `logging.getLogger("bushexa.fileio")`를 쓴다. 이 로거는 propagate=False지만 P0 `logging_setup`이 `bushexa` 루트에 핸들러를 달아 **`logs/bushexa.log`에 적재**된다 → **F04 §4.6 관리자 뷰어가 읽는 바로 그 sink**. (두 요구 — "파일 변경 기록" + "관리자가 로그 관찰" — 가 자동으로 합쳐진다.)
5. **민감정보 비기록:** 경로·크기·동사만 남기고 **파일 내용은 로그하지 않는다**(시크릿/키 유출 방지, ADR-009·S-마스킹과 정합). 경로가 `secret/` 하위면 파일명만 남기고 디렉터리는 마스킹하지 않되 내용은 절대 미기록.

## 범위 (무엇을 기록하고 무엇을 안 하나)

- **기록함:** 앱/크롤러가 디스크에 **생성·수정**하는 파일(시간표 JSON, 공휴일 캐시, CSV 디스크 저장 등).
- **기록 안 함:** ① 파일 **읽기**(get_timetable 등), ② **DB 행** 변경(`bus_timelog`/`bus_arrival_cache`는 데이터이며 별도 데이터 브라우저 F04 §4.3 소관), ③ 로그 파일 자신의 rotation, ④ `.pyc`/`__pycache__` 등 런타임 부산물.
- 삭제(unlink)는 현재 앱 경로에 없음 — 생기면 `file deleted:` 동사를 본 헬퍼에 추가.

## 대안

### 대안 A — 각 호출부에서 직접 `logger.info`
- 단점: 새 쓰기 추가 시 로그 누락이 쉬움(강제 불가). 사용자 "반드시"에 위배.
- 기각.

### 대안 B — OS 레벨 audit(inotify/auditd)
- 단점: 컨테이너·OS 의존, 앱 의미(어떤 노선 시간표인지) 결여, 이식성↓.
- 기각: 단일 호스트·이식 목표(ADR-006)와 불일치.

### 대안 C — 본 결정(앱 내 단일 choke-point 헬퍼)
- 채택. 강제 가능(grep 감리) + 의미 있는 로그 + 원자적 쓰기 보너스 + 관리자 뷰어 sink와 자동 합성.

## 결과

### 긍정적 영향
- 파일 변경이 **빠짐없이** `logs/bushexa.log`에 남고 관리자 뷰어(F04 §4.6)로 관찰됨.
- 원자적 쓰기로 시간표 손상 방지(부수 효과).
- 생성/수정 구분으로 "처음 만든 건지 덮어쓴 건지" 즉시 식별.

### 부정적 영향 / 비용
- 모든 쓰기를 헬퍼로 바꿔야 함(P1 W3, P2 크롤 저장, P4 편집기). 신규 쓰기 리뷰 시 직접 open 금지 규약 준수 필요.

### 따라오는 작업
- **P1:** `bushexa/fileio.py` 신규 + 단위테스트(생성/수정 동사, 원자성, 로그 1줄). W3 `init_timetable`이 이 헬퍼 사용.
- **P2:** 시간표 크롤 저장(`timetable/{busno}.json`)을 헬퍼 경유로.
- **P4:** `TimetableEditor.save`(TP-009)의 "tmp write→fsync→rename"을 본 헬퍼로 통일. 관리자 편집이 로그에 남음.
- **P5(보안 게이트):** `! grep -rn 'open(.*[\"'\'']w' bushexa/` 류로 직접 쓰기 0건 확인을 감리 항목에 추가.

## 검증 방법

```bash
# 생성/수정 동사가 올바르고 INFO 로그가 1줄 남는지
uv run pytest tests/unit/test_fileio.py -v
# 직접 디스크 쓰기(open 'w' / json.dump 파일 / write_text)가 헬퍼 외에 없는지
! grep -rn "open(.*['\"]w['\"]\|\.write_text(\|\.write_bytes(\|json\.dump(" bushexa/ --include='*.py' | grep -v fileio.py
```

## 미해결 / 후속 결정

- Q1: 감사 로그 레벨 — INFO 고정(운영 가시성). 너무 잦으면 전용 로거 `bushexa.audit`로 분리해 뷰어 필터 제공(F04 §4.6 level 필터와 연계).
- Q2: 구조화 로깅(JSON line)로 갈지 — 현재는 사람이 읽는 한 줄. 뷰어가 파싱 필요해지면 P4에서 재검토.
- Q3: 동시 쓰기 락 — 단일 writer 가정(시간표는 관리자/크롤러가 직렬). 경합 생기면 파일락 추가.
