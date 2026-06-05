"""Feature 5: AuditLog 서비스 검증."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from bushexa.services.audit_log import AuditLog

KST = ZoneInfo("Asia/Seoul")


class _FakeClock:
    def __init__(self, dt):
        self._dt = dt

    def now(self):
        return self._dt


_BASE_DT = datetime(2026, 6, 1, 12, 0, 0, tzinfo=KST)


def test_record_and_load(tmp_path):
    """record()가 항목을 기록하고 load()가 최신순으로 반환한다."""
    path = tmp_path / "audit.json"
    log = AuditLog(path, clock=_FakeClock(_BASE_DT))
    log.record("holiday.add", actor_ip="127.0.0.1", date="20260601")

    entries = log.load()
    assert len(entries) == 1
    e = entries[0]
    assert e["action"] == "holiday.add"
    assert e["actor_ip"] == "127.0.0.1"
    assert e["date"] == "20260601"
    assert e["ts"] == _BASE_DT.isoformat()


def test_multiple_entries_newest_first(tmp_path):
    """여러 항목이 최신순으로 반환된다."""
    path = tmp_path / "audit.json"
    from datetime import timedelta
    log = AuditLog(path)
    log.record("a.first", actor_ip=None)
    log.record("a.second", actor_ip=None)
    log.record("a.third", actor_ip=None)

    entries = log.load()
    assert entries[0]["action"] == "a.third"   # 가장 최신
    assert entries[-1]["action"] == "a.first"  # 가장 오래된


def test_max_entries_cap(tmp_path):
    """max_entries를 초과하면 오래된 항목이 잘린다."""
    path = tmp_path / "audit.json"
    log = AuditLog(path, max_entries=5)
    for i in range(10):
        log.record(f"action.{i}", actor_ip=None)

    all_entries = log.load(limit=100)
    assert len(all_entries) == 5  # max_entries=5로 잘림


def test_record_does_not_raise_on_error(tmp_path):
    """best-effort: 기록 실패 시 예외가 전파되지 않는다."""
    # read-only 디렉터리 만들기 — tmp_path의 권한 조작 대신,
    # 존재하지 않는 깊은 경로를 사용해 직렬화 불가능한 값을 테스트
    path = tmp_path / "audit.json"
    log = AuditLog(path)

    # 직렬화 불가능한 값(set)을 details에 전달 → 내부에서 예외 발생
    # record()는 예외를 삼켜야 한다
    try:
        log.record("test.action", actor_ip=None, bad_value=object())
    except Exception:
        assert False, "record()가 예외를 전파하면 안 됩니다"


def test_empty_file_returns_empty_list(tmp_path):
    """파일이 없으면 빈 목록을 반환한다."""
    log = AuditLog(tmp_path / "no_file.json")
    assert log.load() == []
