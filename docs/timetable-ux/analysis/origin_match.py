"""For each direction, compare observed origin-appearance times (weekday) to JSON timetable (read-only).
Metric: fraction of JSON weekday slots with an observed origin appearance within +-3 min on each day,
averaged over weekdays (per-day matching, not pooled clusters)."""
import csv, json, statistics as st
from collections import defaultdict
from analyze import REPO, parse_ts, daytype
DIRS = {"196000421": ("513","덕하","196040142"), "196000422": ("513","삼남","196015417"),
        "195000177": ("713","명촌","999000149"), "195000178": ("713","UNIST","196040233"),
        "195000215": ("743","명촌","999000149"), "195000216": ("743","UNIST","196040233"),
        "195000221": ("753","명촌","999000149"), "195000222": ("753","UNIST","196040233"),
        "194000106": ("1115","꽃바위","194019014"), "194000107": ("1115","UNIST","196040233")}
obs = defaultdict(lambda: defaultdict(list))
with (REPO/"logs/logs.tsv").open(encoding="utf-8") as f:
    r = csv.reader(f, delimiter="\t"); next(r)
    for rec in r:
        if len(rec) < 4 or rec[2] not in DIRS or rec[1] != DIRS[rec[2]][2]: continue
        t = parse_ts(rec[0]); obs[rec[2]][t.date()].append(t.hour*60+t.minute+t.second/60)
for rid,(bus,col,stop) in DIRS.items():
    tt = json.loads((REPO/f"data/timetable/{bus}.json").read_text())
    for dgroup,label in (("0","평일"),("12","주말휴일")):
        rates=[]; offs=[]; nobs=[]
        for day, ts in obs[rid].items():
            dty = daytype(day)
            if dty not in dgroup: continue
            sched = [int(x[:2])*60+int(x[3:]) for x in tt[dty][col]]
            if len(ts) < len(sched)*0.5: continue   # skip days with poor origin coverage
            hit = sum(1 for s in sched if any(abs(t-s) <= 3 for t in ts))
            rates.append(hit/len(sched)); nobs.append(len(ts))
            for t in ts:
                d = min(sched, key=lambda s: abs(t-s)); offs.append(t-d)
        if rates:
            within1 = sum(1 for o in offs if abs(o)<=1.5)/len(offs)
            print(f"{bus:>4} {rid} {col}출발 {label}: days={len(rates):2d} 기점관측/일 med={st.median(nobs):.0f} (시간표 {len(sched)}편) "
                  f"| 시간표 편 중 ±3분 내 기점출현 비율 med={st.median(rates):.0%} | 기점출현-최근접편 |Δ|<=1.5분 {within1:.0%}")
