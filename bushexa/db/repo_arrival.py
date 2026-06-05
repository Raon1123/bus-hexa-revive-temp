"""울산 도착정보 백업본 저장소 (W11, ADR-010).

화면은 울산 API를 직접 호출하지 않고 이 백업본(``bus_arrival_cache``)을 읽는다. arrival poller(P2)가
stop_id별로 최신 스냅샷을 upsert한다(이력 아님 — 항상 1 stop_id = 1 row). payload는 도착 목록을
JSON 문자열로 직렬화해 저장하고 ``fetched_at``(신선도)을 함께 보관한다.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from bushexa.db.connection import placeholder_for_conn


@dataclass(frozen=True)
class ArrivalSnapshot:
    stop_id: str
    payload: Any  # 역직렬화된 도착 목록
    fetched_at: str


class BusArrivalRepo:
    def __init__(self, conn):
        self.conn = conn
        self._ph = placeholder_for_conn(conn)

    def upsert(self, stop_id: str, payload: Any, fetched_at: str) -> None:
        """stop_id 기준 upsert. 같은 stop_id면 최신 payload·fetched_at으로 갱신(행 1개 유지)."""
        ph = self._ph
        sql = (f"INSERT INTO bus_arrival_cache (stop_id, payload, fetched_at) "
               f"VALUES ({ph}, {ph}, {ph}) "
               f"ON CONFLICT(stop_id) DO UPDATE SET "
               f"payload = excluded.payload, fetched_at = excluded.fetched_at")
        cur = self.conn.cursor()
        cur.execute(sql, (stop_id, json.dumps(payload, ensure_ascii=False), fetched_at))
        self.conn.commit()

    def get(self, stop_id: str) -> ArrivalSnapshot | None:
        ph = self._ph
        cur = self.conn.cursor()
        cur.execute(f"SELECT stop_id, payload, fetched_at FROM bus_arrival_cache "
                    f"WHERE stop_id = {ph}", (stop_id,))
        row = cur.fetchone()
        if row is None:
            return None
        return ArrivalSnapshot(stop_id=row[0], payload=json.loads(row[1]), fetched_at=row[2])

    def get_many(self, stop_ids: Iterable[str]) -> dict[str, ArrivalSnapshot]:
        """여러 stop_id를 한 번에 조회해 stop_id→snapshot 매핑 반환(화면 일괄 조회)."""
        stop_ids = list(stop_ids)
        if not stop_ids:
            return {}
        ph = self._ph
        marks = ", ".join([ph] * len(stop_ids))
        cur = self.conn.cursor()
        cur.execute(f"SELECT stop_id, payload, fetched_at FROM bus_arrival_cache "
                    f"WHERE stop_id IN ({marks})", tuple(stop_ids))
        out: dict[str, ArrivalSnapshot] = {}
        for sid, payload, fetched_at in cur.fetchall():
            out[sid] = ArrivalSnapshot(stop_id=sid, payload=json.loads(payload), fetched_at=fetched_at)
        return out
