---
status: verified
postmortem_id: PM-001
severity: high
discovered: 2026-06-01
resolved: 2026-06-01
phase: 운영 / 코드리뷰 → P2 구현
component: bushexa.crawler (구 crawl/govtrack.py)
related: [F09, P2, ADR-008]
auditor_status: execution-pass (P2 EC-1/EC-2 green)
---

# PM-001 — 버스 통과 기록이 `bus_timelog`에 제대로 남지 않음

> 사용자 보고: "버스가 지나간 기록을 log하는데 이 부분이 제대로 동작하지 않고 있는게 지금의 한계이다."
> 본 부검은 운영 결함을 코드리뷰로 진단한 결과를 기록하고, P2 구현에서 회귀 테스트로 봉인한다.

## 1. 요약 (3줄)

- **증상:** govtrack 데몬이 버스의 정류장 통과 이벤트를 `bus_timelog`에 누락·중복·부정확하게 기록한다. running_table(F05)이 신뢰 불가.
- **근본 원인:** 단일 결함이 아니라 폴링 주기·상태 휘발성·예외 비격리·침묵 실패 등 복합 결함(H1~H10)이 누적.
- **재발 방지:** P2에서 책임 분리 재구성 + H1~H10 각각에 자연어 의도가 명시된 회귀 테스트 + 폴링 시뮬레이션.

## 2. 영향 (Impact)

- **기능:** running_table(F05) 운행 재구성, 향후 분석.
- **데이터:** `bus_timelog`에 (a) 통과했으나 누락된 정류장, (b) 재시작 직후 부정확한 시각의 false-positive 행이 혼재. 데이터 신뢰도 저하.
- **지속:** 현 운영 내내. (`postgres-data/` 실측 4KB로 데이터 축적 자체가 미미 — 결함이 적재를 방해해 온 정황과 일치.)

## 3. 타임라인 (발견 경위)

- 사용자가 운영 한계로 보고.
- 코드리뷰(Explore/Plan 단계)에서 `crawl/govtrack.py`, `src/crawl.py`, `crawl/db.py` 정독.
- F09 deep-dive에서 가설 H1~H10으로 분해.

## 4. 근본 원인 분석 (Root Cause)

복합 원인. 핵심 인과:

- **H1 (폴링 20초):** 정류장 머무름(5~10초)보다 폴링 간격이 길어 통과 이벤트의 30~50%가 표본화되지 못함. `crawl/govtrack.py:104`의 `sleep(20)`.
- **H2 (in-memory state 휘발):** `bus_timeline = {}` (`crawl/govtrack.py:78`)가 프로세스 로컬이라 재시작 시 모든 차량을 "신규"로 보고 현재 위치를 즉시 기록 → 통과시각이 아닌 "처음 본 시각"이 들어가는 false-positive.
- **H3 (KeyError 위험):** `STOP_IDS[nodeid]` 직접 조회(`crawl/govtrack.py:62`)가 미등록 ID에서 KeyError → 사이클 중단.
- **H4 (예외 비격리):** `busloc_status` 루프와 `__main__` while에 try/except 부재 → 한 예외가 사이클/데몬 전체를 죽임.
- **H6 (침묵 실패):** `resultCode != "00"`(quota 초과 등)을 print만 하고 정상처럼 진행 → 적재 중단을 아무도 모름.
- **H8:** `logging_file`이 `__main__`에서만 정의된 모듈 전역이라 import 경로 호출 시 NameError.

**왜 기존 테스트가 못 잡았나:** 테스트 인프라가 0건. 회귀 보호 장치가 전무.

## 5. 재현 (Reproduction)

```bash
# (구 코드 기준) 데몬을 재시작하면 첫 사이클에서 현재 정류장에 있는 모든 차량이
# 한꺼번에 INSERT되어, 통과하지도 않은 시각으로 기록이 들어간다.
python -m crawl.govtrack   # 시작 직후 logs/logs.tsv 관찰
```

- 기대: 차량이 추적 정류장을 **통과하는 순간**에만 1행.
- 실제: 재시작 시 현재 위치 일괄 기록 + 폴링 간격 사이 통과 누락.

## 6. 해결 (Resolution)

P2에서 `bushexa/crawler/`로 재구성 (F09 §4 설계):

- 폴링 간격 환경변수화(기본 10초) + 시뮬레이션으로 recall 측정 (H1).
- `VehicleTimeline.warm_from_repo`로 재시작 시 직전 위치 적재 → false-positive 억제 (H2).
- `STOP_IDS.get(nodeid)`로 안전 조회, stop_name None 허용 (H3).
- 차량별 try/except 격리 + 데몬 루프 catch-all (H4).
- result_code 5연속 실패 시 alert hook (H6).
- TSV 경로 인자/`BUSHEXA_TSV_PATH`화, `/app/logs` 하드코딩 제거 (H8/H9).

## 7. 재발 방지 (Prevention) — 필수

- [x] **회귀 테스트 (H1)**: `tests/simulation/test_polling_sampling.py::test_recall_at_poll_10` — 8초 머무름 모델에서 10초 폴링 recall≥75% 검증. (측정 0.825, PASS)
- [x] **회귀 테스트 (H2)**: `tests/crawler/test_vehicle_timeline.py::test_warm_suppresses` + `tests/crawler/test_pm001_regression.py::test_restart_warm_suppresses_false_positive` — warm 후 같은 위치 record가 False(중복 억제)인지 검증. (대조 테스트로 warm이 load-bearing임도 입증)
- [x] **회귀 테스트 (H3)**: `tests/crawler/test_unknown_stop_safe.py::test_unknown_stop_inserts_null_name` — 미등록 nodeid가 KeyError 없이 stop_name=None으로 기록.
- [x] **회귀 테스트 (H4)**: `tests/crawler/test_recorder_isolation.py::test_one_vehicle_failure_no_cascade` — 한 차량(처리 단계) 실패가 다른 차량에 전파되지 않음. except-type mutation으로 비-tautology 실증.
- [x] **회귀 테스트 (H6)**: `tests/crawler/test_api_failure_alerting.py::test_five_consecutive_failures_trigger_alert` — 5연속 실패 시 alert 1회.
- [x] **코드 가드:** `STOP_IDS.get()` 안전 조회, 사이클 단위 batch 트랜잭션, 데몬 graceful shutdown(stop_event), warm_from_repo.
- [x] **프로세스:** ADR-008 회귀 매트릭스 H1~H10 등록, 폴링 시뮬레이션(W8) 도입.
- [x] **회귀 매트릭스 갱신:** ADR-008 §회귀 매트릭스에 H1~H10 1:1 매핑 등록됨.
- [x] **봉인 end-to-end:** `tests/crawler/test_pm001_regression.py::test_passages_are_logged_to_bus_timelog` — 통과가 실제로 bus_timelog에 누적되고 중복이 억제됨(핵심 결함 회복).
- [x] **재연결 무손실:** `tests/crawler/test_batch_commit_and_reconnect.py::test_reconnect_after_drop` — DB 연결 끊김 시 commit 못한 통과 후보를 **이월-재시도**(LogRow의 원래 idx 보존)해 유실 없이 적재. state.record가 즉시 전진하므로 후보를 버리면 PM-001 증상이 DB blip에서 재현되는데, 이월 버퍼가 이를 차단(상한 초과분만 드롭, TSV sink엔 잔존).

## 8. 교훈 (Lessons)

- **표본화 결함은 "에러 로그"를 남기지 않는다.** 누락은 조용하다 — 정량 시뮬레이션 같은 능동 측정이 필요.
- **휘발성 상태 + 재시작 = 데이터 오염.** 장기 데몬의 in-memory 상태는 반드시 영속/워밍 전략을 가진다.
- **침묵 실패 금지.** 외부 API 실패는 카운트하고 임계 초과 시 시끄럽게(alert) 만든다.
- 관련: F09 H1~H10, [[PM-template]] 규약.

## 9. 상태

- 수정 커밋: P2 구현 (`bushexa/crawler/{state,recorder,daemon,arrival_poller}.py`, 2026-06-01)
- 회귀 테스트 통과 확인: ✅ P2 EC-1(H1~H10 회귀)·EC-2(시뮬레이션) green, 전체 104 pass
- Auditor 확인: execution-pass (2026-06-01)
