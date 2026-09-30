"""513 구간 소요 프로필 생성 검증 — 통과기록 짝짓기·요일구분·시간대 창·파일 입출력(네트워크 없음)."""
from __future__ import annotations

from datetime import datetime, timedelta

from bushexa.services.leg_profile import (
    Passage,
    build_leg_profile,
    leg_samples,
    load_profile,
    parse_log_time,
    read_tsv_passages,
    save_profile,
    summarize_samples,
)

R, A, B = "196000421", "196040142", "196040234"


def _p(at, stop, vehicle="v1", route=R):
    return Passage(at, stop, route, vehicle)


def test_parse_log_time_accepts_current_and_legacy_formats():
    """현행 idx(YYYYMMDD_HH:MM:SS)와 옛 TSV(YYYY-MM-DD_HH:MM:SS)를 모두 읽고, 이상한 값은 None."""
    assert parse_log_time("20260602_11:39:19") == datetime(2026, 6, 2, 11, 39, 19)
    assert parse_log_time("2025-01-20_20:24:18") == datetime(2025, 1, 20, 20, 24, 18)
    assert parse_log_time("garbage") is None


def test_leg_samples_pairs_same_vehicle_and_restarts_on_new_run():
    """같은 차량만 짝짓고, 도착 전에 출발 정류장이 다시 나오면 새 기록부터 잰다. 너무 긴 짝은 버린다."""
    t0 = datetime(2026, 5, 6, 7, 0)
    rows = [
        _p(t0, A), _p(t0 + timedelta(minutes=10), A),            # 기점 재목격 → 07:10 부터
        _p(t0 + timedelta(minutes=70), B),                        # 60분
        _p(t0 + timedelta(minutes=65), B, vehicle="v2"),          # 다른 차량, 출발 기록 없음
        _p(t0 + timedelta(hours=3), A), _p(t0 + timedelta(hours=6), B),   # 180분 > 150 버림
        _p(t0, A, route="other"), _p(t0 + timedelta(minutes=5), B, route="other"),
    ]
    assert leg_samples(rows, R, A, B) == [(t0 + timedelta(minutes=10), 60.0)]


def test_summarize_pools_neighbor_hours_and_drops_thin_hours():
    """시간대 값은 앞뒤 1시간을 합쳐 4건 이상일 때만 싣고, 요일구분(평일/토/일·공휴일)은 공휴일 우선으로 나눈다."""
    wed = datetime(2026, 5, 6, 8, 0)        # 평일
    hol = datetime(2026, 5, 5, 8, 0)        # 어린이날(화)
    samples = [(wed, 60), (wed + timedelta(hours=1), 62), (wed + timedelta(hours=1), 64), (wed, 66),
               (wed.replace(hour=20), 50), (hol, 40)]
    out = summarize_samples(samples, {"20260505"})
    assert set(out) == {"0", "2"}
    assert out["0"]["all"]["n"] == 5
    assert out["0"]["hours"]["8"]["n"] == 4 and out["0"]["hours"]["9"]["n"] == 4
    assert "20" not in out["0"]["hours"]          # 창 표본 1건 → 전체값으로 대체
    assert out["2"]["all"]["p50"] == 40


def test_profile_roundtrip_from_tsv(tmp_path):
    """TSV → 프로필 → 파일 저장 → 다시 읽기. 대상 노선만 읽고 기간·구간이 실린다."""
    tsv = tmp_path / "logs.tsv"
    lines = ["time\tstop_id\troute_id\tvehicle_number\tstop_name"]
    for d in range(4, 9):   # 2026-05-04(월)~08(금)
        lines += [f"202605{d:02d}_07:01:00\t{A}\t{R}\tv{d}\t덕하",
                  f"202605{d:02d}_08:02:00\t{B}\t{R}\tv{d}\tUNIST",
                  f"202605{d:02d}_08:02:00\t{B}\t195000178\tx{d}\t다른 노선"]
    tsv.write_text("\n".join(lines) + "\n", encoding="utf-8")
    rows = read_tsv_passages(tsv, {R})
    assert len(rows) == 10
    prof = build_leg_profile(rows, {"20260505"}, generated_at="t", sources=["logs.tsv"],
                             legs={"deokha_unist": (R, A, B)})
    assert prof["period"] == ["2026-05-04", "2026-05-08"]
    leg = prof["legs"]["deokha_unist"]["by_day"]
    assert leg["0"]["all"] == {"n": 4, "p10": 61.0, "p50": 61.0, "p90": 61.0}
    save_profile(tmp_path / "p.json", prof)
    assert load_profile(tmp_path / "p.json") == prof
    assert load_profile(tmp_path / "missing.json") is None
