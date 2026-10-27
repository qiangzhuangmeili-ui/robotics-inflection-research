"""Read-only recomputation of A04 inputs; writes only this issue's audit outputs."""
import csv, json, hashlib, re
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
inputs = {}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    p = ROOT / p; inputs[p.relative_to(ROOT).as_posix()] = sha(p)
    return json.loads(p.read_text(encoding='utf-8-sig'))
def rows(p):
    p = ROOT / p; inputs[p.relative_to(ROOT).as_posix()] = sha(p)
    with p.open(encoding='utf-8-sig', newline='') as f: return list(csv.DictReader(f))
def write(p, d): (OUT/p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def csvout(p, rs, keys):
    with (OUT/p).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rs)

scope=read('runs/issues/P00/collection_scope.json')
rules=read('runs/issues/P00/coverage_acceptance_rules.json')
fp=read('runs/issues/P00/universe_fingerprint.json')
master=rows('data/company_master.csv'); ids={r['security_id'] for r in master}
canonical='\n'.join('\t'.join(r[k] for k in ['security_id','stock_code','stock_name','exchange']) for r in sorted(master,key=lambda r:r['security_id']))+'\n'
roster_hash=hashlib.sha256(canonical.encode()).hexdigest()
queue=rows('data/intake_company_queue.csv'); batches=rows('data/intake_batch_index.csv')
assign=[]; batch_checks=[]
for b in batches:
    rr=rows(b['assignment_path']);assign+=rr
    batch_checks.append({'batch_id':b['batch_id'],'expected':int(b['company_count']),'actual':len(rr),'pass':len(rr)==int(b['company_count'])})
ledger=rows('runs/collection/collection_index.csv')
registry=rows('data/document_registry.csv')
listing={r['security_id']:r for r in rows('data/company_listing_dates.csv')}
status=Counter(r['status'] for r in ledger); pairs=Counter((r['security_id'],r['slot_id']) for r in ledger)
verified=[r for r in ledger if r['status']=='COLLECTED_IDENTITY_VERIFIED']
slotdefs=scope['report_slots']+scope['quarterly_slots']
missing=Counter(); coverage=[]
for s in slotdefs:
    rr=[r for r in ledger if r['slot_id']==s['slot_id']]
    absent=sum((i,s['slot_id']) not in pairs for i in ids)
    missing[s['slot_id']]=absent
    coverage.append({'slot_id':s['slot_id'],'frozen_pool':len(ids),'ledger_rows':len(rr),'absent_from_ledger':absent,'as_of_cutoff_status':s.get('as_of_cutoff_status','APPLICABLE'),'note':'ABSENT_NOT_A_COMPLETED_TERMINAL' if absent else 'LEDGER_PRESENT'})
csvout('frozen_scope_coverage.csv',coverage,list(coverage[0]))
na=[r for r in ledger if r['status']=='NOT_APPLICABLE_PRE_LISTING']
na_no_date=[r for r in na if listing.get(r['security_id'],{}).get('listing_date','') in ('','UNKNOWN')]
unknown_dates=[r for r in verified if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',r['published_on'])]
late=[r for r in verified if r not in unknown_dates and r['published_on']>scope['time_axis']['knowledge_as_of']]
csvout('cutoff_hold.csv',[{k:r[k] for k in ['security_id','slot_id','document_id','published_on','primary_url']} for r in unknown_dates+late],['security_id','slot_id','document_id','published_on','primary_url'])
local_missing=[r for r in verified if not (ROOT/r['local_file']).is_file()]
trace_missing=[r for r in verified if not all(r.get(k) for k in ['document_id','primary_url','sha256','local_file'])]
checkpoint_index_types=Counter()
for p in sorted((ROOT/'runs/collection/checkpoint').glob('*.json')):
    d=read(p.relative_to(ROOT).as_posix());checkpoint_index_types.update(d.get('indexes',{}).keys())
fields=rows('runs/issues/A03/financial_fields_extracted_annual_full.csv')
diag=rows('runs/issues/A03/extraction_diagnostics_annual_full.csv')
quality=rows('runs/issues/A03/field_quality_check_annual_full.csv')
dictionary=rows('runs/issues/P04/financial_field_dictionary.csv')
agg=defaultdict(set)
for r in fields: agg[(r['document_id'],r['slot_id'],r['field_id'])].add(r['extract_status'])
field_docs={r['document_id'] for r in fields};diagnostic_docs={r['document_id'] for r in diag}
fieldcounts=defaultdict(Counter)
for (_,_,fid),sts in agg.items():
    fieldcounts[fid]['EXTRACTED_ANY' if 'EXTRACTED' in sts else ('NEUTRAL_UNKNOWN' if sts<={'NOT_IN_STATEMENT','BLANK_IN_STATEMENT','NOT_APPLICABLE'} else 'FAILED_OR_REVIEW')]+=1
usable=[]
for f in dictionary:
    c=fieldcounts[f['field_id']]
    usable.append({'field_id':f['field_id'],'name_cn':f['name_cn'],'p00_required':f['p00_required'],'annual_documents_with_any_value':c['EXTRACTED_ANY'],'neutral_unknown':c['NEUTRAL_UNKNOWN'],'failed_or_review':c['FAILED_OR_REVIEW'],'denominator_field_documents':len(field_docs),'denominator_annual_identity_verified':sum(r['slot_id'].startswith('annual_') for r in verified),'gate':'HOLD_PENDING_COMPARABILITY','limits':'EXTRACTED_ANY does not prove four quarters complete; missing is not zero; H1/quarter extraction unrun; same currency/unit/consolidation/version and quality checks required'})
csvout('usable_fields_and_limits.csv',usable,list(usable[0]))
checks=[
 {'id':'AC01','result':'PASS' if len(ids)==1054 and roster_hash==fp['canonical_form']['canonical_sha256'] else 'FAIL','evidence':{'count':len(ids),'canonical_sha256':roster_hash}},
 {'id':'AC02','result':'PASS' if all(b['pass'] for b in batch_checks) else 'FAIL','evidence':batch_checks},
 {'id':'AC03','result':'PASS' if len(assign)==len(ids) and {r['security_id'] for r in assign}==ids and {r['security_id'] for r in queue}==ids else 'FAIL','evidence':'assignment and queue set equality'},
 {'id':'AC04','result':'FAIL','evidence':{'duplicate_existing_pairs':sum(v>1 for v in pairs.values()),'frozen_report_slots_absent':dict(missing),'reason':'7-slot implementation does not cover frozen 12 report-slot definitions; deadline-not-yet-due slots need explicit terminal decisions, not assumed downloads'}},
 {'id':'AC05','result':'FAIL','evidence':{'not_tried_in_existing_7_slot_ledger':status['NOT_TRIED'],'missing_predeadline_quarter_slots':sum(missing[s['slot_id']] for s in scope['quarterly_slots'] if s['deadline_before_cutoff']),'reason':'absent slots have no terminal disposition; cannot report full-round NOT_TRIED=0'}},
 {'id':'AC06','result':'PASS' if not na_no_date else 'FAIL','evidence':{'na_rows':len(na),'without_listing_side_table_date':len(na_no_date),'limit':'date/source presence check; no new independent original-source verification'}},
 {'id':'AC07','result':'PASS' if not trace_missing else 'FAIL','evidence':{'verified':len(verified),'missing_trace_fields':len(trace_missing),'local_missing':len(local_missing),'limit':'metadata and local-file presence; not fresh binary hash or business review'}},
 {'id':'AC08','result':'PASS' if status['SOURCE_FAILED']==0 else 'HOLD','evidence':{'source_failed':status['SOURCE_FAILED'],'scope':'existing ledger only; omitted scope untested'}},
 {'id':'AC09','result':'PASS','evidence':{'manual_receipts':len(rows('runs/issues/A03/manual_intake_receipts.csv')),'historical_closures':len(rows('runs/issues/A03/historical_request_closure.csv')),'new_requests_this_audit':0}},
 {'id':'AC10','result':'FAIL' if late else ('HOLD' if unknown_dates else 'PASS'),'evidence':{'known_after_cutoff_in_existing_ledger':len(late),'unknown_disclosure_date':len(unknown_dates),'cutoff':scope['time_axis']['knowledge_as_of'],'hold_register':'cutoff_hold.csv'}}
]
gaps=[
 ('A04-G01','P05/P07 -> M00/A00/A01','BLOCKS_A04_RELEASE','4216 predeadline quarterly slots absent; 1054 Q3_2026 slots need cutoff-aware disposition','Extend automatic scope and reuse checkpoints; log explicit applicability/cutoff terminals. Do not dispatch manual requests.'),
 ('A04-G02','P05/P07 -> M00/A00','BLOCKS_A04_RELEASE','P00 two-year announcement/IR, keyword originals and correction/version linkage not demonstrated by three regular-report index categories','Reconcile full frozen supplementary scope, pagination and revision evidence; do not equate regular-report indexes with full announcement coverage.'),
 ('A04-G03','A03/P04','HOLD_AFFECTED_FIELDS','3082 diagnostics vs 3081 documents with field rows; H1/quarter extraction unrun; restatement, units and crosschecks pending','Account for image-only failure denominator; repair extractor/mapping; preserve field-level HOLD, no zero fill.'),
 ('A04-G04','P06 archive follow-up','OPEN_ARCHIVE_LIMIT','7158 identity-verified ledger documents lack verified Drive archive receipts','Preserve local originals; use connected Drive when available; no new cloud verification claimed by this audit.'),
 ('A04-G05','P01/A03','OPEN_REGISTRY_VERSION_LIMIT','7162 ledger document IDs absent from registry; same-file two IDs and different-binary same-slot crosswalks retained','Reconcile canonical IDs and version lineage reversibly, do not overwrite originals.'),
 ('A04-G06','A00 scheduling bookkeeping','OPEN_CONTROL_LIMIT','intake_batch_index and intake_company_queue retain planned/not-started historical values','Reconcile derived status views against actual checkpoints without resetting verified results.'),
 ('A04-G07','P01/A03','HOLD_AFFECTED_DOCUMENTS','7 verified documents have UNKNOWN disclosure date; no known post-cutoff documents found','Resolve actual official disclosure date before evidence adoption; UNKNOWN does not mean after-cutoff.'),
 ('A04-G08','A03 handoff erratum','OPEN_DOCUMENTATION_LIMIT','remaining_gaps.csv contains 1754 rows, not the 226 claimed in handoff section 4','Use 155 document + 71 dedup + 1528 field rows; retain old handoff and attach correction here.')
]
owners=[dict(zip(['gap_id','owner','gate','finding','next_action'],g)) for g in gaps]
csvout('remaining_gap_owners.csv',owners,list(owners[0]))
result={'issue_key':'A04','issue_number':34,'plan_version':scope['plan_version'],'generated_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),'review_nature':'SELF_CHECK','decision':'RETURN_FOR_REWORK','release_S00':False,'reason':'P00 full frozen scope has unaccounted slots and supplementary scope; no relaxation of frozen standards','checks':checks,'implemented_ledger':{'companies':len(ids),'rows':len(ledger),'statuses':dict(status),'local_missing':len(local_missing),'archive_verified':sum(r['archive_status']=='VERIFIED' for r in verified),'checkpoint_index_types':dict(checkpoint_index_types)},'field_recomputation':{'raw_rows':len(fields),'raw_extracted_rows':sum(r['extract_status']=='EXTRACTED' for r in fields),'diagnostic_documents':len(diagnostic_docs),'documents_with_field_rows':len(field_docs),'diagnostic_documents_without_field_rows':sorted(diagnostic_docs-field_docs),'field_document_pairs':len(agg),'any_extracted_pairs':sum(c['EXTRACTED_ANY'] for c in fieldcounts.values()),'field_rows_status':dict(Counter(r['extract_status'] for r in fields)),'quality_unit':dict(Counter(r['unit_consistent'] for r in quality))},'limits':['Existing P00-A03 self-check decisions preserved; this is a new A04 gate decision.','No new official-source original, binary hash or business evidence verification.','P07 65 archive receipts remain historical; no live Drive probe performed here.','Rejected release does not mean obtained documents are unusable; comparable normalization may start only after gate repair.']}
write('intake_acceptance.json',result)
write('input_fingerprints.json',inputs)
print(json.dumps({'decision':result['decision'],'ledger':result['implemented_ledger'],'fields':result['field_recomputation'],'checks':{c['id']:c['result'] for c in checks}},ensure_ascii=False,indent=2))
