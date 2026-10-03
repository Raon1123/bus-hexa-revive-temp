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


def test_seoul_page_renders_board_from_rail_store(client):
    """/seoul 은 rail_timetable.json 의 서울·수서행을 안내판으로 보이고, 데이터가 없으면 안내 문구, en 은 키 노출 없음."""
    c, data_dir = client
    resp = c.get("/seoul")
    assert resp.status_code == 200 and "서울 가는 길" in resp.data.decode()
    assert "행 열차 시간표를 아직 받지 못했습니다" in resp.data.decode()
    from bushexa.time_utils import KSTClock
    today = KSTClock().now().date().isoformat()
    store = {"version": 1, "metro": {}, "trains": {"pairs": {"NATH13717-NAT010000": {"dates": {today: {
        "trains": [{"grade": "KTX", "dep": f"{today}T23:58:00+09:00", "arr": f"{today}T23:59:00+09:00",
                    "stops": [{"name": "동대구", "arr": "23:58"}]}]}}}}}}
    atomic_write_json(data_dir / "rail_timetable.json", store)
    html = c.get("/seoul?to=seoul&view=board").data.decode()
    assert "23:58" in html and "rb-lit" in html
    en = c.get("/seoul?lang=en&view=board").data.decode()
    assert "Getting to Seoul" in en and "seoul." not in en and "rb." not in en.replace("rail_board.css", "")


def test_rail_view_defaults_to_table_and_board_is_optional(client):
    """열차 목록 기본 보기는 표이고, ?view=board 일 때만 발차 안내판을 그린다. 전환 링크는 다른 인자를 유지한다."""
    c, data_dir = client
    from bushexa.time_utils import KSTClock
    today = KSTClock().now().date().isoformat()
    store = {"version": 1, "metro": {}, "trains": {"pairs": {"NATH13717-NAT014445": {"dates": {today: {
        "trains": [{"grade": "KTX", "dep": f"{today}T23:58:00+09:00", "arr": f"{today}T23:59:00+09:00"}]}}}}}}
    atomic_write_json(data_dir / "rail_timetable.json", store)
    table = c.get("/busan").data.decode()
    assert "rb-board" not in table and "23:58" in table
    board = c.get("/busan?view=board").data.decode()
    assert "rb-board" in board and "직행" in board and "무정차" not in board
    assert "view=table" in c.get("/seoul?to=suseo&view=board").data.decode()


def test_board_marquee_lists_stops_then_destination(client):
    """발차 안내판 흐르는 문구는 '동대구 - 대전 - 서울'처럼 정차역과 행선만 나열한다(출발·정차·도착 문장 아님)."""
    c, data_dir = client
    from bushexa.time_utils import KSTClock
    today = KSTClock().now().date().isoformat()
    store = {"version": 1, "metro": {}, "trains": {"pairs": {"NATH13717-NAT010000": {"dates": {today: {
        "trains": [{"grade": "KTX", "dep": f"{today}T23:58:00+09:00", "arr": f"{today}T23:59:00+09:00",
                    "stops": [{"name": "동대구", "arr": "23:58"}, {"name": "대전", "arr": "23:58"}]}]}}}}}}
    atomic_write_json(data_dir / "rail_timetable.json", store)
    html = c.get("/seoul?view=board").data.decode()
    assert "<span>동대구 - 대전 - 서울</span>" in html
    assert "정차 →" not in html


def test_busan_page_shows_1224_live_at_samjeong_hospital(client, tmp_sqlite_db):
    """arrival 워커가 좋은삼정병원앞(193030929) 캐시에 1224·743 을 넣어 두면 /busan 노포 루트에 실시간 환승을 보인다."""
    c, _ = client
    from bushexa.db.connection import create_connection
    from bushexa.db.repo_arrival import BusArrivalRepo
    from bushexa.db.schema import create_schema
    from bushexa.time_utils import KSTClock
    conn = create_connection(f"sqlite:///{tmp_sqlite_db}")
    create_schema(conn)
    BusArrivalRepo(conn).upsert("193030929", [
        {"route_id": "195000216", "present_stop": "굴화마을", "vehicle_no": "a", "arrival_time": 240},
        {"route_id": "195000247", "present_stop": "삼호교", "vehicle_no": "b", "arrival_time": 600},
    ], KSTClock().now().isoformat())
    html = c.get("/busan").data.decode()
    assert "좋은삼정병원앞 1224(노포 방면) 실시간" in html
    assert "10분 후" in html and "6분 대기" in html
    assert "준비 중" not in html


def test_busan_page_shows_nopo_timetable_plan(client):
    """노포 루트에 '시간표로 보는 연계' 표가 나오고(영문 포함) 도착 캐시 없이도 200이다."""
    c, data_dir = client
    resp = c.get("/busan")
    assert resp.status_code == 200
    assert "시간표로 보는 연계" in resp.get_data(as_text=True)
    assert "Timetable-based connections" in c.get("/busan?lang=en").get_data(as_text=True)
