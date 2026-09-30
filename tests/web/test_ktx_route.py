"""/ktx 라우트 검증 — 데이터 없음·철도+프로필 있음·영문·다른 페이지 링크(파일만 읽고 네트워크 없음)."""
from __future__ import annotations

import re

import pytest

from bushexa.config import AppConfig
from bushexa.fileio import atomic_write_json
from bushexa.time_utils import KST, KSTClock, get_weekday
from bushexa.web.app import create_app


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


def _profile():
    stats = {"n": 20, "p10": 1.0, "p50": 1.0, "p90": 1.0}   # 모든 구간 1분 — 시간표 첫차면 어떤 열차든 닿는다
    legs = ("deokha_unist", "unist_station", "deokha_station", "samnam_station", "station_unist")
    return {"version": 1, "period": ["2026-01-22", "2026-06-01"],
            "legs": {k: {"by_day": {d: {"all": stats, "hours": {}} for d in "012"}} for k in legs}}


def _store(pair, day):
    train = {"no": "00069", "grade": "KTX-산천(A-type)", "dep": f"{day}T23:40:00+09:00",
             "arr": f"{day}T23:58:00+09:00"}
    return {"version": 1, "metro": {}, "trains": {"pairs": {pair: {"dates": {day: {"trains": [train]}}}}}}


def test_ktx_page_without_rail_data_says_so(client):
    """열차 시간표가 없어도 200이고 '받지 못했습니다' 안내, 사이드바 항목이 활성화된다."""
    c, _ = client
    resp = c.get("/ktx")
    html = resp.data.decode()
    assert resp.status_code == 200
    assert "KTX 연계표" in html and "열차 시간표를 아직 받지 못했습니다" in html
    assert re.search(r'nav-link active"\s+href="/ktx"', html)


def test_ktx_outbound_renders_timetable_sheet_with_train_number(client):
    """오늘 울산→부산 열차와 프로필이 있으면 열차번호(앞 0 제거)·버스행 뒤 열차행 순서로 보인다."""
    c, data_dir = client
    today = KSTClock().now().date()
    atomic_write_json(data_dir / "rail_timetable.json", _store("NATH13717-NAT014445", today.isoformat()))
    atomic_write_json(data_dir / "ktx_leg_profile.json", _profile())
    day = get_weekday(today, set())
    html = c.get(f"/ktx?dir=out&to=busan&day={day}").data.decode()
    assert ">69<" in html and "KTX-산천" in html and "(A-type)" not in html
    assert html.index("513 덕하 발") < html.index("UNIST(경유) 탑승") < html.index("울산 발") < html.index("부산 착")
    assert "23:40" in html and "2026-01-22" in html


def test_ktx_inbound_puts_train_rows_above_bus_rows(client):
    """오는 편은 출발역 발·울산 착(열차)이 위, 513 울산역 발·UNIST 착(버스)이 아래다."""
    c, data_dir = client
    today = KSTClock().now().date()
    store = _store("NAT010000-NATH13717", today.isoformat())
    store["trains"]["pairs"]["NAT010000-NATH13717"]["dates"][today.isoformat()]["trains"][0].update(
        dep=f"{today.isoformat()}T05:00:00+09:00", arr=f"{today.isoformat()}T07:00:00+09:00")
    atomic_write_json(data_dir / "rail_timetable.json", store)
    atomic_write_json(data_dir / "ktx_leg_profile.json", _profile())
    day = get_weekday(today, set())
    html = c.get(f"/ktx?dir=in&to=seoul&day={day}").data.decode()
    assert html.index("서울 발") < html.index("울산 착") < html.index("513 울산역 발") < html.index("UNIST(경유) 착")


def test_ktx_page_missing_profile_and_bad_params(client):
    """프로필이 없으면 안내 문구, 잘못된 쿼리는 기본값(가는 편·부산)으로 200."""
    c, data_dir = client
    today = KSTClock().now().date()
    atomic_write_json(data_dir / "rail_timetable.json", _store("NATH13717-NAT014445", today.isoformat()))
    html = c.get(f"/ktx?dir=zz&to=tokyo&day={get_weekday(today, set())}").data.decode()
    assert "구간 소요 자료" in html
    assert c.get("/ktx?day=9").status_code == 200


def test_ktx_english_has_no_raw_keys_and_linked_from_busan_seoul(client):
    """?lang=en 에서 ktx.* 키가 노출되지 않고, /busan·/seoul 에서 연계표로 가는 링크가 있다."""
    c, _ = client
    html = c.get("/ktx?lang=en&dir=in").data.decode()
    assert "KTX" in html and "ktx." not in html.replace("css/ktx.css", "")
    assert "/ktx?dir=out&amp;to=busan" in c.get("/busan").data.decode()
    assert "/ktx?dir=in&amp;to=seoul" in c.get("/seoul").data.decode()
