"""부산 가는 길(/busan) 뷰모델 — 세 루트를 "지금 출발하면" 기준으로 엮는다(순수 함수).

- 루트 1 (부산역): 513 울산역 방면 → 울산역 → KTX 울산→부산
- 루트 2 (노포):   743·753 → 좋은삼정병원앞 → 1224 (좋은삼정병원앞 실시간 도착으로 환승을 잇는다)
- 루트 3 (벡스코·부전): 713·743·753·1115 → 태화강역 → 동해선 광역전철 (+ KTX-이음·ITX-마음·무궁화)

입력은 모두 주입한다(도착 캐시·시간표 provider·철도 시간표 dict). 외부 API·파일·DB 를
직접 읽지 않는다(domain 규칙). 513 덕하 기점 시각은 UNIST 통과 시각으로 쓰지 않고
라벨을 붙여 따로 보인다(timetable UX 결정 D1). UNIST 통과는 실시간 도착만 쓴다.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Callable

from bushexa.data.constants import (
    BUSAN_513_ORIGIN,
    BUSAN_513_ROUTE_ID,
    BUSAN_1224_ROUTE_ID,
    BUSAN_KTX_TRANSFER_MIN,
    BUSAN_NOPO_FEEDER_BUSES,
    BUSAN_NOPO_FEEDER_ROUTE_IDS,
    BUSAN_NOPO_TRANSFER_MIN,
    BUSAN_TAEHWAGANG_BUS_MIN,
    BUSAN_TAEHWAGANG_WALK_MIN,
    BUSAN_UNIST_TO_ULSAN_STATION_MIN,
)
from bushexa.domain.rail_match import service_minutes

TimetableProvider = Callable[[str, int, str], list]

_ROWS = 5


@dataclass(frozen=True)
class Train:
    dep: str          # "HH:MM"
    arr: str          # "HH:MM"
    grade: str


@dataclass(frozen=True)
class KtxLiveRow:
    eta_min: int              # UNIST 도착까지 분(실시간)
    unist_at: str             # "HH:MM"
    station_at: str           # 울산역 도착 예상 "HH:MM"
    train: Train | None       # 탈 수 있는 첫 KTX


@dataclass(frozen=True)
class DonghaeRow:
    busno: str
    unist_dep: str            # UNIST 출발(시간표) "HH:MM"
    taehwagang_at: str        # 태화강역 도착 예상 "HH:MM"
    metro_dep: str | None     # 탈 수 있는 첫 동해선 태화강 출발 "HH:MM"
    bexco_at: str | None
    bujeon_at: str | None


@dataclass(frozen=True)
class NopoRow:
    busno: str
    unist_dep: str


@dataclass(frozen=True)
class LiveBus:
    eta_min: int              # 좋은삼정병원앞 도착까지 분(실시간)
    at: str                   # "HH:MM"


@dataclass(frozen=True)
class NopoLiveRow:
    busno: str                # 743 / 753
    feeder: LiveBus           # 좋은삼정병원앞 도착(실시간)
    bus_1224: LiveBus | None  # 내린 뒤 탈 수 있는 첫 1224 (지금 운행 중인 차 중에서)


@dataclass(frozen=True)
class BusanSnapshot:
    now: str
    weekday: int
    # 루트 1
    ktx_live: list[KtxLiveRow] = field(default_factory=list)
    origin_513: list[str] = field(default_factory=list)   # 덕하 출발 시각(라벨 필수)
    ktx_trains: list[Train] = field(default_factory=list)
    ktx_state: str = "missing"                             # ok / suspect / missing
    arrival_fetched_at: str | None = None
    # 루트 2
    nopo_buses: list[NopoRow] = field(default_factory=list)
    nopo_1224: list[LiveBus] = field(default_factory=list)      # 좋은삼정병원앞 1224 노포 방면
    nopo_live: list[NopoLiveRow] = field(default_factory=list)  # 743·753 → 1224 실시간 연결
    transfer_fetched_at: str | None = None
    # 루트 3
    donghae: list[DonghaeRow] = field(default_factory=list)
    metro_state: str = "missing"                           # ok / saturday_fallback / missing
    intercity_trains: list[Train] = field(default_factory=list)
    intercity_state: str = "missing"
    errors: list[str] = field(default_factory=list)


def _hhmm(minutes: float) -> str:
    m = int(round(minutes)) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def _now_minutes(now: datetime.datetime) -> float:
    return service_minutes(now.strftime("%H:%M:%S"))


def _train_rows(day_entry: dict | None, now: datetime.datetime,
                not_before: datetime.datetime | None = None) -> tuple[list[Train], str]:
    """저장된 날짜 항목 → 지금(또는 not_before) 이후 열차. 상태: ok/suspect/missing."""
    if not day_entry or not day_entry.get("trains"):
        return [], "missing"
    limit = not_before or now
    out = []
    seen: set[tuple] = set()
    for t in day_entry["trains"]:
        try:
            dep = datetime.datetime.fromisoformat(t["dep"])
            arr = datetime.datetime.fromisoformat(t["arr"])
        except (KeyError, ValueError):
            continue
        # 열차번호는 쓰지 않는다 — 중련(예: 00069+09069 같은 시각)은 한 줄로 보인다.
        if dep >= limit and (dep, arr) not in seen:
            seen.add((dep, arr))
            out.append((dep, Train(dep.strftime("%H:%M"), arr.strftime("%H:%M"), t.get("grade", ""))))
    out.sort(key=lambda x: x[0])
    return [t for _, t in out], ("suspect" if day_entry.get("suspect") else "ok")


def _first_train_after(day_entry: dict | None, at: datetime.datetime) -> Train | None:
    trains, _ = _train_rows(day_entry, at)
    return trains[0] if trains else None


def _safe_times(provider: TimetableProvider, busno: str, weekday: int, origin: str,
                errors: list[str]) -> list[str]:
    try:
        return list(provider(busno, weekday, origin))
    except (FileNotFoundError, KeyError) as exc:
        errors.append(f"{busno} {origin} 시간표 없음: {exc}")
        return []


def _upcoming(times: list[str], now_min: float) -> list[str]:
    return [t for t in times if service_minutes(f"{t}:00") >= now_min]


def build_busan_snapshot(
    now: datetime.datetime,
    weekday: int,
    *,
    timetable_provider: TimetableProvider,
    unist_arrivals: list | None = None,
    arrival_fetched_at: str | None = None,
    transfer_arrivals: list | None = None,
    transfer_fetched_at: str | None = None,
    ktx_day: dict | None = None,
    intercity_day: dict | None = None,
    metro_to_bexco: dict | None = None,
    metro_to_bujeon: dict | None = None,
    rows: int = _ROWS,
) -> BusanSnapshot:
    """세 루트의 "지금부터" 행을 만든다.

    ``ktx_day``/``intercity_day`` 는 ``rail_timetable.trains_on`` 결과, ``metro_to_*`` 는
    ``rail_timetable.metro_trips`` 결과(``{"day_type", "trips": [{"dep", "arr"}]}``)다.
    ``transfer_arrivals`` 는 좋은삼정병원앞(노포 방면) 도착 캐시다.
    """
    errors: list[str] = []
    now_min = _now_minutes(now)

    # ── 루트 1: 513 실시간 → 울산역 → KTX ────────────────────────────────
    live: list[KtxLiveRow] = []
    for a in sorted((a for a in (unist_arrivals or []) if a.route_id == BUSAN_513_ROUTE_ID),
                    key=lambda a: a.arrival_time):
        unist_at = now + datetime.timedelta(seconds=a.arrival_time)
        station_at = unist_at + datetime.timedelta(minutes=BUSAN_UNIST_TO_ULSAN_STATION_MIN)
        ready = station_at + datetime.timedelta(minutes=BUSAN_KTX_TRANSFER_MIN)
        live.append(KtxLiveRow(
            eta_min=max(0, round(a.arrival_time / 60)),
            unist_at=unist_at.strftime("%H:%M"),
            station_at=station_at.strftime("%H:%M"),
            train=_first_train_after(ktx_day, ready),
        ))
    origin_513 = _upcoming(_safe_times(timetable_provider, "513", weekday, BUSAN_513_ORIGIN, errors),
                           now_min)[:rows]
    ktx_trains, ktx_state = _train_rows(ktx_day, now)

    # ── 루트 2: 743·753 UNIST 출발 ─────────────────────────────────────────
    nopo: list[NopoRow] = []
    for busno in BUSAN_NOPO_FEEDER_BUSES:
        for t in _upcoming(_safe_times(timetable_provider, busno, weekday, "UNIST", errors), now_min):
            nopo.append(NopoRow(busno, t))
    nopo.sort(key=lambda r: r.unist_dep)

    # 좋은삼정병원앞 실시간: 743·753 명촌 방면과 1224 노포 방면이 같은 정류장에 선다.
    def as_live_bus(a) -> LiveBus:
        return LiveBus(max(0, round(a.arrival_time / 60)),
                       (now + datetime.timedelta(seconds=a.arrival_time)).strftime("%H:%M"))

    transfer = sorted((a for a in (transfer_arrivals or []) if a.arrival_time >= 0),
                      key=lambda a: a.arrival_time)
    buses_1224 = [a for a in transfer if a.route_id == BUSAN_1224_ROUTE_ID]
    nopo_live: list[NopoLiveRow] = []
    for a in transfer:
        busno = BUSAN_NOPO_FEEDER_ROUTE_IDS.get(a.route_id)
        if busno is None:
            continue
        ready = a.arrival_time + BUSAN_NOPO_TRANSFER_MIN * 60
        catch = next((b for b in buses_1224 if b.arrival_time >= ready), None)
        nopo_live.append(NopoLiveRow(busno, as_live_bus(a), as_live_bus(catch) if catch else None))

    # ── 루트 3: 버스 → 태화강역 → 동해선 ────────────────────────────────
    bexco = {t["dep"]: t.get("arr") for t in (metro_to_bexco or {}).get("trips", [])}
    bujeon = {t["dep"]: t.get("arr") for t in (metro_to_bujeon or {}).get("trips", [])}
    metro_deps = sorted(set(bexco) | set(bujeon), key=service_minutes)
    if not metro_deps:
        metro_state = "missing"
    elif (metro_to_bexco or metro_to_bujeon or {}).get("day_type") == "03" and weekday == 1:
        metro_state = "saturday_fallback"
    else:
        metro_state = "ok"

    donghae: list[DonghaeRow] = []
    for busno, minutes in BUSAN_TAEHWAGANG_BUS_MIN.items():
        run = minutes.get(weekday, minutes[0])
        walk = BUSAN_TAEHWAGANG_WALK_MIN.get(busno, 5)
        for t in _upcoming(_safe_times(timetable_provider, busno, weekday, "UNIST", errors), now_min):
            at = service_minutes(f"{t}:00") + run
            catch = next((d for d in metro_deps if service_minutes(d) >= at + walk), None)
            donghae.append(DonghaeRow(
                busno=busno, unist_dep=t, taehwagang_at=_hhmm(at),
                metro_dep=catch[:5] if catch else None,
                bexco_at=bexco.get(catch, None)[:5] if catch and bexco.get(catch) else None,
                bujeon_at=bujeon.get(catch, None)[:5] if catch and bujeon.get(catch) else None,
            ))
    donghae.sort(key=lambda r: (r.unist_dep, r.busno))
    intercity, intercity_state = _train_rows(intercity_day, now)

    return BusanSnapshot(
        now=now.strftime("%H:%M"),
        weekday=weekday,
        ktx_live=live[:rows],
        origin_513=origin_513,
        ktx_trains=ktx_trains[:rows + 1],
        ktx_state=ktx_state,
        arrival_fetched_at=arrival_fetched_at,
        nopo_buses=nopo[:rows],
        nopo_1224=[as_live_bus(a) for a in buses_1224][:rows],
        nopo_live=nopo_live[:rows],
        transfer_fetched_at=transfer_fetched_at,
        donghae=donghae[:rows + 1],
        metro_state=metro_state,
        intercity_trains=intercity[:4],
        intercity_state=intercity_state,
        errors=errors,
    )
