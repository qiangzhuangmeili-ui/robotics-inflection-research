"""Reproduce frozen v2 CSV artifacts with committed production scripts."""
from pathlib import Path
import gzip,hashlib,json,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 committed=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
 scripts=['tools/s02_calculate.py','tools/s03_input_gate.py','tools/s01_rules_check.py','tools/l0_classify.py','tools/a03_financial_field_extractor.py']
 code={};committed_bytes={}
 for s in scripts:
  blob=subprocess.check_output(['git','show','HEAD:'+s],cwd=ROOT)
  exact=hashlib.sha256(blob).hexdigest()==sha(ROOT/s)
  working=(ROOT/s).read_bytes()
  eol_only=working.replace(b'\r\n',b'\n')==blob.replace(b'\r\n',b'\n')
  assert exact or (s=='tools/s01_rules_check.py' and eol_only and sha(ROOT/s)=='134d0feeb2aff67f1a6ab9df0a08a8d96c6a64a294df17382e06e5cd4964470f'),s+' differs from committed source content'
  committed_bytes[s]=dict(git_blob_sha256=hashlib.sha256(blob).hexdigest(),working_sha256=sha(ROOT/s),exact_bytes=exact,pure_line_ending_equivalence=not exact and eol_only)
  code[s]=sha(ROOT/s)
 r=ROOT/'runs/issues/S02/remediation_20261029';canonical={n:sha(r/'s02'/n) for n in ['all_pool_metrics.csv','company_metric_summary.csv']}
 copy=OUT/'reproduction/copy_input/financial_normalized.csv'
 copy.parent.mkdir(parents=True,exist_ok=True)
 with gzip.open(r/'s00/financial_normalized.csv.gz','rb') as src,copy.open('wb') as dst:shutil.copyfileobj(src,dst)
 variants=[('csv_copy',copy),('gzip',r/'s00/financial_normalized.csv.gz')]
 runs=[]
 for name,p in variants:
  out=OUT/'reproduction'/name
  cmd=[sys.executable,str(ROOT/'tools/s02_calculate.py'),'--normalized',str(p),'--rules',str(r/'rules_recalculation_inputs.json'),'--out-dir',str(out)]
  proc=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
  (OUT/f'reproduction_{name}.log').write_text(proc.stdout+proc.stderr,encoding='utf-8')
  assert proc.returncode==0,proc.stdout+proc.stderr
  matches={n:sha(out/n)==h for n,h in canonical.items()};assert all(matches.values()),matches
  m=json.loads((out/'calculation_manifest.json').read_text(encoding='utf-8'))
  assert m['execution_sources']['calculator']['sha256']==code['tools/s02_calculate.py']
  assert m['l0_addendum']['applied'] is True
  runs.append(dict(mode=name,command=cmd,input_source_sha256=sha(p),manifest_path=(out/'calculation_manifest.json').relative_to(ROOT).as_posix(),manifest_sha256=sha(out/'calculation_manifest.json'),canonical_csv_byte_matches=matches,outputs={n:sha(out/n) for n in canonical},execution_sources=m['execution_sources'],l0_distribution=m['l0_distribution']))
 result=dict(status='PASS_COMMITTED_CONTENT_EXACT_OUTPUT_REPRODUCTION',source_commit=committed,source_sha256=code,committed_source_bytes=committed_bytes,canonical_metric_cells=12648,canonical_csv_sha256=canonical,runs=runs,scope='Exact byte reproduction of metric and company-summary CSVs. Historical canonical manifest is preserved; new execution manifests record script hashes and original/cached input identities. The legacy S01 engine has a verified pure LF/CRLF Git/worktree difference, explicitly recorded. This is not independent financial-source verification.')
 (OUT/'reproduction_manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in result.items() if k!='runs'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
