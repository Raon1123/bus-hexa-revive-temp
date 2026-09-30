"""요일별 KTX 연계표 도메인 검증 — 주입한 열차·시간표·소요 프로필만 쓴다(네트워크·파일 없음)."""
from __future__ import annotations

from datetime import date

from bushexa.domain.ktx_connect import (
    build_inbound,
    build_outbound,
    leg_estimate,
    reference_date,
    split_blocks,
)

REF = date(2026, 9, 30)   # 수요일


def _stats(p50, spread=3.0):
    return {"n": 20, "p10": p50 - spread, "p50": p50, "p90": p50 + spread}


def _profile(**legs):
    """구간별 고정 소요(모든 시간대 같은 값). 기본: 덕하→UNIST 60, UNIST→울산역 15, 덕하→울산역 75,
    삼남→울산역 20, 울산역→UNIST 18."""
    base = {"deokha_unist": 60, "unist_station": 15, "deokha_station": 75,
            "samnam_station": 20, "station_unist": 18}
    base.update(legs)
    return {"version": 1, "period": ["2026-01-01", "2026-06-01"],
            "legs": {k: {"by_day": {"0": {"all": _stats(v), "hours": {}}}} for k, v in base.items()}}


def _day(*trains, day="2026-09-30"):
    rows = []
    for i, tr in enumerate(trains):
        dep, arr = tr[0], tr[1]
        no = tr[2] if len(tr) > 2 else f"{i + 1:05d}"
        rows.append({"no": no, "grade": "KTX", "dep": f"{day}T{dep}:00+09:00", "arr": f"{day}T{arr}:00+09:00"})
    return {"trains": rows}


def test_outbound_maps_each_train_to_latest_bus_with_five_minute_margin():
    """덕하 07:00 → UNIST 08:00 → 울산역 08:15. 08:20 열차는 여유 5분이라 07:00, 08:19 는 06:30 버스로 간다."""
    t = build_outbound(0, REF, dest="busan", bus_times=["06:30", "07:00"], profile=_profile(),
                       train_day=_day(("08:19", "08:40"), ("08:20", "08:41")))
    assert [(r.train_dep, r.origin_dep, r.unist_at, r.station_at, r.margin_min) for r in t.rows] == [
        ("08:19", "06:30", "07:30", "07:45", 34),
        ("08:20", "07:00", "08:00", "08:15", 5),
    ]
    assert t.rows[0].train_no == ("1",) and t.rail_state == "ok" and t.profile_state == "ok"


def test_outbound_skips_trains_earlier_than_first_bus():
    """513 첫차로도 5분 여유를 못 맞추는 이른 열차는 행을 만들지 않고 skipped 로 센다."""
    t = build_outbound(0, REF, dest="busan", bus_times=["06:00"], profile=_profile(),
                       train_day=_day(("07:10", "07:30"), ("07:20", "07:40")))
    assert [r.train_dep for r in t.rows] == ["07:20"]
    assert t.skipped == 1


def test_outbound_tight_when_slow_day_breaks_margin():
    """중앙값으로는 여유 5분이지만 늦는 날(p90 덕하→울산역 +3분)이면 모자라 tight 로 표시한다."""
    t = build_outbound(0, REF, dest="busan", bus_times=["07:00"], profile=_profile(),
                       train_day=_day(("08:20", "08:41"), ("08:40", "09:01")))
    assert [r.tight for r in t.rows] == [True, False]


def test_outbound_uses_hour_specific_travel_time():
    """시간대 값이 있으면 요일구분 전체값 대신 그 값을 쓴다(17시 첨두 85분)."""
    prof = _profile()
    prof["legs"]["deokha_unist"]["by_day"]["0"]["hours"] = {"17": _stats(85)}
    t = build_outbound(0, REF, dest="busan", bus_times=["17:00"], profile=prof,
                       train_day=_day(("19:00", "19:21")))
    assert t.rows[0].unist_at == "18:25" and t.rows[0].station_at == "18:40"


def test_inbound_maps_train_to_first_bus_after_arrival_plus_margin():
    """삼남 07:00 → 울산역 07:20 → UNIST 07:38. 07:15 도착은 07:20 버스(대기 5분), 07:16 도착은 다음 버스."""
    t = build_inbound(0, REF, dest="seoul", bus_times=["07:00", "07:30"], profile=_profile(),
                      train_day=_day(("04:50", "07:15"), ("04:51", "07:16")))
    assert [(r.train_arr, r.origin_dep, r.station_at, r.unist_at, r.wait_min) for r in t.rows] == [
        ("07:15", "07:00", "07:20", "07:38", 5),
        ("07:16", "07:30", "07:50", "08:08", 34),
    ]
    assert t.rows[0].tight is True and t.rows[1].tight is False


def test_inbound_skips_trains_after_last_bus():
    """막차가 울산역을 지난 뒤 도착하는 열차는 뺀다."""
    t = build_inbound(0, REF, dest="busan", bus_times=["21:40"], profile=_profile(),
                      train_day=_day(("21:30", "21:50"), ("22:30", "22:51")))
    assert [r.train_arr for r in t.rows] == ["21:50"] and t.skipped == 1


def test_coupled_trains_merge_into_one_column_with_both_numbers():
    """중련(같은 시각 두 번호)은 한 열로 합치고 번호를 둘 다 싣는다(앞자리 0 제거)."""
    t = build_outbound(0, REF, dest="seoul", bus_times=["06:00"], profile=_profile(),
                       train_day=_day(("08:00", "10:30", "09069"), ("08:00", "10:30", "00069")))
    assert len(t.rows) == 1 and t.rows[0].train_no == ("9069", "69")


def test_missing_inputs_are_reported_not_hidden():
    """열차·버스·프로필이 없으면 빈 표가 아니라 각 상태를 missing 으로 알린다."""
    t = build_outbound(1, None, dest="busan", train_day=None, bus_times=[], profile=None)
    assert (t.rail_state, t.bus_state, t.profile_state) == ("missing", "missing", "missing")
    assert t.rows == []


def test_next_day_arrival_is_flagged():
    """자정을 넘겨 도착하는 열차는 arr_next_day 로 표시한다(서울 도착 00:10)."""
    trains = {"trains": [{"no": "1", "grade": "KTX", "dep": "2026-09-30T21:40:00+09:00",
                          "arr": "2026-10-01T00:10:00+09:00"}]}
    t = build_outbound(0, REF, dest="seoul", bus_times=["19:00"], profile=_profile(), train_day=trains)
    assert t.rows[0].arr_next_day and t.rows[0].train_arr == "00:10"


def test_leg_estimate_falls_back_from_hour_to_day_to_weekday():
    """시간대 값이 없으면 요일구분 전체, 요일구분이 없으면 평일 값을 쓴다. 구간이 없으면 None."""
    prof = _profile()
    prof["legs"]["deokha_unist"]["by_day"]["0"]["hours"] = {"8": _stats(70)}
    assert leg_estimate(prof, "deokha_unist", 0, 8 * 60 + 30).p50 == 70
    assert leg_estimate(prof, "deokha_unist", 0, 9 * 60).p50 == 60
    assert leg_estimate(prof, "deokha_unist", 2, 9 * 60).p50 == 60
    assert leg_estimate(prof, "nope", 0, 0) is None and leg_estimate(None, "deokha_unist", 0, 0) is None


def test_reference_date_picks_next_date_of_day_type_with_holidays():
    """저장된 날짜 중 오늘 이후 첫 토요일·일/공휴일을 고른다. 10/3(토, 개천절)은 공휴일로 친다."""
    avail = [date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 3), date(2026, 10, 4), date(2026, 10, 10)]
    hol = {"20261003"}
    assert reference_date(REF, 0, hol, avail) == date(2026, 9, 30)
    assert reference_date(REF, 2, hol, avail) == date(2026, 10, 3)
    assert reference_date(REF, 1, hol, avail) == date(2026, 10, 10)
    assert reference_date(REF, 1, hol, []) is None


def test_split_blocks_by_ulsan_time():
    """가는 편은 울산 출발, 오는 편은 울산 도착 시각으로 오전/오후/저녁 판을 나눈다(자정 뒤는 저녁)."""
    t = build_inbound(0, REF, dest="busan", bus_times=["05:00", "12:00", "23:30"], profile=_profile(),
                      train_day=_day(("05:00", "05:10"), ("11:40", "12:00"), ("23:00", "23:40")))
    keys = [(k, [r.train_arr for r in rows]) for k, rows in split_blocks(t.rows, "in")]
    assert keys == [("morning", ["05:10"]), ("afternoon", ["12:00"]), ("evening", ["23:40"])]


def test_station_layout_orders_trunk_then_branches_and_reverses_for_inbound():
    """서울행은 줄기(경주…대전) → 고속선 → 수원 경유 순, 서울발은 그 역순. 부산행은 중간역이 없다."""
    from bushexa.data.constants import RAIL_BUSAN, RAIL_SEOUL, RAIL_ULSAN
    from bushexa.domain.ktx_connect import station_layout

    out, branches = station_layout((RAIL_ULSAN, RAIL_SEOUL))
    assert out[0] == "경주" and out[4] == "대전" and out[-2:] == ("수원", "영등포")
    assert station_layout((RAIL_SEOUL, RAIL_ULSAN))[0] == out[::-1]
    assert len(branches) == 2 and "광명" in branches[0]
    assert station_layout((RAIL_ULSAN, RAIL_BUSAN)) == ((), ())


def test_via_cells_marks_stop_pass_other_route_and_unknown():
    """선 역은 도착 시각, 같은 갈래 통과는 レ, 다른 갈래 역은 ‖, 정차역을 모르면 빈 칸."""
    from bushexa.domain.ktx_connect import OTHER_ROUTE, PASS, via_cells

    names = ("대전", "오송", "광명", "수원")
    branches = (frozenset({"오송", "광명"}), frozenset({"수원"}))
    express = via_cells([{"name": "대전", "arr": "08:32"}, {"name": "광명", "arr": "09:23"}], names, branches)
    assert express == ("08:32", PASS, "09:23", OTHER_ROUTE)
    via_suwon = via_cells([{"name": "수원", "arr": "10:58"}], names, branches)
    assert via_suwon == (PASS, OTHER_ROUTE, OTHER_ROUTE, "10:58")
    assert via_cells([], names, branches) == (PASS, PASS, PASS, OTHER_ROUTE)   # 무정차는 고속선으로 본다
    assert via_cells(None, names, branches) == ("",) * 4


def test_rows_carry_via_cells_and_count_unknown_stops():
    """pair 를 주면 행마다 중간역 칸이 붙고, 정차역을 모르는 열차 수를 센다."""
    from bushexa.data.constants import RAIL_SEOUL, RAIL_ULSAN

    day = _day(("08:00", "10:30"), ("09:00", "11:30"))
    day["trains"][0]["stops"] = [{"name": "대전", "arr": "09:05"}]
    t = build_outbound(0, REF, dest="seoul", bus_times=["06:00"], profile=_profile(), train_day=day,
                       pair=(RAIL_ULSAN, RAIL_SEOUL))
    assert len(t.stations) == 10 and t.rows[0].via[4] == "09:05"
    assert t.rows[1].via == ("",) * 10 and t.stops_unknown == 1


# ── ② 5001 + 진목회관 환승 ──────────────────────────────────────────────────

def _alt_profile(**extra):
    """① 기본 구간 + ② 5001·환승 구간(고정값). 5001 실측은 기본적으로 없음(근사 구간 사용)."""
    prof = _profile(p513_station_jinmok=20, p1115_kkotbawi_gulhwa=60, p513_gulhwa_jinmok=15,
                    p513_jinmok_station=18, myeongchon_jinmok_713=70, jinmok_unist_713=4,
                    deokha_jinmok=57, jinmok_unist_513=3, unist_jinmok_713=3, samnam_unist=40,
                    unist_jinmok_513=3, **extra)
    return prof


TTS_IN = {("5001", "울산역"): ["07:40", "08:05"], ("713", "명촌"): ["07:00", "07:10", "07:30"]}
TTS_OUT = {("5001", "꽃바위"): ["05:30", "06:00"], ("713", "UNIST"): ["06:30", "06:40", "07:00"]}


def test_inbound_5001_takes_first_5001_then_first_feeder_across_the_road():
    """07:30 도착 → 5분 뒤 첫 5001(07:40) → 진목회관 08:00 → 5분 건너 → 713(07:00 명촌발, 08:10 통과) → UNIST 08:14."""
    t = build_inbound(0, REF, dest="seoul", bus_times=[], profile=_alt_profile(),
                      train_day=_day(("05:10", "07:30")), timetables=TTS_IN)
    a = t.rows[0].alt
    assert (a.bus_dep, a.wait_min, a.jinmok_arr, a.feeder_no, a.feeder_dep, a.unist_at) == (
        "07:40", 10, "08:00", "713", "08:10", "08:14")
    assert t.rows[0].origin_dep is None and t.alt_state == "ok" and t.alt_proxied
    assert a.tight is False                # 근사 구간이면 빠듯 판정을 하지 않는다


def test_transfer_minimums_are_parameters_with_five_minute_default():
    """환승 최소 시간은 울산역·진목회관 각각 매개변수(기본 5분). 울산역 11분이면 07:40 5001 을 못 타
    08:05 5001(진목회관 08:25) → 5분 건너 07:30 명촌발 713(08:40)을 탄다."""
    from bushexa.domain.ktx_connect import Transfers

    assert Transfers() == Transfers(station=5, jinmok=5)
    t = build_inbound(0, REF, dest="seoul", bus_times=[], profile=_alt_profile(),
                      train_day=_day(("05:10", "07:30")), timetables=TTS_IN,
                      transfers=Transfers(station=11, jinmok=5))
    assert (t.rows[0].alt.bus_dep, t.rows[0].alt.feeder_dep) == ("08:05", "08:40")
    assert t.transfers.station == 11
    # 진목회관 45분이면 마지막 713(08:40 통과)도 놓쳐 환승 버스가 없다 → 그 열차는 빠진다
    t2 = build_inbound(0, REF, dest="seoul", bus_times=[], profile=_alt_profile(),
                       train_day=_day(("05:10", "07:30")), timetables=TTS_IN,
                       transfers=Transfers(station=5, jinmok=45))
    assert t2.rows == [] and t2.skipped == 1


def test_outbound_5001_latest_run_and_latest_unist_departure():
    """08:00 열차: 06:00 꽃바위발 5001(진목회관 07:15, 울산역 07:33)은 여유 27분 → 이 5001 에
    진목회관 5분 전까지 닿는 가장 늦은 713(UNIST 07:00 → 07:03)을 붙인다."""
    t = build_outbound(0, REF, dest="busan", bus_times=[], profile=_alt_profile(),
                       train_day=_day(("08:00", "08:21")), timetables=TTS_OUT)
    a = t.rows[0].alt
    assert (a.feeder_no, a.unist_dep, a.jinmok_arr, a.bus_dep, a.station_at, a.margin_min) == (
        "713", "07:00", "07:03", "07:15", "07:33", 27)


def test_best_option_compares_unist_times():
    """두 안이 다 있으면 가는 편은 UNIST 를 더 늦게 떠나는 안, 오는 편은 UNIST 에 먼저 닿는 안이 best."""
    tts = {**TTS_OUT, ("513", "삼남"): []}
    out = build_outbound(0, REF, dest="busan", bus_times=["06:00"], profile=_alt_profile(),
                         train_day=_day(("08:00", "08:21")), timetables=tts)
    assert out.rows[0].unist_at == "07:00" and out.rows[0].alt.unist_dep == "07:00"
    assert out.rows[0].best == "513"                   # 같으면 513
    inn = build_inbound(0, REF, dest="seoul", bus_times=["07:40"], profile=_alt_profile(),
                        train_day=_day(("05:10", "07:30")), timetables=TTS_IN)
    assert inn.rows[0].unist_at == "08:18" and inn.rows[0].alt.unist_at == "08:14"
    assert inn.rows[0].best == "5001"


def test_real_5001_records_replace_proxy_when_enough_samples():
    """5001 실측 표본이 KTX_LEG_REAL_MIN_N 이상이면 근사 대신 실측 구간을 쓰고 빠듯 판정도 켠다."""
    from bushexa.domain.ktx_connect import leg_or_proxy

    prof = _alt_profile()
    est, proxied = leg_or_proxy(prof, "l5001_origin_jinmok", 0, 300)
    assert proxied and est.p50 == 75                   # 1115 60 + 513 15
    prof["legs"]["l5001_origin_jinmok"] = {"by_day": {"0": {"all": {**_stats(50), "n": 30}, "hours": {}}}}
    est, proxied = leg_or_proxy(prof, "l5001_origin_jinmok", 0, 300)
    assert not proxied and est.p50 == 50
    prof["legs"]["l5001_origin_jinmok"]["by_day"]["0"]["all"]["n"] = 5
    assert leg_or_proxy(prof, "l5001_origin_jinmok", 0, 300)[1] is True


def test_train_kept_when_only_5001_reaches_it():
    """513 첫차로는 못 닿는 이른 열차도 5001 안이 있으면 빼지 않는다(① 칸은 None)."""
    t = build_outbound(0, REF, dest="busan", bus_times=["07:30"], profile=_alt_profile(),
                       train_day=_day(("08:00", "08:21")), timetables=TTS_OUT)
    assert t.skipped == 0 and t.rows[0].origin_dep is None and t.rows[0].alt is not None
