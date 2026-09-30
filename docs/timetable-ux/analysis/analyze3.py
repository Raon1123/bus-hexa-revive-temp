"""(read-only) 513: dispatch-anchored model & empirical UNIST-pass timetable, LODO evaluation."""
import csv, datetime as dt, statistics as st
from collections import defaultdict
from analyze import REPO, parse_ts, daytype, q, summ, hour_bucket
R = list(csv.DictReader(open('runs_logs.csv', encoding='utf-8')))
def mins(s):
    h, m, sec = map(int, s.split(':')); return h*60+m+sec/60
grp = lambda d: 'wd' if d == '0' else 'we'
print("## A) 기점 출현(=실제 배차 추정) → 196040234 소요, 시간대별 (n_obs>=5, 0<x<150)")
for rid in ('196000421', '196000422'):
    rr = [r for r in R if r['route_id'] == rid and r['t_origin'] and r['t_196040234']]
    for g in ('wd', 'we'):
        for hb in ('05-06', '07-09', '10-16', '17-19', '20-22'):
            xs = [mins(r['t_196040234'])-mins(r['t_origin']) for r in rr if grp(r['daytype']) == g
                  and hour_bucket(int(r['t_origin'][:2])) == hb]
            xs = [x for x in xs if 0 < x < 150]
            print(f"  {rid} {g} {hb}: {summ(xs)}")
    # LODO error, key=(group, hour of dispatch)
    data = [(r, mins(r['t_196040234'])-mins(r['t_origin'])) for r in rr]
    data = [(r, x) for r, x in data if 0 < x < 150]
    for name, keyf in (("(요일군,출발시각 1h)", lambda r: (grp(r['daytype']), r['t_origin'][:2])),
                       ("(요일군,시간대5구간)", lambda r: (grp(r['daytype']), hour_bucket(int(r['t_origin'][:2]))))):
        errs = []
        for r, x in data:
            pool = [y for s, y in data if s['date'] != r['date'] and keyf(s) == keyf(r)]
            if len(pool) >= 5: errs.append(x - st.median(pool))
        ab = [abs(e) for e in errs]
        print(f"  LODO {rid} {name}: n={len(ab)} medAE={st.median(ab):.1f} MAE={st.mean(ab):.1f} p90AE={q(ab,.9):.1f} "
              f"|e|<=3 {sum(a<=3 for a in ab)/len(ab):.0%} <=5 {sum(a<=5 for a in ab)/len(ab):.0%}")

print("\n## B) 이력 기반 'UNIST 통과 시간표'(요일군별 클러스터 중앙값) LODO: 관측 통과 ↔ 최근접 예측 거리")
passes = defaultdict(lambda: defaultdict(list))  # rid -> date -> [min]
with (REPO/'logs/logs.tsv').open(encoding='utf-8') as f:
    rd = csv.reader(f, delimiter='\t'); next(rd)
    for rec in rd:
        if len(rec) >= 4 and rec[2] in ('196000421', '196000422') and rec[1] == '196040234':
            t = parse_ts(rec[0]); passes[rec[2]][t.date()].append(t.hour*60+t.minute+t.second/60)
def clusters(pts, nd, gap=4, minfrac=0.2):
    pts = sorted(pts); out = []; cur = [pts[0]]
    for p in pts[1:]:
        if p - cur[-1] > gap: out.append(cur); cur = [p]
        else: cur.append(p)
    out.append(cur)
    return [st.median(c) for c in out if len(c) >= max(3, nd*minfrac)]
for rid in ('196000421', '196000422'):
    for g in ('wd', 'we'):
        days = [d for d in passes[rid] if grp(daytype(d)) == g]
        dists = []; ncl = []
        for d in days:
            others = [x for o in days if o != d for x in passes[rid][o]]
            cl = clusters(others, len(days)-1); ncl.append(len(cl))
            for p in passes[rid][d]:
                dists.append(min(abs(p-c) for c in cl))
        print(f"  {rid} {g}: days={len(days)} clusters/일≈{st.median(ncl)} passes={len(dists)} medAE={st.median(dists):.1f} "
              f"p90AE={q(dists,.9):.1f} <=3 {sum(x<=3 for x in dists)/len(dists):.0%} <=5 {sum(x<=5 for x in dists)/len(dists):.0%}")
