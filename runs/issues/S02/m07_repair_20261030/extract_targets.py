"""对 86 家 M07 缺失公司的当期/中间期原件，用 v8 解析器重抽，并与 v7 已入池值逐字段比对。

输出：
  target_reextract.json  每份文档的完整抽取结果（只保留必要字段）
  target_field_diff.csv  与 v7 不同的字段（含新增/改动/丢失）
  target_override.csv    拟采用的覆盖行（仅 FIN.NPDEDT.YTD）
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research")
HERE = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'tools'))
import a03_financial_field_extractor as A          # noqa: E402

SLOT = {'20260331': 'q1_2026', '20260630': 'h1_2026', '20260930': 'q3_2026'}
PERIOD_OF_SLOT = {v: k for k, v in SLOT.items()}
SLOTS = ['annual_2023', 'annual_2024', 'annual_2025',
         'h1_2024', 'h1_2025', 'h1_2026',
         'q1_2024', 'q1_2025', 'q1_2026',
         'q3_2024', 'q3_2025', 'q3_2026']

index = {}
for r in csv.DictReader(open(ROOT / 'runs/collection/collection_index.csv', encoding='utf-8-sig')):
    index[(r['security_id'], r['slot_id'])] = r

det = json.load(open(HERE / 'm07_detail.json', encoding='utf-8'))
sec_of = {}
for (sec, slot), r in index.items():
    sec_of[sec.split(':')[-1]] = sec

# v7 已入池值：{security_id: {(field_id): (value_raw, status)}}
v7 = defaultdict(dict)
for slot in SLOTS:
    p = ROOT / f'runs/issues/S00/extract/{slot}_fields.csv'
    if not p.exists():
        continue
    for r in csv.DictReader(open(p, encoding='utf-8-sig')):
        v7[(r['security_id'], slot)][r['field_id']] = (r['value_raw'], r['extract_status'])
for f in (ROOT / 'runs/issues/S02/remediation_20261029/extracted').glob('*.json'):
    j = json.loads(f.read_text(encoding='utf-8'))
    for r in j.get('fields', []):
        v7[(j['security_id'], j['slot_id'])][r['field_id']] = (r['value_raw'], r['extract_status'])

targets = []
for d in det:
    per = d['period']
    mid = '20260331' if per == '20260630' else '20260630'
    for slot in (SLOT[per], SLOT[mid]):
        targets.append((d['code'], d['name'], slot))
targets = sorted(set(targets))

results, diffs, overrides = [], [], []
for code, name, slot in targets:
    sec = sec_of.get(code)
    rec = index.get((sec, slot))
    if not rec or not (ROOT / rec['local_file']).exists():
        results.append(dict(stock_code=code, slot=slot, state='NO_FILE'))
        continue
    r = A.extract_one(dict(document_id=rec['document_id'], security_id=sec, stock_code=code,
                           slot_id=slot, period_label=slot, path=str(ROOT / rec['local_file'])))
    got = {f['field_id']: f for f in r['fields']}
    results.append(dict(stock_code=code, name=name, slot=slot, doc=rec['document_id'],
                        parse_error=r['parse_error'], n_pages=r['n_pages'],
                        text_chars=r['text_chars'],
                        key_financials=r.get('key_financials_values'),
                        npdedt=(got.get('FIN.NPDEDT.YTD') or {}).get('value_raw', ''),
                        crosscheck=r.get('crosscheck')))
    base = v7.get((sec, slot), {})
    for fid, f in got.items():
        old = base.get(fid)
        newv = f.get('value_raw', '')
        oldv = old[0] if old else None
        if oldv is None and not newv:
            continue
        if oldv != newv:
            diffs.append(dict(stock_code=code, stock_name=name, slot=slot, field_id=fid,
                              old_value=oldv if oldv is not None else '<无此行>',
                              new_value=newv,
                              old_status=old[1] if old else '',
                              new_status=f.get('extract_status'),
                              page=f.get('source_page'), note=f.get('note', '')))
    nd = got.get('FIN.NPDEDT.YTD') or {}
    if nd.get('value_raw') and not (base.get('FIN.NPDEDT.YTD') or ('',))[0]:
        overrides.append(dict(security_id=sec, stock_code=code, stock_name=name, slot=slot,
                              period_key=PERIOD_OF_SLOT[slot], document_id=rec['document_id'],
                              value_raw=nd['value_raw'], unit=nd.get('unit') or '',
                              value_cny=nd.get('value_cny'), source_page=nd.get('source_page'),
                              note=nd.get('note', ''), extract_status=nd.get('extract_status')))

json.dump(results, open(HERE / 'target_reextract.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
with open(HERE / 'target_field_diff.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['stock_code', 'stock_name', 'slot', 'field_id',
                                      'old_value', 'new_value', 'old_status', 'new_status',
                                      'page', 'note'], lineterminator='\n')
    w.writeheader()
    w.writerows(diffs)
with open(HERE / 'target_override.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['security_id', 'stock_code', 'stock_name', 'slot',
                                      'period_key', 'document_id', 'value_raw', 'unit',
                                      'value_cny', 'source_page', 'note', 'extract_status'],
                       lineterminator='\n')
    w.writeheader()
    w.writerows(overrides)

print('docs', len(results), 'overrides', len(overrides))
print('字段差异', len(diffs), dict(Counter(d['field_id'] for d in diffs)))
print('差异类型', dict(Counter(('新增' if d['old_value'] == '<无此行>' else
                               '丢失' if not d['new_value'] else '改动') for d in diffs)))
for d in diffs:
    if d['field_id'] != 'FIN.NPDEDT.YTD':
        print(' 非扣非差异', d['stock_code'], d['slot'], d['field_id'], d['old_value'], '->', d['new_value'])
