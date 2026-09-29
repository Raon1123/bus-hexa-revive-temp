"""동해선 시각 매칭(열차번호 없이 출발↔도착 잇기) 검증. 네트워크 없음 — 실응답 픽스처와 합성 시각."""
from __future__ import annotations

import json
from pathlib import Path

from bushexa.api_clients.tago_rail import parse_metro_schedule
from bushexa.domain.rail_match import infer_run_minutes, match_by_time, service_minutes

FIXTURES = Path(__file__).parents[1] / "fixtures" / "tago_rail"


def _rows(name: str):
    return parse_metro_schedule(json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def test_service_minutes_treats_early_morning_as_previous_service_day():
    """00:16 은 전날 운행일의 24:16 으로 계산돼 23:00 출발보다 뒤에 온다."""
    assert service_minutes("00:16:00") == 24 * 60 + 16
    assert service_minutes("23:00:00") < service_minutes("00:16:00")


def test_match_skips_extra_trains_and_waits_for_delayed_one():
    """중간역 출발 편(도착만 있음)은 건너뛰고, 대피로 5분 늦는 편은 기다려 제 도착을 준다."""
    deps = ["06:00:00", "06:30:00", "07:00:00", "07:30:00"]
    arrs = ["06:40:00",              # 중간역 출발 편 — 어느 출발에도 속하지 않음
            "07:00:00", "07:30:00", "08:05:00", "08:30:00"]   # 07:00 출발 편은 5분 지연
    assert infer_run_minutes(deps, arrs) == 60
    assert match_by_time(deps, arrs) == [
        ("06:00:00", "07:00:00"), ("06:30:00", "07:30:00"),
        ("07:00:00", "08:05:00"), ("07:30:00", "08:30:00"),
    ]


def test_match_returns_none_when_no_arrival_in_window():
    """창(소요+15분) 안에 도착이 없으면 도착을 지어내지 않고 None."""
    assert match_by_time(["06:00:00"], ["08:00:00"], run_minutes=60) == [("06:00:00", None)]
    assert match_by_time(["06:00:00"], []) == [("06:00:00", None)]


def test_real_weekday_taehwagang_to_bexco_and_bujeon_consistent():
    """실응답(평일 상행)으로 태화강 부전행 42편이 벡스코·부전 도착에 모두 짝지어지고,
    남는 도착(중간역 출발 편)은 벡스코→부전 약 20분 간격으로 양쪽에서 같은 편으로 나타난다."""
    origin = [r.dep_time for r in _rows("subway_taehwagang_01U.json")
              if r.dep_time and r.end_station_id == "MTRKRK6K110"]
    bexco = [r.arr_time for r in _rows("subway_bexco_01U.json") if r.arr_time]
    bujeon = [r.arr_time for r in _rows("subway_bujeon_01U.json") if r.arr_time]
    assert len(origin) == 42

    assert infer_run_minutes(origin, bexco) == 55.5
    assert infer_run_minutes(origin, bujeon) == 76
    to_bexco = dict(match_by_time(origin, bexco))
    to_bujeon = dict(match_by_time(origin, bujeon))
    assert all(to_bexco.values()) and all(to_bujeon.values())

    # 같은 편이면 벡스코→부전 구간은 20.5분, 대피 정차가 있는 편은 25~26.5분이다.
    # 잘못 짝지으면 배차 간격(15~30분)만큼 어긋나므로 19~27분 밖이면 오매칭이다.
    legs = [service_minutes(to_bujeon[d]) - service_minutes(to_bexco[d]) for d in origin]
    assert all(19 <= x <= 27 for x in legs), legs

    extra_bexco = sorted(set(bexco) - set(to_bexco.values()), key=service_minutes)
    extra_bujeon = sorted(set(bujeon) - set(to_bujeon.values()), key=service_minutes)
    assert len(extra_bexco) == len(extra_bujeon) == len(bexco) - 42
    assert all(19 <= service_minutes(b) - service_minutes(a) <= 27
               for a, b in zip(extra_bexco, extra_bujeon))
