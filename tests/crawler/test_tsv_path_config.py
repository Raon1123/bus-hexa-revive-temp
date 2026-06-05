"""W3 TSV 경로 설정 (H8/H9 회귀). /app/logs 하드코딩 제거 + 환경변수 오버라이드."""
from __future__ import annotations

import logging
import os

from bushexa.crawler.daemon import make_tsv_sink, resolve_tsv_path
from bushexa.db.repo import LogRow


def test_tsv_path_from_env(tmp_path, monkeypatch):
    """BUSHEXA_TSV_PATH를 설정하면 그 경로가 TSV 경로로 결정되고, sink가 그 파일에 쓰는지 — H8 회귀."""
    target = tmp_path / "sub" / "logs.tsv"
    monkeypatch.setenv("BUSHEXA_TSV_PATH", str(target))

    assert resolve_tsv_path(os.environ) == target

    sink = make_tsv_sink(target)
    sink(LogRow(idx="20260601_08:00:00", stop_id="999000149", route_id="195000177",
                vehicle_no="veh-A", stop_name="명촌 (기점)"))
    logging.shutdown()  # FileHandler flush 보장

    text = target.read_text(encoding="utf-8")
    assert "999000149" in text
    assert "veh-A" in text
    assert "time\tstop_id\troute_id" in text  # 헤더 행


def test_default_path_has_no_app_logs(monkeypatch):
    """환경변수 미설정 시 기본 경로가 컨테이너 하드코딩(/app/logs)이 아닌지 — H9 회귀."""
    monkeypatch.delenv("BUSHEXA_TSV_PATH", raising=False)
    path = resolve_tsv_path({})
    assert "/app/logs" not in str(path)
    assert path.name == "logs.tsv"
