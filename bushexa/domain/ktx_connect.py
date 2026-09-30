"""요일별 KTX 연계표(/ktx) — 열차마다 513 연계 버스를 짝짓는다(순수 함수).

- 가는 편(out): 울산역 출발 KTX(부산·서울·수서행)마다 "최소한 타야 하는 버스", 즉 울산역에
  열차 출발 ``transfer_min`` 분 전까지 닿는(예상) 가장 늦은 513 을 붙인다.
  A = 덕하 출발(시간표) → B = UNIST(경유) 통과(예상) → C = 울산역(언양 방면) 도착(예상).
  어떤 버스로도 닿지 못하는 열차(513 첫차보다 이른 열차)는 표에서 뺀다.
- 오는 편(in): 울산역 도착 KTX(부산·서울·수서발)마다 도착 ``transfer_min`` 분 뒤 이후 울산역
  (시내 방면)에 오는(예상) 첫 513 을 붙인다. A = 삼남 출발(시간표) → C = 울산역 → B = UNIST.
  막차 뒤에 도착하는 열차는 뺀다.

B·C 는 구간 소요 프로필(``services/leg_profile`` 산출, 요일구분·시간대별 중앙값)로 계산한다.
중앙값으로 짝짓되, 늦는 날(p90)이면 여유가 ``transfer_min`` 미만이 되는 짝은 ``tight`` 로 표시한다
(오는 편은 버스가 일찍 오는 날(p10)을 본다). 입력은 모두 주입한다 — 파일·API·DB 를 읽지 않는다.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Iterable

from bushexa.data.constants import (
    KTX_CONNECT_TRANSFER_MIN,
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


@dataclass(frozen=True)
class LegEstimate:
    p10: float
    p50: float
    p90: float


@dataclass(frozen=True)
class OutboundRow:
    train_no: tuple[str, ...]   # 열차번호(중련이면 둘)
    train_dep: str          # 울산역 출발 "HH:MM"
    train_arr: str          # 부산·서울·수서 도착 "HH:MM"
    arr_next_day: bool
    grade: str
    origin_dep: str         # A: 513 덕하 출발(시간표)
    unist_at: str           # B: UNIST(경유) 통과(예상)
    station_at: str         # C: 울산역 도착(예상)
    margin_min: int         # 열차 출발 − C
    tight: bool             # 늦는 날(p90)엔 여유가 최소 여유 미만
    via: tuple[str, ...] = ()   # 중간역 칸(ConnectTable.stations 순서): "HH:MM" 도착 / レ / ‖ / ""(모름)


@dataclass(frozen=True)
class InboundRow:
    train_no: tuple[str, ...]
    train_dep: str          # 부산·서울·수서 출발 "HH:MM"
    train_arr: str          # 울산역 도착 "HH:MM"
    arr_next_day: bool
    grade: str
    origin_dep: str         # A: 513 삼남 출발(시간표)
    station_at: str         # C: 울산역(시내 방면) 도착(예상)
    unist_at: str           # B: UNIST(경유) 도착(예상)
    wait_min: int           # C − 열차 도착
    tight: bool             # 일찍 오는 날(p10)엔 여유가 최소 여유 미만
    via: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConnectTable:
    direction: str                          # out / in
    dest: str                               # busan / seoul / suseo
    day: int                                # 0 평일 / 1 토 / 2 일·공휴일
    ref_date: datetime.date | None          # 열차 시간표를 가져온 날짜
    rows: list = field(default_factory=list)
    skipped: int = 0                        # 이어 탈 버스가 없어 뺀 열차 수
    rail_state: str = "missing"             # ok / suspect / missing
    bus_state: str = "missing"              # ok / missing
    profile_state: str = "missing"          # ok / missing
    transfer_min: int = KTX_CONNECT_TRANSFER_MIN
    stations: tuple[str, ...] = ()          # 중간역(운행 순서) — 없으면 직행 구간(울산↔부산)
    stops_unknown: int = 0                  # 정차역을 모르는 열차 수(조회 안 된 날짜·조회 실패)


# ── 입력 정리 ────────────────────────────────────────────────────────────────

def _hhmm(minutes: float) -> str:
    m = int(round(minutes)) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def leg_estimate(profile: dict | None, leg: str, day: int, minute: float) -> LegEstimate | None:
    """``minute``(운행일 분)에 출발 정류장을 지나는 차의 구간 소요. 시간대 → 요일구분 전체 → 평일 순."""
    try:
        by_day = profile["legs"][leg]["by_day"]
    except (KeyError, TypeError):
        return None
    entry = by_day.get(str(day)) or by_day.get("0")
    if not entry:
        return None
    s = (entry.get("hours") or {}).get(str(int(minute // 60) % 24)) or entry.get("all")
    if not s:
        return None
    return LegEstimate(float(s["p10"]), float(s["p50"]), float(s["p90"]))


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


# ── 가는 편: 513 → 울산역 → KTX ─────────────────────────────────────────────

@dataclass(frozen=True)
class _BusOut:
    a: float
    b: float
    c: float
    c_late: float        # 늦는 날(p90) 울산역 도착


def _outbound_buses(bus_times: list[str], profile: dict | None, day: int) -> list[_BusOut]:
    out = []
    for t in bus_times:
        a = service_minutes(f"{t}:00")
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


def build_outbound(day: int, ref_date: datetime.date | None, *, dest: str,
                   train_day: dict | None, bus_times: list[str] | None,
                   profile: dict | None, pair: tuple[str, str] | None = None,
                   transfer_min: int = KTX_CONNECT_TRANSFER_MIN) -> ConnectTable:
    """울산역 출발 열차마다 제시간에 닿는 가장 늦은 513(덕하 출발)을 붙인다.

    ``pair`` (울산, 도착역) 를 주면 중간역 시각(``via``)도 채운다.
    """
    buses = _outbound_buses(list(bus_times or []), profile, day)
    names, branches = station_layout(pair)
    rows, skipped = [], 0
    for dep, arr, t, nos in _trains(train_day, ref_date):
        ok = [b for b in buses if b.c + transfer_min <= dep]
        if not ok:
            skipped += 1                       # 513 첫차보다 이른 열차
            continue
        bus = max(ok, key=lambda b: b.a)
        rows.append(OutboundRow(
            train_no=nos,
            train_dep=_hhmm(dep), train_arr=_hhmm(arr), arr_next_day=arr >= 1440,
            grade=t.get("grade", ""), origin_dep=_hhmm(bus.a), unist_at=_hhmm(bus.b),
            station_at=_hhmm(bus.c), margin_min=int(dep - round(bus.c)),
            tight=bus.c_late + transfer_min > dep,
            via=via_cells(t.get("stops"), names, branches) if names else (),
        ))
    return ConnectTable(
        direction="out", dest=dest, day=day, ref_date=ref_date, rows=rows, skipped=skipped,
        rail_state=_rail_state(train_day), bus_state="ok" if bus_times else "missing",
        profile_state=_profile_state(profile),
        transfer_min=transfer_min, stations=names,
        stops_unknown=sum(1 for r in rows if names and not any(r.via)),
    )


# ── 오는 편: KTX → 울산역 → 513 → UNIST ─────────────────────────────────────

@dataclass(frozen=True)
class _BusIn:
    a: float
    c: float
    c_early: float       # 일찍 오는 날(p10) 울산역 도착
    b: float


def _inbound_buses(bus_times: list[str], profile: dict | None, day: int) -> list[_BusIn]:
    out = []
    for t in bus_times:
        a = service_minutes(f"{t}:00")
        to_station = leg_estimate(profile, "samnam_station", day, a)
        if to_station is None:
            continue
        c = a + to_station.p50
        to_unist = leg_estimate(profile, "station_unist", day, c)
        if to_unist is None:
            continue
        out.append(_BusIn(a, c, a + to_station.p10, c + to_unist.p50))
    return out


def build_inbound(day: int, ref_date: datetime.date | None, *, dest: str,
                  train_day: dict | None, bus_times: list[str] | None,
                  profile: dict | None, pair: tuple[str, str] | None = None,
                  transfer_min: int = KTX_CONNECT_TRANSFER_MIN) -> ConnectTable:
    """울산역 도착 열차마다 도착 ``transfer_min`` 분 뒤 이후 울산역에 오는 첫 513 을 붙인다."""
    buses = _inbound_buses(list(bus_times or []), profile, day)
    names, branches = station_layout(pair)
    rows, skipped = [], 0
    for dep, arr, t, nos in sorted(_trains(train_day, ref_date), key=lambda x: (x[1], x[0])):
        ok = [b for b in buses if b.c >= arr + transfer_min]
        if not ok:
            skipped += 1                       # 513 막차 뒤에 도착하는 열차
            continue
        bus = min(ok, key=lambda b: b.c)
        rows.append(InboundRow(
            train_no=nos,
            train_dep=_hhmm(dep), train_arr=_hhmm(arr), arr_next_day=arr >= 1440,
            grade=t.get("grade", ""), origin_dep=_hhmm(bus.a), station_at=_hhmm(bus.c),
            unist_at=_hhmm(bus.b), wait_min=int(round(bus.c) - arr),
            tight=bus.c_early < arr + transfer_min,
            via=via_cells(t.get("stops"), names, branches) if names else (),
        ))
    return ConnectTable(
        direction="in", dest=dest, day=day, ref_date=ref_date, rows=rows, skipped=skipped,
        rail_state=_rail_state(train_day), bus_state="ok" if bus_times else "missing",
        profile_state=_profile_state(profile),
        transfer_min=transfer_min, stations=names,
        stops_unknown=sum(1 for r in rows if names and not any(r.via)),
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
