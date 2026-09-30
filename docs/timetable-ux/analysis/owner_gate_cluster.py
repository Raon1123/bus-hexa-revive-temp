"""오너 게이트 × 통과시각 군집 모델: 최근 30일 같은 요일군의 UNIST 통과 시각을 군집화,
서로 다른 날 4일 이상 나타난 군집만 '예측 통과 시각'으로 채택(중앙값). 평가일 d의 실제 통과와 비교."""
import csv, statistics as st
from datetime import date, timedelta
from collections import defaultdict
rows=[r for r in csv.DictReader(open('runs_logs.csv')) if r['route_id'] in ('196000421','196000422') and r['t_196040234']]
def m(t): h,mi,s=t.split(':'); return int(h)*60+int(mi)+int(s)/60
P=defaultdict(list)  # (rid, date) -> pass minutes
dtype={}
for r in rows:
    d=date.fromisoformat(r['date']); P[(r['route_id'],d)].append(m(r['t_196040234'])); dtype[d]=r['daytype']
dates=sorted(dtype); start=dates[0]
def clusters(pts, gap):
    pts=sorted(pts); out=[]; cur=[pts[0]]
    for p in pts[1:]:
        if p[0]-cur[-1][0] <= gap: cur.append(p)
        else: out.append(cur); cur=[p]
    out.append(cur); return out
for rid,name in (('196000421','덕하 출발→UNIST'),('196000422','삼남 출발→UNIST')):
  for dt,dn in (('0','평일'),('1','토'),('2','일·공휴일')):
    errs=[]; tot=0; nclu=[]; spur=0; ncent=0
    for d in dates:
        if d < start+timedelta(days=30) or dtype[d]!=dt or not P.get((rid,d)): continue
        win=[(t,dd) for dd in dates if d-timedelta(days=30)<=dd<d and dtype[dd]==dt for t in P.get((rid,dd),[])]
        if not win: continue
        cents=[st.median([t for t,_ in c]) for c in clusters(win,4) if len({dd for _,dd in c})>=4]
        nclu.append(len(cents))
        actual=P[(rid,d)]
        for a in actual:
            tot+=1
            if cents: errs.append(min(abs(a-c) for c in cents))
        # 실제로 안 온 예측(±8분 내 실제 통과 없음)
        ncent+=len(cents); spur+=sum(1 for c in cents if not any(abs(a-c)<=8 for a in actual))
    if not tot: continue
    errs.sort(); q=lambda x: errs[min(len(errs)-1,int(x*len(errs)))] if errs else float('nan')
    print(f"{name} {dn:6s} 평가일 {len(nclu):2d} 채택 군집/일 {st.median(nclu) if nclu else 0:4.1f}  실제통과 {tot:4d}  최근접오차 중앙 {q(.5):4.1f} p80 {q(.8):4.1f} p90 {q(.9):4.1f} ±5분 {sum(e<=5 for e in errs)/max(1,tot):4.0%}  헛예측 {spur/max(1,ncent):4.0%}")
