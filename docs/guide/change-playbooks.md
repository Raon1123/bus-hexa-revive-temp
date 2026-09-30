---
status: living
last_verified: 2026-09-29 (HEAD 8dc582e)
audience: 반복되는 변경 작업을 수행하는 사람·AI 세션
---

# 작업별 체크리스트 (Change Playbooks)

> 자주 하는 변경마다 "함께 고쳐야 하는 곳"을 모았다. 빠뜨리면 화면마다 말이 달라지거나 운영에서 깨진다.
> 이유와 사례는 [pitfalls.md](pitfalls.md) 참고.

## 1. 노선·경유지 변경 반영 (예: 743 구영리 경유)

**0단계: 사실 확정 (편집 전에)**

- [ ] 울산시·버스회사 **공지 원문**을 확보한다. 정확한 정차 정류장(이름 + 가능하면 정류장 ID), 방향, **시행일**을 적어 둔다.
- [ ] 같은 지역을 지나는 다른 노선과 **같은 정류장인지, 같은 도로인지** 확인한다(743 은 "구영"이 아니라 513 과 같은 "범서중학교"였다).

**1단계: 데이터·화면 (한 커밋에)**

| # | 파일 | 무엇을 |
|---|---|---|
| 1 | `bushexa/data/constants.py` `VIA_STOPS[노선][종점]` | 게시판 경유지 문구. 관리자 override(`data/via_overrides.json`)가 있으면 그것이 우선하므로 확인 |
| 2 | `bushexa/data/constants.py` `ROUTEID`(UNIST 노선)·`EXTRA_TRACKED_ROUTES`(수집 전용, 예: 1224), `STOP_IDS`, `SERACH_STOPS` | 정류장이 새로 생기거나 추적 대상이 바뀌는 경우만 |
| 3 | `bushexa/web/route_diagram.py` `NODES`, `LINE_PATHS`, `ROUTE_CHANGES`, `STOP_NOTE` (+ `route_lines.STOP_LABEL`, `constants.ROUTE_MAP_STOP_LINK`) | 노선도(지도·목록 공용 데이터). 정차 지점이 다르면 다른 노드, 선은 가로·세로·45°, 링크 stop_id 는 `SERACH_STOPS` 안(ui-design §6) |
| 4 | `bushexa/web/templates/info.html` | "For Destination" 표, "For Bus Number" 노선 표, 안내 배너(한/영) |
| 5 | `data/changelog.json` | `{"date":"YYYY-MM-DD","description":"…"}` 를 **맨 뒤**에 추가(오래된 순). 파일 끝 개행 없음 |
| 6 | `/admin/notices` (운영 중) 또는 `bushexa/data/notices.seed.json` (배포 기본값) | 공지가 필요하면 **기한형 공지**로 넣는다: 표시 기간(`show_until` 필수 권장), 시행일(`effective_from` → 시행 후 문구), 대상 노선·화면. 문구에 날짜를 박지 말고 `{date}` 를 쓴다. 템플릿·i18n 에 공지 문구를 하드코딩하지 않는다 |
| 7 | (확인) | 공지는 공통 레이아웃이 모든 공개 화면(`/lite` 포함)에 그린다. 게시판·UNIST·정류소 화면은 공지 영역을 60초마다 갱신. `/admin/notices?at=YYYY-MM-DDTHH:MM` 로 시행 전·후 문구를 미리 본다. 운영 중 편집본이 있으면 seed 변경은 자동 반영되지 않으니 관리 화면의 '기본 공지 가져오기'를 쓴다 |
| 8 | `data/timetable/<노선>.json` | 시간표가 바뀌면 관리자 재크롤 또는 편집(`/admin/timetable`) |
| 9 | `constants.KTX_LEGS`·`KTX_JINMOK_*_FEEDERS`·`KTX_LEG_PROXIES`, `data/ktx_leg_profile.json` | **513·713·743·753·5001** 정류장·경로가 바뀌면 구간 정의를 고치고, 새 경로 통과기록이 쌓인 뒤 `bushexa build-leg-profile --tsv … [--db …]` 로 `/ktx` 소요 프로필을 다시 만든다(그 전까지는 옛 경로 소요로 계산됨을 안내) |

**2단계: 시행일**

- [ ] 시행일이 미래면 `route_diagram.ROUTE_CHANGES` 에 `RouteChange(노선, 시행일, old, new, summary)` 를 추가한다(`LINE_PATHS` 는 새 경로). 목록 예고·`/info` 배너는 자동. 경계일 전후 테스트를 추가한다. 날짜는 KST.
- [ ] 공지는 기한형 공지의 `effective_from`(시행일)·`text_after`(시행 후 문구)·`show_until`(표시 종료)로 처리한다. 날짜 게이트가 없는 정적 텍스트(VIA_STOPS, info)에만 "10/3부터"처럼 시행일을 적는다.
- [ ] 시행일이 지나 안정되면 게이트와 "부터" 문구를 정리하는 후속 작업을 남긴다.

**3단계: 검증**

- [ ] `uv run python -m pytest tests/web/test_route_diagram.py tests/web/test_route_map_page.py tests/web/test_info_route.py -q`
- [ ] 서버를 띄워 `/info` 를 **눈으로** 본다. 지도(`?view=a`): 라벨·번호 pill·철도가 선과 겹치지 않는지, 시행 전 경로도. 목록(`?view=b`): 순서·표시명·링크.
- [ ] `/board`, `/unist` 공지와 경유지 문구를 확인한다. `/admin/notices?at=<시행일>T00:00` 으로 시행 후 문구를 미리 본다. `?lang=en` 도 본다.
- [ ] 커밋 메시지에 공지 출처와 시행일을 적는다.

## 2. 공개 페이지 추가

- [ ] `bushexa/web/routes/<name>.py` 블루프린트 → `web/app.py` 에 `register_blueprint`.
- [ ] 로직은 `domain/<name>.py` 순수 함수(client·clock 주입). 라우트는 얇게.
- [ ] 도착정보는 `services/board_support.arrival_client()`, 시간표는 `timetable_provider_for()` 만 쓴다(직접 API·`get_timetable` 호출 금지).
- [ ] 공지를 받으려면 `services/notices.py` 의 `ENDPOINT_SURFACES`·`SURFACES` 에 endpoint→surface 를 추가한다(HTMX 부분 갱신만 하는 화면이면 `POLL_SURFACES` 에도).
- [ ] 템플릿은 `_base.html` 상속. 사이드바는 `_base.html` 의 `nav_groups` 에 `(endpoint, 이모지, t('nav.<key>'))` 추가 + i18n 키.
- [ ] 자동 갱신이 필요하면 조각 템플릿 + `/partial/<name>` 엔드포인트. 전체 페이지는 같은 조각을 include. `outerHTML` 이면 조각이 hx 속성을 포함.
- [ ] API·캐시 실패 시 오류 배너 + fallback, 500 금지.
- [ ] 테스트: `tests/web/test_<name>_route.py`(200, 빈 상태, 실패 fallback), `tests/web/test_routes_smoke.py` 에 추가.
- [ ] 상호작용 명세가 필요하면 `docs/refactor/touchpoints/TP-NNN-*.md` 를 쓰고 INDEX 등재.

## 3. 외부 API 호출 추가·변경

- [ ] `api_clients/` 에 메서드 추가. 전송은 `_http.get_with_service_key`, timeout 은 `resolve_api_timeout`.
- [ ] 본문 resultCode 검사 → 타입 예외. XML 은 bytes 파싱. TAGO 목록은 `_items_as_list`.
- [ ] 호출자는 **워커**여야 한다(공개 라우트 금지). 결과는 DB 캐시나 atomic 파일로.
- [ ] 실패 시 기존 캐시 보존. 빈 결과로 덮어쓰지 않는다.
- [ ] 일일 호출량을 계산해 [api-usage.md](api-usage.md) §3 표에 추가한다.
- [ ] 실응답을 키를 지우고 `tests/fixtures/<provider>/` 에 저장. 정상·빈·오류 XML 세 가지 테스트.
- [ ] 새 시크릿이나 쿼리스트링 인증 형식이면 `bushexa/redact.py` 패턴과 `tests/unit/test_redact.py` 를 갱신한다(PM-016).

## 4. 설정값(환경변수) 추가

- [ ] `BUSHEXA_` 접두. 읽는 곳은 `config.py` 또는 해당 모듈의 `_resolve_*` 함수 하나.
- [ ] 우선순위는 명시 인자 > env > 기본값. **CLI 인자 기본값이 env 를 가리지 않게** 한다(`--poll` 기본값을 `None` 으로 두고 내부에서 해석). `BUSHEXA_ARRIVAL_POLL_SECONDS` 가 이 실수로 무효다.
- [ ] 잘못된 값은 부팅 시 `ConfigError` 로 빠르게 실패(ADR-013).
- [ ] `.env.example`, `README.md` 설정 표, `docs/guide/architecture.md` §7 표 갱신.
- [ ] 테스트: 기본값, env override, 명시 인자 우선.

## 5. 관리자 편집 기능·런타임 데이터 파일 추가

- [ ] 파일은 `data/` 아래. 읽기 `fileio.read_json(default=…)`, 쓰기 `atomic_write_json`, 여러 워커가 read-modify-write 하면 `locked_update_json`.
- [ ] 라우트: `@login_required`, 폼에 `csrf_token`, POST → flash → redirect, 파괴적 버튼은 confirm.
- [ ] `_audit(action, **details)` 로 감사 기록(값 전체가 아니라 요약).
- [ ] 관리자가 편집한 설정이면 `services/backup.py` 화이트리스트에 추가. transient 파일은 제외.
- [ ] git 추적 여부 결정: 콘텐츠면 추적, 런타임 상태·시크릿이면 `.gitignore` 에 추가하고 `git check-ignore` 로 확인.
- [ ] `docs/guide/architecture.md` §4.2 표에 한 줄.
- [ ] 크로스 워커 테스트(앱 인스턴스 2개)로 공유가 되는지 확인.

## 6. 배포 · 코드 갱신

```bash
# 코드만 바뀜 (bushexa/ 는 ro bind-mount)
podman compose -f docker/compose.yaml restart app
# 의존성·Dockerfile·docker/ 변경
podman compose -f docker/compose.yaml up -d --build
# 확인
podman compose -f docker/compose.yaml exec app supervisorctl -c /app/docker/supervisord.conf status
curl -sf http://localhost:8017/lite >/dev/null && echo OK
```

- [ ] 서버의 `.env`, `secret/`, `data/`, `logs/` 는 덮어쓰지 않는다.
- [ ] 번들은 README.txt 절차 + 시크릿 검사 grep.
- [ ] 스키마 변경이 있으면 `init-db` 는 멱등이지만, 기존 데이터에 UNIQUE 인덱스 생성 실패 같은 경우가 있으니 로그를 확인한다.

## 7. 버그를 고쳤을 때 (부검)

`docs/refactor/00-workflow.md` §8 트리거(운영 오작동, 비자명 버그, 테스트가 못 잡은 회귀, 데이터 오염, 보안 약점, 30분 이상 디버깅)에 해당하면:

- [ ] `docs/refactor/templates/postmortem-template.md` 복사 → `docs/refactor/postmortems/PM-NNN-<slug>.md`(다음 번호).
- [ ] 근본 원인 + 재발 방지(회귀 테스트 경로::이름 + 의도 1줄) 필수.
- [ ] `postmortems/INDEX.md` 에 한 줄.
- [ ] 일반화 가능한 교훈이면 [pitfalls.md](pitfalls.md) 해당 절에 규칙 한 줄 + PM 링크.

## 8. 문서 유지 규칙

| 바뀐 것 | 갱신할 문서 |
|---|---|
| 모듈 구조, 프로세스, 저장소, 불변식 | `docs/guide/architecture.md` |
| API 엔드포인트, 호출량, 이상동작 | `docs/guide/api-usage.md` |
| CSS 토큰, 컴포넌트, 템플릿 구조, 노선도 규칙 | `docs/guide/ui-design.md` |
| 새 실수 유형 | `docs/guide/pitfalls.md` + PM |
| 반복 작업 절차 | 이 문서 |
| 큰 설계 결정 | `docs/refactor/architecture/ADR-NNN-*.md`(템플릿 사용) + architecture.md §8 표 |
| 명령·진입점·핵심 규칙 | 루트 `CLAUDE.md` |

- 각 문서 머리의 `last_verified` 를 갱신한다.
- 문서와 코드가 다르면 코드를 사실로 보고 문서를 고친다.
