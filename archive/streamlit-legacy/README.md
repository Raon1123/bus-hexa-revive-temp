# Streamlit 레거시 아카이브

Flask 기반 `bushexa/` 패키지로 이관되기 전의 Streamlit 앱과 그 실행 환경입니다.
운영/테스트 대상이 아니며 참고용으로만 보관합니다. (pytest `norecursedirs`에서 제외)

- `app.py`, `infopages/`, `src/`, `crawl/` — Streamlit UI · 크롤러 · govtrack 폴링
- `timetable/` — 레거시 시간표 원본(JSON/xlsx). 현행 데이터는 `data/timetable/`
- `Dockerfile`, `docker-compose.yaml`, `podman-compose.yaml`, `requirements.yaml`, `run.sh`, `runscript.sh`, `postgres.sh` — 레거시 배포 스크립트 (postgres 기반)

현행 배포: 루트 `compose.podman.yaml` / `docker/compose.yaml` (README.md 참고).
