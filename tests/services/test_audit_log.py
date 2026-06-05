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


# ──────────────────────────────────────────────────
# #7 E-13: 스레드 2개 동시 record 후 둘 다 존재
# ──────────────────────────────────────────────────

def test_concurrent_record_no_loss(tmp_path):
    """스레드 2개가 동시에 record()를 호출해도 두 항목이 모두 저장된다 (#7).

    locked_update_json(fcntl.flock) 크로스 프로세스 잠금으로 read-modify-write
    경쟁 조건을 방지해야 한다.

    독립 출처: 2개 항목 기록 → load()가 2건 이상 반환해야 한다는 사양(#7).
    """
    import threading

    path = tmp_path / "audit_concurrent.json"
    log = AuditLog(path)

    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def _record_action(action: str) -> None:
        try:
            barrier.wait()  # 두 스레드가 동시에 시작하도록 동기화
            log.record(action, actor_ip="127.0.0.1")
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=_record_action, args=("audit.thread1",))
    t2 = threading.Thread(target=_record_action, args=("audit.thread2",))
    t1.start()
    t2.start()
    t1.join(timeout=5.0)
    t2.join(timeout=5.0)

    assert not errors, f"스레드 record 중 예외 발생: {errors}"

    entries = log.load(limit=100)
    actions = {e["action"] for e in entries}
    assert "audit.thread1" in actions, "스레드1 record가 저장되어야 함"
    assert "audit.thread2" in actions, "스레드2 record가 저장되어야 함"
    assert len(entries) == 2, f"두 항목이 모두 존재해야 함, found {len(entries)}"
