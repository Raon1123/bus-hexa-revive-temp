"""W5 — 정류소 도착 정보 서버 캐시 (F06, TP-003).

stop_id별 10초 in-process 캐시 (dict + threading.Lock).
구 Streamlit session_state 10초 캐시를 대체한다.

캐시 만료 판정은 clock.now()로 수행 (datetime.now 직접 호출 금지 — ADR-008).
TTL: 10초 (F06 §1 UPDATE_THRESHOLD 기반).
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta

from bushexa.domain.stops import StopSnapshot
from bushexa.time_utils import Clock

_TTL_SECONDS = 10

# (timestamp: datetime, snapshot: StopSnapshot)
_cache: dict[str, tuple[datetime, StopSnapshot]] = {}
_lock = threading.Lock()


def get_or_fetch(
    stop_id: str,
    fetch_fn,
    clock: Clock,
) -> StopSnapshot:
    """캐시에서 StopSnapshot을 가져오거나 fetch_fn(stop_id)을 호출해 갱신한다.

    Parameters
    ----------
    stop_id : str
        정류소 ID.
    fetch_fn :
        stop_id를 받아 StopSnapshot을 반환하는 callable.
        서명: fetch_fn(stop_id) -> StopSnapshot
    clock : Clock
        캐시 만료 판정용 시각 공급자. datetime.now 직접 호출 금지.

    Returns
    -------
    StopSnapshot
    """
    now = clock.now()
    with _lock:
        entry = _cache.get(stop_id)
        if entry is not None:
            cached_at, snapshot = entry
            if (now - cached_at) < timedelta(seconds=_TTL_SECONDS):
                return snapshot
    # 캐시 미스 또는 만료 — lock 밖에서 fetch (외부 API 블록 최소화)
    snapshot = fetch_fn(stop_id)
    with _lock:
        _cache[stop_id] = (now, snapshot)
    return snapshot


def clear_cache() -> None:
    """테스트 격리용: 전체 캐시를 비운다."""
    with _lock:
        _cache.clear()
