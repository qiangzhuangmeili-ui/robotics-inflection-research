"""Create a bounded review archive, excluding runtime and duplicate large caches."""
import argparse,hashlib,json,zipfile
from datetime import datetime,timezone,timedelta
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output-version',required=True);args=ap.parse_args()
 version=Path(args.output_version).resolve();assert version.parent==HERE/'integration'
 assert (version/'recovery18_manifest.json').exists()
 assert json.loads((version/'source_adoption_check.json').read_text(encoding='utf-8'))['decision']=='PASS'
 files=[]
 for p in HERE.rglob('*'):
  if not p.is_file():continue
  rel=p.relative_to(HERE);parts=rel.parts
  if 'ocr_runtime' in parts or '__pycache__' in parts or '.input_cache' in parts:continue
  if p.name in ('package_manifest.json','drive_receipt.json','probe_ocr.ps1'):continue
  if p.name=='financial_normalized.csv' or p.name.endswith('_text.json'):continue
  if 'integration' in parts and len(parts)>1:
   second=parts[1]
   if second.startswith('v3_') and p not in version.rglob('*'):continue
   if second.startswith('s02_replay') and second!='s02_replay_v3_run2':continue
   if second.startswith('s02_replay') and p.suffix in ('.csv','.gz'):continue
  # Preserve selection panels and scope proof while avoiding duplicate OCR-page renders.
  if len(parts)>2 and parts[0]=='ocr2' and parts[1].startswith('DOC-') and p.suffix=='.png':continue
  files.append(p)
 dependencies=['tools/a03_financial_field_extractor.py','tools/s00_normalize.py','tools/s01_rules_check.py','tools/s02_calculate.py','tools/l0_classify.py','data/company_master.csv','runs/issues/S01/screen_rules_v2.json','runs/issues/S01/self_check.json','runs/issues/S02/remediation_20261029/l0/l0_rules_patch.json','runs/issues/S02/remediation_20261029/s02/calculation_manifest.json','runs/issues/S02/remediation_20261029/reextract_plan.json']
 for name in dependencies:
  p=ROOT/name;assert p.is_file(),p;files.append(p)
 files=sorted(set(files));manifest=dict(created_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),review_nature='SELF_CHECK',s03_release=False,canonical_v3_directory=str(version.relative_to(ROOT)).replace('\\','/'),files=[dict(path=str(p.relative_to(ROOT)).replace('\\','/'),bytes=p.stat().st_size,sha256=sha(p)) for p in files],note='Contains reviewed source selections/page evidence and a complete normalized v3 gzip; excludes original-report full text, full PDF corpus, OCR runtime, uncompressed normalized table and duplicate input caches. Source review and computational replay are distinct.')
 mp=HERE/'package_manifest.json';mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');files.append(mp)
 dest=ROOT.parent/'S02_18家定向修复_v3_20261030.zip'
 with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p in files:z.write(p,str(p.relative_to(ROOT)).replace('\\','/'))
 with zipfile.ZipFile(dest) as z:
  assert z.testzip() is None
  for row in manifest['files']:assert hashlib.sha256(z.read(row['path'])).hexdigest()==row['sha256']
 print(json.dumps(dict(path=str(dest),bytes=dest.stat().st_size,sha256=sha(dest),files=len(files),manifest_files=len(manifest['files']),zip_hash_checks='PASS'),ensure_ascii=False))
if __name__=='__main__':main()
