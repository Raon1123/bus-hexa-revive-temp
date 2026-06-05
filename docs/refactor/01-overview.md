# Refactor Overview

## 배경

`bus-hexa-revive-temp`은 UNIST 통학·시내버스 정보를 안내하는 사이트로, 현재 Streamlit + Docker(Conda) 스택 위에 동작한다. 운영 중 다음 마찰들이 누적되었다.

- **무거운 conda 환경 (140+ 패키지)** — `pyarrow`, `arrow-cpp`, AWS SDK 등이 conda 의존성으로 끌려와 Dockerfile 빌드가 느리고 이미지 크기가 크다.
- **Streamlit 종속 안티패턴** — `src/crawl.py:326,401`에서 비-UI 모듈이 `import streamlit`을 호출, 컨텍스트 외 실행 시 깨진다.
- **로컬 개발 진입장벽** — `podman-compose up`을 강제, 단순 코드 확인에도 컨테이너 한 세트 필요.
- **실시간 UX 부재** — 출발 게시판·정류장 도착정보 등 본질적으로 폴링 기반인 화면이 사용자 수동 새로고침에 의존.
- **하드코딩 자원** — 10.89.0.1 Podman bridge IP, `WhenMyBusRun` 평문 비밀번호가 추적되는 compose 파일에 노출.

## 리팩토링 목표

1. **Streamlit 제거** — 모든 UI를 Flask + Jinja2 + Vanilla JS + HTMX/SSE 스택으로 이전.
2. **로컬 실행 간편화** — `uv run bushexa serve` 한 줄로 풀스택 가동 가능.
3. **컨테이너 배포 유지** — 운영 서버는 podman-compose로 계속 관리. Dockerfile은 slim Python 기반(conda 제거)으로 재작성. 컴포즈 파일 하나로 dev/prod 분기.
4. **데이터베이스 dual-backend** — 기본 SQLite (개발/단일 호스트), 환경변수로 PostgreSQL 전환 가능 (운영). `crawl/db.py`를 repository 패턴으로 추상화.
5. **실시간 UX 도입** — `departure_board`, `stops`, `unist_board`에 SSE/주기적 HTMX 갱신 추가.
6. **시크릿 위생** — credential을 compose 파일에서 환경변수/`secret/` 디렉토리로 이전, `.env.example` 제공.
7. **govtrack 로그 수집 정확성 회복** — 현재 "버스가 지나간 기록이 제대로 안 남는다"는 핵심 결함을 진단·재설계. 폴링 sampling rate, in-memory state 휘발성, 예외 격리, KeyError 안전성, DB commit 정책 전부 재검토. pytest로 회귀 보호.
8. **관리자 페이지 승격** — `?hexa=6` 숨김 진입 제거, 인증 보호된 정식 `/admin` 라우트로. 기능 확장:
   - bus_timelog 수동 조회 (route_id/stop_id/vehicle/날짜 필터, 페이지네이션, CSV export)
   - govtrack 데몬 상태(마지막 poll 성공시각/실패 횟수) 모니터
   - 시간표 JSON **직접 편집**(시간 추가/삭제/이동) + 검증 + 저장
   - 시간표 재크롤 트리거 (vacation 모드)
   - 비밀번호 재설정
9. **테스트 자동화 (특히 crawling)** — pytest로 (a) API client 응답 fixture, (b) parse_busloc 단위, (c) busloc_status 상태머신, (d) 폴링 sampling 시뮬레이션, (e) 시간표 JSON 스키마 검증, (f) DB repository CRUD 까지 망라. CI 진입 가능한 수준.

## 비-목표 (Out of Scope)

- 외부 API 공급자 변경 (국토부 TAGO, 울산 BIS 그대로 사용).
- 데이터 모델 확장 — `bus_timelog` 테이블 스키마는 유지 (다만 의미 없는 컬럼 정리는 허용).
- 신규 노선/정류장 추가 — `src/constants.py` 데이터 그대로.
- 모바일 앱 / SPA — 본 리팩토링은 서버 사이드 렌더링 + 부분 HTMX로 한정.

## 제약 조건

- **무중단 마이그레이션 불필요** — 현 서비스는 실험적, 배포 후 cutover로 충분.
- **데이터 마이그레이션 부담 낮음** — 현 `postgres-data/`가 거의 비어있음 (4KB).
- **Python 3.12 기반 유지** — 현 conda 환경과 동일.
- **타임존 KST 고정** — 정류장·시간표 계산이 KST 기준.
- **공공 API 키 비공개** — `secret/key.txt`는 git 추적 금지, `.env`도 동일.

## 신규 디렉토리 윤곽 (목표 상태)

```text
bus-hexa-revive-temp/
├── pyproject.toml           # uv 관리, [project.scripts] bushexa=...
├── uv.lock
├── .env.example
├── docker/
│   ├── Dockerfile           # python:3.12-slim + uv 기반, 단일 스테이지
│   └── compose.yaml         # 운영용 (앱 + postgres optional)
├── bushexa/                 # 신규 패키지 루트 (src/ + crawl/ + infopages/ 통합)
│   ├── __init__.py
│   ├── __main__.py          # `python -m bushexa` 엔트리
│   ├── cli.py               # `serve`, `crawl-once`, `crawl-loop`, `init-db` 서브커맨드
│   ├── config.py            # env 기반 설정
│   ├── data/                # constants, timetable JSON 로딩
│   ├── api_clients/         # MoLIT, Ulsan BIS, holiday clients
│   ├── db/                  # SQLite/Postgres dual-backend, schema, repos
│   ├── crawler/             # govtrack daemon, timetable crawl
│   ├── web/                 # Flask app
│   │   ├── app.py
│   │   ├── routes/          # /board, /busno, /info, /stops, /running, /admin, /sse/*
│   │   ├── templates/       # Jinja2
│   │   ├── static/          # JS, CSS, favicon, media
│   │   └── services/        # UI에서 호출하는 도메인 서비스
│   └── tests/
├── secret/                  # gitignored
├── data/                    # SQLite db file (gitignored), timetable JSON (tracked)
├── timetable/               # 기존 위치 유지 가능 (data/ 로 이동도 고려)
├── docs/
│   └── refactor/            # 본 디렉토리
└── README.md
```

## 마이그레이션 전략

- **Stage 0**: 신규 디렉토리는 **만들지 않는다**. 우선 문서만 작성.
- **Stage 1**: ADR 확정 후 비파괴적 골격(`bushexa/` 패키지 빈 트리 + `pyproject.toml`)만 추가. 기존 코드는 그대로 동작.
- **Stage 2**: 데이터/API client 레이어 이전 (UI 무관). 기존 Streamlit과 신규 패키지가 동일 함수 호출하도록 shim.
- **Stage 3**: Flask 라우트·템플릿을 페이지 단위로 이전. 각 페이지가 완료될 때마다 Streamlit 페이지를 제거 가능.
- **Stage 4**: govtrack/timetable-crawl을 신규 CLI로 이전. `runscript.sh` → `docker/compose.yaml`이 새 CLI 호출.
- **Stage 5**: 기존 `app.py`, `infopages/`, `src/`, `crawl/` 제거. README 갱신.

## 성공 기준 (Acceptance)

- [ ] `uv sync && uv run bushexa serve`만으로 로컬에서 풀 UI 동작
- [ ] `podman-compose -f docker/compose.yaml up`으로 운영 배포 가능 (dev override 옵션 포함)
- [ ] 기존 7개 페이지 모두 시각·기능 동등 (HTMX/SSE로 자동 갱신 추가는 +α)
- [ ] govtrack 데몬이 SQLite/Postgres 양쪽으로 정상 기록 + 재시작 후 false-positive 폭주 없음
- [ ] govtrack 결함 5종 모두 회귀 테스트로 보호 (pytest 통과)
- [ ] 관리자 페이지: 로그인, 데이터 조회(필터+페이지네이션+CSV), 데몬 상태, 시간표 편집, 재크롤, 비밀번호 재설정 동작
- [ ] 모든 시크릿이 env 또는 `secret/`에서 로드, compose 파일에 평문 없음 (`.env.example` 제공)
- [ ] `tests/` pytest suite 통과 — crawler 핵심 케이스 ≥10건, repository ≥6건, 라우트 smoke ≥7건
- [ ] `docs/refactor/` 전 문서 Auditor PASS
