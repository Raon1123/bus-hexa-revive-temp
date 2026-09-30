"""Anchor-free: cluster observed pass times-of-day at a stop across weekdays (read-only)."""
import csv, json, statistics as st, sys
from collections import defaultdict
from analyze import REPO, parse_ts, daytype
rid, stop, org = sys.argv[1], sys.argv[2], sys.argv[3]
dgroup = sys.argv[4] if len(sys.argv) > 4 else "0"
tt = json.loads((REPO/"data/timetable/513.json").read_text())
seen = set(); pts = []; days=set()
with (REPO/"logs/logs.tsv").open(encoding="utf-8") as f:
    r = csv.reader(f, delimiter="\t"); next(r)
    for rec in r:
        if len(rec)<4 or rec[2]!=rid or rec[1]!=stop: continue
        t = parse_ts(rec[0])
        if daytype(t.date()) not in dgroup: continue
        key=(t.date(),rec[3],t.hour*60+t.minute)
        pts.append(t.hour*60+t.minute+t.second/60); days.add(t.date())
pts.sort()
cl=[[pts[0]]]
for p in pts[1:]:
    if p-cl[-1][-1] > 4: cl.append([p])
    else: cl[-1].append(p)
nd=len(days)
print(f"# {rid} stop={stop} daytype in {dgroup}: days={nd} passes={len(pts)} clusters={len(cl)}")
sched=[int(h)*60+int(m) for h,m in (x.split(':') for x in tt[dgroup[0]][org])]
for c in cl:
    if len(c) < max(3, nd*0.2):
        print(f"   (minor) {int(st.median(c))//60:02d}:{int(st.median(c))%60:02d} n={len(c)}")
        continue
    med=st.median(c); 
    prev=[s for s in sched if s<=med]
    D=prev[-1] if prev else None
    print(f"{int(med)//60:02d}:{int(med)%60:02d}  n={len(c):3d} ({len(c)/nd:4.0%} of days) span=[{int(c[0])//60:02d}:{int(c[0])%60:02d},{int(c[-1])//60:02d}:{int(c[-1])%60:02d}]  IQR={st.quantiles(c,n=4)[2]-st.quantiles(c,n=4)[0]:.1f}m  latest sched<= : {D//60:02d}:{D%60:02d} (+{med-D:.0f}m)" if D else f"{med}")
