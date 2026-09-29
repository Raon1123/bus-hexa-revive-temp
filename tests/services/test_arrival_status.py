"""Feature 4: ArrivalStatusWriter / ArrivalStatusReader 검증."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bushexa.services.arrival_status import ArrivalStatusReader, ArrivalStatusWriter

KST = ZoneInfo("Asia/Seoul")
BASE = datetime(2026, 6, 1, 8, 0, 0, tzinfo=KST)


def test_write_then_latest(tmp_path):
    """write 후 latest()가 동일한 값을 반환한다 (성공 사이클)."""
    path = tmp_path / "arrival_status.json"
    ArrivalStatusWriter(path).write(
        cycle_started_at=BASE, stops_ok=17, stops_total=17
    )
    s = ArrivalStatusReader(path).latest()
    assert s is not None
    assert s.stops_ok == 17
    assert s.stops_total == 17
    assert s.consecutive_errors == 0
    assert s.last_success_at == BASE.isoformat()
    assert s.last_error_msg is None


def test_failure_increments_consecutive_errors(tmp_path):
    """부분 실패 사이클은 consecutive_errors를 증가시키고, 성공 시 리셋된다."""
    path = tmp_path / "arrival_status.json"
    w = ArrivalStatusWriter(path)
    r = ArrivalStatusReader(path)

    for i in range(3):
        w.write(cycle_started_at=BASE + timedelta(minutes=i),
                stops_ok=10, stops_total=17, last_error_msg="timeout")
    assert r.latest().consecutive_errors == 3

    # 성공 사이클 → 리셋
    w.write(cycle_started_at=BASE + timedelta(minutes=3),
            stops_ok=17, stops_total=17)
    s = r.latest()
    assert s.consecutive_errors == 0
    assert s.last_success_at is not None


def test_max_history_trimming(tmp_path):
    """max_history를 초과하면 오래된 항목이 잘린다."""
    path = tmp_path / "arrival_status.json"
    w = ArrivalStatusWriter(path, max_history=10)
    for i in range(15):
        w.write(cycle_started_at=BASE + timedelta(minutes=i),
                stops_ok=17, stops_total=17)
    hist = ArrivalStatusReader(path).history(limit=100)
    assert len(hist) == 10  # max_history=10 으로 잘림


def test_history_newest_first(tmp_path):
    """history()는 최신순(역순)으로 반환한다."""
    path = tmp_path / "arrival_status.json"
    w = ArrivalStatusWriter(path)
    for i in range(5):
        w.write(cycle_started_at=BASE + timedelta(minutes=i), stops_ok=i, stops_total=17)
    hist = ArrivalStatusReader(path).history(limit=5)
    assert hist[0].stops_ok == 4   # 최신
    assert hist[-1].stops_ok == 0  # 가장 오래된


def test_missing_file_returns_none(tmp_path):
    """status 파일이 없으면 latest()는 None을 반환한다."""
    r = ArrivalStatusReader(tmp_path / "no_file.json")
    assert r.latest() is None


def test_last_error_msg_redacts_service_key(tmp_path):
    """poller가 넘긴 예외 문자열에 serviceKey가 있어도 status 파일에는 가려서 저장한다 (PM-016).

    이 파일은 관리자 대시보드에 표시되므로 기록 시점에 가려야 한다.
    """
    path = tmp_path / "arrival_status.json"
    secret = "AbCd%2BSecretKey%3D%3D"
    ArrivalStatusWriter(path).write(
        cycle_started_at=datetime(2026, 6, 1, 8, 30, tzinfo=ZoneInfo("Asia/Seoul")),
        stops_ok=16, stops_total=17,
        last_error_msg=f"Read timed out. (url: /getBusArrivalInfo.xo?serviceKey={secret}&stopid=1)",
    )
    raw = path.read_text(encoding="utf-8")
    assert secret not in raw
    latest = ArrivalStatusReader(path).latest()
    assert latest.last_error_msg.endswith("serviceKey=***&stopid=1)")
