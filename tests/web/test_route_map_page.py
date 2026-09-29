"""/info 노선도 페이지(A 지도 + B 노선별 목록) · A/B 카운터 · /stops 미리 선택 테스트.

테스트 의도:
  test_route_lines_order_and_links — B 목록: 노선 번호순, UNIST → /busno, 도착 링크는 조회 가능한 정류소
  test_route_lines_upcoming_notes  — 10/3 전에는 743 범서중 "10/3부터", 1115 현대자동차 "10/2까지" 예고
  test_counter_record_and_summary  — 카운터: 날짜별 누적, 알 수 없는 이벤트 거부, 방식별 노출·전환·전환율
  test_info_page_has_map_and_list  — /info 에 지도·칩·패널·목록 카드·전환 링크·스크립트가 있고, 하나만 보인다
  test_info_random_assignment      — 쿠키 없는 첫 방문은 A·B 를 무작위로 받고, 쿠키로 유지되며, 노출이 세어진다
  test_info_view_switch_no_js      — ?view= 로 다른 쪽을 고르면 그 화면을 보여 주고 전환 1회를 센다
  test_info_event_endpoint         — POST /info/event: 브라우저 이벤트만 204, 노출·모르는 이벤트는 400
  test_stops_preselect             — /stops?stop_id= 가 유효한 정류소만 미리 선택·즉시 조회
  test_admin_dashboard_shows_ab    — 관리자 대시보드에 A/B 사용량 표가 나온다
네트워크 없음. 파일은 tmp_path 격리.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from bushexa.data.constants import ROUTE_MAP_STOP_LINK, SERACH_STOPS
from bushexa.services import route_map_ab
from bushexa.web.app import create_app
from bushexa.web.route_lines import build_route_lines


def test_route_lines_order_and_links():
    """B 목록은 노선 번호순이고, UNIST 는 시간표로, 나머지 링크는 /stops 조회 가능한 정류소로 간다."""
    lines = build_route_lines(date(2026, 10, 3))
    assert [ln.line for ln in lines] == ["513", "713", "743", "753", "1115"]
    for ln in lines:
        unist = [s for s in ln.stops if s.is_unist]
        assert len(unist) == 1 and unist[0].href == f"/busno?bus={ln.line}"
        for s in ln.stops:
            if s.href and s.href.startswith("/stops?stop_id="):
                assert s.href.split("=", 1)[1] in SERACH_STOPS


def test_route_lines_upcoming_notes():
    """시행 전에는 바뀌는 정류장을 예고로 함께 보이고, 시행 후에는 예고 없이 새 경로만 보인다."""
    def notes(today, line):
        ln = next(x for x in build_route_lines(today) if x.line == line)
        return {s.key: s.note for s in ln.stops if s.note}

    assert notes(date(2026, 10, 2), "743") == {"범서중": "10/3부터"}
    assert notes(date(2026, 10, 2), "1115") == {"현대자동차": "10/2까지"}
    assert notes(date(2026, 10, 3), "743") == {}
    after_1115 = [s.key for s in next(x for x in build_route_lines(date(2026, 10, 3))
                                      if x.line == "1115").stops]
    assert "현대자동차" not in after_1115


def test_counter_record_and_summary(tmp_path):
    """이벤트를 날짜별로 누적하고, 방식별 노출·전환·전환율(전환/노출)을 낸다."""
    path = route_map_ab.default_path(tmp_path / "data")
    d = date(2026, 10, 1)
    for ev in ["view_a"] * 4 + ["view_b"] * 2 + ["switch_to_b", "map_stop"]:
        route_map_ab.record(path, ev, d)
    route_map_ab.record(path, "view_b", date(2026, 9, 1))  # 최근 7일 밖
    with pytest.raises(ValueError):
        route_map_ab.record(path, "hack", d)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["2026-10-01"] == {"view_a": 4, "view_b": 2, "switch_to_b": 1, "map_stop": 1}
    a, b = route_map_ab.summary(path, d)["arms"]
    assert a["recent"] == {"views": 4, "switches": 1, "rate": 0.25}
    assert b["recent"] == {"views": 2, "switches": 0, "rate": 0.0}
    assert b["total"]["views"] == 3


@pytest.fixture
def app(app_config_test):
    return create_app(app_config_test)


def _counts(app) -> dict:
    data_dir = app.config["BUSHEXA_CONFIG"].data_dir
    data = json.loads(route_map_ab.default_path(data_dir).read_text(encoding="utf-8"))
    out: dict = {}
    for day in data.values():
        for k, v in day.items():
            out[k] = out.get(k, 0) + v
    return out


def test_info_page_has_map_and_list(app):
    """/info 는 지도·칩·패널·목록 카드·전환 링크·스크립트를 모두 담되, 고른 쪽만 보인다(다른 쪽 hidden)."""
    html = app.test_client().get("/info?view=a").get_data(as_text=True)
    assert '<svg class="route-svg"' in html
    assert html.count('class="route-chip"') >= 5
    assert 'class="route-map-panel"' in html
    assert html.count('<section class="route-card') == 5
    assert 'href="/busno?bus=743"' in html
    assert f'href="/stops?stop_id={ROUTE_MAP_STOP_LINK["천상"]}"' in html
    assert 'href="?view=b"' in html and "js/route_map.js" in html
    assert '<div class="route-view" data-view="a" >' in html
    assert '<div class="route-view" data-view="b" hidden>' in html


def test_info_random_assignment(app, monkeypatch):
    """첫 방문은 무작위로 A·B 중 하나를 받고 쿠키로 유지된다. 보여 줄 때마다 노출을 센다."""
    import bushexa.web.routes.info as info_mod

    monkeypatch.setattr(info_mod.secrets, "choice", lambda seq: "b")
    c = app.test_client()
    r = c.get("/info")
    assert "route_map_view=b" in r.headers["Set-Cookie"]
    assert '<div class="route-view" data-view="b" >' in r.get_data(as_text=True)
    monkeypatch.setattr(info_mod.secrets, "choice", lambda seq: "a")
    r2 = c.get("/info")  # 쿠키가 있으면 다시 뽑지 않는다
    assert '<div class="route-view" data-view="b" >' in r2.get_data(as_text=True)
    assert _counts(app) == {"view_b": 2}


def test_info_view_switch_no_js(app):
    """JS 없이 ?view= 링크로 다른 쪽을 고르면 그 화면·쿠키로 바뀌고 전환 1회를 센다. 같은 쪽이면 안 센다."""
    c = app.test_client()
    c.get("/info?view=a")
    r = c.get("/info?view=b")
    assert "route_map_view=b" in r.headers["Set-Cookie"]
    c.get("/info?view=b")
    counts = _counts(app)
    assert counts["view_a"] == 1 and counts["view_b"] == 2
    assert counts["switch_to_b"] == 1 and "switch_to_a" not in counts


def test_info_event_endpoint(app):
    """브라우저 이벤트(전환·조작)만 204 로 세고, 노출(서버 전용)·모르는 이벤트는 400."""
    c = app.test_client()
    assert c.post("/info/event", data={"e": "switch_to_a"}).status_code == 204
    assert c.post("/info/event", data={"e": "map_stop"}).status_code == 204
    assert c.post("/info/event", data={"e": "view_a"}).status_code == 400
    assert c.post("/info/event", data={"e": "x" * 50}).status_code == 400
    assert _counts(app) == {"switch_to_a": 1, "map_stop": 1}


def test_stops_preselect(app):
    """노선도 링크(/stops?stop_id=)로 들어오면 그 정류소가 선택되고 곧바로 조회한다. 잘못된 id 는 무시."""
    c = app.test_client()
    sid = ROUTE_MAP_STOP_LINK["천상"]
    html = c.get(f"/stops?stop_id={sid}").get_data(as_text=True)
    assert f'value="{sid}" selected' in html
    assert f'hx-get="/partial/stops?stop_id={sid}"' in html
    bad = c.get("/stops?stop_id=nope").get_data(as_text=True)
    assert 'hx-trigger="load"' not in bad


def test_admin_dashboard_shows_ab(app):
    """관리자 대시보드에 방식별 노출·전환·전환율 표가 보인다."""
    c = app.test_client()
    c.get("/info?view=a")
    c.get("/info?view=b")
    with c.session_transaction() as sess:
        sess["admin_authed"] = True
    html = c.get("/admin/").get_data(as_text=True)
    assert 'id="route-map-ab"' in html
    assert "A 지도" in html and "B 목록" in html
    assert "100.0%" in html  # A 노출 1, B 로 전환 1
