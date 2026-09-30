"""오너 게이트 시뮬레이션: 최근 30일, 같은 요일군·같은 편(slot)에 표본 4건 이상이면 예측.
예측 = 편 시각(sched_dep) + 창 내 offset 중앙값. 평가일 d 의 실제 UNIST(196040234) 통과와 비교(전진 평가).
"""
import csv, statistics as st
from datetime import date, datetime, timedelta
from collections import defaultdict
rows=[r for r in csv.DictReader(open('runs_logs.csv')) if r['route_id'] in ('196000421','196000422') and r['sched_dep'] and r['t_196040234']]
def m(t): h,mi,*s=t.split(':'); return int(h)*60+int(mi)+(int(s[0])/60 if s else 0)
obs=defaultdict(list)   # (rid, daytype, slot) -> [(date, offset)]
for r in rows:
    off=m(r['t_196040234'])-m(r['sched_dep'])
    if 0<off<150: obs[(r['route_id'],r['daytype'],r['sched_dep'])].append((date.fromisoformat(r['date']),off))
dates=sorted({date.fromisoformat(r['date']) for r in rows}); start=dates[0]
dtype={date.fromisoformat(r['date']):r['daytype'] for r in rows}
def iqr(x):
    q=st.quantiles(x,n=4); return q[2]-q[0]
for rid,name in (('196000421','덕하 출발'),('196000422','삼남 출발')):
  for dt,dn in (('0','평일'),('1','토'),('2','일·공휴일')):
    for guard in (None,10):
      tot=cov=0; errs=[]
      for d in dates:
        if d < start+timedelta(days=30) or dtype.get(d)!=dt: continue
        for (r2,t2,slot),lst in obs.items():
            if r2!=rid or t2!=dt: continue
            actual=[o for (dd,o) in lst if dd==d]
            if not actual: continue
            tot+=1
            win=[o for (dd,o) in lst if d-timedelta(days=30)<=dd<d]
            if len(win)>=4 and (guard is None or iqr(win)<=guard):
                cov+=1; errs.append(abs(st.median(win)-actual[0]))
      if tot:
        errs.sort()
        p=lambda q: errs[min(len(errs)-1,int(q*len(errs)))] if errs else float('nan')
        print(f"{name} {dn:5s} guard={'IQR≤%d'%guard if guard else '없음':6s} 평가편 {tot:4d} 예측가능 {cov/tot:5.0%}  오차 중앙 {p(.5):4.1f} p80 {p(.8):4.1f} p90 {p(.9):4.1f} ±5분 {sum(e<=5 for e in errs)/max(1,len(errs)):4.0%}")
