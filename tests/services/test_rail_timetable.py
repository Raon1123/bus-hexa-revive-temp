"""철도 시간표 스토어 갱신 규칙 검증. 클라이언트 대역 주입, 네트워크 없음."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from bushexa.api_clients.tago_rail import MetroStopTime, Train
from bushexa.data.constants import METRO_QUERIES, RAIL_BUSAN, RAIL_PAIRS, RAIL_ULSAN
from bushexa.services.rail_timetable import (
    load_rail_store,
    metro_day_type,
    metro_schedule,
    refresh_metro,
    refresh_trains,
    refreshed_today,
    trains_on,
)
from bushexa.time_utils import KST

UL, BS = RAIL_ULSAN, RAIL_BUSAN


class _Clock:
    def __init__(self, dt):
        self._dt = dt

    def now(self):
        return self._dt


def _trains(d: date, n: int) -> list[Train]:
    base = datetime(d.year, d.month, d.day, 6, 0, tzinfo=KST)
    return [Train(f"{i:05d}", "KTX", "울산", "부산", base + timedelta(minutes=10 * i),
                  base + timedelta(minutes=10 * i + 21), 7500) for i in range(n)]


class _TrainClient:
    """(dep, arr, date) → 편수 또는 예외. 지정 없으면 20편."""
    def __init__(self, plan=None):
        self.plan = plan or {}

    def fetch_trains(self, dep, arr, d):
        v = self.plan.get((dep, arr, d), 20)
        if isinstance(v, Exception):
            raise v
        return _trains(d, v)


def _metro(n: int, day_type="01") -> list[MetroStopTime]:
    return [MetroStopTime("MTRKRK6K132", "태화강", "MTRKRK6", "MTRKRK6K110", "부전",
                          f"{6 + i // 60:02d}:{i % 60:02d}:00", None, day_type, "U") for i in range(n)]


class _MetroClient:
    def __init__(self, plan=None):
        self.plan = plan or {}

    def fetch_station_schedule(self, station_id, day_type, direction):
        v = self.plan.get((station_id, day_type), 0 if day_type == "02" else 40)
        if isinstance(v, Exception):
            raise v
        return _metro(v, day_type)


TODAY = datetime(2026, 9, 29, 2, 30, tzinfo=KST)


def test_refresh_trains_stores_horizon_and_marks_success(tmp_path):
    """모든 구간·날짜 조회가 성공하면 days 일치가 저장되고 그날 갱신 완료로 기록된다."""
    path = tmp_path / "rail.json"
    s = refresh_trains(_TrainClient(), path, clock=_Clock(TODAY), days=3)
    assert len(s.stored) == 3 * len(RAIL_PAIRS) and not s.failed
    store = load_rail_store(path)
    assert len(trains_on(store, UL, BS, date(2026, 10, 1))["trains"]) == 20
    assert trains_on(store, UL, BS, date(2026, 10, 2)) is None   # 수집 범위 밖 = 모름
    assert refreshed_today(path, "trains", TODAY.date())


def test_refresh_trains_failure_keeps_existing_and_not_marked(tmp_path):
    """조회가 실패한 날짜는 기존 값을 유지하고, 실패가 있으면 그날 갱신 완료로 기록하지 않는다(PM-008)."""
    path = tmp_path / "rail.json"
    refresh_trains(_TrainClient(), path, clock=_Clock(TODAY), days=2)
    bad = _TrainClient({(UL, BS, date(2026, 9, 30)): RuntimeError("timeout")})
    s = refresh_trains(bad, path, clock=_Clock(TODAY), days=2)
    assert s.failed == [f"{UL}-{BS} 2026-09-30"]
    assert len(trains_on(load_rail_store(path), UL, BS, date(2026, 9, 30))["trains"]) == 20
    fresh = tmp_path / "fresh.json"
    refresh_trains(bad, fresh, clock=_Clock(TODAY), days=2)
    assert not refreshed_today(fresh, "trains", TODAY.date())


def test_refresh_trains_empty_keeps_existing_or_stores_nothing(tmp_path):
    """빈 결과는 기존 값이 있으면 유지하고, 없으면 저장하지 않는다(없음 = 모름)."""
    path = tmp_path / "rail.json"
    refresh_trains(_TrainClient(), path, clock=_Clock(TODAY), days=1)
    d0, d1 = date(2026, 9, 29), date(2026, 9, 30)
    empty = _TrainClient({(UL, BS, d0): 0, (UL, BS, d1): 0})
    refresh_trains(empty, path, clock=_Clock(TODAY), days=2)
    store = load_rail_store(path)
    assert len(trains_on(store, UL, BS, d0)["trains"]) == 20
    assert trains_on(store, UL, BS, d1) is None


def test_refresh_trains_sharp_drop_keeps_existing(tmp_path):
    """기존 60편이던 날짜가 3편으로 급감하면 새 값을 버리고 기존 값을 유지한다."""
    path = tmp_path / "rail.json"
    d = date(2026, 9, 29)
    refresh_trains(_TrainClient({(UL, BS, d): 60}), path, clock=_Clock(TODAY), days=1)
    s = refresh_trains(_TrainClient({(UL, BS, d): 3}), path, clock=_Clock(TODAY), days=1)
    assert f"{UL}-{BS} 2026-09-29" in s.kept
    assert len(trains_on(load_rail_store(path), UL, BS, d)["trains"]) == 60


def test_refresh_trains_flags_suspect_date_against_median(tmp_path):
    """처음 받는 날짜가 같은 구간 다른 날짜 중앙값의 절반 미만이면 저장하되 suspect 로 표시한다(2026-10-13 3편 사례)."""
    path = tmp_path / "rail.json"
    odd = date(2026, 10, 1)
    refresh_trains(_TrainClient({(UL, BS, odd): 3}), path, clock=_Clock(TODAY), days=5)
    store = load_rail_store(path)
    assert trains_on(store, UL, BS, odd)["suspect"] is True
    assert trains_on(store, UL, BS, date(2026, 9, 30))["suspect"] is False


def test_refresh_trains_prunes_past_dates(tmp_path):
    """다음 날 갱신하면 지난 날짜 항목은 지운다."""
    path = tmp_path / "rail.json"
    refresh_trains(_TrainClient(), path, clock=_Clock(TODAY), days=2)
    refresh_trains(_TrainClient(), path, clock=_Clock(TODAY + timedelta(days=1)), days=2)
    store = load_rail_store(path)
    assert trains_on(store, UL, BS, date(2026, 9, 29)) is None
    assert trains_on(store, UL, BS, date(2026, 10, 1)) is not None


def test_refresh_metro_stores_and_keeps_on_failure_or_empty(tmp_path):
    """동해선 시간표는 실패·빈 응답·급감이면 기존 값을 유지한다. 토요일처럼 처음부터 빈 것은 빈 채로 저장."""
    path = tmp_path / "rail.json"
    s = refresh_metro(_MetroClient(), path, clock=_Clock(TODAY))
    assert len(s.stored) == len(METRO_QUERIES) * 3 and not s.failed
    st = METRO_QUERIES[0][0]
    bad = _MetroClient({(st, "01"): RuntimeError("down"), (st, "03"): 0})
    s2 = refresh_metro(bad, path, clock=_Clock(TODAY))
    store = load_rail_store(path)
    assert len(metro_schedule(store, st, "U", "01")["times"]) == 40
    assert len(metro_schedule(store, st, "U", "03")["times"]) == 40
    assert s2.failed and not refreshed_today(path, "metro", date(2099, 1, 1))


def test_metro_saturday_falls_back_to_holiday_schedule(tmp_path):
    """토요일(02) 시간표가 비어 있으면 일·공휴일(03) 시간표를 돌려주고 실제 쓴 코드를 알 수 있다."""
    path = tmp_path / "rail.json"
    refresh_metro(_MetroClient(), path, clock=_Clock(TODAY))
    entry = metro_schedule(load_rail_store(path), METRO_QUERIES[0][0], "U", "02")
    assert entry["day_type"] == "03" and len(entry["times"]) == 40


def test_metro_day_type_holiday_first():
    """평일 공휴일은 03, 토요일은 02, 평일은 01 이다."""
    assert metro_day_type(date(2026, 10, 9), {"20261009"}) == "03"   # 한글날(금)
    assert metro_day_type(date(2026, 10, 10), set()) == "02"
    assert metro_day_type(date(2026, 10, 8), set()) == "01"


def test_load_missing_store_is_empty(tmp_path):
    """파일이 없으면 빈 스토어 — 화면은 '데이터 없음' 으로 처리할 수 있다."""
    store = load_rail_store(tmp_path / "none.json")
    assert trains_on(store, UL, BS, date(2026, 9, 29)) is None


def test_metro_trips_matches_by_time_and_drops_non_busan_trains(tmp_path):
    """저장된 동해선 시간표로 태화강→벡스코 편을 시각 매칭하고, 부산 방향이 아닌 망양행은 뺀다(평일 45→42편)."""
    from pathlib import Path

    from bushexa.api_clients.tago_rail import parse_metro_schedule
    from bushexa.services.rail_timetable import metro_trips

    fx = Path(__file__).parents[1] / "fixtures" / "tago_rail"
    files = {"MTRKRK6K132": "subway_taehwagang_01U.json", "MTRKRK6K119": "subway_bexco_01U.json",
             "MTRKRK6K110": "subway_bujeon_01U.json"}

    class _FixtureMetro:
        def fetch_station_schedule(self, station_id, day_type, direction):
            if day_type != "01":
                return []
            return parse_metro_schedule(json.loads((fx / files[station_id]).read_text(encoding="utf-8")))

    path = tmp_path / "rail.json"
    refresh_metro(_FixtureMetro(), path, clock=_Clock(TODAY))
    r = metro_trips(load_rail_store(path), "MTRKRK6K132", "MTRKRK6K119", "01")
    assert r["run_minutes"] == 55.5 and len(r["trips"]) == 42
    assert r["trips"][0] == {"dep": "05:36:00", "arr": "06:31:30", "end_name": "부전"}
    assert all(t["arr"] for t in r["trips"])
    assert metro_trips(load_rail_store(path), "MTRKRK6K132", "MTRKRK6K119", "03") is None
