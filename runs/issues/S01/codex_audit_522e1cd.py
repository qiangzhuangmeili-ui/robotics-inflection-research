"""Read-only recheck of S01 rework; emits aggregate results and boundary fixtures."""
import sys,json,hashlib
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))
import s01_rules_check as s
rows,meta,_,_=s.load_rows();latest={}
for (sec,pk),fields in rows.items():
    if any(fields.get(f) and fields[f]['status'] in s.USABLE|s.USABLE_FLAG and fields[f]['value'] is not None for f in ('FIN.REV.YTD','FIN.REV.SQ','FIN.NPDEDT.YTD')):latest[sec]=max(latest.get(sec,0),pk)
l2=Counter();viol=Counter();m1=Counter()
for sec,pk in latest.items():
    rm,_=s.evaluate(rows,meta,sec,pk,stale=pk<s.prior_quarter(max(latest.values())))
    fired=s.signals_of(rows,sec,pk,rm);_,y2,_,_,_=s.layers(fired,rm);l2[y2]+=1;m1[rm['M01']['status']]+=1
    if any(f['id']=='SG02' for f in fired) and rm['M03']['value']<5:viol['SG02_below_documented_5pp']+=1
    for f in fired:
        if f['id']=='SG07' and 'Q06' in rm['M09']['flags'] and 'Q06' not in f['flags']:viol['SG07_missing_M09_Q06']+=1
s.synthetic_tests()
r,m=s._base('SYNTHETIC',rev=(100e6,100e6),gm=(20,20),npdedt=(15e6,15e6),npp=(15e6,15e6),ocf=(15e6,15e6))
rm,_=s.evaluate(r,m,'SYNTHETIC',20260630);rm['M03']=s.res(1,'OK',set())
accel=any(f['id']=='SG02' for f in s.signals_of(r,'SYNTHETIC',20260630,rm))
rm['M03']=s.res(0,'OK',set());rm['M08']=s.res(1,'OK',set());rm['M09']=s.res(10e6,'PROVISIONAL',{'Q06'},20e6,10e6)
combo=[dict(f,flags=sorted(f['flags'])) for f in s.signals_of(r,'SYNTHETIC',20260630,rm) if f['id']=='SG07']
r[('SYNTHETIC',20260630)]['FIN.REV.YTD']['scope']='UNKNOWN'
scope,_=s.evaluate(r,m,'SYNTHETIC',20260630)
result={'companies':len(latest),'L2':dict(l2),'M01':dict(m1),'synthetic_existing_pass':sum(t['result']=='PASS' for t in s.tests),'synthetic_existing_total':len(s.tests),'anonymous_violations':dict(viol),'SG02_1pp_fixture_fired':accel,'SG07_provisional_M09_fixture':combo,'nonlegacy_UNKNOWN_scope_fixture':dict(scope['M01'],flags=sorted(scope['M01']['flags'])),'rules_sha256':hashlib.sha256((ROOT/'runs/issues/S01/screen_rules_v1.json').read_bytes()).hexdigest()}
print(json.dumps(result,ensure_ascii=False,indent=2))
