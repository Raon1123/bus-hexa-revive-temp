"""W8 테스트: running route (F05, TP-006).

테스트 의도:
  test_grid_rendered  — in-memory SQLite 시드 + /running → 200 + 운행 그리드
  test_no_data        — 로그 없음 → 200 + "검색된 버스가 없습니다"
  test_bad_date_handled — ?date=abc → 200 (기본값 폴백 또는 400), 500 아님

E-13 준수: 기대값은 직접 시드한 알려진 데이터 + 알려진 ROUTEID 상수에서.
W8 SQLite 격리: app_config에 file-based tmp SQLite를 사용해야 route와 같은 DB를 본다.
(sqlite:///:memory: 는 연결마다 새 DB → route 쪽 연결이 빈 DB를 보게 됨)
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from bushexa.config import AppConfig
from bushexa.data.constants import ROUTEID
from bushexa.db.repo import BusLogRepo
from bushexa.db.schema import create_schema
from bushexa.web.app import create_app

# ---------------------------------------------------------------------------
# 테스트용 노선·날짜·정류소 상수
# ---------------------------------------------------------------------------

# ROUTEID에서 '713 UNIST 출발' 노선 선택
_ROUTE_ID = "195000178"  # 713 명촌 방면, departure=UNIST
_BUSNO, _TERMINAL, _DEP, _STOPS = ROUTEID[_ROUTE_ID]
# 알려진 시드 데이터: 첫 두 정류소 통과 (2026-06-01)
_DATE = date(2026, 6, 1)
_DATE_STR = "20260601"
_VEHICLE = "TEST-713-001"


def _seed_db(db_path: Path) -> None:
    """SQLite 파일에 bus_timelog 테이블을 생성하고 알려진 로그를 시드한다."""
    conn = sqlite3.connect(str(db_path))
    create_schema(conn)
    repo = BusLogRepo(conn)
    # 첫 번째 정류소
    repo.insert_log(
        idx=f"{_DATE_STR}_08:30:00",
        stop_id=_STOPS[0],
        route_id=_ROUTE_ID,
        vehicle_no=_VEHICLE,
        stop_name="UNIST 기점",
    )
    # 두 번째 정류소
    repo.insert_log(
        idx=f"{_DATE_STR}_08:32:00",
        stop_id=_STOPS[1],
        route_id=_ROUTE_ID,
        vehicle_no=_VEHICLE,
        stop_name="정류소2",
    )
    conn.close()


@pytest.fixture
def db_app(tmp_path, tmp_sqlite_db):
    """file-based SQLite DB를 시드하고, 그 경로를 database_url로 쓰는 app을 반환."""
    from zoneinfo import ZoneInfo
    _seed_db(tmp_sqlite_db)
    config = AppConfig(
        api_key="test-api-key",
        database_url=f"sqlite:///{tmp_sqlite_db}",
        session_secret="test-secret",
        manager_password_path=tmp_path / "pw.txt",
        data_dir=tmp_path / "data",
        tz=ZoneInfo("Asia/Seoul"),
        log_level="DEBUG",
        log_dir=tmp_path / "logs",
    )
    return create_app(config)


@pytest.fixture
def db_client(db_app):
    return db_app.test_client()


@pytest.fixture
def empty_db_app(tmp_path, tmp_sqlite_db):
    """시드 없는 빈 SQLite DB를 쓰는 app."""
    from zoneinfo import ZoneInfo
    conn = sqlite3.connect(str(tmp_sqlite_db))
    create_schema(conn)
    conn.close()
    config = AppConfig(
        api_key="test-api-key",
        database_url=f"sqlite:///{tmp_sqlite_db}",
        session_secret="test-secret",
        manager_password_path=tmp_path / "pw.txt",
        data_dir=tmp_path / "data",
        tz=ZoneInfo("Asia/Seoul"),
        log_level="DEBUG",
        log_dir=tmp_path / "logs",
    )
    return create_app(config)


@pytest.fixture
def empty_client(empty_db_app):
    return empty_db_app.test_client()


# ---------------------------------------------------------------------------
# AC-1 — 시드 로그로 /running → 200 + 운행 그리드
# ---------------------------------------------------------------------------

def test_grid_rendered(db_client):
    """in-memory SQLite에 운행 로그를 시드하고 /running 호출 시 정류장×회차 그리드가 렌더되는지.

    독립 출처: _seed_db 에서 직접 삽입한 알려진 데이터.
    기대값: running-table 클래스 테이블 + 시드된 차량번호.
    """
    resp = db_client.get(f"/running?route_id={_ROUTE_ID}&date={_DATE_STR}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    html = resp.data.decode("utf-8")
    assert "running-table" in html, "running-table class missing from grid response"
    # 시드된 통과 시각이 표시돼야 한다
    assert "08:30" in html, "Seeded stop time 08:30 not in HTML"


# ---------------------------------------------------------------------------
# 날짜 picker — <input type="date">가 제출하는 YYYY-MM-DD 형식 처리
# ---------------------------------------------------------------------------

def test_grid_rendered_dashed_date(db_client):
    """YYYY-MM-DD(date picker 제출 형식)도 YYYYMMDD와 동일하게 그리드를 렌더하는지.

    독립 출처: _seed_db의 알려진 데이터(2026-06-01).
    """
    resp = db_client.get(f"/running?route_id={_ROUTE_ID}&date=2026-06-01")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    html = resp.data.decode("utf-8")
    assert "running-table" in html, "running-table missing for dashed date"
    assert "08:30" in html, "Seeded stop time 08:30 not in HTML for dashed date"


# ---------------------------------------------------------------------------
# AC-2 — 로그 없음 → 200 + "검색된 버스가 없습니다"
# ---------------------------------------------------------------------------

def test_no_data(empty_client):
    """해당 날짜·노선에 로그 없을 때 500 아니라 200 + 안내 메시지.

    독립 출처: P4 W8 AC-2, F05 §1 엣지케이스 — "검색된 버스가 없습니다".
    """
    resp = empty_client.get(f"/running?route_id={_ROUTE_ID}&date={_DATE_STR}")
    assert resp.status_code == 200, f"Expected 200 not 500, got {resp.status_code}"
    html = resp.data.decode("utf-8")
    assert "검색된 버스가 없습니다" in html, (
        '"검색된 버스가 없습니다" message not found in empty-data response'
    )


# ---------------------------------------------------------------------------
# test_bad_date_handled — ?date=abc → 200 (폴백), 500 아님
# ---------------------------------------------------------------------------

def test_bad_date_handled(empty_client):
    """?date=abc 같은 잘못된 형식이 400 또는 기본값 폴백 + 경고로 처리되는지 검증.

    독립 출처: P4 W8 테스트 의도 — 잘못된 date 형식은 500 회피.
    """
    resp = empty_client.get(f"/running?route_id={_ROUTE_ID}&date=abc")
    # 400 또는 200(기본값 폴백) 모두 허용 — 500은 아니어야 한다
    assert resp.status_code in (200, 400), (
        f"Expected 200 or 400 for bad date, got {resp.status_code}"
    )
    if resp.status_code == 200:
        html = resp.data.decode("utf-8")
        # 경고 배너 또는 빈 상태 메시지가 있어야 한다
        assert (
            "warning-banner" in html
            or "검색된 버스가 없습니다" in html
            or "날짜 형식" in html
        ), "No warning/fallback indication for bad date"
