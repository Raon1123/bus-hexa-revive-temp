"""Govtrack 기록기 — 버스 위치 응답을 bus_timelog INSERT 결정으로 변환 (W2a/b/c).

PM-001 회복의 중심. 책임:
- run_single_route: 한 노선 1회 폴링 + 차량별 변경 감지. **차량별 try/except 격리(H4)** 와
  ``STOP_IDS.get`` 안전 조회(H3)로 한 차량/미등록 정류장이 사이클을 죽이지 않게 한다.
- run_cycle: 전 노선 순회 후 후보 행을 **사이클당 1 트랜잭션으로 batch insert(H5)**.
  per-vehicle 격리는 오염 행을 batch 밖으로 걸러 batch가 항상 깨끗하게 commit되게 하는 게이트다.
  DB 연결 끊김(OperationalError) 시 다음 사이클 시작 시 재연결한다.
- alert hook: result_code≠"00" 등 노선별 5사이클 연속 실패 시 1회 alert(H6, 침묵 실패 방지).

[설계 실현 메모] F09 §4.4의 ``GovtrackRecorder(client, parser, state, ...)``에서 ``parser``는
P1에서 ``TagoClient.fetch_bus_locations``가 이미 파싱된 ``TagoResponse.items``를 반환하도록
감리·동결되며 client 내부 책임으로 흡수되었다. 따라서 본 생성자는 ``parser``를 받지 않는다
(P2 doc §5 W2a changelog 참조). AC를 약화하는 변경이 아니라 파싱 책임의 단일화다(E-13 무위반).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from bushexa.data.constants import STOP_IDS
from bushexa.db.connection import operational_errors
from bushexa.db.repo import LogRow

logger = logging.getLogger("bushexa.crawler.recorder")

# 감사 2-1/2-6: node_ord 역전 허용 범위. 이 값 이하의 역전은 GPS 지터로 간주해 기록 skip.
# 초과(또는 None) 역전은 종점 회차로 보고 정상 기록한다.
JITTER_WINDOW: int = 3


@dataclass
class RouteStats:
    """한 노선 1회 폴링 결과 집계 (F09 §4.4)."""

    route_id: str
    api_ok: bool = True
    api_error: str | None = None
    parsed_count: int = 0
    inserts: int = 0
    skipped_unchanged: int = 0
    # 변경됐으나 추적 대상(ROUTEID[rid][3]) 밖 정류장 → 기록 안 함. (H3의 '미등록 이름'과 다른 개념)
    skipped_unknown_stop: int = 0
    # H4: 차량별로 격리된 처리 예외 수(관측용). 사이클 total_errors로 집계된다.
    vehicle_errors: int = 0
    # 감사 2-1/2-6: node_ord 역전(GPS 지터)으로 기록을 skip한 건수(관측용).
    skipped_reversed: int = 0


@dataclass
class CycleStats:
    """한 사이클(전 노선) 결과 집계 (F09 §4.4)."""

    cycle_started_at: datetime
    route_results: dict[str, RouteStats] = field(default_factory=dict)
    total_inserts: int = 0
    total_errors: int = 0
    committed: bool = True  # batch가 실제로 commit됐는지(연결 끊김 시 False)


class GovtrackRecorder:
    def __init__(self, client, state, repo, clock, *, tracked_stops_by_route,
                 stop_names=None, route_names=None, route_ids=None, alert_hook=None,
                 alert_threshold=5, passage_sink=None, reconnect=None):
        """``client``: TagoClient(파싱 포함). ``state``: VehicleTimeline. ``repo``: BusLogRepo.
        ``clock``: Clock(ADR-008). ``tracked_stops_by_route``: {route_id: set(node_id)}.
        ``stop_names``: node_id→명칭(기본 STOP_IDS).
        ``route_names``: route_id→버스번호(기본 None, 주입 시 LogRow.route_nm 채움, 감사 2-3).
        ``passage_sink``: LogRow→None (TSV append seam).
        ``reconnect``: ()→BusLogRepo (연결 끊김 시 다음 사이클 재연결, H5). ``alert_hook``: (route_id, n)→None.
        """
        self.client = client
        self.state = state
        self.repo = repo
        self.clock = clock
        self.tracked = {rid: set(s) for rid, s in tracked_stops_by_route.items()}
        self.stop_names = STOP_IDS if stop_names is None else stop_names
        # 감사 2-3: route_id → 버스 번호 매핑. ROUTEID[rid][0] 에 해당.
        self.route_names: dict[str, str] = {} if route_names is None else dict(route_names)
        self.route_ids = list(route_ids) if route_ids is not None else list(self.tracked)
        self.alert_hook = alert_hook
        self.alert_threshold = alert_threshold
        self.passage_sink = passage_sink
        self.reconnect = reconnect
        self._consec_fail: dict[str, int] = {}
        self._alerted: set[str] = set()
        self._reconnect_pending = False
        # commit 실패 시 후보를 버리지 않고 다음 사이클 배치로 이월(유실 방지, PM-001 재발 차단).
        self._pending: list[LogRow] = []
        self._pending_cap = 5000  # 장기 장애 시 무한 증가 방지(상한 초과분만 드롭, TSV엔 잔존)

    # ---- alert (H6) -----------------------------------------------------
    def _note_failure(self, route_id: str) -> None:
        n = self._consec_fail.get(route_id, 0) + 1
        self._consec_fail[route_id] = n
        if n >= self.alert_threshold and route_id not in self._alerted:
            self._alerted.add(route_id)  # 임계 도달 시 1회만 알림
            logger.error("route %s %d사이클 연속 실패 — alert", route_id, n)
            if self.alert_hook is not None:
                self.alert_hook(route_id, n)

    def _note_success(self, route_id: str) -> None:
        self._consec_fail[route_id] = 0
        self._alerted.discard(route_id)  # 성공 시 카운터+플래그 리셋 → 이후 재발 시 재알림

    # ---- 단일 노선 (W2a) ------------------------------------------------
    def run_single_route(self, route_id: str, *, dry_run: bool = False) -> tuple[RouteStats, list[LogRow]]:
        """한 노선 1회 폴링. (RouteStats, INSERT 후보 LogRow 목록) 반환. 실제 INSERT는 run_cycle이 batch로 수행."""
        stats = RouteStats(route_id=route_id)
        tracked = self.tracked.get(route_id, set())
        ts = self.clock.now()
        idx = ts.strftime("%Y%m%d_%H:%M:%S")
        try:
            resp = self.client.fetch_bus_locations(route_id)
        except Exception as exc:  # TagoError(quota/키)·RequestException 등 노선 단위 실패(H4 데몬·H6)
            stats.api_ok = False
            stats.api_error = str(exc) or type(exc).__name__
            self._note_failure(route_id)
            logger.error("route %s 위치 조회 실패: %s", route_id, stats.api_error)
            return stats, []
        self._note_success(route_id)
        stats.parsed_count = len(resp.items)

        # 감사 2-3: 이 노선의 버스 번호(route_nm). ROUTEID[rid][0]에 해당.
        route_nm = self.route_names.get(route_id)

        candidates: list[LogRow] = []
        for loc in resp.items:
            try:
                # ---- 감사 2-1/2-6: node_ord 순방향 게이트 ----
                # node_ord가 양쪽 모두 있고 역전 폭이 JITTER_WINDOW 이하이면 GPS 지터로 판단해 skip.
                # 폭이 JITTER_WINDOW 초과이면 종점 회차로 보고 정상 기록(state 전진).
                # node_ord가 None이면(울산 BIS fallback 경로) 게이트 통과(기존 동작 유지).
                new_ord = loc.node_ord
                prev_ord = self.state.last_node_ord(route_id, loc.vehicle_no)
                if (
                    prev_ord is not None
                    and new_ord is not None
                    and 0 < (prev_ord - new_ord) <= JITTER_WINDOW
                ):
                    # GPS 지터/소역전 — state 전진 없이 skip(감사 2-1)
                    stats.skipped_reversed += 1
                    logger.debug(
                        "route %s vehicle %s node_ord 역전 skip: prev=%d new=%d (지터 추정)",
                        route_id, loc.vehicle_no, prev_ord, new_ord,
                    )
                    continue

                # ---- 감사 2-7: dry_run 상태 격리 ----
                # dry_run=True이면 state.record를 호출하지 않아 실제 run 사이클이 영향받지 않는다.
                if dry_run:
                    prev_node = self.state.last_node(route_id, loc.vehicle_no)
                    changed = prev_node != loc.node_id
                else:
                    changed = self.state.record(
                        route_id, loc.vehicle_no, loc.node_id, ts, node_ord=new_ord
                    )

                if not changed:
                    stats.skipped_unchanged += 1
                    continue
                if loc.node_id not in tracked:
                    # 추적 대상이 아닌 정류장: timeline은 갱신됐으나(위 record) 기록은 안 함.
                    stats.skipped_unknown_stop += 1
                    continue
                # H3: STOP_IDS에 없는 nodeid라도 .get→None으로 안전 처리하고 그대로 INSERT한다.
                stop_name = self.stop_names.get(loc.node_id)
                # 감사 2-3: route_nm을 LogRow에 채워 DB에 버스 번호를 기록한다.
                row = LogRow(idx=idx, stop_id=loc.node_id, route_id=route_id,
                             vehicle_no=loc.vehicle_no, stop_name=stop_name,
                             route_nm=route_nm)
                candidates.append(row)
                stats.inserts += 1
                if self.passage_sink is not None and not dry_run:
                    self.passage_sink(row)  # TSV append seam (logging 경유, fileio 아님)
            except Exception as exc:
                # H4: 한 차량 처리 예외가 같은 사이클의 다른 차량 처리를 막지 않도록 격리한다.
                stats.vehicle_errors += 1
                logger.error("route %s vehicle %s 처리 실패(격리): %s",
                             route_id, getattr(loc, "vehicle_no", "?"), exc)
        return stats, candidates

    # ---- 사이클 (W2b) ---------------------------------------------------
    def run_cycle(self, *, dry_run: bool = False) -> CycleStats:
        """전 노선 1회 폴링 → 후보를 사이클당 1 트랜잭션으로 batch INSERT(H5)."""
        # 직전 사이클에서 연결이 끊겼으면 사이클 시작 시점에 재연결한다.
        if self._reconnect_pending and self.reconnect is not None:
            self.repo = self.reconnect()
            self._reconnect_pending = False
            logger.info("DB 재연결 완료 — 적재 재개")

        started = self.clock.now()
        results: dict[str, RouteStats] = {}
        # 직전 사이클에서 commit하지 못한 후보를 앞에 둔다 — state는 이미 전진했으므로 후보를
        # 버리면 그 통과는 영구 유실된다(PM-001 증상). LogRow가 원래 idx를 보존하므로 재시도해도
        # 통과 시각이 정확하다.
        candidates: list[LogRow] = list(self._pending)
        for route_id in self.route_ids:
            rstats, rows = self.run_single_route(route_id, dry_run=dry_run)
            results[route_id] = rstats
            candidates.extend(rows)

        committed = True
        if candidates and not dry_run:
            try:
                self.repo.insert_batch(candidates)  # H5: 단일 트랜잭션 commit(전부 또는 전무)
                self._pending = []                   # 성공 → 이월 버퍼 비움
            except operational_errors() as exc:
                committed = False
                self._reconnect_pending = True
                # 후보를 버리지 않고 버퍼링 → 다음 사이클 배치에 재시도(상한 초과분만 드롭).
                self._pending = candidates[-self._pending_cap:]
                logger.error("배치 commit 중 DB 연결 오류 — %d건 이월 후 다음 사이클 재연결: %s",
                             len(self._pending), exc)

        total_inserts = sum(s.inserts for s in results.values())
        total_errors = (sum(s.vehicle_errors for s in results.values())
                        + sum(1 for s in results.values() if not s.api_ok)
                        + (0 if committed else 1))
        # AC-M1: 매 사이클 INFO 한 줄 요약(route별 inserts)
        brk = " ".join(f"{r}={s.inserts}" for r, s in results.items() if s.inserts)
        logger.info("cycle inserts=%d errors=%d committed=%s %s",
                    total_inserts if committed else 0, total_errors, committed, brk)
        return CycleStats(cycle_started_at=started, route_results=results,
                          total_inserts=total_inserts, total_errors=total_errors,
                          committed=committed)
