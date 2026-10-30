"""把 74 份重抽得到的「扣非累计」行落成 s00_normalize 可直接消费的行结构。

只取 FIN.NPDEDT.YTD 一行；其余字段一律沿用 v7 已入池结果，避免把解析器历史漂移
（当前 HEAD 解析器在部分科创板季报找不到利润表归母）带进本轮。
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research")
HERE = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'tools'))
import a03_financial_field_extractor as A          # noqa: E402

index = {}
for r in csv.DictReader(open(ROOT / 'runs/collection/collection_index.csv', encoding='utf-8-sig')):
    index[(r['security_id'], r['slot_id'])] = r

rows = list(csv.DictReader(open(HERE / 'target_override.csv', encoding='utf-8-sig')))
out = {}
for r in rows:
    rec = index[(r['security_id'], r['slot']) ]
    res = A.extract_one(dict(document_id=rec['document_id'], security_id=r['security_id'],
                             stock_code=r['stock_code'], slot_id=r['slot'],
                             period_label=r['slot'], path=str(ROOT / rec['local_file'])))
    hit = [f for f in res['fields'] if f['field_id'] == 'FIN.NPDEDT.YTD'
           and f['extract_status'] == 'EXTRACTED']
    if len(hit) != 1:
        print('SKIP', r['stock_code'], r['slot'], 'rows=', len(hit))
        continue
    row = dict(hit[0])
    if row['value_raw'] != r['value_raw']:
        print('MISMATCH', r['stock_code'], r['slot'], row['value_raw'], r['value_raw'])
        continue
    out[f"{r['security_id']}|{r['slot']}"] = row

Path(HERE / 'npdedt_override_rows.json').write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
print('rows', len(out))
print(json.dumps(next(iter(out.values())), ensure_ascii=False, indent=1))
