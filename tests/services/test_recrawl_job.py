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
    time.sleep(0.1)  # JSONL flush 여유

    progress_path = tmp_path / "data" / "timetable_crawl_progress.jsonl"
    assert progress_path.exists(), "진행 JSONL 파일이 생성되어야 함"

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
