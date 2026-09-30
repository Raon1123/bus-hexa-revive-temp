"""KTX 연계표 배선 검증 — 같은 요일구분 다른 날짜에서 정차역 빌려 오기(순수 dict, 파일·네트워크 없음)."""
from __future__ import annotations

from bushexa.services.ktx_connections import borrow_stops


def _t(no, dep, arr, stops=None, day="2026-10-03", with_key=True):
    row = {"no": no, "dep": f"{day}T{dep}:00+09:00", "arr": f"{day}T{arr}:00+09:00"}
    if with_key:
        row["stops"] = stops
    return row


def test_borrow_stops_matches_number_and_times_only():
    """번호·출발·도착 시각이 모두 같은 열차에서만 빌리고, 이미 아는 정차역과 원본은 건드리지 않는다."""
    known = [{"name": "대전", "arr": "08:30"}]
    day = {"trains": [_t("12", "07:21", "09:43"), _t("14", "07:45", "10:16", with_key=False),
                      _t("16", "08:11", "10:33", stops=[{"name": "오송", "arr": "09:40"}])]}
    other = {"trains": [_t("12", "07:21", "09:43", known, day="2026-10-04"),
                        _t("14", "07:46", "10:16", known, day="2026-10-04"),
                        _t("16", "08:11", "10:33", known, day="2026-10-04")]}
    out = borrow_stops(day, [other])
    assert out["trains"][0]["stops"] == known
    assert "stops" not in out["trains"][1]                     # 출발 시각이 달라 빌리지 않음
    assert out["trains"][2]["stops"] == [{"name": "오송", "arr": "09:40"}]
    assert day["trains"][0]["stops"] is None                   # 원본 불변
