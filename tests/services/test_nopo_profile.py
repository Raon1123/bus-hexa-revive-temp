"""노포 구간 소요 실측 프로필 — DB 통과기록에서 요약하고, 기록이 없으면 기존 파일을 지키는지 검증."""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from bushexa.services.nopo_profile import load_nopo_profile, nopo_profile_path, refresh_nopo_profile


def _db(path, rows):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE bus_timelog (idx VARCHAR(40), stop_id VARCHAR(20), route_id VARCHAR(20), "
              "route_nm VARCHAR(20), vehicle_number VARCHAR(20), stop_name VARCHAR(50))")
    c.executemany("INSERT INTO bus_timelog VALUES (?,?,?,?,?,?)", rows)
    c.commit()
    c.close()


def test_refresh_builds_profile_from_passages(tmp_path):
    """1224 가 농소(195025331)→좋은삼정병원앞(193030929)을 33분에 지난 기록이 소요 33분으로 요약된다."""
    db = tmp_path / "t.db"
    rows = []
    for d in range(1, 5):
        rows += [(f"2026090{d}_08:00:00", "195025331", "195000247", "1224", "v1", ""),
                 (f"2026090{d}_08:33:00", "193030929", "195000247", "1224", "v1", "")]
    _db(db, rows)
    cfg = SimpleNamespace(database_url=f"sqlite:///{db}", data_dir=tmp_path)
    assert refresh_nopo_profile(cfg) is True
    leg = load_nopo_profile(tmp_path)["legs"]["1224_origin_stop"]["by_day"]
    assert leg["0"]["all"]["p50"] == 33.0 and leg["0"]["all"]["n"] == 4


def test_refresh_without_passages_keeps_existing_file(tmp_path):
    """통과기록이 없으면 갱신을 건너뛰고 이미 있던 프로필 파일을 그대로 둔다."""
    db = tmp_path / "t.db"
    _db(db, [])
    nopo_profile_path(tmp_path).write_text('{"legs": {"x": {}}}')
    cfg = SimpleNamespace(database_url=f"sqlite:///{db}", data_dir=tmp_path)
    assert refresh_nopo_profile(cfg) is False
    assert load_nopo_profile(tmp_path) == {"legs": {"x": {}}}
