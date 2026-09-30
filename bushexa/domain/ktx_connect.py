"""요일별 KTX 연계표(/ktx) — 열차마다 이어 타는 버스를 짝짓는다(순수 함수).

열차마다 두 안을 계산한다.

① 513 직행
- 가는 편(out): 울산역 출발 KTX(부산·서울·수서행)마다 "최소한 타야 하는 버스", 즉 울산역에
  열차 출발 ``transfers.station`` 분 전까지 닿는(예상) 가장 늦은 513.
  A = 덕하 출발(시간표) → B = UNIST(경유) 통과(예상) → C = 울산역(언양 방면) 도착(예상).
- 오는 편(in): 울산역 도착 KTX 마다 도착 ``transfers.station`` 분 뒤 이후 울산역(시내 방면)에
  오는(예상) 첫 513. A = 삼남 출발(시간표) → C = 울산역 → B = UNIST.

② 5001 + 진목회관 환승 (5001 은 UNIST 에 서지 않고 양방향 모두 진목회관에 선다)
- 가는 편: UNIST 에서 713·743·753·513 으로 진목회관(시내 방면) → 길 건너 ``transfers.jinmok`` 분
  → 5001(꽃바위발) 진목회관(UNIST 방면) → 울산역 → KTX.
- 오는 편: KTX → ``transfers.station`` 분 → 5001(울산역발) → 진목회관(시내 방면) → 길 건너
  ``transfers.jinmok`` 분 → 513·713·743·753 → UNIST.

두 안이 모두 없는 열차(첫차 전·막차 뒤)는 표에서 뺀다. 소요는 구간 소요 프로필(``services/leg_profile``,
요일구분·시간대별 중앙값)로 계산하고, 5001 처럼 기록이 모자란 구간은 ``KTX_LEG_PROXIES`` 의 근사
구간을 이어 붙인다. 중앙값으로 짝짓되, 늦는 날(p90)·이른 날(p10)에 환승 최소 시간을 못 지키는 짝은
``tight`` 로 표시한다. 입력은 모두 주입한다 — 파일·API·DB 를 읽지 않는다.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Iterable

from bushexa.data.constants import (
    KTX_5001,
    KTX_5001_FROM_STATION,
    KTX_5001_TO_STATION,
    KTX_CONNECT_TRANSFER_MIN,
    KTX_JINMOK_IN_FEEDERS,
    KTX_JINMOK_OUT_FEEDERS,
    KTX_JINMOK_TRANSFER_MIN,
    KTX_LEG_PROXIES,
    KTX_LEG_REAL_MIN_N,
    RAIL_STATIONS,
    RAIL_STOP_CANDIDATES,
    RAIL_STRIP_LAYOUT,
)
from bushexa.domain.rail_match import service_minutes
from bushexa.time_utils import get_weekday

DAYS = (0, 1, 2)
DIRECTIONS = ("out", "in")
PASS = "レ"            # 통과(일본 시각표 관례)
OTHER_ROUTE = "‖"      # 다른 갈래로 달려 이 역을 지나지 않음(고속선 ↔ 수원 경유)

Timetables = dict  # {(버스번호, 시간표 키): ["HH:MM", ...]}


@dataclass(frozen=True)
class Transfers:
    """환승마다 지켜야 할 최소 시간(분). 기본 5분."""
    station: int = KTX_CONNECT_TRANSFER_MIN   # 울산역 버스 정류장 ↔ KTX
    jinmok: int = KTX_JINMOK_TRANSFER_MIN     # 진목회관 길 건너 버스 ↔ 버스


@dataclass(frozen=True)
class LegEstimate:
    p10: float
    p50: float
    p90: float


@dataclass(frozen=True)
class Alt5001Out:
    """가는 편 ② 안: UNIST → (환승 버스) → 진목회관 → 5001 → 울산역."""
    feeder_no: str          # UNIST 에서 타는 버스 번호
    unist_dep: str          # UNIST 출발(713·743·753 은 시간표, 513 은 예상)
    jinmok_arr: str         # 진목회관(시내 방면) 도착(예상)
    bus_dep: str            # 5001 진목회관(UNIST 방면) 통과(예상)
    station_at: str         # 5001 울산역 도착(예상)
    margin_min: int         # 열차 출발 − 울산역 도착
    tight: bool
    unist_min: float        # 비교용(UNIST 출발, 운행일 분)


@dataclass(frozen=True)
class Alt5001In:
    """오는 편 ② 안: 울산역 → 5001 → 진목회관 → (환승 버스) → UNIST."""
    bus_dep: str            # 5001 울산역 출발(시간표)
    wait_min: int           # 5001 출발 − 열차 도착
    jinmok_arr: str         # 진목회관(시내 방면) 도착(예상)
    feeder_no: str          # 진목회관(UNIST 방면)에서 타는 버스 번호
    feeder_dep: str         # 환승 버스 진목회관 통과(예상)
    unist_at: str           # UNIST 도착(예상)
    tight: bool
    unist_min: float


@dataclass(frozen=True)
class OutboundRow:
    train_no: tuple[str, ...]   # 열차번호(중련이면 둘)
    train_dep: str          # 울산역 출발 "HH:MM"
    train_arr: str          # 부산·서울·수서 도착 "HH:MM"
    arr_next_day: bool
    grade: str
    origin_dep: str | None  # ① A: 513 덕하 출발(시간표). ① 안이 없으면 None
    unist_at: str | None    # ① B: UNIST(경유) 통과(예상)
    station_at: str | None  # ① C: 울산역 도착(예상)
    margin_min: int | None  # ① 열차 출발 − C
    tight: bool             # ① 늦는 날(p90)엔 여유가 최소 환승 시간 미만
    via: tuple[str, ...] = ()   # 중간역 칸(ConnectTable.stations 순서): "HH:MM" 도착 / レ / ‖ / ""(모름)
    alt: Alt5001Out | None = None
    best: str | None = None     # "513" / "5001" — UNIST 를 더 늦게 떠나도 되는 안


@dataclass(frozen=True)
class InboundRow:
    train_no: tuple[str, ...]
    train_dep: str          # 부산·서울·수서 출발 "HH:MM"
    train_arr: str          # 울산역 도착 "HH:MM"
    arr_next_day: bool
    grade: str
    origin_dep: str | None  # ① A: 513 삼남 출발(시간표)
    station_at: str | None  # ① C: 울산역(시내 방면) 도착(예상)
    unist_at: str | None    # ① B: UNIST(경유) 도착(예상)
    wait_min: int | None    # ① C − 열차 도착
    tight: bool             # ① 일찍 오는 날(p10)엔 여유가 최소 환승 시간 미만
    via: tuple[str, ...] = ()
    alt: Alt5001In | None = None
    best: str | None = None     # "513" / "5001" — UNIST 에 먼저 닿는 안


@dataclass(frozen=True)
class ConnectTable:
    direction: str                          # out / in
    dest: str                               # busan / seoul / suseo
    day: int                                # 0 평일 / 1 토 / 2 일·공휴일
    ref_date: datetime.date | None          # 열차 시간표를 가져온 날짜
    rows: list = field(default_factory=list)
    skipped: int = 0                        # 이어 탈 버스가 없어 뺀 열차 수
    rail_state: str = "missing"             # ok / suspect / missing
    bus_state: str = "missing"              # ok / missing (513)
    profile_state: str = "missing"          # ok / missing
    transfer_min: int = KTX_CONNECT_TRANSFER_MIN   # = transfers.station (호환)
    stations: tuple[str, ...] = ()          # 중간역(운행 순서) — 없으면 직행 구간(울산↔부산)
    stops_unknown: int = 0                  # 정차역을 모르는 열차 수(조회 안 된 날짜·조회 실패)
    transfers: Transfers = field(default_factory=Transfers)
    alt_state: str = "missing"              # ok / missing (5001 시간표)
    alt_proxied: bool = False               # 5001 소요에 근사 구간을 썼는가


# ── 입력 정리 ────────────────────────────────────────────────────────────────

def _hhmm(minutes: float) -> str:
    m = int(round(minutes)) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def _day_entry(profile: dict | None, leg: str, day: int) -> dict | None:
    try:
        by_day = profile["legs"][leg]["by_day"]
    except (KeyError, TypeError):
        return None
    return by_day.get(str(day)) or by_day.get("0")


def leg_estimate(profile: dict | None, leg: str, day: int, minute: float) -> LegEstimate | None:
    """``minute``(운행일 분)에 출발 정류장을 지나는 차의 구간 소요. 시간대 → 요일구분 전체 → 평일 순."""
    entry = _day_entry(profile, leg, day)
    if not entry:
        return None
    s = (entry.get("hours") or {}).get(str(int(minute // 60) % 24)) or entry.get("all")
    if not s:
        return None
    return LegEstimate(float(s["p10"]), float(s["p50"]), float(s["p90"]))


def leg_or_proxy(profile: dict | None, leg: str, day: int,
                 minute: float) -> tuple[LegEstimate | None, bool]:
    """실측 표본이 ``KTX_LEG_REAL_MIN_N`` 이상이면 그 구간, 아니면 근사 구간을 이어 붙인 값.

    반환: (소요, 근사 여부). 근사 구간은 앞 구간 중앙값만큼 시각을 옮겨 가며 더한다.
    """
    entry = _day_entry(profile, leg, day)
    if entry and (entry.get("all") or {}).get("n", 0) >= KTX_LEG_REAL_MIN_N:
        return leg_estimate(profile, leg, day, minute), False
    parts = KTX_LEG_PROXIES.get(leg)
    if not parts:
        return leg_estimate(profile, leg, day, minute), False
    p10 = p50 = p90 = 0.0
    at = minute
    for part in parts:
        est = leg_estimate(profile, part, day, at)
        if est is None:
            return None, True
        p10, p50, p90 = p10 + est.p10, p50 + est.p50, p90 + est.p90
        at += est.p50
    return LegEstimate(p10, p50, p90), True


def _minutes(times: Iterable[str]) -> list[float]:
    return sorted(service_minutes(f"{t}:00") for t in times)


def _train_no(value) -> str:
    """TAGO 열차번호("00069") → 표기("69"). 숫자가 아니면 그대로."""
    text = str(value or "").strip()
    return str(int(text)) if text.isdigit() else text


def _trains(day_entry: dict | None, ref_date: datetime.date | None,
            ) -> list[tuple[float, float, dict, tuple[str, ...]]]:
    """날짜 항목 → (출발 분, 도착 분, 원본, 열차번호들) — 기준일 자정부터의 분.

    중련(같은 출발·도착 시각에 번호 둘)은 한 편으로 합치고 번호를 모두 싣는다.
    """
    if not day_entry or not ref_date:
        return []
    merged: dict[tuple, list] = {}
    for t in day_entry.get("trains") or []:
        try:
            dep = datetime.datetime.fromisoformat(t["dep"])
            arr = datetime.datetime.fromisoformat(t["arr"])
        except (KeyError, ValueError, TypeError):
            continue
        slot = merged.setdefault((dep, arr), [t, []])
        no = _train_no(t.get("no"))
        if no and no not in slot[1]:
            slot[1].append(no)

    def rel(x: datetime.datetime) -> float:
        return (x.date() - ref_date).days * 1440 + x.hour * 60 + x.minute
    out = [(rel(dep), rel(arr), t, tuple(nos)) for (dep, arr), (t, nos) in merged.items()]
    out.sort(key=lambda x: x[0])
    return out


def station_layout(pair: tuple[str, str] | None) -> tuple[tuple[str, ...], tuple[frozenset, ...]]:
    """구간의 중간역 행(운행 순서)과 갈래별 역 집합.

    갈래가 있는 구간(서울행: 대전 뒤 고속선 / 수원 경유)은 줄기 → 갈래 순으로 늘어놓는다.
    반대 방향은 같은 배치를 뒤집어 쓴다.
    """
    if not pair or pair not in RAIL_STOP_CANDIDATES:
        return (), ()
    dep_id, arr_id = pair
    layout, reverse = RAIL_STRIP_LAYOUT.get(pair), False
    if layout is None and (arr_id, dep_id) in RAIL_STRIP_LAYOUT:
        layout, reverse = RAIL_STRIP_LAYOUT[(arr_id, dep_id)], True
    if layout is None:
        return tuple(RAIL_STATIONS.get(c, c) for c in RAIL_STOP_CANDIDATES[pair]), ()
    order = layout["trunk"] + [c for b in layout["branches"] for c in b]
    names = tuple(RAIL_STATIONS.get(c, c) for c in (order[::-1] if reverse else order))
    branches = tuple(frozenset(RAIL_STATIONS.get(c, c) for c in b) for b in layout["branches"])
    return names, branches


def via_cells(stops, names: tuple[str, ...], branches: tuple[frozenset, ...]) -> tuple[str, ...]:
    """열차의 ``stops``(``[{"name", "arr"}]`` 또는 None=모름) → 중간역 칸.

    선다 → 도착 "HH:MM", 같은 갈래를 지나며 서지 않는다 → ``PASS``, 다른 갈래 역 → ``OTHER_ROUTE``.
    갈래는 열차가 서는 역이 있는 갈래, 없으면 첫 갈래(고속선)로 본다. 모르면 빈 칸.
    """
    if stops is None:
        return ("",) * len(names)
    at = {s.get("name"): s.get("arr") for s in stops if isinstance(s, dict)}
    route = next((b for b in branches if any(n in at for n in b)), branches[0] if branches else None)
    out = []
    for n in names:
        if at.get(n):
            out.append(at[n])
        elif route is not None and any(n in b for b in branches) and n not in route:
            out.append(OTHER_ROUTE)
        else:
            out.append(PASS)
    return tuple(out)


def _profile_state(profile: dict | None) -> str:
    return "ok" if profile and profile.get("legs") else "missing"


def _rail_state(day_entry: dict | None) -> str:
    if not day_entry or not day_entry.get("trains"):
        return "missing"
    return "suspect" if day_entry.get("suspect") else "ok"


def reference_date(today: datetime.date, day: int, holiday_set: set[str],
                   available: Iterable[datetime.date]) -> datetime.date | None:
    """``available``(열차 시간표가 있는 날짜) 중 오늘 이후 요일구분이 ``day`` 인 첫 날."""
    for d in sorted(x for x in available if x >= today):
        if get_weekday(d, holiday_set) == day:
            return d
    return None



# ── ① 513 직행 ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class _BusOut:
    a: float
    b: float
    c: float
    c_late: float        # 늦는 날(p90) 울산역 도착


def _outbound_buses(bus_times: list[str], profile: dict | None, day: int) -> list[_BusOut]:
    out = []
    for a in _minutes(bus_times):
        to_unist = leg_estimate(profile, "deokha_unist", day, a)
        if to_unist is None:
            continue
        b = a + to_unist.p50
        to_station = leg_estimate(profile, "unist_station", day, b)
        if to_station is None:
            continue
        c = b + to_station.p50
        direct = leg_estimate(profile, "deokha_station", day, a)
        late = a + direct.p90 if direct else b + (to_unist.p90 - to_unist.p50) + to_station.p90
        out.append(_BusOut(a, b, c, max(c, late)))
    return out


@dataclass(frozen=True)
class _BusIn:
    a: float
    c: float
    c_early: float       # 일찍 오는 날(p10) 울산역 도착
    b: float


def _inbound_buses(bus_times: list[str], profile: dict | None, day: int) -> list[_BusIn]:
    out = []
    for a in _minutes(bus_times):
        to_station = leg_estimate(profile, "samnam_station", day, a)
        if to_station is None:
            continue
        c = a + to_station.p50
        to_unist = leg_estimate(profile, "station_unist", day, c)
        if to_unist is None:
            continue
        out.append(_BusIn(a, c, a + to_station.p10, c + to_unist.p50))
    return out


# ── ② 5001 + 진목회관 환승 ──────────────────────────────────────────────────

@dataclass(frozen=True)
class _Trip:
    """한 버스 편의 한 정류장 통과(예상). ``at`` 중앙값, ``early``/``late`` p10/p90."""
    busno: str
    board: float         # 타는 곳 시각(가는 편: UNIST 출발, 오는 편: 진목회관 통과)
    at: float            # 내리는 곳 시각(가는 편: 진목회관 도착, 오는 편: UNIST 도착)
    early: float
    late: float


def _out_feeders(tts: Timetables, profile: dict | None, day: int) -> list[_Trip]:
    """UNIST → 진목회관(시내 방면) 버스 편."""
    out = []
    for busno, key, pre, leg in KTX_JINMOK_OUT_FEEDERS:
        for a in _minutes(tts.get((busno, key)) or []):
            board, pre_late = a, 0.0
            if pre:
                est = leg_estimate(profile, pre, day, a)
                if est is None:
                    continue
                board, pre_late = a + est.p50, est.p90 - est.p50
            ride = leg_estimate(profile, leg, day, board)
            if ride is None:
                continue
            out.append(_Trip(busno, board, board + ride.p50, board + ride.p10,
                             board + pre_late + ride.p90))
    return out


def _in_feeders(tts: Timetables, profile: dict | None, day: int) -> list[_Trip]:
    """진목회관(UNIST 방면) → UNIST 버스 편. ``board`` 는 진목회관 통과(예상)."""
    out = []
    for busno, key, to_jinmok, to_unist in KTX_JINMOK_IN_FEEDERS:
        for a in _minutes(tts.get((busno, key)) or []):
            est = leg_estimate(profile, to_jinmok, day, a)
            if est is None:
                continue
            f = a + est.p50
            ride = leg_estimate(profile, to_unist, day, f)
            if ride is None:
                continue
            out.append(_Trip(busno, f, f + ride.p50, a + est.p10, a + est.p90))
    return out


@dataclass(frozen=True)
class _Run5001Out:
    j: float             # 진목회관(UNIST 방면) 통과
    j_early: float
    s: float             # 울산역 도착
    s_late: float
    proxied: bool        # 근사 구간으로 계산 — 퍼짐(p10·p90)을 믿을 수 없어 빠듯 판정을 하지 않는다


def _runs_5001_out(tts: Timetables, profile: dict | None, day: int) -> tuple[list[_Run5001Out], bool]:
    runs, proxied = [], False
    for a in _minutes(tts.get((KTX_5001, KTX_5001_TO_STATION)) or []):
        to_j, px1 = leg_or_proxy(profile, "l5001_origin_jinmok", day, a)
        if to_j is None:
            continue
        j = a + to_j.p50
        to_s, px2 = leg_or_proxy(profile, "l5001_jinmok_station", day, j)
        if to_s is None:
            continue
        proxied |= px1 or px2
        runs.append(_Run5001Out(j, a + to_j.p10, j + to_s.p50, a + to_j.p90 + to_s.p90, px1 or px2))
    return runs, proxied


def _alt_out(dep: float, runs: list[_Run5001Out], feeders: list[_Trip],
             tr: Transfers) -> Alt5001Out | None:
    """열차 출발 ``dep`` 에 닿는 가장 늦은 5001 과, 그 5001 에 건너가 탈 수 있는 가장 늦은 UNIST 출발."""
    for run in sorted((r for r in runs if r.s + tr.station <= dep), key=lambda r: -r.j):
        ok = [f for f in feeders if f.at + tr.jinmok <= run.j]
        if not ok:
            continue
        f = max(ok, key=lambda f: (f.board, -f.at))
        return Alt5001Out(
            feeder_no=f.busno, unist_dep=_hhmm(f.board), jinmok_arr=_hhmm(f.at),
            bus_dep=_hhmm(run.j), station_at=_hhmm(run.s), margin_min=int(dep - round(run.s)),
            # 5001 이 늦으면 열차를, 일찍 오면 5001 을 놓친다(환승 버스는 중앙값으로 본다).
            # 근사 구간이면 퍼짐을 믿을 수 없어 판정하지 않는다(화면이 근사 안내를 따로 띄움).
            tight=not run.proxied and (run.s_late + tr.station > dep
                                       or run.j_early < f.at + tr.jinmok),
            unist_min=f.board,
        )
    return None


def _alt_in(arr: float, deps_5001: list[float], feeders: list[_Trip], profile: dict | None,
            day: int, tr: Transfers) -> tuple[Alt5001In | None, bool]:
    """열차 도착 ``arr`` 뒤 첫 5001 → 진목회관 → 건너편에서 UNIST 에 가장 먼저 닿는 버스."""
    for d in (x for x in deps_5001 if x >= arr + tr.station):
        to_j, proxied = leg_or_proxy(profile, "l5001_station_jinmok", day, d)
        if to_j is None:
            return None, False
        j, j_late = d + to_j.p50, d + to_j.p90
        ok = [f for f in feeders if f.board >= j + tr.jinmok]
        if not ok:
            return None, proxied          # 더 늦은 5001 로도 환승 버스가 없다(막차 뒤)
        f = min(ok, key=lambda f: (f.at, f.board))
        return Alt5001In(
            bus_dep=_hhmm(d), wait_min=int(round(d - arr)), jinmok_arr=_hhmm(j),
            feeder_no=f.busno, feeder_dep=_hhmm(f.board), unist_at=_hhmm(f.at),
            # 5001 이 늦으면(p90) 이 환승 버스를 놓친다(환승 버스는 중앙값으로 본다). 근사면 판정 안 함.
            tight=not proxied and j_late + tr.jinmok > f.board, unist_min=f.at,
        ), proxied
    return None, False


# ── 표 만들기 ─────────────────────────────────────────────────────────────────

def _transfers(transfers: Transfers | None, transfer_min: int | None) -> Transfers:
    tr = transfers or Transfers()
    return Transfers(station=transfer_min, jinmok=tr.jinmok) if transfer_min is not None else tr


def build_outbound(day: int, ref_date: datetime.date | None, *, dest: str,
                   train_day: dict | None, bus_times: list[str] | None,
                   profile: dict | None, pair: tuple[str, str] | None = None,
                   timetables: Timetables | None = None,
                   transfers: Transfers | None = None,
                   transfer_min: int | None = None) -> ConnectTable:
    """울산역 출발 열차마다 ① 제시간에 닿는 가장 늦은 513, ② 5001 + 진목회관 환승 안을 붙인다.

    ``bus_times`` 는 513 덕하 출발, ``timetables`` 는 5001·환승 버스 시간표(없으면 ② 생략).
    ``pair`` (울산, 도착역) 를 주면 중간역 시각(``via``)도 채운다. ``transfer_min`` 은
    ``transfers.station`` 의 단축 인자다.
    """
    tr = _transfers(transfers, transfer_min)
    tts = timetables or {}
    buses = _outbound_buses(list(bus_times or []), profile, day)
    runs, proxied = _runs_5001_out(tts, profile, day)
    feeders = _out_feeders(tts, profile, day)
    names, branches = station_layout(pair)
    rows, skipped = [], 0
    for dep, arr, t, nos in _trains(train_day, ref_date):
        ok = [b for b in buses if b.c + tr.station <= dep]
        bus = max(ok, key=lambda b: b.a) if ok else None
        alt = _alt_out(dep, runs, feeders, tr)
        if bus is None and alt is None:
            skipped += 1                       # 어느 버스로도 닿지 못하는 이른 열차
            continue
        best = None
        if bus and alt:
            best = "5001" if alt.unist_min > bus.b else "513"
        rows.append(OutboundRow(
            train_no=nos,
            train_dep=_hhmm(dep), train_arr=_hhmm(arr), arr_next_day=arr >= 1440,
            grade=t.get("grade", ""),
            origin_dep=_hhmm(bus.a) if bus else None, unist_at=_hhmm(bus.b) if bus else None,
            station_at=_hhmm(bus.c) if bus else None,
            margin_min=int(dep - round(bus.c)) if bus else None,
            tight=bool(bus) and bus.c_late + tr.station > dep,
            via=via_cells(t.get("stops"), names, branches) if names else (),
            alt=alt, best=best,
        ))
    return ConnectTable(
        direction="out", dest=dest, day=day, ref_date=ref_date, rows=rows, skipped=skipped,
        rail_state=_rail_state(train_day), bus_state="ok" if bus_times else "missing",
        profile_state=_profile_state(profile),
        transfer_min=tr.station, stations=names,
        stops_unknown=sum(1 for r in rows if names and not any(r.via)),
        transfers=tr, alt_state="ok" if runs and feeders else "missing", alt_proxied=proxied,
    )


def build_inbound(day: int, ref_date: datetime.date | None, *, dest: str,
                  train_day: dict | None, bus_times: list[str] | None,
                  profile: dict | None, pair: tuple[str, str] | None = None,
                  timetables: Timetables | None = None,
                  transfers: Transfers | None = None,
                  transfer_min: int | None = None) -> ConnectTable:
    """울산역 도착 열차마다 ① 도착 뒤 울산역에 오는 첫 513, ② 5001 + 진목회관 환승 안을 붙인다."""
    tr = _transfers(transfers, transfer_min)
    tts = timetables or {}
    buses = _inbound_buses(list(bus_times or []), profile, day)
    deps_5001 = _minutes(tts.get((KTX_5001, KTX_5001_FROM_STATION)) or [])
    feeders = _in_feeders(tts, profile, day)
    names, branches = station_layout(pair)
    rows, skipped, proxied = [], 0, False
    for dep, arr, t, nos in sorted(_trains(train_day, ref_date), key=lambda x: (x[1], x[0])):
        ok = [b for b in buses if b.c >= arr + tr.station]
        bus = min(ok, key=lambda b: b.c) if ok else None
        alt, px = _alt_in(arr, deps_5001, feeders, profile, day, tr)
        proxied |= px
        if bus is None and alt is None:
            skipped += 1                       # 막차 뒤에 도착하는 열차
            continue
        best = None
        if bus and alt:
            best = "5001" if alt.unist_min < bus.b else "513"
        rows.append(InboundRow(
            train_no=nos,
            train_dep=_hhmm(dep), train_arr=_hhmm(arr), arr_next_day=arr >= 1440,
            grade=t.get("grade", ""),
            origin_dep=_hhmm(bus.a) if bus else None, station_at=_hhmm(bus.c) if bus else None,
            unist_at=_hhmm(bus.b) if bus else None,
            wait_min=int(round(bus.c) - arr) if bus else None,
            tight=bool(bus) and bus.c_early < arr + tr.station,
            via=via_cells(t.get("stops"), names, branches) if names else (),
            alt=alt, best=best,
        ))
    return ConnectTable(
        direction="in", dest=dest, day=day, ref_date=ref_date, rows=rows, skipped=skipped,
        rail_state=_rail_state(train_day), bus_state="ok" if bus_times else "missing",
        profile_state=_profile_state(profile),
        transfer_min=tr.station, stations=names,
        stops_unknown=sum(1 for r in rows if names and not any(r.via)),
        transfers=tr, alt_state="ok" if deps_5001 and feeders else "missing", alt_proxied=proxied,
    )


# 시각표 한 판에 싣는 시간대(울산역 기준 시각의 시). 열이 수십 개라 판을 나눠 가로 스크롤을 줄인다.
BLOCKS = (("morning", 0, 12), ("afternoon", 12, 18), ("evening", 18, 48))


def split_blocks(rows: list, direction: str) -> list[tuple[str, list]]:
    """행을 오전·오후·저녁 판으로 나눈다. 기준은 울산역 시각(가는 편 출발, 오는 편 도착)."""
    out = []
    for key, lo, hi in BLOCKS:
        part = [r for r in rows
                if lo * 60 <= service_minutes(f"{r.train_dep if direction == 'out' else r.train_arr}:00")
                < hi * 60]
        if part:
            out.append((key, part))
    return out
