---
status: living
last_verified: 2026-09-29 (HEAD 8dc582e)
audience: 이 저장소에서 코드를 고치는 모든 사람·AI 세션 — 작업 전에 해당 절을 읽을 것
---

# 자주 범하는 오류 (Pitfalls)

> 부검(`docs/refactor/postmortems/PM-*.md`), 코드리뷰(`code-review-2026-06-05.md`), recorder 감사, 운영 이력에서
> **실제로 한 번 이상 일어난 실수**만 모았다. 각 항목은 "규칙 — 왜 — 근거" 순서다.
> 새 부검을 쓰면 여기에도 규칙 한 줄을 추가한다(00-workflow §8).

## 0. 작업 전 30초 체크

- [ ] `git status` 로 다른 세션·사람의 미커밋 변경이 있는지 본다. 내 변경만 스테이징한다(§8).
- [ ] 고치려는 영역의 절(아래 1~9)을 읽는다.
- [ ] "없다/미구현이다"라고 결론 내리기 전에 잘리지 않은 검색을 한다(§7).
- [ ] 끝나면 `uv run python -m pytest -q` 전체 통과, UI 변경이면 브라우저로 확인한다.

## 1. 외부 API · 데이터 수집

| 규칙 | 왜 | 근거 |
|---|---|---|
| **"빈 결과"와 "오류"를 구분한다.** 오류를 `[]`·`None` 으로 돌려주지 말고 타입 예외(`TagoError`, `UlsanBisError`, `HolidayError`, `ParseError`)를 올린다 | 공휴일 API 인증 오류가 "공휴일 없음"이 되어 공휴일에 평일 시간표가 나갔다 | PM-008, ADR-013 |
| **HTTP 200 이어도 본문 resultCode 를 검사한다** | data.go.kr 게이트웨이는 키·한도 오류를 200 + XML 로 준다 | PM-008 |
| **실패 결과로 알려진 좋은 캐시·파일을 덮지 않는다.** 쓰기 전에 "전부 비었으면 저장 안 함" 가드 | 0행 재크롤이 시간표 JSON 을 비울 수 있었다 | PM-008 (review #2, #3) |
| 외부 호출은 반드시 `api_clients/_http.get_with_service_key` 로 한다. 키 인코딩·timeout 을 직접 처리하지 않는다 | 보일러플레이트 4벌 중 1벌만 `unquote` 가 빠져 이중 인코딩 발생 | PM-008 (C1) |
| XML 은 `resp.content`(bytes)로 파싱한다. `resp.text` 금지 | charset 헤더가 없으면 latin-1 로 디코드되어 한글이 깨진다 | PM-003 |
| TAGO `items.item` 은 1건이면 dict, 0건이면 `""` 다. `_items_as_list` 를 거친다 | 타입 가정이 깨지면 노선 전체가 실패한다 | api-usage §2.2 |
| timeout·폴링 주기·재시도는 상수가 아니라 설정값으로 둔다 | 고정 10초 timeout 이 울산 API 지연에 잘렸다 | PM-012 |
| 폴링 주기를 늘릴 때는 recall 을 측정한다(`tests/simulation/`) | 버스 정차 5~10초. 10s 폴링 recall ≈ 0.825, 15s 는 미측정 | PM-001, recorder 감사 2-4 |
| 공개 화면 라우트에서 외부 API 를 부르지 않는다. `board_support.arrival_client()`(DB 캐시)만 쓴다 | 방문자 수만큼 API 호출이 늘고 장애가 화면으로 번진다 | ADR-010 |
| 울산 `fetch_arrivals` 의 `[]` 는 "버스 없음"일 수도, "호출 실패"일 수도 있다. 이 값을 신선한 사실로 저장·표시하지 않도록 주의 | 현재 poller 가 실패를 새 타임스탬프의 빈 결과로 저장한다(미해결) | api-usage §4 |
| 정류장 이름은 `STOP_IDS.get(...)` 으로 읽는다. `STOP_IDS[...]` 금지 | 모르는 정류장 ID 에서 KeyError 로 사이클이 죽었다 | PM-001 H3, ADR-011 |
| 매뉴얼 예시 값(cityCode 25 등)을 복사하지 않는다. 울산은 `cityCode=26`, TAGO ID 는 `'USB'+울산ID` | 예시는 대전 기준 | api-usage §1.1 |

## 2. 동시성 · 멀티 프로세스

| 규칙 | 왜 | 근거 |
|---|---|---|
| 웹 상태를 `current_app.config`·모듈 전역에 두지 않는다. 요청 간 공유 상태는 DB 또는 잠금 파일 | gunicorn 워커 2개 이상. SSE 가 다른 워커에서 404, lockout 이 워커 수 × 5 | PM-015 |
| 여러 프로세스가 read-modify-write 하는 파일은 `fileio.locked_update_json` | `atomic_write` 는 파일 손상만 막고 lost update 는 못 막는다(audit 로그 유실) | PM-015 (review #7) |
| 파일 쓰기는 `fileio.atomic_write_*` 만 쓴다. `open(...,'w')`, `json.dump(f)`, `write_text` 금지 | 쓰기 도중 읽기·크래시로 파일이 깨진다. 감사 로그도 남지 않는다 | ADR-012 |
| 크롤러 병렬화는 **fetch 만** 스레드로. 상태·알림·DB 쓰기는 메인 스레드에서 고정 순서 | SQLite `check_same_thread`, 노선별 격리·폴백 순서 보존 | code-review E3/E4 |
| 병렬 fetch 기본값(1)을 올리기 전에 상류 오류율 기준선을 잰다 | TAGO "세션 부족(30/30)" 오류가 순차 호출에서도 관측됨 | api-usage §4 |
| 데몬 루프는 예외로 죽으면 안 된다. 격리는 cycle > route > request, 잡은 예외는 반드시 로그 | 한 차량·한 노선 오류가 전체 수집을 멈췄다 | PM-001, ADR-013 |

## 3. 부팅 · 배포 · 컨테이너

| 규칙 | 왜 | 근거 |
|---|---|---|
| 각 프로세스는 자기 저장소 전제조건(스키마 등)을 **멱등으로 직접** 세운다. 부팅 순서를 가정하지 않는다 | 새 DB 에서 `/lite` 500, healthcheck 실패 | PM-009 |
| mock 없는 스모크를 배포 게이트로 유지한다(`scripts/smoke_compose.sh`) | 데이터 접근을 전부 mock 한 라우트 테스트는 배선 결함을 못 본다 | PM-009 |
| 코드만 바뀌면 `restart app`, `pyproject.toml`·`uv.lock`·`docker/` 가 바뀌면 `up -d --build` | 소스는 ro bind-mount 라 재빌드가 필요 없다. 반대로 의존성 변경은 재시작만으론 반영 안 됨 | README.txt |
| compose 의 Dockerfile 경로는 `docker/Dockerfile`. 바꾸면 CI docker-build 잡이 잡는다 | 경로 변경이 커밋 메시지에 없이 섞여 들어가 혼선 | PM-012 §4 |
| 컨테이너는 root 로 돈다. `data/`·`logs/` 의 런타임 파일은 root 소유다 | 호스트에서 편집·삭제 시 권한 오류 | architecture §2 |
| 배포 번들은 README.txt 절차대로 만들고 `tar tf … \| grep -E '\.env$\|secret/\|password\|\.db'` 가 비어야 한다 | 시크릿이 번들로 새어 나간다 | PM-013 |

## 4. 시간 · 날짜

| 규칙 | 왜 | 근거 |
|---|---|---|
| 시간대는 `time_utils.KST` 하나. `ZoneInfo("Asia/Seoul")` 리터럴·naive `datetime.now()`·`date.today()` 금지 | 컨테이너 TZ 에 따라 자정 경계가 어긋난다. 노선도 날짜 게이트(`ROUTE_CHANGES`)는 `get_now()` 사용 | ADR-008, PM-014 |
| 시간 의존 로직은 `Clock` 을 주입하고 테스트는 `FakeClock` | 실제 시계에 의존하면 테스트가 시각에 따라 깨진다 | ADR-008 |
| "없음"은 `None` 으로 표현한다. 시각 필드에 `0` sentinel 금지 | `until_ts=0` 이 `now >= 0` 으로 "만료"가 되어 lockout 이 영영 발동하지 않았다 | PM-005 |
| 시행일이 미래인 변경은 날짜 게이트 + 경계일 테스트 | 743 변경을 시행일 없이 즉시 반영했다 | PM-014 |

## 5. 시크릿 · 보안

| 규칙 | 왜 | 근거 |
|---|---|---|
| `.env`, `secret/`, `data/manager_password.txt`, `data/bushexa.db*` 는 절대 커밋하지 않는다. `git add -A`·`git add .` 금지 | 비밀번호 해시가 3개월 넘게 추적·push 됐다 | PM-013 |
| 시크릿 파일 경로를 바꾸면 같은 커밋에서 `git check-ignore -v <새경로>` 로 확인한다 | `secret/` → `data/` 이사로 ignore 보호가 사라졌다 | PM-013 |
| 노출된 시크릿은 추적 해제가 아니라 **교체**가 1순위다 | 추적 해제는 이력을 지우지 않는다 | PM-013 |
| 시크릿 가림은 **기록 시점**에, 규칙은 `bushexa/redact.py` 한 곳에. `str(exc)` 를 로그·상태 파일·SSE 로 내보내는 모든 곳이 기록 지점이다 | `serviceKey=` 가 로그 파일에 수백 줄 기록됐고 뷰어 패턴도 몰랐다 | PM-016, PM-006 |
| 마스킹 패턴에 새 키워드를 넣을 때 실제 형태(`Authorization: Bearer x`, `?serviceKey=x`)로 테스트한다 | `\S+` 가 `Bearer` 에서 멈춰 토큰이 노출됐다 | PM-006 |
| 보안 가드는 단일 조건으로 쓰지 않는다(다층 검증) | `//` 만 막아서 `/\evil.com` 우회 | PM-007 |
| 관리자 폼은 CSRF 토큰 필수, 비교는 `hmac.compare_digest`(bytes) | 비-ASCII str 비교는 TypeError → 500 | PM-011 §2 |
| CSV 내보내기는 수식 인젝션 방어(`=`,`+`,`-`,`@` 접두)를 유지한다 | `tests/security/` 가 봉인 | ADR-009 |

## 6. 테스트

| 규칙 | 왜 | 근거 |
|---|---|---|
| 테스트마다 자연어 의도 1~2줄 docstring(무엇을·어떤 입력에서·어떤 결함을 막는가) | 의도 없는 테스트는 감리 FAIL(E-8) | ADR-008 |
| 모듈 전역 캐시·싱글턴을 추가하면 **같은 커밋에** 테스트 리셋 훅(autouse 픽스처)을 추가한다 | 연결 캐시가 `sqlite:///:memory:` 를 공유해 간헐 실패 | PM-010 |
| "5회 연속 통과"는 순서 독립의 증거가 아니다 | 같은 순서로 5번 돌았을 뿐 | PM-010 |
| 단위 테스트는 네트워크를 쓰지 않는다(`responses`, `no_network` 픽스처, 가짜 클라이언트) | 외부 API 는 느리고 불안정하며 키가 필요하다 | ADR-008, api-usage §5 |
| 오류 경로 테스트는 **실응답 형식** 픽스처로 쓴다. 키는 지우고 저장 | 울산 도착정보 픽스처가 임의 스키마라 검사 로직이 사실상 미검증 | api-usage §5 |
| pytest 는 저장소 루트에서 `uv run python -m pytest` 로 돌린다 | `.venv` 가 `~/Project`(대문자)에서 만들어져 `uv run pytest` 가 "Failed to spawn" 을 낸다. 고치려면 `uv sync --reinstall` | PM-002 변형 |
| dev 도구는 `[dependency-groups]`(PEP 735)에 둔다 | optional-dependencies 에 두면 `uv run pytest` 가 못 찾는다 | PM-002 |
| `bushexa*` 로거는 `propagate=False` 다. `caplog` 대신 로거에 핸들러를 직접 붙이거나 `capsys` | caplog 가 아무것도 못 받는다 | PM-002 |
| 금지 리터럴 lint 는 테스트·문서를 스캔하지 않게 하고, 비교 리터럴은 조각으로 만든다(`"/app/"+"logs"`) | "X 를 제거했다"는 설명문이 오탐 | PM-004 |
| 시각 산출물(노선도, 레이아웃)은 테스트 통과 후에도 브라우저로 본다 | 노선도 박스가 엉뚱한 레인을 덮는 것을 테스트가 못 잡았다 | PM-014 |
| 번역된 이름 문자열(예: 공휴일 이름 "Constitution Day"/"제헌절")로 필터링하지 않는다. 날짜·코드로 판단한다 | locale(en_US vs C.UTF-8)에 따라 로컬 통과·CI 실패가 갈렸다 | `f80e55e` |
| 로케일·TZ 에 민감한 테스트는 `LANG=C.UTF-8` 과 `en_US.UTF-8` 둘 다에서 돌려 본다 | CI 러너와 로컬 환경이 다르다 | `f80e55e` |
| 테스트가 `data/` 실파일을 건드리지 않게 `tmp_path`·`BUSHEXA_TIMETABLE_DIR` 로 격리한다 | 실데이터 오염 | architecture §7 |

## 7. 조사 · 리뷰 · 감리 프로세스

| 규칙 | 왜 | 근거 |
|---|---|---|
| **부재 주장 규칙:** "X 가 없다/미구현"은 잘리지 않은 검색(`grep -rl`, `-c`, `--include=*.py`) + 관련 테스트 확인 후에만 말한다. `head`/`tail` 로 자른 출력은 부재 증거가 아니다 | 잘린 grep 으로 "CSRF 미구현" 오판 | PM-011 |
| `docs/refactor/` 설계 문서와 코드가 다르면 **코드가 사실**이다. ADR 현행성은 `docs/guide/architecture.md` §8 표를 본다 | ADR-002·005·006 이 현재 배포와 다르다 | architecture §8 |
| ADR-008 회귀 매트릭스의 일부 테스트명은 실제와 다르다. 테스트명을 인용할 때는 `grep "def test_…"` 로 확인한다 | `test_restart_no_falsepositive.py` 등은 존재하지 않는다 | 감사 결과 |
| 성능 수정은 전후 측정(`Server-Timing` 헤더)을 남긴다 | 18.7초 원인이 "추정"으로만 남았다 | PM-010 |
| 서브에이전트·자동 리뷰의 결론은 코드로 재확인한 뒤 문서에 옮긴다 | 감리 오판이 문서에 기록된 적이 있다 | PM-011 |

## 8. Git · 협업

| 규칙 | 왜 | 근거 |
|---|---|---|
| 커밋 전에 `git status` / `git diff --stat` 를 보고 **내가 바꾼 파일만** 경로로 지정해 스테이징한다 | 여러 세션이 동시에 작업한다. 무관한 테스트 파일과 `data/logs.tsv` 가 노선도 커밋에 섞여 들어갔다(`177f444`) | PM-014 §7 |
| `data/logs.tsv` 는 추적되지만 런타임에 계속 바뀐다. 그 변경은 커밋하지 않는다 | 운영 로그가 커밋 노이즈가 된다 | architecture §4.2 |
| `data/*.json` 런타임 상태 파일(`*_status.json`, `govtrack_state.json`, `holiday_cache.json` 등)은 미추적이지만 ignore 도 아니다. 스테이징하지 않는다 | `git add -A` 한 번에 런타임 상태가 저장소로 들어간다 | architecture §4.2 |
| 한 커밋 한 목적. 부수 변경(경로·기본값 변경)은 커밋 메시지에 적는다 | compose Dockerfile 경로 변경이 메시지 없이 섞였다 | PM-012 §4 |
| 커밋 메시지는 한국어로 "무엇을·왜"를 적는다(기존 관례). 콘텐츠 변경은 출처(공지)와 시행일을 적는다 | 틀린 정보가 3번 정정됐다 | PM-014 |

## 9. 콘텐츠 · UI

| 규칙 | 왜 | 근거 |
|---|---|---|
| 노선 변경은 **공식 공지 원문**으로 정차 지점과 시행일을 확인한 뒤 편집한다 | 743 을 틀린 정류장으로 게시했다 | PM-014 |
| 노선 사실은 여러 곳에 복제되어 있다. `change-playbooks.md` §1 체크리스트로 전부 고친다 | 한 곳만 고치면 화면마다 말이 다르다 | PM-014 |
| 노선 색은 `style.css`, `timetable.css`, `route_diagram.COLORS` 3곳 동기화 | 화면마다 색이 달라진다 | ui-design §3.1 |
| 노선도 지도는 격자·45° 개략도다(PR #6). 옛 가로 레인·공유 박스 방식으로 되돌리지 않는다. 좌표를 바꾸면 `test_rough_geography` 와 브라우저 렌더(시행 전 경로 포함)를 함께 본다. `ROUTE_MAP_STOP_LINK` 값은 `SERACH_STOPS` 안 | 레인 SVG 는 라벨 겹침·박스가 사이 레인을 삼키는 문제로 3번 정정됐다. 좌표 배치는 테스트가 통과해도 라벨·pill 이 선을 덮을 수 있다 | PM-014, ui-design §6 |
| HTMX `outerHTML` swap 을 쓰면 응답 조각이 hx 속성을 다시 포함해야 한다 | `/unist` 자동 갱신이 첫 교체 후 멈춘다(미해결) | ui-design §7 |
| 새 공개 문구는 `t()` 로, ko·en 둘 다 넣는다 | 누락 키는 키 문자열이 그대로 화면에 나온다 | ui-design §5 |
| 변경이력은 `data/changelog.json`(라이브)을 고친다. `static/data/changelog.json` 은 시드 | 시드는 2025-08 이후 갱신되지 않는다 | architecture §4.2 |
| 외부 CDN 을 추가하지 않는다. 벤더링한다 | 오프라인·저사양 환경, `/lite` 원칙 | ui-design §1 |
