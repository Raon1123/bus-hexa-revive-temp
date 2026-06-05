"""W12 테스트: admin data browser + CSV (F04, TP-008).

E-13 준수: 기대값은 직접 시드한 알려진 데이터 + repo.count() 독립 검증.
W8 패턴 적용: tmp_sqlite_db fixture로 in-memory가 아닌 파일 기반 SQLite 주입.

CSRF 처리: 세션에 토큰 직접 주입 후 사용.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from bushexa.config import AppConfig
from bushexa.db.repo import BusLogRepo
from bushexa.db.schema import create_schema
from bushexa.web.app import create_app

_KST = ZoneInfo("Asia/Seoul")
_ROUTE_ID = "195000177"   # 알려진 테스트용 노선 ID
_DAY = date(2026, 6, 1)
_DAY_STR = "20260601"

# ──────────────────────────────────────────────────
# 시드 데이터
# ──────────────────────────────────────────────────

def _seed_db(db_path: Path) -> None:
    """테스트 DB에 알려진 3개 로그를 시드한다."""
    conn = sqlite3.connect(str(db_path))
    create_schema(conn)
    repo = BusLogRepo(conn)
    # 노선 _ROUTE_ID, 날짜 _DAY, 차량 2대
    repo.insert_log(idx=f"{_DAY_STR}_08:00:00", stop_id="S001", route_id=_ROUTE_ID,
                    vehicle_no="VH-001", stop_name="정류소A")
    repo.insert_log(idx=f"{_DAY_STR}_08:05:00", stop_id="S002", route_id=_ROUTE_ID,
                    vehicle_no="VH-001", stop_name="정류소B")
    repo.insert_log(idx=f"{_DAY_STR}_09:00:00", stop_id="S001", route_id=_ROUTE_ID,
                    vehicle_no="VH-002", stop_name="정류소A")
    # 다른 날짜 로그 1건 (필터에서 제외되어야 함)
    repo.insert_log(idx="20260602_08:00:00", stop_id="S001", route_id=_ROUTE_ID,
                    vehicle_no="VH-001", stop_name="정류소A")
    conn.close()


# ──────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────

@pytest.fixture
def db_app(tmp_path, tmp_sqlite_db):
    """시드된 SQLite DB를 database_url로 쓰는 Flask app."""
    _seed_db(tmp_sqlite_db)
    pw_path = tmp_path / "manager_password.txt"
    pw_path.write_text("adminpassword123")   # legacy 평문
    config = AppConfig(
        api_key="test-api-key",
        database_url=f"sqlite:///{tmp_sqlite_db}",
        session_secret="test-secret",
        manager_password_path=pw_path,
        data_dir=tmp_path / "data",
        tz=_KST,
        log_level="DEBUG",
        log_dir=tmp_path / "logs",
    )
    return create_app(config)


@pytest.fixture
def authed_client(db_app, tmp_sqlite_db):
    """로그인 + CSRF 토큰이 주입된 test_client."""
    client = db_app.test_client()
    with client.session_transaction() as sess:
        sess["admin_authed"] = True
        sess["csrf_token"] = "test-csrf-token"
    return client, tmp_sqlite_db


# ──────────────────────────────────────────────────
# AC-1: 필터 결과 행 수 == repo.count()
# ──────────────────────────────────────────────────

def test_filter_count(authed_client):
    """route_id+day 필터 결과 행 수 = repo.count() 독립 검증.

    독립 출처: W12 AC-1, F04 §7 AC-D1.
    """
    client, db_path = authed_client

    # repo count — 독립 oracle
    conn = sqlite3.connect(str(db_path))
    with BusLogRepo(conn) as repo:
        expected_count = repo.count(route_id=_ROUTE_ID, day=_DAY)
    # 시드에서 3건 (동일 날짜 3건)
    assert expected_count == 3, f"Seed: expected 3 rows, got {expected_count}"

    # 브라우저 요청
    resp = client.get(f"/admin/data?route_id={_ROUTE_ID}&day={_DAY_STR}")
    assert resp.status_code == 200, f"data_browser expected 200, got {resp.status_code}"
    html = resp.data.decode("utf-8")

    # total-count 엘리먼트 확인
    assert "total-count" in html, "total-count element not found"
    assert f"총 {expected_count}건" in html, (
        f"Expected '총 {expected_count}건' in HTML, got something else"
    )


# ──────────────────────────────────────────────────
# AC-2: /admin/data.csv 응답이 UTF-8 BOM으로 시작
# ──────────────────────────────────────────────────

def test_csv_bom(authed_client):
    """CSV 응답 본문이 UTF-8 BOM(\\xef\\xbb\\xbf)으로 시작한다.

    독립 출처: W12 AC-2, F04 §7 AC-D3 "UTF-8 BOM 시작".
    E-13: BOM 값은 Unicode 표준에서 독립적으로 정의된 상수.
    """
    client, _ = authed_client
    resp = client.get(f"/admin/data.csv?route_id={_ROUTE_ID}&day={_DAY_STR}")
    assert resp.status_code == 200, f"data.csv expected 200, got {resp.status_code}"
    assert resp.data[:3] == b"\xef\xbb\xbf", (
        f"CSV should start with UTF-8 BOM, got {resp.data[:6]!r}"
    )


# ──────────────────────────────────────────────────
# test_bad_day_400: ?day=abc → 400
# ──────────────────────────────────────────────────

def test_bad_day_400(authed_client):
    """잘못된 day 형식 ?day=abc → 400.

    독립 출처: W12 spec "잘못된 day 형식은 400", F04 §7 AC-D5.
    """
    client, _ = authed_client
    resp = client.get("/admin/data?day=abc")
    assert resp.status_code == 400, f"Bad day format should return 400, got {resp.status_code}"

    # CSV 엔드포인트도 동일
    resp2 = client.get("/admin/data.csv?day=abc")
    assert resp2.status_code == 400, f"CSV bad day should return 400, got {resp2.status_code}"
