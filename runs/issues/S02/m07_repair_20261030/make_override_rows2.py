"""生成扣非覆盖行（v2）：不再只补「抽不到」的，也补「抽到但单位 UNKNOWN 未折算」的。

判定：v8 解析器在该槽取到 FIN.NPDEDT.YTD 且单位可折算，而 s00_v7 该期没有可用的
扣非累计值（无行或 value_cny 为空），才生成覆盖行；其余一律不动。
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research")
HERE = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'tools'))
import a03_financial_field_extractor as A          # noqa: E402

SLOT = {'20260331': 'q1_2026', '20260630': 'h1_2026', '20260930': 'q3_2026'}
PERIOD_OF_SLOT = {v: k for k, v in SLOT.items()}
USABLE_UNITS = {'元', '千元', '万元', '百万元', '千万元'}

index = {}
for r in csv.DictReader(open(ROOT / 'runs/collection/collection_index.csv', encoding='utf-8-sig')):
    index[(r['security_id'], r['slot_id'])] = r
sec_of = {s.split(':')[-1]: s for s in {k[0] for k in index}}

# s00_v7 现状
v7 = {}
for r in csv.DictReader(open(ROOT / 'runs/issues/S02/remediation_20261029/collect_q3_2026/s00_v7.csv',
                            encoding='utf-8-sig')):
    if r['field_id'] == 'FIN.NPDEDT.YTD':
        v7[(r['security_id'], r['period_key'])] = r['value_cny']

det = json.load(open(HERE / 'm07_detail.json', encoding='utf-8'))
targets = []
for d in det:
    per = d['period']
    mid = '20260331' if per == '20260630' else '20260630'
    for p in (per, mid):
        targets.append((d['code'], d['name'], SLOT[p]))
targets = sorted(set(targets))

rows, skipped = {}, []
for code, name, slot in targets:
    sec = sec_of.get(code)
    rec = index.get((sec, slot))
    if not rec or not (ROOT / rec['local_file']).exists():
        skipped.append(dict(stock_code=code, slot=slot, reason='NO_FILE'))
        continue
    period = PERIOD_OF_SLOT[slot]
    if v7.get((sec, period)):
        continue                     # v7 已有可用值，不动
    res = A.extract_one(dict(document_id=rec['document_id'], security_id=sec, stock_code=code,
                             slot_id=slot, period_label=slot, path=str(ROOT / rec['local_file'])))
    hit = [f for f in res['fields'] if f['field_id'] == 'FIN.NPDEDT.YTD'
           and f['extract_status'] == 'EXTRACTED']
    if len(hit) != 1:
        skipped.append(dict(stock_code=code, slot=slot, reason=f'NO_NPDEDT:{len(hit)}'))
        continue
    row = hit[0]
    if row['unit_raw'] not in USABLE_UNITS or not row['value_cny']:
        skipped.append(dict(stock_code=code, slot=slot,
                            reason=f"UNIT:{row['unit_raw']}/{row['value_raw']}"))
        continue
    rows[f'{sec}|{slot}'] = row

Path(HERE / 'npdedt_override_rows.json').write_text(
    json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
Path(HERE / 'npdedt_override_skipped.json').write_text(
    json.dumps(skipped, ensure_ascii=False, indent=1), encoding='utf-8')
import collections
print('rows', len(rows), dict(collections.Counter(k.split('|')[1] for k in rows)))
print('units', dict(collections.Counter(v['unit_raw'] for v in rows.values())))
print('skipped', len(skipped), dict(collections.Counter(x['reason'].split(':')[0] for x in skipped)))
for x in skipped:
    print('  SKIP', x['stock_code'], x['slot'], x['reason'])
