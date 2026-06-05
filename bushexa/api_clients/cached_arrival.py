"""cache 기반 도착정보 클라이언트 — 화면 서빙 경로 전용 (ADR-010 정합).

배경: 화면(`board`/`stops`/`unist_board`)이 ``UlsanBisClient``를 직접 만들어 매 요청·매 HTMX
폴링마다 느린 울산 API를 라이브 호출하던 문제를 바로잡는다. ADR-010이 의도한 대로, 화면은
arrival poller가 ``bus_arrival_cache``에 백업해 둔 스냅샷만 읽는다.

이 어댑터는 ``UlsanBisClient.fetch_arrivals(stop_id) -> list[Arrival]``과 동일한 인터페이스를
제공하는 **드롭인 대체재**다. 도메인(`get_board_data` 등)은 client 주입형이므로 시그니처 변경
없이 이 객체를 넘기기만 하면 된다. 네트워크 호출이 없어 화면 응답이 빠르다.
"""
from __future__ import annotations

import logging
from dataclasses import fields

from bushexa.api_clients.ulsan_bis import Arrival
from bushexa.db.repo_arrival import BusArrivalRepo

logger = logging.getLogger("bushexa.api_clients.cached_arrival")

# Arrival 재구성 시 허용할 필드명(payload에 잉여 키가 섞여도 안전하게 필터).
_ARRIVAL_FIELDS = {f.name for f in fields(Arrival)}


class CachedArrivalClient:
    """``BusArrivalRepo``의 백업본을 읽어 ``Arrival`` 목록을 돌려주는 클라이언트.

    poller가 ``[asdict(a) for a in arrivals]`` 형태로 저장하므로, payload의 dict를 그대로
    ``Arrival``로 복원한다. cache 미스(아직 폴링 전/해당 정류장 없음)는 ``[]``로 처리한다 —
    라이브 클라이언트가 오류 시 ``[]``을 반환하던 것과 동일한 graceful 동작(ADR-013).
    """

    def __init__(self, repo: BusArrivalRepo):
        self._repo = repo

    def fetch_arrivals(self, stop_id: str, *, page: int = 1, rows: int = 50) -> list[Arrival]:
        # page/rows는 라이브 클라와 시그니처 호환을 위해 받되, cache는 전체 스냅샷이라 무시.
        snapshot = self._repo.get(stop_id)
        if snapshot is None or not snapshot.payload:
            return []
        out: list[Arrival] = []
        for item in snapshot.payload:
            try:
                out.append(Arrival(**{k: v for k, v in item.items() if k in _ARRIVAL_FIELDS}))
            except (TypeError, AttributeError) as exc:
                logger.warning("cache payload 항목 복원 실패 stop=%s: %s", stop_id, exc)
        return out

    def last_fetched_at(self, stop_id: str) -> str | None:
        """해당 정류장 백업본의 신선도(ISO8601 KST). 없으면 None — staleness 표시용."""
        snapshot = self._repo.get(stop_id)
        return snapshot.fetched_at if snapshot else None
