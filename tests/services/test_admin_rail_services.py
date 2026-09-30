"""/admin/rail 서비스 검증 — 환승 설정 저장소, 철도 상태 요약, 프로필 병합·적용·되돌리기, 잡 이름·스냅샷·인자."""
from __future__ import annotations

import time
from datetime import date

import pytest

from bushexa.services.ktx_settings import KtxSettingsStore
from bushexa.services.leg_profile import (
    default_profile_path,
    load_profile,
    merge_profiles,
    previous_profile_path,
    promote_profile,
    rollback_profile,
    save_profile,
)
from bushexa.services.rail_status import summarize_rail_store
from bushexa.services.recrawl_job import RecrawlJob


def test_ktx_settings_strict_save_lenient_load(tmp_path):
    """save 는 범위 밖·비정수를 거부하고 빈 값은 기본값 복귀, load 는 깨진 값을 무시한다."""
    store = KtxSettingsStore(tmp_path / "k.json")
    assert store.effective() == {"transfer_station_min": 5, "transfer_jinmok_min": 5}
    assert store.save(transfer_station_min="7", transfer_jinmok_min="") == {"transfer_station_min": 7}
    assert store.effective()["transfer_station_min"] == 7
    with pytest.raises(ValueError):
        store.save(transfer_station_min="31")
    with pytest.raises(ValueError):
        store.save(transfer_jinmok_min="abc")
    (tmp_path / "k.json").write_text('{"transfer_station_min": -3}', encoding="utf-8")
    assert store.effective()["transfer_station_min"] == 5


def test_rail_status_summary_flags_missing_suspect_and_stops():
    """구간별로 저장 없음·오늘 없음·급감·정차역 미확인을 경고로 붙인다."""
    today = date(2026, 9, 30)
    t = lambda d, stops: {"dep": f"{d}T07:00:00+09:00", "arr": f"{d}T09:00:00+09:00", "stops": stops}  # noqa: E731
    store = {"trains": {"last_success_date": "2026-09-29", "pairs": {
        "NATH13717-NAT014445": {"dates": {"2026-09-30": {"trains": [t("2026-09-30", None)]},
                                          "2026-10-01": {"trains": [], "suspect": True}}},
        "NATH13717-NAT010000": {"dates": {"2026-10-01": {"trains": [t("2026-10-01", None)]}}},
    }}}
    s = summarize_rail_store(store, today)
    assert not s.ok_today
    busan = next(p for p in s.pairs if p.key == "NATH13717-NAT014445")
    assert busan.today_trains == 1 and busan.suspect == ("2026-10-01",) and not busan.wants_stops
    seoul = next(p for p in s.pairs if p.key == "NATH13717-NAT010000")
    assert "오늘 열차 없음" in seoul.warnings and "정차역 정보 없음" in seoul.warnings
    suseo = next(p for p in s.pairs if p.key == "NATH13717-NATH30000")
    assert suseo.dates == 0 and "저장된 날짜 없음 — 재수집 필요" in suseo.warnings


def _prof(**legs):
    return {"version": 1, "period": ["2026-01-01", "2026-06-01"], "legs": {
        leg: {"route_id": "r", "by_day": {d: {"all": {"n": n, "p10": 1, "p50": 2, "p90": 3}, "hours": {}}
                                         for d, n in days.items()}} for leg, days in legs.items()}}


def test_merge_keeps_larger_sample_per_leg_and_day():
    """병합은 구간·요일별로 n 이 큰 쪽을 고르고(같으면 현재), 새 구간은 후보에서 채운다."""
    current = _prof(deokha_unist={"0": 700, "1": 10})
    candidate = _prof(deokha_unist={"0": 50, "1": 30}, l5001_origin_jinmok={"0": 25})
    candidate["period"] = ["2026-09-01", "2026-09-30"]
    merged, choices = merge_profiles(current, candidate)
    assert choices["deokha_unist"] == {"0": "current", "1": "candidate"}
    assert choices["l5001_origin_jinmok"] == {"0": "candidate"}
    assert merged["legs"]["deokha_unist"]["by_day"]["1"]["all"]["n"] == 30
    assert merged["period"] == ["2026-01-01", "2026-09-30"]


def test_promote_and_rollback_swap_with_prev(tmp_path):
    """적용하면 이전 값이 .prev 로, 되돌리기는 맞바꾼다. prev 가 없으면 False."""
    assert rollback_profile(tmp_path) is False
    save_profile(default_profile_path(tmp_path), _prof(a={"0": 1}))
    promote_profile(tmp_path, _prof(b={"0": 2}))
    assert "b" in load_profile(default_profile_path(tmp_path))["legs"]
    assert "a" in load_profile(previous_profile_path(tmp_path))["legs"]
    assert rollback_profile(tmp_path) is True
    assert "a" in load_profile(default_profile_path(tmp_path))["legs"]
    assert "b" in load_profile(previous_profile_path(tmp_path))["legs"]


def test_named_job_passes_params_and_snapshot(tmp_path):
    """이름별 잡 파일을 쓰고, start 인자를 작업 함수에 넘기며, snapshot 은 블로킹 없이 상태·이벤트를 준다."""
    seen = {}

    def fn(*, vacation, on_progress, days):
        seen["days"] = days
        on_progress({"stage": "trains", "label": "x", "ok": True})

    job = RecrawlJob(fn, data_dir=tmp_path, name="rail_crawl")
    job.start(days=3)
    for _ in range(50):
        if job.snapshot()["done"]:
            break
        time.sleep(0.05)
    snap = job.snapshot()
    assert seen == {"days": 3} and snap["done"] and not snap["running"]
    assert snap["events"][0]["payload"]["label"] == "x"
    assert (tmp_path / "rail_crawl_job.json").exists() and not (tmp_path / "timetable_crawl_job.json").exists()
