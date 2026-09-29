"""/busan 라우트 검증 — 빈 데이터·철도 캐시 있음·도착 캐시 장애에서 모두 200."""
from __future__ import annotations

import re
from unittest.mock import patch

import pytest

from bushexa.config import AppConfig
from bushexa.fileio import atomic_write_json
from bushexa.web.app import create_app
from bushexa.time_utils import KST


@pytest.fixture
def client(tmp_path, tmp_sqlite_db):
    config = AppConfig(
        api_key="k", database_url=f"sqlite:///{tmp_sqlite_db}", session_secret="s",
        manager_password_path=tmp_path / "pw.txt", data_dir=tmp_path / "data",
        tz=KST, log_level="DEBUG", log_dir=tmp_path / "logs",
    )
    app = create_app(config)
    app.config["TESTING"] = True
    return app.test_client(), tmp_path / "data"


def test_busan_page_renders_without_rail_data(client):
    """철도 캐시가 없어도 200이고 '아직 받지 못했습니다' 안내를 보이며, 사이드바 항목이 활성화된다."""
    c, _ = client
    resp = c.get("/busan")
    html = resp.data.decode()
    assert resp.status_code == 200
    assert "부산 가는 길" in html
    assert "열차 시간표를 아직 받지 못했습니다" in html
    assert re.search(r'nav-link active"\s+href="/busan"', html)


def test_busan_page_shows_rail_store_trains(client):
    """rail_timetable.json 에 오늘 열차가 있으면 그 시각을 보인다(공개 화면은 파일만 읽음)."""
    c, data_dir = client
    from bushexa.time_utils import KSTClock
    today = KSTClock().now().date().isoformat()
    store = {"version": 1, "metro": {}, "trains": {"pairs": {"NATH13717-NAT014445": {"dates": {today: {
        "trains": [{"no": "1", "grade": "KTX", "dep": f"{today}T23:58:00+09:00",
                    "arr": f"{today}T23:59:00+09:00", "charge": 7500}]}}}}}}
    atomic_write_json(data_dir / "rail_timetable.json", store)
    html = c.get("/busan").data.decode()
    assert "23:58" in html


def test_busan_page_survives_arrival_cache_failure(client):
    """도착 캐시 조회가 실패해도 500 대신 오류 배너와 함께 200."""
    c, _ = client
    with patch("bushexa.web.routes.busan.arrival_client", side_effect=RuntimeError("db down")):
        resp = c.get("/busan")
    assert resp.status_code == 200
    assert "실시간 정보를 가져오지 못했습니다" in resp.data.decode()


def test_busan_page_english_has_no_raw_keys(client):
    """?lang=en 에서 번역 키 문자열(busan.*)이 그대로 노출되지 않는다."""
    c, _ = client
    html = c.get("/busan?lang=en").data.decode()
    assert "Getting to Busan" in html
    assert "busan." not in html.replace("css/busan.css", "")
