"""W4 시간표 재크롤 (F10). 기대값은 주입한 페이지·totalCnt에서 직접 도출(E-13)."""
from __future__ import annotations

import json

import pytest
import requests

from bushexa.api_clients.ulsan_bis import TimetableRow
from bushexa.crawler.timetable_crawl import (
    ProgressEvent,
    TimetableCrawlError,
    crawl_all_timetables,
    crawl_route_day,
)

BUSNOS = {"513", "713", "743", "753", "1115"}


class FakeTimetableClient:
    """page=1에 고정 행과 totalCnt를 돌려주는 시간표 client 대역. 요청 페이지를 기록한다."""

    def __init__(self, rows, total=None):
        self._rows = list(rows)
        self._total = total if total is not None else len(rows)
        self.requested: list[tuple[str, int, int]] = []

    def fetch_timetable_page(self, route_no, day_of_week, *, page=1, rows=50):
        self.requested.append((str(route_no), day_of_week, page))
        if page == 1:
            return list(self._rows), self._total
        return [], self._total


def test_writes_five_routes(tmp_path):
    """mock 시간표 응답으로 재크롤을 돌리면 5개 노선 JSON이 atomic하게 기록되고 각 파일이
    valid JSON(요일 키 0/1/2)인지 검증한다."""
    client = FakeTimetableClient([TimetableRow("05:30", 1), TimetableRow("06:15", 2)], total=2)

    written = crawl_all_timetables(client, out_dir=tmp_path)

    assert set(written) == BUSNOS
    for busno in BUSNOS:
        path = tmp_path / f"{busno}.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert set(data.keys()) == {"0", "1", "2"}  # 평일/토/일·공휴일


def test_progress_callback():
    """on_progress에 수집 리스트를 주면 페이지마다 ProgressEvent(route, day, page)가 순서대로
    전달되는지 검증한다(2페이지 분량)."""
    events: list[ProgressEvent] = []
    client = FakeTimetableClient([TimetableRow("05:30", 1)], total=75)  # 75 > 50 → 2페이지

    crawl_route_day(client, "713", 0, rows=50, on_progress=events.append)

    assert [(e.route, e.day, e.page) for e in events] == [("713", 0, 1), ("713", 0, 2)]


def test_pagination_no_off_by_one():
    """totalCount가 페이지 크기의 정확한 배수(100/50)일 때 마지막 빈 페이지를 추가 요청하지
    않는지 검증한다 — F10 결함5 회귀."""
    client = FakeTimetableClient([TimetableRow("05:30", 1)], total=100)

    crawl_route_day(client, "713", 0, rows=50)

    pages = [p for (_r, _d, p) in client.requested]
    assert pages == [1, 2]  # 3페이지(빈 페이지)를 요청하지 않음


def test_atomic_write_on_failure(tmp_path, monkeypatch):
    """쓰기 도중 예외(os.replace 실패)를 주입하면 기존 JSON이 손상되지 않고 보존되는지 검증한다.

    크롤은 직접 open-truncate 하지 않고 fileio.atomic_write_json(임시파일+rename)에 위임하므로,
    rename 실패 시 원본이 그대로 남아야 한다.
    """
    sentinel = tmp_path / "513.json"
    sentinel.write_text('{"sentinel": true}', encoding="utf-8")

    def _boom(*a, **k):
        raise OSError("rename failed")

    monkeypatch.setattr("bushexa.fileio.os.replace", _boom)
    client = FakeTimetableClient([TimetableRow("05:30", 1)], total=1)

    try:
        crawl_all_timetables(client, out_dir=tmp_path)
    except OSError:
        pass  # 첫 노선(513) 기록에서 rename 실패가 전파된다(쓰기 오류는 격리 대상 아님)

    assert json.loads(sentinel.read_text(encoding="utf-8")) == {"sentinel": True}


class FlakyTimetableClient(FakeTimetableClient):
    """처음 ``fail_first``회 호출은 일시 네트워크 오류를 던지는 client 대역(ADR-013 재시도 검증)."""

    def __init__(self, rows, total=None, *, fail_first=0):
        super().__init__(rows, total)
        self._remaining_failures = fail_first

    def fetch_timetable_page(self, route_no, day_of_week, *, page=1, rows=50):
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            self.requested.append((str(route_no), day_of_week, page))
            raise requests.exceptions.ReadTimeout("read timed out")
        return super().fetch_timetable_page(route_no, day_of_week, page=page, rows=rows)


def test_retry_recovers_from_transient_error():
    """일시 오류 2회 후 성공하면 백오프(1s, 2s) 재시도로 결과를 얻는지 검증한다 — ADR-013 결정 4."""
    client = FlakyTimetableClient([TimetableRow("05:30", 1)], total=1, fail_first=2)
    sleeps: list[float] = []

    rows = crawl_route_day(client, "713", 0, attempts=3, sleep=sleeps.append)

    assert [r.time for r in rows] == ["05:30"]
    assert sleeps == [1, 2]  # 지수 백오프, 무한 즉시 재시도 금지


def test_retry_exhausted_raises():
    """재시도 상한(3회) 초과 시 마지막 네트워크 예외가 전파되는지 검증한다."""
    client = FlakyTimetableClient([TimetableRow("05:30", 1)], total=1, fail_first=3)

    with pytest.raises(requests.exceptions.ReadTimeout):
        crawl_route_day(client, "713", 0, attempts=3, sleep=lambda _s: None)


class OneRouteDownClient(FakeTimetableClient):
    """특정 노선만 항상 네트워크 오류를 던지는 client 대역(노선 격리 검증)."""

    def __init__(self, rows, total=None, *, down_route="513"):
        super().__init__(rows, total)
        self._down_route = down_route

    def fetch_timetable_page(self, route_no, day_of_week, *, page=1, rows=50):
        if str(route_no) == self._down_route:
            raise requests.exceptions.ConnectTimeout("connection timed out")
        return super().fetch_timetable_page(route_no, day_of_week, page=page, rows=rows)


def test_one_route_failure_isolated(tmp_path):
    """한 노선(513)이 계속 실패해도 나머지 4개 노선은 기록되고, 실패 노선 파일은 쓰지 않으며,
    종료 시 TimetableCrawlError로 부분 실패를 집계 보고하는지 검증한다 — ADR-013 결정 2.

    2026-06-05 울산 API 간헐 무응답 실측 회귀: 기존엔 첫 실패가 전체 스윕을 중단시켰다."""
    sentinel = tmp_path / "513.json"
    sentinel.write_text('{"sentinel": true}', encoding="utf-8")
    client = OneRouteDownClient([TimetableRow("05:30", 1)], total=1, down_route="513")

    with pytest.raises(TimetableCrawlError) as excinfo:
        crawl_all_timetables(client, out_dir=tmp_path, attempts=2, sleep=lambda _s: None)

    err = excinfo.value
    assert set(err.failed) == {"513"}
    assert set(err.written) == BUSNOS - {"513"}
    for busno in BUSNOS - {"513"}:
        assert (tmp_path / f"{busno}.json").exists()
    # 실패 노선은 부분 시간표로 덮어쓰지 않는다 — 기존 파일 보존
    assert json.loads(sentinel.read_text(encoding="utf-8")) == {"sentinel": True}


def test_all_empty_crawl_preserves_existing_file(tmp_path):
    """전 요일 0행 수집(클라이언트 오류 검사를 통과한 알 수 없는 오류·빈 페이지)이면 파일을
    쓰지 않고 실패로 집계해 기존 시간표를 보존하는지 — 빈 덮어쓰기 방지(2026-06-05 리뷰)."""
    existing = tmp_path / "713.json"
    existing.write_text(json.dumps({"0": {"덕하": ["05:30"]}}), encoding="utf-8")

    client = FakeTimetableClient([], total=0)  # 모든 노선·요일이 빈 결과

    with pytest.raises(TimetableCrawlError) as exc_info:
        crawl_all_timetables(client, out_dir=tmp_path)

    assert set(exc_info.value.failed) == BUSNOS  # 전 노선 실패 집계
    assert exc_info.value.written == {}
    # 기존 713.json은 빈 데이터로 덮이지 않고 보존된다
    assert json.loads(existing.read_text(encoding="utf-8")) == {"0": {"덕하": ["05:30"]}}
    # 다른 노선 파일은 생성되지 않는다
    assert not (tmp_path / "1115.json").exists()
