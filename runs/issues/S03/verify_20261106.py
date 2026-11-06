"""Parent technical check, independent of screening execution; no writes to source inputs."""
import csv,json,hashlib
from collections import Counter
from pathlib import Path
R=Path(__file__).resolve().parents[3];O=R/'runs/issues/S03/rerun_20261106'
def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(name,rows,fields=None):
    fields=fields or list(rows[0])
    with (O/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)
cfg=json.loads((R/'runs/issues/S03/l1_config.json').read_text(encoding='utf-8'))
contract=json.loads((R/'runs/issues/S02/acceptance_20261106/s03_input_contract.json').read_text(encoding='utf-8'))
snap=json.loads((R/contract['snapshot']).read_text(encoding='utf-8'))
guard={r['security_id'] for r in contract['guard_companies']}
rows=read(O/'l1_screen_results.csv');old=read(R/'runs/issues/S03/l1_screen_results.csv')
prior={r['company_id']:r for r in old};by={r['company_id']:r for r in rows}
master=read(R/'data/company_master.csv');assigned={r['security_id'] for r in master}
checks=[]
def check(name,ok,detail=None):checks.append(dict(name=name,pass_check=bool(ok),detail=detail))
check('1054 unique rows and exact master keys',len(rows)==len(by)==1054 and set(by)==assigned)
check('Cutoff guard has four distinct companies',len(guard)==4 and guard<=set(by))
leaks=[]
for s in guard:
    r=by[s]
    if r['l1_bucket']!='OBSERVE_QUEUE' or r['l1_subtag']!='WATCH_AFTER_CUTOFF' or r['s04_review_priority']!='WATCH_AFTER_CUTOFF':leaks.append(s+':route')
    for k in ('sg_hit_clean_list','sg_hit_provisional_list','sg_hit_lowbase_list','sg_hit_all_list','rh_hit_list','sg_hold_list','sg_blocked_would_fire','rh_blocked_would_fire'):
        if r[k]:leaks.append(s+':'+k)
    for k in ('clean_ok_dims_count','total_potential_dims_count','hold_dims_count'):
        if int(r[k])!=0:leaks.append(s+':'+k)
    if r['anchor_period']!=prior[s]['anchor_period']:leaks.append(s+':silent_fallback')
check('Cutoff company routes and zero signal/dimension leakage',not leaks,leaks)
diff=[s for s in set(by)-guard if by[s]!=prior[s]]
check('Other 1050 company rows unchanged in every field',not diff,dict(compared=len(by)-len(guard),differences=diff))
inputs={}
for key in ('normalized_input','metrics','company_summary','review'):
    p=R/snap[key]['path'];inputs[key]=sha(p)==snap[key]['sha256']
check('Four frozen S02 input/output files unmodified',all(inputs.values()),inputs)
pass_rows=[];unknown=[];defer=[]
unknown_subtags={'WATCH_AFTER_CUTOFF','OQ_PROVISIONAL_ONLY','OQ_LOW_BASE_PROVISIONAL','OQ_HOLD_PROTECTED','NS_INCOMPLETE_EVIDENCE','RW_HAS_HOLD'}
for r in rows:
    if r['l1_subtag'].startswith(('REF_ONLY_','L0_')) or r['l1_subtag'] in unknown_subtags:unknown.append(r)
    elif r['l1_subtag']=='OQ_CLEAN_OK':pass_rows.append(r)
    else:defer.append(r)
partkeys=[{r['company_id'] for r in p} for p in (pass_rows,defer,unknown)]
check('Three delivery partitions cover 1054 without overlap',set.union(*partkeys)==assigned and sum(map(len,partkeys))==1054)
check('All cutoff companies remain in unknown partition',guard<=partkeys[2])
confirmed=[r for r in rows if r['l1_subtag']=='NS_CONFIRMED']
check('Only explicitly confirmed no-signal rows in defer',all(r['company_id'] in partkeys[1] for r in confirmed))
targets=read(O/'s04_review_targets.csv')
check('Cutoff companies absent from S04 verification targets',not (guard & {r['company_id'] for r in targets}))
report=dict(review_nature='SELF_CHECK_PARENT_VERIFICATION_NOT_INDEPENDENT_BUSINESS_AUDIT',checks=checks,pass_all=all(c['pass_check'] for c in checks),universe=len(rows),bucket_counts=dict(Counter(r['l1_bucket'] for r in rows)),subtag_counts=dict(Counter(r['l1_subtag'] for r in rows)),priority_counts=dict(Counter(r['s04_review_priority'] for r in rows)),partitions=dict(wide_pass=len(pass_rows),wide_defer=len(defer),wide_unknown=len(unknown)),partition_semantics=dict(wide_pass='Clean signal observation; not investment candidate or L2 acceptance',wide_defer='Complete no-signal or clean risk-watch; retained, not deleted',wide_unknown='Uncertain/provisional/low-base/hold/scope/cutoff observation; no final rejection'),s04_review_targets=len(targets),outputs={})
for name,p in [('wide_pass.csv',pass_rows),('wide_defer.csv',defer),('wide_unknown.csv',unknown)]:
    dump(name,p,list(rows[0]));report['outputs'][name]=dict(rows=len(p),sha256=sha(O/name))
(O/'parent_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
(O/'wide_summary.json').write_text(json.dumps({k:v for k,v in report.items() if k!='checks'},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True,indent=2));raise SystemExit(0 if report['pass_all'] else 2)
