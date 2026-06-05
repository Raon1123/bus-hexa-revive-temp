# Govtrack 파이프라인 정확성 감사

**일자**: 2026-06-05  
**감사자**: 분석 에이전트 (read-only)  
**저장소**: `/home/mlv/Project/bushexa/bus-hexa-revive-temp`  
**대상**: 버스 정류소 통과 기록 파이프라인(govtrack)  

---

## 1. 파이프라인 동작 요약

```
[TAGO API]──┐
            ├→ CompositeLocationClient.fetch_bus_locations(route_id)
[울산 BIS]─┘   ↓ TagoResponse.items: List[BusLocation(node_id, vehicle_no, node_ord)]
                                       ↓
            GovtrackRecorder.run_single_route(route_id)
              ├─ VehicleTimeline.record(route_id, vehicle_no, node_id, ts)
              │    └─ 직전 node_id와 다르면 True(변경) → 상태 항상 갱신
              ├─ node_id ∈ tracked_stops[route_id]? → LogRow 후보 생성
              └─ passage_sink(row) → TSV append (dry_run=False 시)
                                       ↓
            GovtrackRecorder.run_cycle()
              ├─ 전 노선 후보 수집 + _pending(이월 버퍼) 합산
              └─ BusLogRepo.insert_batch(candidates) → 단일 트랜잭션 commit
                                       ↓
            [bus_timelog] idx / stop_id / route_id / vehicle_number / stop_name
                                       ↓
            BusLogRepo.get_by_route(route_id, day=date)
                                       ↓
            domain/running.py  parse_runs() → build_running_grid()
                                       ↓
            [운행 재구성 테이블 — /running 페이지]
```

**주기**: 10초마다 `run_cycle()` 실행. `_NIGHT = (01:00, 05:00)` 구간은 60초 대기 후 skip.  
**상태 영속**: 매 사이클 `state.persist()` → `govtrack_state.json` (JSONFileStore, 원자적 기록).  
**재시작 워밍**: 기동 시 `warm_from_repo(since=now-3h)` → DB의 최근 통과 stop_id 복원.  
**tracked_stops**: `ROUTEID[rid][3]` = 각 노선의 전체 정류소 목록(constants.py). 노선당 수십~수백 정류소.

---

## 2. 발견 사항

> 심각도 구분: **버그** = 잘못된 DB 행을 생성하는 확정 결함 / **위험** = 특정 조건에서 기록 오류·소실 가능 / **개선** = 설계 갭, 기능 부재

---

### 2-1. [위험] GPS 지터·방향 역전 시 허위 통과 기록

| 항목 | 내용 |
|------|------|
| 파일:줄 | `recorder.py:118`, `state.py:99`, `tago.py:52,99` |
| 심각도 | **위험** |

**감지 기준 확인**: 통과 판정은 순전히 node_id 변화로만 이루어진다.

```python
# state.py:99
changed = self._last.get(key) != node_id
```

```python
# tago.py:52,99
node_ord: int | None = None  # 파싱됨
out.append(BusLocation(node_id=..., node_name=..., vehicle_no=..., node_ord=int(node_ord) ...))
```

`node_ord`는 TAGO API로부터 정상적으로 파싱되어 `BusLocation`에 담기지만, recorder가 이를 전혀 사용하지 않는다(`recorder.py:118` — `state.record()`에 `loc.node_id`만 전달).

**실패 시나리오**: 차량이 A(정류소 5번) → B(6번) 순서로 이동한 뒤, GPS 스냅 또는 종점 회차 후 재진입으로 API가 다시 A를 반환하면:

1. B 감지 → `changed=True`, B 기록 (정상)
2. A 재반환 → `A != B` → `changed=True` → A 기록 (허위)

`node_ord`가 5 → 6 → 5로 역전됐다는 신호가 있어도 탐지 로직에서 무시된다. 종점에서 종점 반대 방향 재진입 시에도 같은 정류장이 양방향에서 다시 나타날 수 있다.

**권장 수정**: `node_ord`가 이전 값 이상인 경우에만 기록을 진행하는 순방향 게이트를 `run_single_route` 내에 추가한다. 단, 종점 회차(node_ord 리셋)를 정상으로 처리하는 예외가 필요하다.

---

### 2-2. [위험] UlsanBIS fallback — 동명 정류소 오매핑

| 항목 | 내용 |
|------|------|
| 파일:줄 | `composite_location.py:36-51`, `composite_location.py:93-94` |
| 심각도 | **위험** |

**감지 기준 확인**: fallback 시 `present_stop` 이름 → node_id 역인덱스를 사용한다.

```python
# composite_location.py:43-44
exact: dict[str, str] = {}
for nid, nm in STOP_IDS.items():
    exact.setdefault(nm, nid)   # 먼저 본 것 우선(선착순)
```

STOP_IDS에는 동명 정류소가 다수 존재한다(예: '공업탑' → 193040401/402/403/404, '태화강역광장' ×2, '남목1동' ×2, '일산해수욕장' ×2). `setdefault`로 먼저 등장한 node_id만 index에 남고 나머지는 탈락한다.

**실패 시나리오**: 노선이 '공업탑(193040403)'를 tracked_stop으로 갖고 있으나 fallback index는 '공업탑 → 193040401'을 가리킨다. 실제 차량이 193040403을 통과해도 fallback은 193040401로 기록한다. 이 stop_id가 해당 노선의 tracked_stops에 없으면 통과가 누락되고, 있으면 엉뚱한 stop_id로 기록된다.

**clean 인덱스도 동일 문제**: clean 인덱스는 `clean_counts[c] == 1`인 경우만 포함하므로 동명 정류소는 제외되지만, 그 경우 매핑 자체가 없어 역시 통과 누락이 발생한다.

**추가 불확실성**: 울산 BIS `presentstopnm` 필드가 "현재 위치 정류소"인지 "다음 도착 정류소"인지 API 문서로 확인되지 않았다. 의미가 다르면 통과 기록이 항상 1정류소 앞서거나 뒤처진다.

**권장 수정**: 동명 정류소가 있을 경우, 노선의 stop_ids 목록과 교집합하여 소속 노선 기반으로 disambiguate한다. present_stop 의미를 API 문서로 확인한다.

---

### 2-3. [버그] route_nm 컬럼 항상 NULL

| 항목 | 내용 |
|------|------|
| 파일:줄 | `repo.py:21`, `repo.py:129`, `schema.py:16` |
| 심각도 | **버그** |

**확인 증거**:

```python
# repo.py:21
_COLS = "idx, stop_id, route_id, route_nm, vehicle_number, stop_name"
```

```python
# repo.py:129 — insert_batch SQL
sql = ("INSERT INTO bus_timelog (idx, stop_id, route_id, vehicle_number, stop_name) "
       "VALUES (?, ?, ?, ?, ?)")
```

```python
# recorder.py:128-129 — LogRow 생성
row = LogRow(idx=idx, stop_id=loc.node_id, route_id=route_id,
             vehicle_no=loc.vehicle_no, stop_name=stop_name)
```

스키마에 `route_nm VARCHAR(20)` 컬럼이 존재하고, SELECT 시 `_COLS`에 포함되어 읽히지만, INSERT 구문과 LogRow 생성 모두 route_nm을 전달하지 않아 전체 DB가 이 컬럼을 NULL로 유지한다. 레거시 `govtrack.py`는 이 컬럼을 채웠다.

**영향**: 관리자 데이터 브라우저, CSV export의 route_nm 컬럼이 항상 비어 있다. 데이터 완전성 결함이다.

**권장 수정**: `ROUTEID[route_id][0]`(버스 번호)을 `LogRow.route_nm`에 채우고 INSERT SQL에 `route_nm` 컬럼을 추가한다.

---

### 2-4. [위험] 10초 사이클 — 정류소 간 통과 누락(샘플링 한계)

| 항목 | 내용 |
|------|------|
| 파일:줄 | `daemon.py:119`, `tests/simulation/test_polling_sampling.py` |
| 심각도 | **위험** |

**확인 증거**: `run_daemon`의 기본 `poll_seconds=10`. 시뮬레이션 테스트가 recall을 정량화한다:

- 5초 폴링: recall ≈ 0.975
- **10초 폴링: recall ≈ 0.825** (17.5% 누락)
- 20초 폴링: recall ≈ 0.500 (50% 누락)

**실패 시나리오**: 10초 사이클 동안 버스가 두 정류소를 연속으로 통과하면, 두 번째 정류소의 node_id만 `state.record()`에 전달된다. 첫 번째 정류소는 API 폴링에서 이미 사라졌으므로 영구 누락된다. tracked_stops가 연속 인접 정류소를 포함하는 경우 발생 빈도가 높다.

이 한계는 레거시 govtrack.py(20초)에도 동일하게 존재했으며, 신규 구현에서 10초로 개선되었다. 그러나 여전히 구조적 샘플링 오류다.

**권장 수정**: 폴링 주기를 5초 이하로 낮추거나, TAGO WebSocket/실시간 피드(존재 시)로 전환. 단기적으로는 시뮬레이션 결과를 운영 문서에 명시한다.

---

### 2-5. [위험] 스키마 UNIQUE 제약 없음 — DB 레벨 중복 방지 부재

| 항목 | 내용 |
|------|------|
| 파일:줄 | `schema.py:10-23`, `recorder.py:79-81, 155, 165-170` |
| 심각도 | **위험** |

**확인 증거**:

```sql
-- schema.py:11-20
CREATE TABLE IF NOT EXISTS bus_timelog (
    idx VARCHAR(40),
    stop_id VARCHAR(20),
    route_id VARCHAR(20),
    route_nm VARCHAR(20),
    vehicle_number VARCHAR(20),
    stop_name VARCHAR(50)
)
```

PRIMARY KEY도, UNIQUE 제약도 없다. 중복 방지는 전적으로 메모리 내 `VehicleTimeline.record()`의 `changed` 체크에만 의존한다.

**실패 시나리오 — 상태 오류 시 중복 삽입**: 발견사항 2-1(GPS 지터)이 VehicleTimeline을 정상 전진시킨 뒤 동일 node_id로 재도달하면, `changed=True` → INSERT가 두 번 발생한다. DB 레벨에서는 이를 막을 방법이 없다.

**실패 시나리오 — DB 연결 복구 시 중복 삽입**: `_pending` 이월 버퍼는 DB disconnect 전 rollback된 행을 보존한다. 이 경우 atomicity가 보장되어 중복이 발생하지 않는 것이 일반적이다. 그러나 운영자가 수동으로 같은 데이터를 재기동/재수집하는 경우 DB 레벨 가드가 없다.

**권장 수정**: `UNIQUE(idx, vehicle_number, stop_id)` 인덱스 추가 + `INSERT OR IGNORE`(SQLite) / `ON CONFLICT DO NOTHING`(PostgreSQL)으로 幂등 INSERT.

---

### 2-6. [개선] node_ord 파싱됨 — 감지 로직에서 미사용

| 항목 | 내용 |
|------|------|
| 파일:줄 | `tago.py:52,99`, `recorder.py:118`, `composite_location.py:110-112` |
| 심각도 | **개선** |

**확인 증거**:

```python
# tago.py:52,99
node_ord: int | None = None
out.append(BusLocation(..., node_ord=int(node_ord) if node_ord is not None else None))
```

TAGO API는 `nodeord`(정류소 순번)를 반환하고 파싱되지만, `recorder.py:118`의 `state.record()` 호출에서는 `loc.node_id`만 전달되며 순방향 진행 여부를 검사하지 않는다. 이것이 발견 2-1(GPS 지터 허위 기록)의 근본 원인이다.

UlsanBIS fallback 경로(`composite_location.py:110-112`)에서는 `BusLocation`을 `node_ord` 없이 생성하므로(`node_ord=None` 기본값), node_ord 기반 순방향 게이트를 추가하더라도 TAGO 1차 경로에만 적용된다. 울산 BIS fallback 경로는 node_ord 정보 자체가 없다.

**권장 수정**: `run_single_route`에서 `loc.node_ord`가 이전 관측값 이상인 경우에만 통과 기록을 진행하는 순방향 게이트를 추가(None이면 통과). node_ord 역전 시 `skipped_reversed` 카운터로 관측 가능하게 한다.

---

### 2-7. [개선] dry_run이 VehicleTimeline 상태를 전진시킴

| 항목 | 내용 |
|------|------|
| 파일:줄 | `recorder.py:117-119`, `recorder.py:132-133` |
| 심각도 | **개선** |

**확인 증거**:

```python
# recorder.py:117-119
changed = self.state.record(route_id, loc.vehicle_no, loc.node_id, ts)  # 항상 실행
if not changed:
    stats.skipped_unchanged += 1
    continue
```

```python
# recorder.py:132-133
if self.passage_sink is not None and not dry_run:
    self.passage_sink(row)   # TSV append만 억제
```

`dry_run=True`일 때 INSERT와 TSV append는 억제되지만, `state.record()`는 항상 호출된다. 따라서 dry_run 실행 후 실제 run을 수행하면, dry_run이 "소비"한 통과가 `changed=False`로 처리되어 **실제 기록을 건너뛰게** 된다.

**실패 시나리오**: 관리자가 `crawl_once(..., dry_run=True)`로 진단 테스트를 실행 → 바로 뒤 정규 사이클이 해당 통과를 누락.

**권장 수정**: `dry_run=True`이면 `state.record()` 호출 전에 return하거나, state를 복사해 임시 적용 후 버리는 방식으로 상태를 격리한다.

---

### 2-8. [개선] 야간 창 진입 시 state.persist() 미호출

| 항목 | 내용 |
|------|------|
| 파일:줄 | `daemon.py:138-142` |
| 심각도 | **개선** |

**확인 증거**:

```python
# daemon.py:138-142
while not stop_event.is_set():
    now = clock.now()
    if _in_night_window(now.time(), night_window):
        sleep(night_sleep_seconds)   # persist() 호출 없음
        continue
```

야간 창(01:00~05:00) 진입 시 `state.persist()`를 호출하지 않고 바로 `sleep`한다. 01:00 직전 마지막 사이클의 상태는 영속 파일에 반영되어 있지만, 이후 야간 창 기동 중 예외·충돌 시에는 마지막 persist 이후의 상태 변화가 유실될 수 있다.

**실패 시나리오**: 01:00 직전 사이클 직후 야간 창 진입 → 60초 sleep → 데몬 비정상 종료 → 재기동 후 warm_from_repo가 DB의 tracked-passage 위치만 복원(untracked 정류소 통과 상태 유실) → false-positive 가능.

**권장 수정**: 야간 창 진입 직전(sleep 호출 전)에 `state.persist()`를 호출한다.

---

### 2-9. [개선] ts 파라미터 상태에 미저장 — 체류시간 분석 불가

| 항목 | 내용 |
|------|------|
| 파일:줄 | `state.py:92-100` |
| 심각도 | **개선** |

**확인 증거**:

```python
# state.py:95-96
# ``ts``는 F09 §6 계약 시그니처 유지를 위한 인자다(현재는 호출자가 timestamp를
# 직접 idx로 만들므로 상태에 저장하지 않는다 — 향후 체류시간 분석 시 활용 여지).
def record(self, route_id: str, vehicle_no: str, node_id: str, ts: datetime) -> bool:
```

`ts`가 인터페이스에 정의되어 있으나 실제 저장되지 않는다. 체류시간(버스가 정류소에 몇 초 머물렀는지) 계산이나 실제 통과 시각 추적이 불가능하다.

**권장 수정**: `_last` 딕셔너리 값을 `(node_id, ts)` 튜플로 확장하고 JSONFileStore 직렬화를 갱신한다.

---

### 2-10. [개선] 60분 trip 분리 임계값 하드코딩

| 항목 | 내용 |
|------|------|
| 파일:줄 | `domain/running.py:40` |
| 심각도 | **개선** |

**확인 증거**:

```python
# running.py:40
_SPLIT_GAP_MINUTES = 60
```

60분 초과 간격을 별개 운행으로 분리한다. 종점 회차 대기가 60분을 초과하면 왕복 운행이 한 회차로 병합되어 그리드가 왜곡된다.

**권장 수정**: `split_gap_minutes`를 설정 파라미터로 외부화하거나 노선별로 조정 가능하게 한다.

---

### 2-11. [개선] running.py — naive datetime + 당일 경계 정합

| 항목 | 내용 |
|------|------|
| 파일:줄 | `domain/running.py:47-58`, `web/routes/running.py:87` |
| 심각도 | **개선** |

**확인 증거**:

```python
# running.py:55-57
dt = datetime.datetime.strptime(date_part + " " + time_part, "%Y%m%d %H:%M:%S")
return dt  # tzinfo 없음, naive datetime
```

```python
# web/routes/running.py:87
timelog_rows = repo.get_by_route(route_id, day=target_date)
# get_by_route: idx LIKE 'YYYYMMDD_%' — day 필터
```

`parse_runs`는 naive datetime을 반환한다. 웹 라우트의 `_today_kst()`는 KST 기준 오늘을 계산하지만(`KSTClock().now().date()`), DB 쿼리의 day 필터는 idx 문자열의 날짜 prefix에만 의존한다. idx는 기록 시각(KST 또는 서버 로컬) 기반이므로, 서버 시간대가 KST가 아닐 경우 자정 전후 기록이 다른 날 버킷으로 분류될 수 있다.

**권장 수정**: `KSTClock`으로 idx를 일관되게 생성하는 것을 문서화하고, `_parse_timelog`에 `pytz.timezone('Asia/Seoul')`을 명시하거나, 컨테이너 TZ=Asia/Seoul 설정을 인프라 문서에 명시한다.

---

### ※ 레거시 "update double pushing" 커밋 — recorder 결함 없음

커밋 2a9c5fb "update double pushing"은 레거시 소스에 존재하며, 해당 변경은 `running_table.py`(display 레이어)의 정류소 중복 표시 처리 수정이다. 기록 레이어(`govtrack.py`)와 무관하다. 신규 구현의 `VehicleTimeline.record()`는 동일 node_id 연속 반환 시 `changed=False`로 정상 처리한다(`test_same_node_no_change` 테스트로 검증).

---

## 3. 상태 수명 확인

**`VehicleTimeline._last`는 차량을 결코 잊지 않는다** (`state.py:87,100`). `_last`는 삽입만 되고 제거 경로가 없으며, JSONFileStore는 전체 딕셔너리를 영속화한다. 실운영에서 수개월치 차량 키가 메모리에 누적되는 점은 관측이 필요하다.

**재시작 복원 범위**: `warm_from_repo`는 `since=now-3h` 창의 tracked-passage(DB 기록된 정류소)만 복원한다(`state.py:103-115`). 재시작 직전 차량이 untracked 정류소에 있었다면 DB에 해당 위치가 없으므로 warm 후 첫 폴링에서 `changed=True` → 그 정류소가 tracked라면 false-positive 기록이 발생할 수 있다. JSONFileStore persist 파일이 정상이면 이 위험은 회피된다(파일 우선, state.py:111-114).

**첫 관측 = 항상 changed=True**: `_last.get(key)`가 None이면 `None != node_id` → True. 재시작 시 warm이 실패하거나 완전히 새로운 차량 투입 시에도 첫 위치가 추적 정류소이면 INSERT가 발생한다.

---

## 4. 소비처 정합 확인 (domain/running.py)

| 검사 항목 | 결과 |
|-----------|------|
| `get_by_route` day 필터 | `idx LIKE 'YYYYMMDD_%'` — 문자열 날짜 prefix 기반 (repo.py:99-100). 올바름. |
| `parse_runs` 정렬 | `logs.sort(key=lambda r: r.idx)` — idx 사전식 = 시간순. 올바름. |
| 60분 간격 trip 분리 | 하드코딩(_SPLIT_GAP_MINUTES=60). 개선 항목 2-10 참조. |
| 같은 stop_id 2회 기록 | `current_run_stops[log.stop_id] = time_str` — 마지막 기록이 덮어씀(running.py:126). 허위 통과 기록(발견 2-1)이 있을 경우 그리드에서 최신 시각만 표시된다. |
| `route_nm` 활용 | `get_by_route` 결과의 `route_nm`은 항상 NULL(발견 2-3). running.py는 route_nm을 사용하지 않으므로 직접 영향 없음. |

---

## 5. 테스트 갭 목록

| # | 미커버 시나리오 | 관련 발견 |
|---|----------------|-----------|
| T1 | GPS 지터/방향 역전 → 허위 통과 기록 | 발견 2-1 |
| T2 | node_ord 역전 차단 로직(미구현 게이트) | 발견 2-1 |
| T3 | 동명 정류소(공업탑 등) UlsanBIS fallback 오매핑 | 발견 2-2 |
| T4 | UlsanBIS `presentstopnm` 의미 검증(현재 vs 다음 정류소) | 발견 2-2 |
| T5 | `route_nm`이 항상 NULL로 삽입됨 | 발견 2-3 |
| T6 | `dry_run=True` 이후 정규 사이클에서 통과 누락 | 발견 2-7 |
| T7 | 야간 창 진입 시 `state.persist()` 미호출 | 발견 2-8 |
| T8 | UNIQUE 제약 없음 — 조건 충족 시 중복 행 삽입 | 발견 2-5 |
| T9 | `_pending_cap` 초과 시 오래된 행 드롭(LogRow 유실 경로) | `recorder.py:170` |
| T10 | 종점 회차 — 동일 차량이 같은 run 내에서 같은 정류소를 두 번 통과 | 발견 2-1, 2-10 |
| T11 | 60분 초과 종점 대기 → 왕복 병합 오류 | 발견 2-10 |
| T12 | warm_from_repo — 재시작 전 untracked 정류소에 있던 차량 (DB 복원 불가 케이스) | `state.py:103-115` |

---

## 6. 기능 확장 제안

### E-1. 실제 통과 시각 정밀화

**현황**: `idx`가 폴링 시각(API 호출 완료 기준)이므로 실제 통과는 최대 10초 이전일 수 있다.

**제안**: `VehicleTimeline._last`를 `{key: (node_id, ts)}` 형태로 확장하고, API 응답에 차량별 타임스탬프가 포함될 경우 이를 우선 사용한다.

**필요 변경**: `state.py` VehicleTimeline 값 타입 변경 + JSONFileStore 직렬화 + `LogRow.actual_ts` 컬럼 추가(schema.py).

---

### E-2. 시간표 대비 통과 지연 분석

**제안**: 각 정류소별 시간표 통과 예정 시각(`BusTimetable`)과 실제 기록 시각(`bus_timelog.idx`)을 매핑하여 지연(초)을 계산하는 분석 뷰 또는 집계 쿼리를 추가한다.

**필요 변경**: `bus_delay_stats` 뷰 또는 집계 테이블 추가(route_id, stop_id, day, avg_delay_sec, p95_delay_sec).

---

### E-3. 사이클당 recall 모니터링

**제안**: `run_single_route`가 반환하는 `RouteStats.skipped_unknown_stop`(추적 외 정류소 통과 수)와 `inserts` 비율로 샘플링 손실 추정치를 사이클 로그에 기록한다.

**필요 변경**: `RouteStats`에 `adjacent_miss_estimate: int` 필드 추가(레거시 시뮬레이션 공식 적용), `CycleStats` 요약에 포함.

---

### E-4. 차량별 운행 이력 조회 API

**제안**: `GET /api/vehicle-history?vehicle_no=&date=` 엔드포인트를 추가하여 특정 차량 번호의 당일 전체 정류소 통과 기록(stop_id, idx, route_id)을 반환한다.

**필요 변경**: `BusLogRepo.query_paged(vehicle_no=..., day=...)` 활용(이미 존재) + Flask Blueprint 추가(web/routes/vehicle_history.py).

---

### E-5. 정류소별 시간대 통과 빈도 히트맵

**제안**: `bus_timelog`의 stop_id × 시간대(hour)별 통과 횟수를 집계하여 운행 밀도 히트맵을 제공한다. 특정 정류소에 버스가 잘 오지 않는 시간대를 시각화할 수 있다.

**필요 변경**: `bus_stop_hourly_count(stop_id, day, hour, count)` 집계 테이블(배치 계산) 또는 `SELECT stop_id, SUBSTR(idx,10,2) hour, COUNT(*) FROM bus_timelog GROUP BY 1,2` 뷰.

---

## 요약

| 심각도 | 건수 | 주요 내용 |
|--------|------|-----------|
| **버그** | 1 | route_nm 컬럼 항상 NULL |
| **위험** | 4 | GPS 지터 허위 기록, UlsanBIS fallback 오매핑, 스키마 UNIQUE 제약 없음, 10초 폴링 샘플링 누락 |
| **개선** | 6 | dry_run 상태 전진, 야간 창 persist 누락, ts 미저장, 60분 분리 하드코딩, naive datetime, node_ord 미사용 |
| **테스트 갭** | 12 | 위 표 참조 |
