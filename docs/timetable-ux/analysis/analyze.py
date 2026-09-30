"""Run-history analysis: origin departure -> UNIST passing/arrival time.

Read-only. Input: logs/logs.tsv (govtrack TSV sink, 2026-04-16 ~ 2026-06-01) and
data/timetable/*.json. Output: stdout report + runs.csv.

Method
------
Rows are (time, stop_id, route_id, vehicle, stop_name) written when a vehicle's
reported node changes to a tracked stop (recorder.py:188-205), poll ~15s.
Runs: per (route_id, vehicle) sorted by time; a new run starts when the vehicle
is (re)observed at the origin stop after being elsewhere, or after a >60 min gap
(same as domain/running.py:_SPLIT_GAP_MINUTES).

Departure anchor D (schedule-matched): the latest scheduled departure from the
origin (day type timetable) that is <= t_first_after (first tracked stop after
origin) and >= t_origin - 3min (if origin was observed) else >= t_first_after - 45min.
travel = t_target - D.  Also reports t_target - t_origin (raw, includes layover).
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path("/home/mlv/project/bushexa/bus-hexa-revive-temp")
TSV = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "logs/logs.tsv"
OUT = Path(__file__).parent

HOLIDAYS = {dt.date(2026, 5, 5), dt.date(2026, 5, 24), dt.date(2026, 5, 25),
            dt.date(2025, 1, 1), dt.date(2025, 1, 27), dt.date(2025, 1, 28),
            dt.date(2025, 1, 29), dt.date(2025, 1, 30)}

# route_id -> (busno, origin label (timetable key), origin stop, target stops [primary, fallbacks])
DIRS = {
    "196000421": ("513", "덕하", "196040142", ["196040234", "196040232", "196040231"]),
    "196000422": ("513", "삼남", "196015417", ["196040234", "196040232", "196040231"]),
    "195000177": ("713", "명촌", "999000149", ["196040232", "999000145"]),
    "195000215": ("743", "명촌", "999000149", ["196040232", "999000145"]),
    "195000221": ("753", "명촌", "999000149", ["196040232", "999000145"]),
    "194000106": ("1115", "꽃바위", "194019014", ["196040232", "999000145"]),
}


def parse_ts(s: str) -> dt.datetime:
    d, t = s.split("_")
    fmt = "%Y-%m-%d %H:%M:%S" if "-" in d else "%Y%m%d %H:%M:%S"
    return dt.datetime.strptime(d + " " + t, fmt)


def daytype(d: dt.date) -> str:
    if d in HOLIDAYS or d.weekday() == 6:
        return "2"
    if d.weekday() == 5:
        return "1"
    return "0"


def load_tt():
    tt = {}
    for bus in ("513", "713", "743", "753", "1115"):
        tt[bus] = json.loads((REPO / f"data/timetable/{bus}.json").read_text())
    return tt


def hour_bucket(h: int) -> str:
    if h < 7:
        return "05-06"
    if h < 10:
        return "07-09"
    if h < 17:
        return "10-16"
    if h < 20:
        return "17-19"
    return "20-22"


def q(xs, p):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * p
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def summ(xs):
    if not xs:
        return "n=0"
    return (f"n={len(xs):4d} med={st.median(xs):5.1f} IQR=[{q(xs,.25):5.1f},{q(xs,.75):5.1f}] "
            f"p10={q(xs,.1):5.1f} p90={q(xs,.9):5.1f} (IQR폭 {q(xs,.75)-q(xs,.25):4.1f})")


def main():
    tt = load_tt()
    rows = defaultdict(list)
    with TSV.open(encoding="utf-8") as f:
        r = csv.reader(f, delimiter="\t")
        next(r)
        for rec in r:
            if len(rec) < 4:
                continue
            ts, stop, rid, veh = rec[0], rec[1], rec[2], rec[3]
            if rid not in DIRS:
                continue
            try:
                rows[(rid, veh)].append((parse_ts(ts), stop))
            except ValueError:
                continue

    runs = []
    for (rid, veh), obs in rows.items():
        obs.sort()
        bus, olabel, ostop, targets = DIRS[rid]
        cur = []
        prev_t = None
        for t, s in obs:
            new = False
            if prev_t is not None and (t - prev_t).total_seconds() > 3600:
                new = True
            if s == ostop and cur and cur[-1][1] != ostop:
                new = True
            if new and cur:
                runs.append((rid, veh, cur))
                cur = []
            cur.append((t, s))
            prev_t = t
        if cur:
            runs.append((rid, veh, cur))

    out_rows = []
    for rid, veh, obs in runs:
        bus, olabel, ostop, targets = DIRS[rid]
        t_origin = next((t for t, s in obs if s == ostop), None)
        after = [(t, s) for t, s in obs if s != ostop]
        if not after:
            continue
        t_first_after, s_first_after = after[0]
        tgt = {}
        for t, s in obs:
            if s in targets and s not in tgt:
                tgt[s] = t
        day = (t_origin or t_first_after).date()
        dty = daytype(day)
        sched = tt[bus].get(dty, {}).get(olabel, [])
        lo = (t_origin - dt.timedelta(minutes=3)) if t_origin else (t_first_after - dt.timedelta(minutes=45))
        D = None
        for hhmm in sched:
            h, m = map(int, hhmm.split(":"))
            cand = dt.datetime.combine(day, dt.time(h, m))
            if lo <= cand <= t_first_after:
                D = cand  # sched sorted -> keep latest
        prim = targets[0]
        rec = {
            "route_id": rid, "bus": bus, "origin": olabel, "vehicle": veh, "date": day.isoformat(),
            "daytype": dty, "t_origin": t_origin.strftime("%H:%M:%S") if t_origin else "",
            "t_first_after": t_first_after.strftime("%H:%M:%S"), "first_after_stop": s_first_after,
            "sched_dep": D.strftime("%H:%M") if D else "",
            "n_obs": len(obs),
        }
        for s in targets:
            rec[f"t_{s}"] = tgt[s].strftime("%H:%M:%S") if s in tgt else ""
            rec[f"travel_{s}"] = round((tgt[s] - D).total_seconds() / 60, 2) if (s in tgt and D) else ""
        rec["raw_origin_to_primary"] = (round((tgt[prim] - t_origin).total_seconds() / 60, 2)
                                        if (prim in tgt and t_origin) else "")
        rec["dep_lag_first_after"] = round((t_first_after - D).total_seconds() / 60, 2) if D else ""
        out_rows.append(rec)

    keys = sorted({k for r in out_rows for k in r}, key=lambda k: (k.startswith("t_1") or k.startswith("t_9"), k))
    with (OUT / f"runs_{TSV.stem}.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(out_rows)

    dates = sorted({r["date"] for r in out_rows})
    print(f"# source={TSV}  days={len(dates)} range={dates[0]}..{dates[-1]}")
    for rid, (bus, olabel, ostop, targets) in DIRS.items():
        rr = [r for r in out_rows if r["route_id"] == rid]
        prim = targets[0]
        n_tgt = sum(1 for r in rr if r[f"t_{prim}"])
        n_anch = sum(1 for r in rr if r["sched_dep"])
        n_orig = sum(1 for r in rr if r["t_origin"])
        both = [r for r in rr if r[f"travel_{prim}"] != ""]
        print(f"\n## {bus} {rid} {olabel} 출발 -> {prim}")
        print(f"runs={len(rr)} origin관측={n_orig} target관측={n_tgt} 시간표매칭={n_anch} 유효(매칭&target)={len(both)}")
        # sanity filter
        trav = [r[f"travel_{prim}"] for r in both if 0 < r[f"travel_{prim}"] < 150]
        print("전체       ", summ(trav))
        for dty in "012":
            xs = [r[f"travel_{prim}"] for r in both if r["daytype"] == dty and 0 < r[f"travel_{prim}"] < 150]
            print(f"daytype={dty} ", summ(xs))
        for hb in ("05-06", "07-09", "10-16", "17-19", "20-22"):
            for dty in "0":
                xs = [r[f"travel_{prim}"] for r in both
                      if r["daytype"] == dty and hour_bucket(int(r["sched_dep"][:2])) == hb
                      and 0 < r[f"travel_{prim}"] < 150]
                print(f"  평일 {hb}", summ(xs))
        for hb in ("05-06", "07-09", "10-16", "17-19", "20-22"):
            xs = [r[f"travel_{prim}"] for r in both
                  if r["daytype"] in "12" and hour_bucket(int(r["sched_dep"][:2])) == hb
                  and 0 < r[f"travel_{prim}"] < 150]
            print(f"  주말휴일 {hb}", summ(xs))
        lag = [r["dep_lag_first_after"] for r in rr if r["dep_lag_first_after"] != ""]
        print(f"출발→첫추적정류장 관측 지연(first_after - D): {summ(lag)}")
        raw = [r["raw_origin_to_primary"] for r in rr if r["raw_origin_to_primary"] != "" and 0 < r["raw_origin_to_primary"] < 240]
        print(f"raw 기점관측→target(대기 포함): {summ(raw)}")
        for s in targets[1:]:
            xs = [r[f"travel_{s}"] for r in rr if r[f"travel_{s}"] != "" and 0 < r[f"travel_{s}"] < 150]
            print(f"  대체 target {s}: {summ(xs)}")
        # per-scheduled-departure slot table (weekday) for 513
        if bus == "513":
            print("  [평일 슬롯별] sched_dep: n, median, min, max")
            slot = defaultdict(list)
            for r in both:
                if r["daytype"] == "0" and 0 < r[f"travel_{prim}"] < 150:
                    slot[r["sched_dep"]].append(r[f"travel_{prim}"])
            for k in sorted(slot):
                xs = slot[k]
                print(f"   {k}: n={len(xs):2d} med={st.median(xs):5.1f} min={min(xs):5.1f} max={max(xs):5.1f}")
            # coverage: scheduled weekday departures vs matched
            sched_w = tt[bus]["0"][olabel]
            wdays = [d for d in dates if daytype(dt.date.fromisoformat(d)) == "0"]
            matched = sum(1 for r in rr if r["daytype"] == "0" and r["sched_dep"])
            print(f"  평일 시간표 편수 {len(sched_w)} x 평일 {len(wdays)}일 = {len(sched_w)*len(wdays)} 예정 / 매칭 run {matched}")

    # leave-one-day-out prediction error for 513 using median by (dir, daytype-group, sched slot) and by (dir,dtgroup,hourbucket)
    print("\n## 513 예측 오차 (leave-one-day-out)")
    for rid in ("196000421", "196000422"):
        prim = DIRS[rid][3][0]
        data = [r for r in out_rows if r["route_id"] == rid and r[f"travel_{prim}"] != ""
                and 0 < r[f"travel_{prim}"] < 150]
        for name, keyf in (
            ("slot(요일군+시간표편)", lambda r: (r["daytype"] == "0", r["sched_dep"])),
            ("hour-bucket(요일군)", lambda r: (r["daytype"] == "0", hour_bucket(int(r["sched_dep"][:2])))),
            ("전체 중앙값", lambda r: 0),
        ):
            errs = []
            for r in data:
                pool = [x[f"travel_{prim}"] for x in data if x["date"] != r["date"] and keyf(x) == keyf(r)]
                if len(pool) < 3:
                    continue
                pred = st.median(pool)
                errs.append(r[f"travel_{prim}"] - pred)
            ab = [abs(e) for e in errs]
            if ab:
                w3 = sum(1 for a in ab if a <= 3) / len(ab)
                w5 = sum(1 for a in ab if a <= 5) / len(ab)
                print(f"{rid} {name:22s} n={len(ab)} MAE={st.mean(ab):.2f} medAE={st.median(ab):.2f} "
                      f"p90AE={q(ab,.9):.2f} |err|<=3m {w3:.0%} <=5m {w5:.0%} late(>+5) {sum(1 for e in errs if e>5)/len(errs):.0%}")


if __name__ == "__main__":
    main()
