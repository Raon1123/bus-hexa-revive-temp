"""차량 위치 타임라인 상태 (W1).

H2 회귀: govtrack 데몬의 in-memory 상태(``bus_timeline = {}``)는 프로세스 로컬이라
재시작 시 모든 차량을 "신규"로 보고 현재 위치를 통과시각으로 오기록하는 false-positive를
유발했다(PM-001). 본 모듈은 ``warm_from_repo``로 DB의 직전 위치를 적재하고,
``JSONFileStore``로 프로세스 간 상태를 영속해 그 결함을 봉인한다.

상태 키는 ``(route_id, vehicle_no)``, 값은 마지막으로 관측된 ``node_id``.
JSON은 tuple 키를 쓸 수 없으므로 ``[route_id, vehicle_no, node_id]`` 레코드 목록으로 저장한다.
파일 쓰기는 ADR-012 ``fileio.atomic_write_json`` choke-point를 경유한다(원자적 + 감사 로그).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from bushexa import fileio

logger = logging.getLogger("bushexa.crawler.state")

Snapshot = dict[tuple[str, str], str]


@runtime_checkable
class TimelineStore(Protocol):
    """타임라인 영속 계약 (F09 §6). load/save만 노출."""

    def load(self) -> Snapshot: ...
    def save(self, snapshot: Snapshot) -> None: ...


class InMemoryStore:
    """프로세스 메모리에만 사는 store (테스트·단발 실행용)."""

    def __init__(self, initial: Snapshot | None = None) -> None:
        self._data: Snapshot = dict(initial or {})

    def load(self) -> Snapshot:
        return dict(self._data)

    def save(self, snapshot: Snapshot) -> None:
        self._data = dict(snapshot)


class JSONFileStore:
    """JSON 파일 영속 store. tuple 키를 ``[rid, veh, node]`` 레코드로 직렬화한다.

    쓰기는 ``fileio.atomic_write_json``(ADR-012)로 원자적 기록 + 감사 로그.
    파일이 없거나 손상되면 빈 상태로 시작한다(데몬이 죽지 않게, ADR-013).
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(self) -> Snapshot:
        if not self.path.exists():
            return {}
        try:
            records = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            # 손상 파일에 데몬이 죽지 않도록 빈 상태로 시작하되, 침묵하지 않는다(ADR-013).
            logger.warning("타임라인 상태 로드 실패(%s), 빈 상태로 시작: %s", self.path, exc)
            return {}
        out: Snapshot = {}
        for rec in records:
            try:
                rid, veh, node = rec
            except (ValueError, TypeError):
                logger.warning("타임라인 레코드 형식 오류, 건너뜀: %r", rec)
                continue
            out[(rid, veh)] = node
        return out

    def save(self, snapshot: Snapshot) -> None:
        records = [[rid, veh, node] for (rid, veh), node in snapshot.items()]
        fileio.atomic_write_json(self.path, records)


class VehicleTimeline:
    """``(route_id, vehicle_no)`` → 마지막 ``node_id``. 변경 감지 + 영속/워밍."""

    def __init__(self, store: TimelineStore | None = None) -> None:
        self._store: TimelineStore = store or InMemoryStore()
        self._last: Snapshot = self._store.load()

    def last_node(self, route_id: str, vehicle_no: str) -> str | None:
        return self._last.get((route_id, vehicle_no))

    def record(self, route_id: str, vehicle_no: str, node_id: str, ts: datetime) -> bool:
        """직전 node와 다르면 True(변경=기록 후보), 같으면 False. 상태는 항상 갱신한다.

        ``ts``는 F09 §6 계약 시그니처 유지를 위한 인자다(현재는 호출자가 timestamp를
        직접 idx로 만들므로 상태에 저장하지 않는다 — 향후 체류시간 분석 시 활용 여지).
        """
        key = (route_id, vehicle_no)
        changed = self._last.get(key) != node_id
        self._last[key] = node_id
        return changed

    def warm_from_repo(self, repo, since: datetime) -> int:
        """데몬 시작 시 DB의 차량별 최근 통과 node를 적재(H2). 워밍된 차량 수 반환.

        이미 ``_last``에 있는 키(영속 파일에서 온 최신 상태)는 보존한다 — 파일이 DB의
        tracked-passage proxy보다 더 최근의 실관측일 수 있으므로 파일을 우선한다.
        """
        latest = repo.latest_node_per_vehicle(since=since)
        warmed = 0
        for key, node in latest.items():
            if key not in self._last:
                self._last[key] = node
                warmed += 1
        return warmed

    def persist(self) -> None:
        self._store.save(self._last)
