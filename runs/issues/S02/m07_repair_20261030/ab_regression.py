"""A/B 回归：同一份 PDF、同一个营收锚点，比较「HEAD 解析器」与「v8 补丁解析器」
在主要会计数据表上的输出差异。只比关键表，不重跑整份抽取。

判定口径：允许的差异只有「补出原本没有的扣非」；任何既有值被改写或丢失都算回归。
"""
import csv
import json
import random
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research")
HERE = Path(__file__).parent
EXTRACT = ROOT / 'runs/issues/S00/extract'
SLOTS = ['annual_2023', 'annual_2024', 'annual_2025',
         'h1_2024', 'h1_2025', 'h1_2026',
         'q1_2024', 'q1_2025', 'q1_2026',
         'q3_2024', 'q3_2025', 'q3_2026']


def build_docs():
    index = {}
    for r in csv.DictReader(open(ROOT / 'runs/collection/collection_index.csv', encoding='utf-8-sig')):
        if r['status'] != 'COLLECTED_IDENTITY_VERIFIED':
            continue
        if not (ROOT / r['local_file']).exists():
            continue
        index[(r['security_id'], r['slot_id'])] = r
    survey = json.load(open(HERE / 'survey.json', encoding='utf-8'))
    codes = {x['code'] for x in survey}
    focus = {k for k in index if k[0].split(':')[-1] in codes and k[1] in ('q1_2026', 'h1_2026', 'q3_2026')}
    plan = json.loads((ROOT / 'runs/issues/S02/remediation_20261029/reextract_plan.json')
                      .read_text(encoding='utf-8'))
    rem = {(t['security_id'], t['slot_id']) for t in plan['tasks']} & set(index)
    rest = sorted(set(index) - focus - rem)
    random.seed(20261030)
    control = set(random.sample(rest, min(300, len(rest))))
    return index, sorted(focus | rem | control)


def anchor_map():
    out = {}
    for slot in SLOTS:
        p = EXTRACT / f'{slot}_fields.csv'
        if not p.exists():
            continue
        for r in csv.DictReader(open(p, encoding='utf-8-sig')):
            if r['field_id'] == 'FIN.REV.YTD' and r['extract_status'] == 'EXTRACTED':
                out[(r['security_id'], slot)] = r['value_raw']
    for f in (ROOT / 'runs/issues/S02/remediation_20261029/extracted').glob('*.json'):
        j = json.loads(f.read_text(encoding='utf-8'))
        for r in j.get('fields', []):
            if r['field_id'] == 'FIN.REV.YTD' and r['extract_status'] == 'EXTRACTED':
                out[(j['security_id'], j['slot_id'])] = r['value_raw']
    return out


def work(task):
    sec, slot, path, anchor = task
    sys.path.insert(0, str(ROOT / 'tools'))
    sys.path.insert(0, str(HERE))
    from pypdf import PdfReader
    import a03_financial_field_extractor as NEW
    import a03_baseline as OLD
    try:
        reader = PdfReader(str(path))
        pages = [reader.pages[k].extract_text() or '' for k in range(min(60, len(reader.pages)))]
    except Exception as exc:                      # noqa: BLE001
        return dict(security_id=sec, slot=slot, error=f'OPEN:{exc}')
    a = OLD.extract_key_financials(pages, anchor_rev=anchor, with_details=True)
    b = NEW.extract_key_financials(pages, anchor_rev=anchor, with_details=True)
    # v8 的补漏通道在 extract_one 里：原逻辑取不到扣非时才启用，只补这一行
    if 'FIN.NPDEDT.YTD' not in b[0]:
        nd = NEW.find_npdedt_row(pages, anchor_rev=anchor)
        if nd:
            b[0]['FIN.NPDEDT.YTD'] = nd['value']
            b[3]['FIN.NPDEDT.YTD'] = nd
    rows = []
    for fid in sorted(set(a[0]) | set(b[0])):
        if a[0].get(fid) != b[0].get(fid):
            rows.append(dict(security_id=sec, stock_code=sec.split(':')[-1], slot=slot,
                             field_id=fid, old=a[0].get(fid), new=b[0].get(fid),
                             old_page=a[1], new_page=b[1],
                             new_col=(b[3].get(fid) or {}).get('column_index'),
                             new_raw=(b[3].get(fid) or {}).get('raw_row', '')[:120]))
    return dict(security_id=sec, slot=slot, rows=rows)


def main():
    index, docs = build_docs()
    anchors = anchor_map()
    tasks = [(s, sl, ROOT / index[(s, sl)]['local_file'], anchors.get((s, sl))) for s, sl in docs]
    print(f'docs={len(tasks)}', flush=True)
    diffs, errors, done = [], [], 0
    with ProcessPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(work, t) for t in tasks]
        for fu in as_completed(futs):
            r = fu.result()
            done += 1
            if r.get('error'):
                errors.append(r)
            diffs.extend(r.get('rows', []))
            if done % 100 == 0:
                print(f'  {done}/{len(tasks)} diffs={len(diffs)}', flush=True)
    with open(HERE / 'ab_regression.csv', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['security_id', 'stock_code', 'slot', 'field_id',
                                          'old', 'new', 'old_page', 'new_page', 'new_col', 'new_raw'],
                           lineterminator='\n')
        w.writeheader()
        w.writerows(diffs)
    summary = dict(docs=len(tasks), errors=len(errors), diff_rows=len(diffs),
                   by_field=dict(Counter(d['field_id'] for d in diffs)),
                   added=sum(1 for d in diffs if not d['old'] and d['new']),
                   changed=sum(1 for d in diffs if d['old'] and d['new'] and d['old'] != d['new']),
                   lost=sum(1 for d in diffs if d['old'] and not d['new']))
    (HERE / 'ab_regression_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for d in diffs:
        if d['old'] and d['new'] and d['old'] != d['new']:
            print(' CHANGED', d['stock_code'], d['slot'], d['field_id'], d['old'], '->', d['new'])
        if d['old'] and not d['new']:
            print(' LOST', d['stock_code'], d['slot'], d['field_id'], d['old'])


if __name__ == '__main__':
    main()
