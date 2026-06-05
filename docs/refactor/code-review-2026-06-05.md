# 전체 패키지 코드 리뷰 — 2026-06-05

`/code-review` (high effort, 7 파인더 × 검증) 결과. 범위: `bushexa/` 패키지 전체(67파일, ~8,000줄).
git diff 없이 전체 코드 대상이므로 아래는 "가장 심각한 상위 10건"이며 전수 감사가 아님.
검증: 19건 중 17 CONFIRMED / 1 PLAUSIBLE / 1 REFUTED.

> **수정 현황 (2026-06-05):** #1(holiday unquote+오류검사), #2(캐시 오염), #3(빈 시간표
> 덮어쓰기)은 같은 날 수정 완료 — `HolidayError`/`UlsanBisError` 도입, fetch 계약을
> raise로 변경, crawl 전요일-빈-결과 가드 추가. **#10(로그 UNKNOWN 필터 탈락)도 수정 완료**
> (2차 웨이브, 회귀 테스트 포함 450 passed). #4~#9는 미수정.
>
> **감리 중 신규 발견 (2026-06-05 2차 웨이브):** 모든 admin 템플릿이
> `csrf_token` hidden 필드를 넣지만(`session['csrf_token']`), **서버측에서 토큰을 생성·검증하는
> 코드가 bushexa/ 어디에도 없다** — 항상 빈 값으로 렌더되고 POST에서 검증되지 않는 죽은
> 패턴. 세션 쿠키 SameSite=Lax 기본값이 cross-site POST를 완화하지만, 명시적 CSRF
> 생성+before_request 검증을 추가하거나 hidden 필드를 제거해 오해를 없애야 한다.

## Top 10 (심각도순)

```json
[
  {
    "file": "bushexa/api_clients/holiday.py",
    "line": 38,
    "summary": "HolidayClient만 serviceKey를 unquote() 없이 전달(tago.py:139, ulsan_bis.py:105/117/126은 unquote 적용)하고 status/오류XML 검사도 없어, 키/쿼터 오류가 '공휴일 없음([])'으로 조용히 파싱됨 — 문서화된 이중 인코딩 버그의 회귀.",
    "failure_scenario": "Encoding 키 사용 시 requests가 %를 재인코딩 → SERVICE_KEY_IS_NOT_REGISTERED 오류 XML(HTTP 200) → parse_holidays가 locdate 0건으로 [] 반환. 모든 공휴일 조회가 무공휴일로 동작."
  },
  {
    "file": "bushexa/services/holiday_service.py",
    "line": 100,
    "summary": "HolidayCache.refresh가 fetch()의 [] 반환(오류 경로 포함)을 권위 있는 빈 달로 취급해 raw[ym]=[]를 영속화, 이전에 정상이던 캐시 월을 덮어씀 — '실패 월 보존' 계약은 예외에서만 발동.",
    "failure_scenario": "새벽 cache-refresh 중 data.go.kr 일시 오류 → fetch가 예외 없이 [] 반환 → 해당 월 공휴일 캐시가 빈 값으로 영속화 → 보드/노선이 실제 공휴일을 평일 시간표로 렌더링, 다음 성공까지 지속."
  },
  {
    "file": "bushexa/crawler/timetable_crawl.py",
    "line": 90,
    "summary": "crawl_all_timetables가 0행 수집(울산 API 오류 XML→([],0), 빈 페이지)에도 무조건 atomic_write_json으로 기존 정상 {busno}.json을 덮어써 발행 시간표를 비울 수 있음 — '빈 결과면 쓰지 않음' 가드 부재.",
    "failure_scenario": "야간 재크롤 중 1개 노선이 일시 오류 → 해당 노선 시간표 JSON이 빈/부분 데이터로 교체 → 다음 성공 크롤까지 시간표 공란. (2026-06-05 라이브 테스트에서 울산 API 간헐 무응답 실측됨)"
  },
  {
    "file": "bushexa/domain/unist_board.py",
    "line": 155,
    "summary": "get_unist_board_data가 get_weekday(now, clock=clock)에 holiday_set을 넘기지 않아(/board·/busno·/timetable은 전달) 공휴일에도 평일 시간표를 표시.",
    "failure_scenario": "평일에 해당하는 공휴일(예: 화요일 신정)에 /unist 카드 보드만 평일 출발 시각을 표시 — 운행하지 않는 버스를 보여주고 공휴일 시간표를 숨김."
  },
  {
    "file": "bushexa/web/routes/unist_board.py",
    "line": 34,
    "summary": "/unist만 bare get_timetable을 provider로 전달 — board/busno/unist_timetable은 모두 특별>공휴일>요일 edition 래퍼를 구성하므로, 특별시간표 지정일에 /unist만 평시 시간표를 보여줌.",
    "failure_scenario": "관리자가 오늘 날짜에 특별편 지정 → /board·/busno·/timetable은 특별편 표시, /unist는 기본 시간표 표시 → 같은 사이트 안에서 모순."
  },
  {
    "file": "bushexa/web/routes/admin.py",
    "line": 627,
    "summary": "시간표 재크롤 잡 상태가 current_app.config(프로세스 로컬)에 저장 — gunicorn 워커 2개에서 시작 POST와 SSE 스트림 GET이 다른 워커에 떨어지면 진행률 스트림이 404, 동시 실행 방지(409) 가드도 무력화.",
    "failure_scenario": "POST가 워커 A에 잡 생성, EventSource GET이 ~50% 확률로 워커 B에 도착 → progress(job_id) KeyError → abort(404). 워커 B에서 두 번째 크롤 시작 가능 → 동일 timetable_dir 동시 기록."
  },
  {
    "file": "bushexa/services/audit_log.py",
    "line": 68,
    "summary": "AuditLog.record()가 잠금 없는 read-modify-write(_load→append→atomic_write_json)라 워커 2개에서 동시 관리자 작업 시 감사 항목이 유실됨 — atomic write는 파일 깨짐만 막고 lost update는 못 막음.",
    "failure_scenario": "두 워커가 동시에 [A]를 읽고 각자 항목 추가 후 기록 → 나중 스왑이 먼저 것을 덮어써 감사 로그 1건 영구 유실."
  },
  {
    "file": "bushexa/web/routes/board.py",
    "line": 72,
    "summary": "공개 요청마다 새 SQLite 연결 생성+PRAGMA(WAL/foreign_keys/busy_timeout=5000) 재실행 — 같은 DB 파일을 쓰는 크롤러 2개와 잠금 경합 시 읽기가 최대 5초 블록(18.7초 cold /board의 유력 원인). board_lite는 요청당 연결 2개.",
    "failure_scenario": "HTMX 폴링마다 connect+PRAGMA 비용 + writer 잠금 대기 최대 5s. cold 시 WAL checkpoint+경합으로 수초~수십초. 워커별 재사용 read 연결(또는 mode=ro)로 해소 가능."
  },
  {
    "file": "bushexa/web/routes/admin.py",
    "line": 115,
    "summary": "로그인 실패 잠금 상태(_ADMIN_LOCKOUT)가 current_app.config(워커 로컬)라 _MAX_FAILS=5가 실질 워커수×5회로 늘고, 잠금도 한 워커에만 적용됨.",
    "failure_scenario": "워커 2개에서 무차별 대입 시 ~10회 시도 허용, 잠금 걸려도 다른 워커로 가는 요청은 통과 — 보호 강도가 워커 수에 반비례."
  },
  {
    "file": "bushexa/services/log_reader.py",
    "line": 112,
    "summary": "_LINE_RE 불일치 라인이 level 'UNKNOWN'(값 0)으로 분류돼 어떤 레벨 필터에도 탈락 — 61행 주석('level 필터에서 걸리지 않도록 UNKNOWN 처리')과 정반대 동작.",
    "failure_scenario": "관리자가 ERROR 필터로 로그 조회 → 트레이스백 헤더만 보이고 'File ...'/'ValueError: ...' 연속 라인은 전부 사라져 스택트레이스가 소실됨."
  }
]
```

## Top 10에서 제외됐지만 CONFIRMED인 항목 (리팩토링 입력)

### 정확성 (하위 심각도)
- `web/routes/board.py:63` — edition 래퍼가 KeyError만 catch; `edition_exists`는 디렉터리 존재만 검사하므로 부분 편성 edition에서 FileNotFoundError가 래퍼의 평일 폴백을 건너뛰고 도메인 catch로 흡수 → 해당 노선 빈 행 (D8)
- `domain/unist_timetable.py:110` — 0행 기여 노선도 bus_legend에 포함 → 그리드에 없는 버스의 범례 표시 (D7)
- `services/arrival_status.py:51`/`govtrack_status.py:57` — rec[키] 직접 인덱싱, 구버전 스키마 파일에서 KeyError로 관리자 상태 페이지 500 (PLAUSIBLE; 현 writer는 모든 필드 기록)

### 효율 (E2–E5, 모두 CONFIRMED)
- `board_lite.py:31` — /lite 요청당 SQLite 연결 2개(_build_snapshot + _last_fetched_at) → 1개로 재사용
- `crawler/recorder.py:156` — route_ids 순차 fetch(CompositeLocation TAGO→BIS 폴백 포함) → 소형 ThreadPool로 사이클 시간 ≈ 최장 1콜
- `crawler/arrival_poller.py:67` — SERACH_STOPS 17개 순차 fetch, 7초 주기 대비 사이클 1.7–8.5s → 병렬화
- `data/timetable.py:40` — get_timetable 호출마다 open+json.load, 보드 1회 빌드에 ~10회 → mtime 키 캐시
- `domain/board.py:264` — merged 정렬 직후 merge_live_rows에서 재정렬(306) → 중복 정렬 제거

### 재사용/altitude (모두 CONFIRMED)
- **스냅샷·provider 조립 중복**: board/board_lite/unist_board/stops 4개 라우트가 `create_connection→BusArrivalRepo→CachedArrivalClient→close` 배선을 복제, 특별편 래퍼는 라우트별 복사 — services 계층의 단일 팩토리(`provider_for_date`, `arrival_client(config)`)로 올리면 위 D1/D2 버그가 구조적으로 재발 불가 (E6 + altitude)
- **API 클라이언트 HTTP 보일러플레이트 4벌**: unquote+timeout+오류XML 검사를 공용 헬퍼 1개로 — holiday.py 회귀(C1)의 근본 원인 (reuse)
- `domain/board.py:139·181` — unist_busnos set 컴프리헨션 동일 2벌 → 모듈 상수 (E5)
- `domain/unist_board.py:197` — `elif busno == "513"` 하드코딩 → ROUTEID 데이터 필드로; `:159` stop id "196040234"가 board.py:29 `_STOP_ID`와 별개 리터럴 → constants.py 단일 상수 (E7)
- KST/`ZoneInfo("Asia/Seoul")` 리터럴 5곳(audit_log, backup, config, logging_setup) — ADR-008 위반, time_utils로 통일
- `_PAREN_RE` 정류소명 정규화 정규식이 composite_location.py와 domain/board.py에 동일 2벌
- JSON 읽기 헬퍼 부재: ~12곳이 read+기본값 처리를 제각각 구현(fileio는 쓰기 전용) → fileio에 read_json 추가
- `web/routes/admin.py:1160/1052/1509` — _resolve_preview 쌍둥이 루프, special_save의 _parse_timetable_form 복제, worker_status stale 검사 2벌
- `cli.py:21` — _todo()와 폴백 도달 불가(dead code), 모듈 docstring의 'serve 아직 stub' 기술 낡음 (E8)

### REFUTED (기록용)
- `data/timetable.py:39` split()[0] IndexError — departure 인자는 ROUTEID 상수에서만 옴(전부 비어있지 않은 리터럴), 도달 불가

## 확인된 부정적 사실 (good news)
- 공개 웹 라우트에서 외부 API 동기 호출 **없음** — ADR-010대로 모든 라이브 호출이 크롤러/포터로 이동 완료. admin.py의 호출만 존재(운영자 게이트, 메모이즈됨)
- timing.py·i18n.py·route_diagram.py·stop_cache.py — request 스코프 `g`·threading.Lock 사용 올바름
- arrival_poller 상태 파일은 단일 writer라 경합 없음
