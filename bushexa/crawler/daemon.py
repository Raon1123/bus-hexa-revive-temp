"""govtrack 데몬 루프 + recorder 빌더 + TSV sink (W3).

graceful 종료(H, 데이터 손실 방지): SIGTERM/SIGINT은 CLI(메인 스레드)에서만 등록하고, 본 루프는
주입된 ``stop_event``를 폴링해 '진행 중 사이클을 끝낸 뒤' 종료한다 — 스레드에서 ``signal.signal``
호출이 불가한 문제를 피한다. ``sleep``도 주입 가능해 테스트가 결정적으로 제어한다.

TSV append(H8): logging ``FileHandler`` 경유라 bushexa 코드에 ``open()``이 없고(EC-10/H9 충족),
경로는 ``BUSHEXA_TSV_PATH``/인자로 설정 가능하다(컨테이너 경로 하드코딩 제거 — H9).
"""
from __future__ import annotations

import logging
import os
import threading
import time as _time
from datetime import time, timedelta
from pathlib import Path
from typing import Callable

from bushexa.crawler.recorder import GovtrackRecorder
from bushexa.crawler.state import JSONFileStore, VehicleTimeline
from bushexa.data.constants import STOP_IDS, TRACKED_ROUTES
from bushexa.db.connection import create_connection
from bushexa.db.repo import BusLogRepo
from bushexa.db.schema import create_schema
from bushexa.services.crawl_settings import CrawlSettingsStore, default_crawl_settings_path
from bushexa.time_utils import KSTClock

logger = logging.getLogger("bushexa.crawler.daemon")

_NIGHT = (time(1, 0), time(5, 0))


def resolve_tsv_path(environ=None, data_dir=None) -> Path:
    """TSV 경로 결정: ``BUSHEXA_TSV_PATH`` > ``data_dir/logs.tsv`` > ``./logs/logs.tsv`` (H8/H9)."""
    environ = os.environ if environ is None else environ
    env = environ.get("BUSHEXA_TSV_PATH")
    if env:
        return Path(env)
    base = Path(data_dir) if data_dir else Path("logs")
    return base / "logs.tsv"


def make_tsv_sink(path) -> Callable:
    """LogRow를 TSV 한 줄로 append하는 sink. ``logging.FileHandler`` 경유(직접 ``open()`` 미사용)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    tlog = logging.getLogger(f"bushexa.crawler.tsv:{path}")
    tlog.setLevel(logging.INFO)
    tlog.propagate = False
    already = any(getattr(h, "_tsv_path", None) == str(path) for h in tlog.handlers)
    if not already:
        fh = logging.FileHandler(path, encoding="utf-8")
        fh._tsv_path = str(path)
        fh.setFormatter(logging.Formatter("%(message)s"))
        tlog.addHandler(fh)
        if new_file:
            tlog.info("time\tstop_id\troute_id\tvehicle_number\tstop_name")

    def sink(row) -> None:
        tlog.info("%s\t%s\t%s\t%s\t%s", row.idx, row.stop_id, row.route_id,
                  row.vehicle_no, row.stop_name or "")
    return sink


def tracked_stops_by_route() -> dict[str, set[str]]:
    """TRACKED_ROUTES[rid][3](추적 정류장 목록)을 ``{route_id: set(node_id)}``로 변환.

    UNIST 경유 노선(ROUTEID)에 수집 전용 노선(EXTRA_TRACKED_ROUTES, 예: 1224)을 더한 것이다.
    """
    return {rid: set(meta[3]) for rid, meta in TRACKED_ROUTES.items()}


def build_recorder(config, *, repo=None, client=None, state=None, clock=None,
                   passage_sink=None, warm_hours=3) -> GovtrackRecorder:
    """config로부터 실제 GovtrackRecorder를 조립한다(테스트는 각 의존을 주입)."""
    clock = clock or KSTClock()
    dsn = config.database_url
    if repo is None:
        conn = create_connection(dsn)
        create_schema(conn)
        repo = BusLogRepo(conn)
    if client is None:
        # TAGO 위치조회 우선 + 울산 BIS 도착정보 fallback(혼용). TAGO 키 미등록/쿼터/장애 시
        # govtrack이 멈추지 않고 울산 BIS로 위치를 보완한다.
        from bushexa.api_clients.composite_location import CompositeLocationClient
        from bushexa.api_clients.tago import TagoClient
        from bushexa.api_clients.ulsan_bis import UlsanBisClient
        client = CompositeLocationClient(
            TagoClient(config.api_key), UlsanBisClient(config.api_key),
        )
    if state is None:
        state = VehicleTimeline(JSONFileStore(Path(config.data_dir) / "govtrack_state.json"))
    if passage_sink is None:
        passage_sink = make_tsv_sink(resolve_tsv_path(os.environ, config.data_dir))

    def _reconnect():
        conn = create_connection(dsn)
        create_schema(conn)
        return BusLogRepo(conn)

    # 감사 2-3: route_id → 버스 번호 매핑을 TRACKED_ROUTES에서 추출해 recorder에 주입한다.
    # TRACKED_ROUTES[rid][0] = 버스 번호(예: "713"). 의존성 주입으로 테스트 격리 유지.
    _route_names = {rid: meta[0] for rid, meta in TRACKED_ROUTES.items()}

    recorder = GovtrackRecorder(
        client, state, repo, clock,
        tracked_stops_by_route=tracked_stops_by_route(),
        stop_names=STOP_IDS, route_names=_route_names,
        passage_sink=passage_sink, reconnect=_reconnect,
    )
    # H2: 재시작 시 직전 위치 워밍(false-positive 억제). 워밍 실패가 기동을 막지 않게(ADR-013).
    try:
        warmed = state.warm_from_repo(repo, since=clock.now() - timedelta(hours=warm_hours))
        logger.info("warm_from_repo: %d 차량 적재", warmed)
    except Exception as exc:
        logger.warning("warm_from_repo 실패(무시하고 계속): %s", exc)
    return recorder


def _in_night_window(now_t, window) -> bool:
    start, end = window
    return start <= now_t < end


def run_daemon(config, *, recorder=None, poll_seconds=15, night_sleep_seconds=60,
               night_window=_NIGHT, clock=None, sleep=None, stop_event=None,
               max_cycles=None, on_cycle=None, settings_store=None) -> int:
    """govtrack 데몬 루프. 반환: 수행한 사이클 수. ``stop_event.set()`` 시 현재 사이클 완료 후 종료.

    설정 파일(``crawl_settings.json``)을 매 사이클 재읽으므로 govtrack 폴링 주기 변경은
    다음 사이클부터(최대 현재 주기만큼 지연) 적용된다(ADR-013).
    """
    clock = clock or KSTClock()
    sleep = sleep or _time.sleep
    stop_event = stop_event or threading.Event()
    if settings_store is None:
        data_dir = getattr(config, "data_dir", None)
        if data_dir is not None:
            settings_store = CrawlSettingsStore(default_crawl_settings_path(data_dir))
    if recorder is None:
        recorder = build_recorder(config, clock=clock)

    cycles = 0
    while not stop_event.is_set():
        now = clock.now()
        if _in_night_window(now.time(), night_window):
            # 감사 2-8: 야간 창 진입 직전에 state를 영속화한다(sleep 전 호출).
            # recorder가 None일 수 없는 경로이지만 방어적 체크. 예외는 warning 후 계속(ADR-013).
            if recorder is not None:
                try:
                    recorder.state.persist()
                except Exception as exc:
                    logger.warning("야간 창 진입 시 state.persist 실패(무시): %s", exc)
            sleep(night_sleep_seconds)   # H7: 600→60 단축(설정 가능)
            continue
        try:
            cyc = recorder.run_cycle()
            if on_cycle is not None:
                on_cycle(cyc)
            try:
                recorder.state.persist()   # 재시작 워밍을 위해 상태 영속
            except Exception as exc:
                logger.warning("state.persist 실패(무시): %s", exc)
        except Exception as exc:
            # ADR-013: 사이클 전체 예외도 데몬을 죽이지 않는다 — 로그 후 계속.
            logger.error("사이클 처리 중 예외(계속 진행): %s", exc, exc_info=True)
        cycles += 1
        if max_cycles is not None and cycles >= max_cycles:
            break
        sleep(settings_store.govtrack_poll_seconds(poll_seconds) if settings_store else poll_seconds)
    logger.info("govtrack 데몬 종료(사이클 %d회 수행)", cycles)
    return cycles


def crawl_once(recorder, route_id, *, dry_run=False):
    """단일 노선 1회 폴링. ``dry_run``이면 실제 INSERT 0건(EC-3). RouteStats 반환."""
    stats, candidates = recorder.run_single_route(route_id, dry_run=dry_run)
    if candidates and not dry_run:
        recorder.repo.insert_batch(candidates)
    return stats
