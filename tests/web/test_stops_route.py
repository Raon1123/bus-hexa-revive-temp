"""W5 테스트: stops route + 캐시 (F06, TP-003).

테스트 의도:
  test_stops_ok      — GET /stops → 200, 정류장 선택 셀렉터 포함
  test_cache_hit     — 같은 stop_id 10초 내 두 번 partial 요청 → domain 1회만 호출
  test_cache_expires — FakeClock으로 11초 경과 → 캐시 만료, domain 재호출

E-13 준수: 기대값은 hand-built StopSnapshot 에서 독립적으로 정해짐.
캐시 만료 테스트는 FakeClock advance로 11초 경과를 시뮬레이션.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from bushexa.domain.stops import BusArrivalRow, StopSnapshot
from bushexa.services import stop_cache as cache_mod
from bushexa.web.app import create_app

KST = ZoneInfo("Asia/Seoul")
_STOP_ID = "196040234"


# ---------------------------------------------------------------------------
# Known test fixture — E-13 독립 출처
# ---------------------------------------------------------------------------

_KNOWN_ROW = BusArrivalRow(
    bus_number="713",
    direction_str="명촌 (시내) 방면",
    arrival_str="5분 30초",
    arrival_seconds=330,
    present_stop="천상 (시내)",
    vehicle_no="TEST-001",
)

_MOCK_SNAPSHOT = StopSnapshot(
    stop_id=_STOP_ID,
    stop_name="울산과학기술원 (경유)",
    rows=[_KNOWN_ROW],
    has_no_bus=False,
    long_gap=False,
    error=None,
    minutes_until=[5],
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """각 테스트 전후 캐시 초기화 — 전역 singleton 오염 방지."""
    cache_mod.clear_cache()
    yield
    cache_mod.clear_cache()


@pytest.fixture
def app(app_config_test):
    return create_app(app_config_test)


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# AC-1 — GET /stops → 200 + 정류장 선택 셀렉터
# ---------------------------------------------------------------------------

def test_stops_ok(client):
    """GET /stops가 200이고 정류장 선택 셀렉터가 있는지 검증.

    독립 출처: P4 W5 AC-1, TP-003 §2 명세.
    """
    resp = client.get("/stops")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    html = resp.data.decode("utf-8")
    # 정류장 선택 셀렉터 확인
    assert "stop-select" in html, "stop-select element missing from /stops response"
    # SERACH_STOPS의 첫 번째 stop_id가 option으로 있는지
    assert _STOP_ID in html, f"stop_id {_STOP_ID} not listed in selector"


# ---------------------------------------------------------------------------
# AC-2 — 10초 내 재요청 캐시 적중 (domain 1회만 호출)
# ---------------------------------------------------------------------------

def test_cache_hit(client):
    """같은 stop_id로 10초 내 두 번 partial 요청 시 domain이 1회만 호출되는지 검증.

    독립 출처: P4 W5 AC-2, F06 §2.3 캐시 10초 기준.
    측정: mock get_stop_data 의 call_count == 1.
    """
    call_count = 0

    def fake_get_stop_data(stop_id, clock, *, client):
        nonlocal call_count
        call_count += 1
        return _MOCK_SNAPSHOT

    with patch("bushexa.web.routes.stops.get_stop_data", side_effect=fake_get_stop_data):
        resp1 = client.get(f"/partial/stops?stop_id={_STOP_ID}")
        resp2 = client.get(f"/partial/stops?stop_id={_STOP_ID}")

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert call_count == 1, (
        f"get_stop_data called {call_count} times; expected 1 (cache hit on 2nd request)"
    )


# ---------------------------------------------------------------------------
# test_cache_expires — FakeClock 11초 경과 → 캐시 만료
# ---------------------------------------------------------------------------

def test_cache_expires():
    """FakeClock으로 11초 경과시키면 캐시가 만료되어 재조회하는지 검증.

    독립 출처: P4 W5 테스트 의도 — "FakeClock으로 11초 경과시키면 재조회".
    이 테스트는 stop_cache 모듈을 직접 단위 테스트함 (route 통과 불필요).
    """
    # FakeClock: 시각을 수동으로 조작
    class AdvanceClock:
        def __init__(self, start: datetime):
            self._now = start

        def now(self) -> datetime:
            return self._now

        def advance(self, seconds: float):
            self._now = self._now + timedelta(seconds=seconds)

    start = datetime(2026, 6, 1, 8, 30, 0, tzinfo=KST)
    clock = AdvanceClock(start)

    call_count = 0

    def fetch_fn(stop_id: str):
        nonlocal call_count
        call_count += 1
        return _MOCK_SNAPSHOT

    # 첫 번째 호출 — 캐시 미스
    result1 = cache_mod.get_or_fetch(_STOP_ID, fetch_fn, clock)
    assert call_count == 1, "First call should fetch"

    # 5초 경과 — 캐시 유효 (TTL 10초)
    clock.advance(5)
    result2 = cache_mod.get_or_fetch(_STOP_ID, fetch_fn, clock)
    assert call_count == 1, "5s later: should still use cache"

    # 11초 경과 (총 16초) — 캐시 만료
    clock.advance(11)
    result3 = cache_mod.get_or_fetch(_STOP_ID, fetch_fn, clock)
    assert call_count == 2, "11s later (TTL expired): should refetch"
