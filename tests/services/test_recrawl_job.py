"""#6 E-13: RecrawlJob 파일 기반 크로스 워커 재크롤 잡 검증.

독립 출처(E-13 준수):
- test_preempt_conflict: 메타 선점 → 두 번째 start는 ConflictError(409).
- test_progress_jsonl_written: 진행 이벤트가 jsonl에 기록됨.
- test_cross_worker_progress: 다른 '워커'(새 RecrawlJob 인스턴스, 같은 data_dir)에서 progress 조회 가능.
- test_done_terminates_stream: done 이벤트 후 스트림 종결.
- test_error_terminates_stream: 크롤 실패 시 error 이벤트 후 스트림 종결.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from bushexa.services.recrawl_job import RecrawlJob, ConflictError


# ──────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────

def _simple_crawl(*, vacation, on_progress):
    """단순 crawl_fn: progress 2건 후 정상 종료."""
    on_progress({"route": "713", "day": 0, "page": 1})
    on_progress({"route": "713", "day": 0, "page": 2})


def _failing_crawl(*, vacation, on_progress):
    """실패 crawl_fn: progress 1건 후 예외."""
    on_progress({"route": "713", "day": 0, "page": 1})
    raise RuntimeError("크롤 실패 테스트")


# ──────────────────────────────────────────────────
# AC-1: 메타 선점 / 두 번째 start → ConflictError (#6)
# ──────────────────────────────────────────────────

def test_preempt_conflict(tmp_path):
    """첫 번째 잡이 실행 중일 때 두 번째 start는 ConflictError를 발생시킨다 (#6 크로스 워커 가드).

    독립 출처: #6 spec "heartbeat가 120초 이내면 ConflictError 409 — 크로스 워커 가드 복원".
    """
    release = threading.Event()

    def _blocking_crawl(*, vacation, on_progress):
        release.wait(timeout=3.0)

    job = RecrawlJob(_blocking_crawl, data_dir=tmp_path / "data")
    job_id = job.start(vacation=False)

    # 메타 파일이 job_id를 기록했는지 확인
    meta_path = tmp_path / "data" / "timetable_crawl_job.json"
    assert meta_path.exists(), "메타 파일이 생성되어야 함"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["job_id"] == job_id

    # 두 번째 start → ConflictError
    with pytest.raises(ConflictError):
        job.start(vacation=False)

    release.set()  # 첫 잡 정리


# ──────────────────────────────────────────────────
# AC-2: 진행 이벤트가 JSONL에 기록됨 (#6)
# ──────────────────────────────────────────────────

def test_progress_jsonl_written(tmp_path):
    """crawl_fn이 on_progress를 호출하면 timetable_crawl_progress.jsonl에 기록된다 (#6).

    독립 출처: #6 spec "진행 이벤트 timetable_crawl_progress.jsonl(append, 각 줄 JSON)".
    """
    done_event = threading.Event()
    _orig = _simple_crawl

    def _tracked_crawl(*, vacation, on_progress):
        _orig(vacation=vacation, on_progress=on_progress)
        done_event.set()

    job = RecrawlJob(_tracked_crawl, data_dir=tmp_path / "data")
    job.start(vacation=False)

    # 크롤이 완료될 때까지 최대 3초 대기
    done_event.wait(timeout=3.0)

    progress_path = tmp_path / "data" / "timetable_crawl_progress.jsonl"
    assert progress_path.exists(), "진행 JSONL 파일이 생성되어야 함"

    # "done" 줄은 crawl_fn 반환 뒤 _mark_done(flock) 이후에 append된다 — 고정 sleep 대신
    # 기한부 폴링으로 기다린다(부하 걸린 CI 러너에서 0.1s 고정 대기가 레이스로 실패).
    deadline = time.monotonic() + 3.0
    while '"done"' not in progress_path.read_text(encoding="utf-8") and time.monotonic() < deadline:
        time.sleep(0.02)

    lines = [l.strip() for l in progress_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) >= 2, f"progress 이벤트가 2건 이상이어야 함, found {len(lines)}"

    # 모든 줄이 유효한 JSON
    kinds = []
    for line in lines:
        rec = json.loads(line)
        kinds.append(rec["kind"])

    assert "progress" in kinds, "progress 이벤트가 기록되어야 함"
    assert "done" in kinds, "done 이벤트가 기록되어야 함"


# ──────────────────────────────────────────────────
# AC-3: 다른 '워커'(새 인스턴스)에서 progress 조회 (#6)
# ──────────────────────────────────────────────────

def test_cross_worker_progress(tmp_path):
    """start-POST 워커의 RecrawlJob이 기록한 진행을 다른 인스턴스에서도 읽을 수 있다 (#6).

    독립 출처: #6 spec "SSE GET(어느 워커든): 파일을 폴링-tail하며 새 줄을 이벤트로 보냄".
    """
    data_dir = tmp_path / "data"
    done_event = threading.Event()

    def _tracked_crawl(*, vacation, on_progress):
        _simple_crawl(vacation=vacation, on_progress=on_progress)
        done_event.set()

    # 워커 A: 잡 시작
    job_a = RecrawlJob(_tracked_crawl, data_dir=data_dir)
    job_id = job_a.start(vacation=False)

    # 크롤 완료 대기
    done_event.wait(timeout=3.0)
    time.sleep(0.2)  # JSONL flush 여유

    # 워커 B: 새 인스턴스에서 progress 조회 (crawl_fn은 실제로 실행하지 않음)
    def _dummy_crawl(*, vacation, on_progress):
        pass  # 사용하지 않음

    job_b = RecrawlJob(_dummy_crawl, data_dir=data_dir)
    events = list(job_b.progress(job_id))

    kinds = [k for k, _ in events]
    assert "progress" in kinds, "워커 B에서 progress 이벤트를 읽어야 함"
    assert "done" in kinds, "워커 B에서 done 이벤트를 읽어야 함"
    assert kinds[-1] == "done", "스트림의 마지막이 done이어야 함"


# ──────────────────────────────────────────────────
# AC-4: done 이벤트 후 스트림 종결 (#6)
# ──────────────────────────────────────────────────

def test_done_terminates_stream(tmp_path):
    """정상 종료 시 progress 이벤트 후 done으로 스트림이 종결된다 (#6, TP-010 AC-1).

    독립 출처: TP-010 §2 "progress(route/day/page) ≥1회 후 done — 스트림 종결".
    """
    done_event = threading.Event()

    def _tracked_crawl(*, vacation, on_progress):
        _simple_crawl(vacation=vacation, on_progress=on_progress)
        done_event.set()

    job = RecrawlJob(_tracked_crawl, data_dir=tmp_path / "data")
    job_id = job.start(vacation=False)

    done_event.wait(timeout=3.0)
    time.sleep(0.2)

    events = list(job.progress(job_id))
    kinds = [k for k, _ in events]

    assert "progress" in kinds, "progress 이벤트가 ≥1건이어야 함"
    assert kinds[-1] == "done", "마지막 이벤트가 done이어야 함"
    assert kinds.index("progress") < kinds.index("done"), "progress가 done보다 앞이어야 함"


# ──────────────────────────────────────────────────
# AC-5: 크롤 실패 시 error 이벤트 후 스트림 종결 (#6)
# ──────────────────────────────────────────────────

def test_error_terminates_stream(tmp_path):
    """crawl_fn이 예외를 던지면 error 이벤트 후 스트림이 종결된다 (#6).

    독립 출처: TP-010 §6 "오류 발생 시 error 이벤트로 종결" + 기존 TimetableCrawlJob 계약.
    """
    done_event = threading.Event()

    def _tracked_failing(*, vacation, on_progress):
        _failing_crawl(vacation=vacation, on_progress=on_progress)
        done_event.set()  # 예외 발생 전에는 호출되지 않음 (finally에서 처리됨)

    job = RecrawlJob(_tracked_failing, data_dir=tmp_path / "data")
    job_id = job.start(vacation=False)

    # 크롤 실패는 내부적으로 처리됨 — 최대 3초 대기
    time.sleep(1.5)

    events = list(job.progress(job_id))
    kinds = [k for k, _ in events]

    assert "progress" in kinds, "실패 전 progress 이벤트가 있어야 함"
    assert kinds[-1] == "error", "마지막 이벤트가 error이어야 함"


# ──────────────────────────────────────────────────
# AC-6: unknown job_id → KeyError (#6)
# ──────────────────────────────────────────────────

def test_unknown_job_id_raises_keyerror(tmp_path):
    """존재하지 않는 job_id로 progress()를 호출하면 KeyError가 발생한다 (#6).

    독립 출처: TP-010 §6 "미존재 job_id → 404" — 라우트가 KeyError를 abort(404)로 변환.
    """
    job = RecrawlJob(_simple_crawl, data_dir=tmp_path / "data")

    with pytest.raises(KeyError):
        list(job.progress("nonexistent-job-id"))


# ──────────────────────────────────────────────────
# 크로스 워커 가드 경계: stale heartbeat / 파손 메타 / 안전 탈출
# ──────────────────────────────────────────────────

def _write_meta(tmp_path, **meta):
    (tmp_path / "timetable_crawl_job.json").write_text(json.dumps(meta), encoding="utf-8")


def test_stale_heartbeat_allows_restart(tmp_path):
    """heartbeat가 _HEARTBEAT_TIMEOUT(120s)보다 오래된 미완료 잡은 죽은 잡으로 보고
    새 start가 ConflictError 없이 선점하는지 검증한다(워커 크래시 후 영구 409 방지)."""
    old = time.time() - 121
    _write_meta(tmp_path, job_id="dead", started_at=old, heartbeat=old, done=False, error=None)
    job = RecrawlJob(_simple_crawl, data_dir=tmp_path)
    assert job.is_running is False

    new_id = job.start()
    assert new_id != "dead"
    events = list(job.progress(new_id))
    assert events[-1] == ("done", None)


def test_fresh_heartbeat_blocks_restart(tmp_path):
    """heartbeat가 최근인 미완료 잡이 있으면(다른 워커 실행 중) is_running=True이고 start가 ConflictError인지 검증한다."""
    now = time.time()
    _write_meta(tmp_path, job_id="alive", started_at=now, heartbeat=now, done=False, error=None)
    job = RecrawlJob(_simple_crawl, data_dir=tmp_path)
    assert job.is_running is True
    with pytest.raises(ConflictError):
        job.start()


def test_corrupt_meta_treated_as_idle(tmp_path):
    """메타 JSON이 파손돼 있으면 빈 메타로 간주 — is_running=False, start 가능한지 검증한다."""
    (tmp_path / "timetable_crawl_job.json").write_text("{not json", encoding="utf-8")
    job = RecrawlJob(_simple_crawl, data_dir=tmp_path)
    assert job.is_running is False
    job_id = job.start()
    assert list(job.progress(job_id))[-1] == ("done", None)


def test_progress_safe_exit_when_meta_done_but_jsonl_lacks_terminal(tmp_path, monkeypatch):
    """메타는 done인데 JSONL에 done 줄이 없으면(append 실패 등) 무한 대기하지 않고
    메타 기준으로 ('done', None)을 내고 종결하는지 검증한다."""
    import bushexa.services.recrawl_job as rj
    monkeypatch.setattr(rj, "_POLL_INTERVAL", 0)
    now = time.time()
    _write_meta(tmp_path, job_id="j1", started_at=now, heartbeat=now, done=True, error=None)
    (tmp_path / "timetable_crawl_progress.jsonl").write_text(
        json.dumps({"kind": "progress", "payload": {"page": 1}, "ts": now}) + "\n",
        encoding="utf-8")

    events = list(RecrawlJob(_simple_crawl, data_dir=tmp_path).progress("j1"))
    assert events == [("progress", {"page": 1}), ("done", None)]


def test_progress_safe_exit_with_meta_error(tmp_path, monkeypatch):
    """메타에 error만 기록되고 JSONL이 없을 때 메타의 에러 메시지로 ('error', Exception)을 내고 종결하는지 검증한다."""
    import bushexa.services.recrawl_job as rj
    monkeypatch.setattr(rj, "_POLL_INTERVAL", 0)
    now = time.time()
    _write_meta(tmp_path, job_id="j1", started_at=now, heartbeat=now, done=False, error="api 99")

    events = list(RecrawlJob(_simple_crawl, data_dir=tmp_path).progress("j1"))
    assert len(events) == 1
    kind, exc = events[0]
    assert kind == "error" and str(exc) == "api 99"


def test_progress_skips_malformed_jsonl_lines(tmp_path):
    """JSONL에 파손된 줄이 섞여 있어도 건너뛰고 유효한 이벤트만 순서대로 yield하는지 검증한다."""
    now = time.time()
    _write_meta(tmp_path, job_id="j1", started_at=now, heartbeat=now, done=True, error=None)
    lines = [
        json.dumps({"kind": "progress", "payload": {"page": 1}, "ts": now}),
        "{broken",
        "",
        json.dumps({"kind": "done", "payload": None, "ts": now}),
    ]
    (tmp_path / "timetable_crawl_progress.jsonl").write_text("\n".join(lines) + "\n",
                                                             encoding="utf-8")

    events = list(RecrawlJob(_simple_crawl, data_dir=tmp_path).progress("j1"))
    assert events == [("progress", {"page": 1}), ("done", None)]


def test_progress_ends_when_job_replaced(tmp_path, monkeypatch):
    """스트림 도중 메타의 job_id가 다른 잡으로 바뀌면(새 잡이 선점) 이전 스트림이 조용히 종결되는지 검증한다."""
    import bushexa.services.recrawl_job as rj
    now = time.time()
    _write_meta(tmp_path, job_id="old", started_at=now, heartbeat=now, done=False, error=None)
    (tmp_path / "timetable_crawl_progress.jsonl").write_text("", encoding="utf-8")

    def fake_sleep(_s):
        _write_meta(tmp_path, job_id="new", started_at=now, heartbeat=now, done=False, error=None)

    monkeypatch.setattr(rj.time, "sleep", fake_sleep)
    assert list(RecrawlJob(_simple_crawl, data_dir=tmp_path).progress("old")) == []


def test_dataclass_progress_payload_serialized(tmp_path):
    """on_progress에 dataclass(ProgressEvent류)를 넘기면 dict로 직렬화되어 스트림에 전달되는지 검증한다."""
    from dataclasses import dataclass

    @dataclass
    class Ev:
        route: str
        page: int

    def crawl(*, vacation, on_progress):
        on_progress(Ev("713", 3))

    job = RecrawlJob(crawl, data_dir=tmp_path)
    events = list(job.progress(job.start()))
    assert events == [("progress", {"route": "713", "page": 3}), ("done", None)]


def test_error_payload_and_meta_redact_service_key(tmp_path):
    """재크롤 실패 예외에 요청 URL(serviceKey)이 섞여도 진행 JSONL·메타 파일에는 가려서 저장한다 (PM-016).

    두 파일은 SSE로 관리자 브라우저에 그대로 전달된다.
    """
    secret = "AbCd%2BSecretKey%3D%3D"

    def _crawl_with_url_error(*, vacation, on_progress):
        raise RuntimeError(f"Max retries exceeded with url: /BusTimetable.xo?serviceKey={secret}&routeNo=713")

    job = RecrawlJob(_crawl_with_url_error, data_dir=tmp_path / "data")
    job_id = job.start(vacation=False)
    deadline = time.time() + 5
    while time.time() < deadline:
        events = list(job.progress(job_id))
        if events and events[-1][0] == "error":
            break
        time.sleep(0.1)

    stored = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "data").rglob("*") if p.is_file())
    assert secret not in stored
    assert "serviceKey=***" in stored
    assert events[-1][0] == "error" and secret not in str(events[-1][1])  # SSE로 나가는 오류 값
