"""W3 timetable 로더·검증·저장 검증. tmp_path에 통제된 샘플 JSON을 만들어 확인."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from bushexa.data import timetable as tt


def _write(p: Path, obj: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def test_load_existing_route(tmp_path):
    """713.json(평일 UNIST 3건)을 만들고 get_timetable이 그 목록을 그대로 반환하는지."""
    _write(tmp_path / "713.json", {"0": {"UNIST": ["05:00", "05:15", "05:30"]}})
    assert tt.get_timetable("713", 0, "UNIST", dir=tmp_path) == ["05:00", "05:15", "05:30"]


def test_validate_rejects_out_of_range():
    """weekday 0에 '25:00'이 든 데이터에 validate가 code='out_of_range' 이슈를 반환하는지."""
    issues = tt.validate_timetable({"0": {"명촌": ["25:00"]}})
    assert any(i.code == "out_of_range" for i in issues)


def test_validate_rejects_duplicate():
    """동일 시각이 2번 든 데이터에 validate가 code='duplicate' 이슈를 반환하는지."""
    issues = tt.validate_timetable({"0": {"명촌": ["05:00", "05:00"]}})
    assert any(i.code == "duplicate" for i in issues)


def test_env_override(tmp_path, monkeypatch):
    """BUSHEXA_TIMETABLE_DIR 설정 시 기본 경로가 아닌 그 경로의 JSON을 읽는지."""
    monkeypatch.setenv("BUSHEXA_TIMETABLE_DIR", str(tmp_path))
    _write(tmp_path / "713.json", {"0": {"UNIST": ["06:00"]}})
    assert tt.get_timetable("713", 0, "UNIST") == ["06:00"]


def test_save_timetable_via_fileio(tmp_path):
    """[ADR-012] save_timetable이 fileio 경유로 파일을 만들고 'created' 감사 로그를 남기는지."""
    log = logging.getLogger("bushexa.data.timetable")
    records: list[logging.LogRecord] = []

    class _H(logging.Handler):
        def emit(self, r):
            records.append(r)

    h = _H()
    log.addHandler(h)
    log.setLevel(logging.INFO)
    try:
        data = {"0": {"UNIST": ["05:00", "05:15"]}}
        path = tt.save_timetable("713", data, dir=tmp_path)
    finally:
        log.removeHandler(h)

    assert json.loads(path.read_text(encoding="utf-8")) == data
    assert any("created" in r.getMessage() for r in records)
