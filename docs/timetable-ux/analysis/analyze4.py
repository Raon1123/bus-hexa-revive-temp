"""(read-only) inbound-to-UNIST routes: raw origin appearance -> UNIST & upstream segment times."""
import csv
from collections import defaultdict
from analyze import REPO, parse_ts, summ
R = list(csv.DictReader(open('runs_logs.csv', encoding='utf-8')))
def mins(s):
    h, m, sec = map(int, s.split(':')); return h*60+m+sec/60
print("## 기점출현 → UNIST (raw, 전체 요일)")
for rid, tgt in (('195000177','196040232'),('195000215','196040232'),('195000221','196040232'),('194000106','999000145')):
    xs=[mins(r['t_'+tgt])-mins(r['t_origin']) for r in R if r['route_id']==rid and r['t_origin'] and r.get('t_'+tgt)]
    xs=[x for x in xs if 0<x<180]
    print(f"  {rid} -> {tgt}: {summ(xs)}")
rows=defaultdict(list)
with (REPO/'logs/logs.tsv').open(encoding='utf-8') as f:
    rd=csv.reader(f,delimiter='\t'); next(rd)
    for rec in rd:
        if len(rec)>=4 and rec[2] in ('195000177','195000215','195000221','194000106'):
            rows[(rec[2],rec[3])].append((parse_ts(rec[0]),rec[1]))
print("## 상류 정류장 → UNIST 구간 (실시간 ETA 근거)")
for rid, ups, tgt in (('195000177',['193040224','196020808','196040212'],'196040232'),
                      ('195000215',['193040224','196020808'],'196040232'),
                      ('195000221',['193040224','196020416','196040212'],'196040232'),
                      ('194000106',['193040224','196020808'],'999000145')):
    for up in ups:
        xs=[]
        for (r_,v),obs in rows.items():
            if r_!=rid: continue
            obs.sort()
            for i,(t,s) in enumerate(obs):
                if s!=up: continue
                for t2,s2 in obs[i+1:]:
                    if (t2-t).total_seconds()>3600 or s2==up: break
                    if s2==tgt: xs.append((t2-t).total_seconds()/60); break
        xs=[x for x in xs if 0<x<90]
        print(f"  {rid} {up}->{tgt}: {summ(xs)}")
