#!/usr/bin/env bash
# scripts/smoke_compose.sh — compose 스모크 테스트
#
# 목적:
#   docker compose 기반 배포 환경이 올바르게 기동되는지 검증한다.
#   HTTP-200 체크는 독립 실행 가능.
#   실시간 피드 확인(live-feed)은 실제 BUSHEXA_API_KEY + 울산 BIS 네트워크가 필요하며
#   SMOKE_SKIP_FEED=1 환경변수로 건너뛸 수 있다.
#
# 사용법:
#   # 전체 실행 (API key + 네트워크 필요):
#   bash scripts/smoke_compose.sh
#
#   # HTTP-200 만 확인 (sandbox / CI 환경):
#   SMOKE_SKIP_FEED=1 bash scripts/smoke_compose.sh
#
# 운영자 전용 명령 (live-feed 부분):
#   docker compose -f docker/compose.yaml logs worker-govtrack | grep CycleStats
#   docker compose -f docker/compose.yaml logs worker-arrival  | grep -i 'upsert\|arrival'
#
# 종료 코드: 0=성공, 1=실패

set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker/compose.yaml}"
WEB_PORT="${WEB_PORT:-8017}"
WAIT_SECS="${WAIT_SECS:-15}"
SMOKE_SKIP_FEED="${SMOKE_SKIP_FEED:-}"

# --- 색상 출력 ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }
info() { echo -e "${YELLOW}[INFO]${NC} $*"; }

# --- 정리 함수 ---
cleanup() {
    info "compose down 중..."
    docker compose -f "$COMPOSE_FILE" down --timeout 10 2>/dev/null || true
}
trap cleanup EXIT

# --- 1. DB 스키마 초기화 + 단일 컨테이너 기동 ---
# SQLite 단일 백엔드라 별도 DB 서비스/헬스체크가 없다. 스키마는 init-db로 1회 생성
# (기존 스키마가 있으면 no-op). 그 뒤 supervisord가 web+worker를 한 컨테이너에서 띄운다.
info "DB 스키마 초기화 (init-db)..."
docker compose -f "$COMPOSE_FILE" run --rm --entrypoint python app -m bushexa init-db \
    || fail "init-db 실패. DATABASE_URL(=sqlite) / data 디렉토리 쓰기권한 확인 필요."
ok "init-db 완료"

# 단일 서비스 기동 (web + workers = supervisord)
info "app 컨테이너 기동 (web + workers via supervisord)..."
docker compose -f "$COMPOSE_FILE" up -d

# --- 2. 기동 대기 ---
info "${WAIT_SECS}초 대기 (web 초기화)..."
sleep "$WAIT_SECS"

# --- 3. HTTP-200 체크 (항상 실행) ---
info "HTTP 체크: /lite (경량 평문 HTML, 가장 빠른 헬스 신호)"
curl -sf "http://localhost:${WEB_PORT}/lite" -o /dev/null \
    || fail "/lite 가 HTTP 200을 반환하지 않음 (host port=${WEB_PORT})"
ok "/lite HTTP 200"

info "HTTP 체크: /board"
curl -sf "http://localhost:${WEB_PORT}/board" -o /dev/null \
    || fail "/board 가 HTTP 200을 반환하지 않음 (host port=${WEB_PORT})"
ok "/board HTTP 200"

info "HTTP 체크: /admin/login"
curl -sf "http://localhost:${WEB_PORT}/admin/login" -o /dev/null \
    || fail "/admin/login 이 HTTP 200을 반환하지 않음"
ok "/admin/login HTTP 200"

# --- 4. 실시간 피드 체크 (live-feed) ---
# SMOKE_SKIP_FEED=1 이면 건너뜀.
# 이 부분은 실제 BUSHEXA_API_KEY + 울산 BIS 네트워크가 필요한 OPERATOR 영역.
if [[ -n "$SMOKE_SKIP_FEED" ]]; then
    echo ""
    info "=== LIVE-FEED 체크 건너뜀 (SMOKE_SKIP_FEED=1) ==="
    info "운영 환경에서 아래 명령으로 직접 확인하세요(단일 app 컨테이너 통합 로그):"
    info "  docker compose -f $COMPOSE_FILE logs app | grep CycleStats        # govtrack"
    info "  docker compose -f $COMPOSE_FILE logs app | grep -i 'upsert\|arrival'  # arrival"
    echo ""
else
    echo ""
    info "=== LIVE-FEED 체크 (BUSHEXA_API_KEY + 울산 BIS 네트워크 필요) ==="

    # 단일 app 컨테이너의 통합 로그에서 두 워커 활동을 확인한다(supervisord가 prefix 부여).
    APP_LOGS=$(docker compose -f "$COMPOSE_FILE" logs app 2>&1)

    info "app 로그에서 govtrack CycleStats 검색..."
    if echo "$APP_LOGS" | grep -q "CycleStats"; then
        ok "worker-govtrack: CycleStats 발견"
    else
        fail "app 로그에 CycleStats 없음. API key 또는 네트워크 확인 필요."
    fi

    info "app 로그에서 arrival upsert 검색..."
    if echo "$APP_LOGS" | grep -qi "upsert\|arrival"; then
        ok "worker-arrival: arrival upsert 활동 발견"
    else
        fail "app 로그에 upsert/arrival 없음. API key 또는 네트워크 확인 필요."
    fi
fi

# --- 완료 ---
echo ""
ok "스모크 테스트 완료. 모든 체크 통과."
