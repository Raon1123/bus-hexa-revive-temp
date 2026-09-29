# bushexa — AI 작업 가이드 (모든 세션이 먼저 읽는 파일)

UNIST 경유 시내버스(513·713·743·753·1115)의 실시간 도착·시간표·운행 기록 웹 서비스.
Python 3.12 · Flask 3 · Jinja2 + HTMX · SQLite · uv · 단일 컨테이너(supervisord: web + 워커 3개).
문서·주석·커밋 메시지는 **한국어**가 관례다.

## 먼저 읽을 문서

| 작업 | 읽을 문서 |
|---|---|
| 무엇을 고치든 | [docs/guide/pitfalls.md](docs/guide/pitfalls.md) — 이 저장소에서 실제로 일어난 실수와 규칙 |
| 구조·데이터 흐름·불변식 | [docs/guide/architecture.md](docs/guide/architecture.md) |
| 국토부 TAGO·울산 BIS·특일정보 API, 크롤러 | [docs/guide/api-usage.md](docs/guide/api-usage.md) |
| 화면·CSS·템플릿·노선도·i18n | [docs/guide/ui-design.md](docs/guide/ui-design.md) |
| 노선 변경, 페이지·API·설정 추가, 배포, 부검 | [docs/guide/change-playbooks.md](docs/guide/change-playbooks.md) |
| 과거 결함 상세 | [docs/refactor/postmortems/INDEX.md](docs/refactor/postmortems/INDEX.md) |
| 설계 결정 원문(일부 낡음, 현행성은 architecture.md §8) | `docs/refactor/architecture/ADR-*.md` |

`docs/refactor/` 는 리팩터 당시 계획 문서다. **코드와 다르면 코드가 사실**이다.

## 명령

```bash
uv sync                                         # 의존성 (.venv)
uv run python -m pytest -q                      # 전체 테스트 (uv run pytest 가 "Failed to spawn" 이면 이 형태 또는 uv sync --reinstall)
DATABASE_URL=sqlite:///./data/bushexa.db uv run bushexa init-db
DATABASE_URL=sqlite:///./data/bushexa.db uv run bushexa serve --dev   # http://localhost:8000/board
uv run bushexa crawl-once --route 195000177 --dry-run                  # API 단발 점검 (키 필요)
podman compose -f docker/compose.yaml restart app                      # 운영: 코드만 바뀐 경우 (8017→8000)
```

## 구조 한눈에

```text
bushexa/
  api_clients/  외부 API 어댑터. 모든 호출은 _http.get_with_service_key 경유
  crawler/      워커: govtrack(TAGO 버스위치 15s) / arrival(울산 도착 7s) / cache-refresh(공휴일·시간표 일 1회)
  db/           SQLite: bus_timelog(통과 기록), bus_arrival_cache(도착정보 캐시)
  data/         constants.py(노선·정류장 ID와 문구의 유일한 출처), timetable.py
  domain/       순수 뷰모델 빌더 (web·db·api 를 import 하지 않음)
  services/     파일 기반 스토어·에디터, board_support(공개 화면 공통 배선)
  web/          Flask 팩토리·라우트·템플릿·i18n·route_diagram(노선도 SVG·경로 데이터)·route_lines(노선별 목록)
data/           런타임·콘텐츠 파일 (timetable/*.json, changelog.json 은 git 추적)
archive/        Streamlit 레거시 (수정 대상 아님)
```

## 절대 규칙

1. **공개 화면에서 외부 API 를 호출하지 않는다.** `services/board_support` 의 `arrival_client()`·`timetable_provider_for()` 만 쓴다(ADR-010).
2. **API 오류를 빈 결과로 만들지 않고, 실패 결과로 좋은 캐시·파일을 덮지 않는다.** HTTP 200 이어도 본문 resultCode 를 검사한다.
3. **파일 쓰기는 `bushexa/fileio.py` 만** 쓴다(`atomic_write_*`; 여러 프로세스가 고치는 파일은 `locked_update_json`).
4. **웹 상태를 프로세스 메모리에 두지 않는다.** gunicorn 워커가 2개 이상이다.
5. **시간은 `time_utils.KST` 와 주입된 `Clock`.** naive `datetime.now()`·`date.today()`·`ZoneInfo` 리터럴 금지.
6. **노선·정류장 ID와 문구는 `data/constants.py` 에만.** `STOP_IDS[...]` 대신 `.get`.
7. **데몬 루프는 예외로 죽지 않는다.** 잡은 예외는 반드시 로그한다(ADR-013).
8. **시크릿 커밋 금지:** `.env`, `secret/`, `data/manager_password.txt`, `data/bushexa.db*`, `data/debug/`. 예외 문자열·URL 을 로그나 파일에 남길 때 키 가림은 `bushexa/redact.py` 가 담당하며, 새 시크릿 형식이 생기면 그 패턴을 갱신한다.
9. **단위 테스트는 네트워크를 쓰지 않는다.** 테스트마다 자연어 의도 docstring 을 단다.

## 작업 방식

- **여러 세션·사람이 동시에 이 저장소를 고친다.** 시작할 때와 커밋 직전에 `git status` 를 보고, **내가 바꾼 파일만 경로로 지정해** 스테이징한다. `git add -A`·`git add .` 금지. `data/logs.tsv` 와 `data/*_status.json` 등 런타임 파일은 스테이징하지 않는다.
- **"없다/미구현"이라고 말하기 전에** 잘리지 않은 검색(`grep -rl … --include=*.py`)과 관련 테스트를 확인한다. `head` 로 자른 출력은 부재의 증거가 아니다.
- 노선·경유지 변경은 공식 공지로 **정차 정류장과 시행일**을 확정한 뒤 [change-playbooks §1](docs/guide/change-playbooks.md) 체크리스트대로 한 커밋에 반영하고, `/info` 노선도를 브라우저로 확인한다.
- UI 변경은 테스트 통과 후 브라우저로 확인한다. `?lang=en` 도 본다.
- 비자명 버그를 고치면 부검(`docs/refactor/postmortems/PM-NNN-*.md`)과 회귀 테스트를 쓰고, 교훈을 `pitfalls.md` 에 한 줄 추가한다.
- 구조·API·UI 규칙을 바꾸면 해당 `docs/guide/*.md` 를 같은 커밋에서 갱신한다.
- 이슈는 GitHub issue 번호로 참조한다(커밋 메시지 `Fixes #N` / `Refs #N`).

## 알려진 미해결 문제 (2026-09-29)

| 문제 | 문서 |
|---|---|
| 관리자 비밀번호 해시가 git 이력에 남아 있음 — 다음 배포 때 운영자가 비밀번호 교체 | PM-013, README.txt |
| 수정(PM-016) 이전 로그 파일에 API 키가 남아 있음 — 배포 때 1회 정리 | PM-016 §6.2 |
| 울산 도착정보 호출 실패가 "도착 버스 없음"으로 캐시·표시됨 | api-usage §4 |
| `/unist` HTMX 자동 갱신이 첫 교체 후 멈춤 | ui-design §7 |
| `BUSHEXA_ARRIVAL_POLL_SECONDS` 가 CLI 기본값에 가려 무효 | api-usage §4 |
| 새 DB `/lite` 회귀 테스트 없음 | PM-009 |
