"""Server-Timing 계측 — 페이지 서버측 단계별 소요시간 진단.

board/lite/partial 렌더의 각 단계(공휴일 API, 특별 시간표, DB, 도메인, 템플릿 렌더 등)
소요를 ``flask.g`` 에 누적하고, ``after_request`` 에서 ``Server-Timing`` 응답 헤더로 노출한다.

배포판에서 별도 프로파일러 없이 브라우저 DevTools Network → 각 요청 → Timing 패널의
"Server Timing" 섹션에서 어느 단계가 느린지 직접 확인할 수 있다. 특히 cold 상태의
data.go.kr 공휴일 API 호출(첫 요청 ~수십초 관측)을 ``holiday`` 구간으로 분리한다.

사용 예::

    from bushexa.web.timing import span

    with span("holiday"):
        holiday_set = get_effective_holiday_set(...)

오버헤드는 ``time.perf_counter()`` 두 번뿐으로 무시 가능하며, 항상 켜 두어 운영 중에도
재현 즉시 진단할 수 있도록 한다.
"""
from __future__ import annotations

import time
from contextlib import contextmanager

from flask import g

_ATTR = "_timing_spans"


def _spans() -> dict[str, float]:
    """현재 요청의 구간 누적 dict(이름 → 누적 ms). 없으면 생성."""
    spans = getattr(g, _ATTR, None)
    if spans is None:
        spans = {}
        setattr(g, _ATTR, spans)
    return spans


@contextmanager
def span(name: str):
    """``name`` 구간의 소요시간(ms)을 flask.g에 누적한다(같은 이름은 합산).

    Server-Timing 메트릭 이름 규칙상 ``name`` 은 공백 없는 토큰을 쓴다(예: ``holiday``).
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        spans = _spans()
        spans[name] = spans.get(name, 0.0) + elapsed_ms


def record(name: str, elapsed_ms: float) -> None:
    """이미 측정한 소요(ms)를 직접 누적(컨텍스트매니저를 못 쓰는 경우)."""
    spans = _spans()
    spans[name] = spans.get(name, 0.0) + elapsed_ms


def server_timing_header() -> str | None:
    """누적된 구간들을 ``Server-Timing`` 헤더 값으로 직렬화. 구간 없으면 None."""
    spans = getattr(g, _ATTR, None)
    if not spans:
        return None
    return ", ".join(f"{name};dur={ms:.1f}" for name, ms in spans.items())
