import io, json, hashlib, csv, os
from pathlib import Path

ROOT = Path('../../../..').resolve()
e = json.load(open('rulings_resolved.json', encoding='utf-8'))['entries'][0]
rf = (ROOT / e['ruling_file']).resolve()
print("ruling_file", rf, rf.exists())
sha2 = hashlib.sha256(rf.read_bytes()).hexdigest()
print("sha match", sha2 == e['ruling_file_sha256'], sha2[:16])

rows = [{
    "ruling_section": e['ruling_section'],
    "allowed_key": e['key'],
    "ruling_file": e['ruling_file'],
    "ruling_file_sha256": sha2,
    "note": "裁决只解除该键；不得扩用到同公司其他字段或期间",
}]
with io.open('ruling_scope.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print(open('ruling_scope.csv', encoding='utf-8-sig').read())
