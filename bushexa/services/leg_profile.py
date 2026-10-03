"""513 구간 소요 프로필 — 통과기록(TSV·bus_timelog)을 요일구분·시간대별 소요 분위수로 요약한다.

요일별 KTX 연계표(/ktx)가 "A시 덕하 출발 → B시 UNIST 경유 → (예상) C시 울산역"을 계산할 때
쓰는 입력이다. 공개 화면은 결과 파일 ``<data_dir>/ktx_leg_profile.json`` 만 읽고, 이 파일은
CLI ``bushexa build-leg-profile`` 로 운영자가 다시 만든다(git 추적 콘텐츠, 런타임에 바뀌지 않음).

측정 방법: 같은 노선·같은 차량의 통과기록을 시각순으로 놓고, 출발 정류장 기록 뒤에 처음 나오는
도착 정류장 기록과 짝짓는다. 그 사이에 출발 정류장이 다시 나오면(다음 운행) 새 기록으로 옮기고,
``KTX_LEG_MAX_MIN`` 보다 긴 짝은 버린다. 시간대는 출발 정류장 기록 시각의 시(hour)이고,
표본이 적은 토·일요일을 위해 앞뒤 1시간을 합쳐(3시간 창) 분위수를 낸다. 창 표본이
``KTX_LEG_MIN_SAMPLES`` 미만인 시간대는 싣지 않는다 — 읽는 쪽이 요일구분 전체값으로 대체한다.
"""
from __future__ import annotations

import csv
import datetime
import logging
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Iterable, NamedTuple

from bushexa.data.constants import KTX_LEG_MAX_MIN, KTX_LEG_MIN_SAMPLES, KTX_LEGS
from bushexa.fileio import atomic_write_json, read_json
from bushexa.time_utils import get_weekday

logger = logging.getLogger("bushexa.services.leg_profile")

PROFILE_VERSION = 1


class Passage(NamedTuple):
    at: datetime.datetime      # naive KST 벽시계 시각(기록 원문 그대로)
    stop_id: str
    route_id: str
    vehicle: str


def default_profile_path(data_dir) -> Path:
    return Path(data_dir) / "ktx_leg_profile.json"


def parse_log_time(value: str) -> datetime.datetime | None:
    """통과기록 시각 → datetime. ``20260602_11:39:19``(현행)·``2025-01-20_20:24:18``(옛 TSV)."""
    for fmt in ("%Y%m%d_%H:%M:%S", "%Y-%m-%d_%H:%M:%S"):
        try:
            return datetime.datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def read_tsv_passages(path, route_ids: set[str]) -> list[Passage]:
    """레거시·현행 ``logs.tsv``(time, stop_id, route_id, vehicle_number, …)에서 대상 노선만 읽는다."""
    out: list[Passage] = []
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row.get("route_id") not in route_ids:
                continue
            at = parse_log_time(row.get("time") or "")
            if at is None or not row.get("stop_id") or not row.get("vehicle_number"):
                continue
            out.append(Passage(at, row["stop_id"], row["route_id"], row["vehicle_number"]))
    return out


def read_db_passages(conn, route_ids: set[str]) -> list[Passage]:
    """``bus_timelog`` 에서 대상 노선 통과기록을 읽는다(idx = ``YYYYMMDD_HH:MM:SS``)."""
    from bushexa.db.connection import placeholder_for_conn

    ph = ",".join(placeholder_for_conn(conn) for _ in route_ids)
    cur = conn.cursor()
    cur.execute(f"SELECT idx, stop_id, route_id, vehicle_number FROM bus_timelog "
                f"WHERE route_id IN ({ph})", sorted(route_ids))
    out = []
    for idx, stop_id, route_id, vehicle in cur.fetchall():
        at = parse_log_time(idx or "")
        if at is not None and stop_id and vehicle:
            out.append(Passage(at, stop_id, route_id, vehicle))
    return out


def leg_samples(passages: Iterable[Passage], route_id: str, from_stop: str, to_stop: str,
                max_minutes: float = KTX_LEG_MAX_MIN) -> list[tuple[datetime.datetime, float]]:
    """같은 차량의 ``from_stop`` → ``to_stop`` 통과 짝 (출발 기록 시각, 소요 분) 목록."""
    by_vehicle: dict[str, list[Passage]] = defaultdict(list)
    for p in passages:
        if p.route_id == route_id and p.stop_id in (from_stop, to_stop):
            by_vehicle[p.vehicle].append(p)
    out = []
    for seq in by_vehicle.values():
        seq.sort(key=lambda p: p.at)
        start: datetime.datetime | None = None
        for p in seq:
            if p.stop_id == from_stop:
                start = p.at                      # 다음 운행이 시작되면 새 기록으로 옮긴다
            elif start is not None:
                minutes = (p.at - start).total_seconds() / 60
                if 0 < minutes <= max_minutes:
                    out.append((start, minutes))
                start = None
    out.sort()
    return out


def _stats(values: list[float]) -> dict:
    values = sorted(values)
    if len(values) >= 2:
        q = statistics.quantiles(values, n=10, method="inclusive")
        p10, p90 = q[0], q[8]
    else:
        p10 = p90 = values[0]
    return {"n": len(values), "p10": round(p10, 1), "p50": round(statistics.median(values), 1),
            "p90": round(p90, 1)}


def summarize_samples(samples: list[tuple[datetime.datetime, float]], holiday_set: set[str],
                      min_samples: int = KTX_LEG_MIN_SAMPLES) -> dict:
    """(시각, 분) 표본 → ``{"0"|"1"|"2": {"all": stats, "hours": {"H": stats}}}``."""
    by_day_hour: dict[int, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for at, minutes in samples:
        by_day_hour[get_weekday(at.date(), holiday_set)][at.hour].append(minutes)
    out: dict[str, dict] = {}
    for day, hours in sorted(by_day_hour.items()):
        every = [m for ms in hours.values() for m in ms]
        hour_stats = {}
        for h in range(24):
            window = [m for hh in (h - 1, h, h + 1) for m in hours.get(hh, [])]
            if h in hours and len(window) >= min_samples:
                hour_stats[str(h)] = _stats(window)
        out[str(day)] = {"all": _stats(every), "hours": hour_stats}
    return out


def build_leg_profile(passages: list[Passage], holiday_set: set[str], *,
                      generated_at: str, sources: list,
                      legs: dict = KTX_LEGS) -> dict:
    """모든 ``KTX_LEGS`` 구간의 프로필 dict(파일 형식 그대로)."""
    out_legs = {}
    span: list[datetime.datetime] = []
    for name, (route_id, from_stop, to_stop) in legs.items():
        samples = leg_samples(passages, route_id, from_stop, to_stop)
        span += [samples[0][0], samples[-1][0]] if samples else []
        out_legs[name] = {"route_id": route_id, "from": from_stop, "to": to_stop,
                          "by_day": summarize_samples(samples, holiday_set)}
    return {
        "version": PROFILE_VERSION,
        "generated_at": generated_at,
        "sources": sources,
        "period": [min(span).date().isoformat(), max(span).date().isoformat()] if span else None,
        "legs": out_legs,
    }


def holidays_for_span(passages: list[Passage], extra: set[str] | None = None) -> set[str]:
    """표본 기간의 공휴일(YYYYMMDD) — ``holidays`` 패키지(음력·대체·선거일 포함) ∪ ``extra``."""
    from bushexa.services.holiday_service import offline_month_holidays

    months = sorted({(p.at.year, p.at.month) for p in passages})
    out = set(extra or ())
    for y, m in months:
        out |= {d.strftime("%Y%m%d") for d in offline_month_holidays(y, m)}
    return out


def save_profile(path, profile: dict) -> None:
    atomic_write_json(Path(path), profile, indent=1)  # git diff 가 읽히게


def load_profile(path) -> dict | None:
    """프로필 파일. 없거나 깨졌으면 None(화면은 '소요 자료 없음'을 보인다)."""
    data = read_json(Path(path), default=None, expect=dict, warn_label="구간 소요 프로필",
                     logger=logger)
    if not data or not isinstance(data.get("legs"), dict):
        return None
    return data


# ── 관리자 재계산: 후보 → 비교 → 적용/되돌리기 ─────────────────────────────────
# 운영 DB 는 표본이 적을 수 있어 후보로 만든 뒤, 기본은 구간·요일별로 표본이 많은 쪽을 병합한다.

def candidate_profile_path(data_dir) -> Path:
    return Path(data_dir) / "ktx_leg_profile.candidate.json"


def previous_profile_path(data_dir) -> Path:
    return Path(data_dir) / "ktx_leg_profile.prev.json"


def source_meta(name: str, rows: list[Passage]) -> dict:
    """프로필 출처 한 줄: 이름·기록 수·기간(같은 이름의 TSV 가 여럿이어도 구분되게)."""
    days = sorted(p.at.date().isoformat() for p in rows)
    return {"name": name, "rows": len(rows), "period": [days[0], days[-1]] if days else None}


def collect_passages(*, db_url: str | None = None, tsv_paths=(),
                     on_progress=None, legs: dict = KTX_LEGS) -> tuple[list[Passage], list[dict]]:
    """DB(bus_timelog)·TSV 에서 ``legs``(기본 ``KTX_LEGS``) 노선 통과기록을 모아 중복을 뺀다. (통과기록, 출처)."""
    route_ids = {leg[0] for leg in legs.values()}
    passages: list[Passage] = []
    sources: list[dict] = []
    for path in tsv_paths:
        rows = read_tsv_passages(path, route_ids)
        passages += rows
        sources.append(source_meta(Path(path).name, rows))
        if on_progress:
            on_progress({"stage": "read", "label": f"{Path(path).name}: {len(rows)}건", "ok": True})
    if db_url:
        from bushexa.db.connection import create_connection

        conn = create_connection(db_url)
        try:
            rows = read_db_passages(conn, route_ids)
        finally:
            conn.close()
        passages += rows
        sources.append(source_meta("bus_timelog", rows))
        if on_progress:
            on_progress({"stage": "read", "label": f"bus_timelog: {len(rows)}건", "ok": True})
    # 같은 통과가 TSV·DB 에 겹쳐 있어도 한 번만 센다.
    passages = sorted(set(passages), key=lambda p: (p.route_id, p.vehicle, p.at))
    return passages, sources


def _day_n(profile: dict | None, leg: str, day: str) -> int:
    try:
        return int(profile["legs"][leg]["by_day"][day]["all"]["n"])
    except (KeyError, TypeError, ValueError):
        return 0


def merge_profiles(current: dict | None, candidate: dict) -> tuple[dict, dict]:
    """구간·요일별로 표본(n)이 더 많은 쪽을 고른 프로필과 선택 기록 ``{leg: {day: "current"|"candidate"}}``.

    같으면 현재 값을 유지한다. 출처는 둘을 합쳐 적고, 기간은 선택된 쪽 기간을 아우른다.
    """
    merged_legs: dict = {}
    choices: dict[str, dict[str, str]] = {}
    for leg in sorted(set((current or {}).get("legs", {})) | set(candidate.get("legs", {}))):
        cur_leg = ((current or {}).get("legs") or {}).get(leg) or {}
        cand_leg = (candidate.get("legs") or {}).get(leg) or {}
        base = {k: v for k, v in (cand_leg or cur_leg).items() if k != "by_day"}
        by_day: dict = {}
        choices[leg] = {}
        for day in sorted(set(cur_leg.get("by_day", {})) | set(cand_leg.get("by_day", {}))):
            if _day_n(candidate, leg, day) > _day_n(current, leg, day):
                by_day[day] = cand_leg["by_day"][day]
                choices[leg][day] = "candidate"
            else:
                by_day[day] = cur_leg["by_day"][day]
                choices[leg][day] = "current"
        merged_legs[leg] = {**base, "by_day": by_day}
    periods = [p for p in ((current or {}).get("period"), candidate.get("period")) if p]
    merged = {
        "version": PROFILE_VERSION,
        "generated_at": candidate.get("generated_at"),
        "sources": list((current or {}).get("sources") or []) + list(candidate.get("sources") or []),
        "period": [min(p[0] for p in periods), max(p[1] for p in periods)] if periods else None,
        "merged": True,
        "legs": merged_legs,
    }
    return merged, choices


def compare_profiles(current: dict | None, candidate: dict | None) -> list[dict]:
    """관리자 비교표 행: 구간·요일별 (현재 n·p50, 후보 n·p50, 병합 시 선택)."""
    _, choices = merge_profiles(current, candidate) if candidate else (None, {})
    rows = []
    legs = sorted(set((current or {}).get("legs", {})) | set((candidate or {}).get("legs", {})),
                  key=lambda k: list(KTX_LEGS).index(k) if k in KTX_LEGS else 999)
    for leg in legs:
        for day in ("0", "1", "2"):
            def cell(p):
                try:
                    a = p["legs"][leg]["by_day"][day]["all"]
                    return {"n": a["n"], "p50": a["p50"]}
                except (KeyError, TypeError):
                    return None
            cur, cand = cell(current), cell(candidate)
            if cur is None and cand is None:
                continue
            rows.append({"leg": leg, "day": day, "current": cur, "candidate": cand,
                         "pick": (choices.get(leg) or {}).get(day)})
    return rows


def promote_profile(data_dir, profile: dict) -> None:
    """``profile`` 을 현재 프로필로 쓰고, 이전 현재 값은 ``.prev`` 로 남긴다. 후보 파일은 지운다."""
    current = load_profile(default_profile_path(data_dir))
    if current is not None:
        save_profile(previous_profile_path(data_dir), current)
    save_profile(default_profile_path(data_dir), profile)
    candidate_profile_path(data_dir).unlink(missing_ok=True)


def rollback_profile(data_dir) -> bool:
    """``.prev`` 와 현재 프로필을 맞바꾼다(한 번 더 누르면 다시 돌아온다). prev 가 없으면 False."""
    prev = load_profile(previous_profile_path(data_dir))
    if prev is None:
        return False
    current = load_profile(default_profile_path(data_dir))
    save_profile(default_profile_path(data_dir), prev)
    if current is not None:
        save_profile(previous_profile_path(data_dir), current)
    else:
        previous_profile_path(data_dir).unlink(missing_ok=True)
    return True
