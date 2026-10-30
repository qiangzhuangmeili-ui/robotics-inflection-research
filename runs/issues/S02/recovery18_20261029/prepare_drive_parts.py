"""Split the authorized ZIP without changing any archive bytes."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;WORKSPACE=HERE.parents[4]
NAME='S02_18家定向修复_v3_20261030.zip'
EXPECTED='c6e5db79b6e1a19ad90724cda4aa2e861cdf068f883888d0be9393cde8cd6196'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 source=WORKSPACE/NAME;assert sha(source)==EXPECTED
 dest=WORKSPACE/'S02_v3_Drive分卷_20261030';dest.mkdir(exist_ok=True)
 parts=[]
 with source.open('rb') as f:
  n=1
  while data:=f.read(64*1024*1024):
   p=dest/(NAME+f'.part{n:02}');p.write_bytes(data);parts.append(dict(name=p.name,bytes=len(data),sha256=sha(p)));n+=1
 h=hashlib.sha256()
 for item in parts:
  with (dest/item['name']).open('rb') as f:
   for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 assert h.hexdigest()==EXPECTED
 spec=dict(original_name=NAME,original_bytes=source.stat().st_size,original_sha256=EXPECTED,parts=parts,concat_sha256_verified=True)
 (dest/'S02_v3_parts_manifest.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8')
 script='''from pathlib import Path
import hashlib,json
BASE=Path(__file__).resolve().parent
spec=json.loads((BASE/'S02_v3_parts_manifest.json').read_text(encoding='utf-8'))
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
output=BASE/spec['original_name']
if output.exists():
    if sha(output)!=spec['original_sha256']:raise RuntimeError('Existing ZIP differs; keep it and select an empty restore folder.')
    print('VERIFIED: '+str(output));raise SystemExit(0)
temporary=BASE/(spec['original_name']+'.reassembling')
with temporary.open('xb') as target:
    for item in spec['parts']:
        p=BASE/item['name']
        if p.stat().st_size!=item['bytes'] or sha(p)!=item['sha256']:raise RuntimeError('Part mismatch: '+str(p))
        with p.open('rb') as f:
            for b in iter(lambda:f.read(1024*1024),b''):target.write(b)
if temporary.stat().st_size!=spec['original_bytes'] or sha(temporary)!=spec['original_sha256']:raise RuntimeError('Restored ZIP checksum failed')
temporary.rename(output)
print('VERIFIED: '+str(output))
'''
 (dest/'restore_S02_v3.py').write_text(script,encoding='utf-8')
 print(json.dumps(dict(directory=str(dest),**spec),ensure_ascii=False))
if __name__=='__main__':main()
