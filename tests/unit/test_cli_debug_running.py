"""debug-running CLI tests: 스냅샷 DB에서 /running 재구성 진단 출력.

테스트 의도:
- test_prints_diagnostics: --db 로 시드한 SQLite 파일을 읽어 운행·제외·분리 요약 출력 (config 불필요).
- test_unknown_route_lists_routes: 미등록 노선 → 종료코드 2 + 사용 가능 노선 목록.
- test_bad_date: 날짜 형식 오류 → 종료코드 2.
"""
from __future__ import annotations

import sqlite3

from bushexa.cli import main
from bushexa.db.repo import BusLogRepo
from bushexa.db.schema import create_schema

ROUTE_ID_713 = "195000178"
STOP_A = "196040233"
STOP_B = "196040231"


def _seed(db_path) -> None:
    conn = sqlite3.connect(str(db_path))
    create_schema(conn)
    repo = BusLogRepo(conn)
    for idx, stop_id, name in [
        ("20260601_08:00:00", STOP_A, "UNIST"),
        ("20260601_08:02:00", "XXXXXXXX", "범서중학교"),
        ("20260601_08:05:00", STOP_B, "정문"),
        ("20260601_09:35:00", STOP_A, "UNIST"),
    ]:
        repo.insert_log(idx=idx, stop_id=stop_id, route_id=ROUTE_ID_713,
                        vehicle_no="TEST-001", stop_name=name)
    conn.close()


def test_prints_diagnostics(tmp_path, capsys):
    db = tmp_path / "snap.db"
    _seed(db)

    code = main(["debug-running", "--route", ROUTE_ID_713, "--date", "2026-06-01",
                 "--db", f"sqlite:///{db}", "-v"])
    out = capsys.readouterr().out

    assert code == 0
    assert "rows=4 runs=2" in out
    assert "XXXXXXXX  범서중학교  x1" in out
    assert "TEST-001  20260601_08:05:00 → 20260601_09:35:00  (90분)" in out
    assert "08:05" in out  # -v: 정류장별 통과 시각


def test_unknown_route_lists_routes(tmp_path, capsys):
    code = main(["debug-running", "--route", "NOPE", "--db", f"sqlite:///{tmp_path / 'x.db'}"])
    out = capsys.readouterr().out

    assert code == 2
    assert ROUTE_ID_713 in out


def test_bad_date(tmp_path, capsys):
    code = main(["debug-running", "--route", ROUTE_ID_713, "--date", "abc",
                 "--db", f"sqlite:///{tmp_path / 'x.db'}"])

    assert code == 2
    assert "날짜 형식 오류" in capsys.readouterr().out


def test_missing_db_file(tmp_path, capsys):
    missing = tmp_path / "nope.db"
    code = main(["debug-running", "--route", ROUTE_ID_713, "--db", f"sqlite:///{missing}"])

    assert code == 2
    assert "DB 파일 없음" in capsys.readouterr().out
    assert not missing.exists()  # 빈 DB를 만들지 않음
