#!/usr/bin/env bash
# scripts/recrawl_rail.sh — 운영 컨테이너 안에서 KTX·동해선 시간표를 지금 다시 받는다(bushexa crawl-rail).
#
# 배포 루트(docker/compose.yaml 이 있는 곳)에서:
#   scripts/recrawl_rail.sh              # 오늘부터 14일치
#   scripts/recrawl_rail.sh --days 7     # 일수 지정
#
# 평소에는 worker-cache-refresh 가 매일 02~03시에 받는다. 배포 직후·정차역이 비었을 때만 쓴다.
# 실패한 날짜·구간·정차역은 기존 값을 유지한다(PM-008, PM-017). TAGO 열차정보 호출 약 300회.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export CONTAINERS_CONF_OVERRIDE="${CONTAINERS_CONF_OVERRIDE:-$ROOT/containers.conf}"
exec ${COMPOSE:-podman-compose} -f "$ROOT/docker/compose.yaml" exec -T app python -m bushexa crawl-rail "$@"
