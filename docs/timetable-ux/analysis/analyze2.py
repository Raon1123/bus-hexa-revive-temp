"""Supplementary analysis (read-only).

1) Per-day run counts vs timetable count (schedule-conformance check).
2) Campus-stop observation coverage (196040234 / any of 232,234,231).
3) Short-segment travel (upstream tracked stop -> 196040234): basis for real-time ETA
   from govtrack positions.
4) Anchor-free hit-rate: prediction P = D + slot-median (leave-one-day-out); for each
   (day, slot) check whether any observed UNIST pass on that day lies within +-3/5 min.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

from analyze import DIRS, REPO, daytype, parse_ts, q, summ

TSV = REPO / "logs/logs.tsv"
OUT = Path(__file__).parent
RUNS = list(csv.DictReader((OUT / "runs_logs.csv").open(encoding="utf-8")))


def fnum(x):
    return float(x) if x not in ("", None) else None


def main():
    tt = {b: json.loads((REPO / f"data/timetable/{b}.json").read_text()) for b in ("513",)}
    # raw rows
    rows = defaultdict(list)
    with TSV.open(encoding="utf-8") as f:
        r = csv.reader(f, delimiter="\t")
        next(r)
        for rec in r:
            if len(rec) >= 4 and rec[2] in ("196000421", "196000422"):
                rows[(rec[2], rec[3])].append((parse_ts(rec[0]), rec[1]))
    for k in rows:
        rows[k].sort()

    print("## 1) 평일 일별 run 수(원점 이후 첫 추적정류장 관측 기준) vs 시간표 편수")
    for rid, org in (("196000421", "덕하"), ("196000422", "삼남")):
        per = defaultdict(int)
        for r in RUNS:
            if r["route_id"] == rid and r["daytype"] == "0":
                per[r["date"]] += 1
        xs = sorted(per.values())
        print(f"{rid} {org}: 시간표 평일 {len(tt['513']['0'][org])}편, 관측 run/일 median={st.median(xs)} min={min(xs)} max={max(xs)} (days={len(xs)})")

    print("\n## 2) 캠퍼스 정류장 관측률 (run 기준)")
    for rid in ("196000421", "196000422", "195000177", "195000215", "195000221", "194000106"):
        rr = [r for r in RUNS if r["route_id"] == rid]
        tg = DIRS[rid][3]
        prim = sum(1 for r in rr if r.get(f"t_{tg[0]}"))
        anyc = sum(1 for r in rr if any(r.get(f"t_{s}") for s in tg))
        # exclude short/partial runs: require >=5 obs
        rr5 = [r for r in rr if int(r["n_obs"]) >= 5]
        anyc5 = sum(1 for r in rr5 if any(r.get(f"t_{s}") for s in tg))
        print(f"{rid} {DIRS[rid][0]}: runs={len(rr)} primary({tg[0]})={prim/len(rr):.0%} any={anyc/len(rr):.0%} | n_obs>=5 runs={len(rr5)} any={anyc5/len(rr5):.0%}")

    print("\n## 3) 상류 정류장 -> 196040234 구간 소요(분) — 실시간 ETA 근거")
    segs = {"196000421": ["193031110", "193040224", "196020412", "196040212", "196040236"],
            "196000422": ["196015414"]}
    for rid, ups in segs.items():
        for up in ups:
            xs = []
            for (r_, veh), obs in rows.items():
                if r_ != rid:
                    continue
                for i, (t, s) in enumerate(obs):
                    if s != up:
                        continue
                    for t2, s2 in obs[i + 1:]:
                        if (t2 - t).total_seconds() > 3600:
                            break
                        if s2 == "196040234":
                            xs.append((t2 - t).total_seconds() / 60)
                            break
                        if s2 == up:
                            break
            xs = [x for x in xs if 0 < x < 90]
            print(f"{rid} {up}->196040234: {summ(xs)}")

    print("\n## 4) anchor-free 적중률: P = D + slot중앙값(LODO), 당일 관측 UNIST 통과가 P±k분 안에 있는가")
    for rid, org in (("196000421", "덕하"), ("196000422", "삼남")):
        rr = [r for r in RUNS if r["route_id"] == rid and r["travel_196040234"] != ""
              and 0 < float(r["travel_196040234"]) < 150]
        # observed passes per date (from raw, any vehicle)
        passes = defaultdict(list)
        for (r_, veh), obs in rows.items():
            if r_ == rid:
                for t, s in obs:
                    if s == "196040234":
                        passes[t.date()].append(t)
        for dgroup, label in ((("0",), "평일"), (("1", "2"), "주말휴일")):
            hits3 = hits5 = tot = 0
            fb_hit5 = 0
            for day in sorted(passes):
                dty = daytype(day)
                if dty not in dgroup:
                    continue
                for hhmm in tt["513"][dty][org]:
                    pool = [float(r["travel_196040234"]) for r in rr
                            if r["sched_dep"] == hhmm and r["date"] != day.isoformat()
                            and r["daytype"] in dgroup]
                    if len(pool) < 3:
                        continue
                    D = dt.datetime.combine(day, dt.time(*map(int, hhmm.split(":"))))
                    P = D + dt.timedelta(minutes=st.median(pool))
                    d = min(abs((t - P).total_seconds()) / 60 for t in passes[day])
                    tot += 1
                    hits3 += d <= 3
                    hits5 += d <= 5
            print(f"{rid} {org} {label}: slots={tot} 적중 ±3분 {hits3/tot:.0%} ±5분 {hits5/tot:.0%}")
        # observation coverage caveat: days*slots where no pass observed at all is counted as miss


if __name__ == "__main__":
    main()
