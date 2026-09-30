import csv, json, statistics as st
from collections import defaultdict
R=list(csv.DictReader(open('runs_logs.csv',encoding='utf-8')))
TGT={'196000421':'196040234','196000422':'196040234','195000177':'196040232','195000215':'196040232','195000221':'196040232','194000106':'999000145'}
BUS={'196000421':('513','덕하'),'196000422':('513','삼남'),'195000177':('713','명촌'),'195000215':('743','명촌'),'195000221':('753','명촌'),'194000106':('1115','꽃바위')}
def q(xs,p):
    xs=sorted(xs); k=(len(xs)-1)*p; f=int(k); c=min(f+1,len(xs)-1); return xs[f]+(xs[c]-xs[f])*(k-f)
def band(h):
    return '05-06' if h<7 else '07-09' if h<10 else '10-16' if h<17 else '17-19' if h<20 else '20-23'
repo='/home/mlv/project/bushexa/bus-hexa-revive-temp/data/timetable/'
GATES={'G_strict':dict(n=12,days=8,iqr=8,p80=6),'G_mid':dict(n=8,days=6,iqr=10,p80=8),'G_plan':dict(n=30,days=0,iqr=15,p80=999)}
for rid,tg in TGT.items():
    bus,orig=BUS[rid]
    tt=json.load(open(repo+bus+'.json',encoding='utf-8'))
    for dty in ('0',):
        slots=tt[dty][orig] if dty in tt else tt[int(dty)][orig]
        data=defaultdict(list)
        for r in R:
            if r['route_id']==rid and r['daytype']==dty and r['sched_dep'] and r['travel_'+tg]!='':
                x=float(r['travel_'+tg])
                if 0<x<150: data[r['sched_dep']].append((r['date'],x))
        bdata=defaultdict(list)
        for s,v in data.items(): bdata[band(int(s[:2]))]+=v
        res={g:{'slot':0,'band':0} for g in GATES}
        rows=[]
        for s in slots:
            v=data.get(s,[])
            xs=[x for _,x in v]; days=len({d for d,_ in v})
            errs=[]
            for d,x in v:
                pool=[y for d2,y in v if d2!=d]
                if len(pool)>=3: errs.append(abs(x-st.median(pool)))
            iqr=(q(xs,.75)-q(xs,.25)) if len(xs)>=4 else 99
            p80=q(errs,.8) if len(errs)>=4 else 99
            rows.append((s,len(xs),days,round(st.median(xs),1) if xs else None,round(iqr,1),round(p80,1)))
            bv=bdata[band(int(s[:2]))]; bxs=[x for _,x in bv]
            berr=[]
            for d,x in bv:
                pool=[y for d2,y in bv if d2!=d]
                if len(pool)>=3: berr.append(abs(x-st.median(pool)))
            biqr=(q(bxs,.75)-q(bxs,.25)) if len(bxs)>=4 else 99; bp80=q(berr,.8) if len(berr)>=4 else 99
            for g,c in GATES.items():
                ok=len(xs)>=c['n'] and days>=c['days'] and iqr<=c['iqr'] and p80<=c['p80']
                if ok: res[g]['slot']+=1
                elif len(bxs)>=c['n'] and biqr<=c['iqr'] and bp80<=c['p80']: res[g]['band']+=1
        print(f"{rid} {bus} {orig}발 평일 JSON편 {len(slots)}: "+"; ".join(f"{g}: slot {v['slot']} +band {v['band']} / fallback {len(slots)-v['slot']-v['band']}" for g,v in res.items()))
        if bus=='513':
            for r in rows: print('   ',r)
