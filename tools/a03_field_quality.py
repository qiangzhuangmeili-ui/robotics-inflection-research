"""A03 字段质检：用可复算的恒等式检查抽取结果，而不是靠抽样肉眼。

三条校验：
1. 分季度加总 = 全年累计（FIN.*.SQ 四季度之和 vs FIN.*.YTD）。分季度表与合并三表是年报里
   两处独立排版，能对上说明两处都抽对了；对不上必须逐份看，不能默认是公司口径差异。
2. 单位一致性：同一份年报里资产负债表/利润表/现金流量表/分季度表的表头单位应一致。
3. 会计恒等式：资产总计 ≥ 应收账款 + 存货（弱约束，仅用于抓「取错行」这类明显错误）。

输出 runs/issues/A03/field_quality_check.csv 与 field_quality_summary.json。
"""
import argparse
import csv
import io
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/issues/A03'

PAIRS = [
    ('FIN.REV.SQ', 'FIN.REV.YTD'),
    ('FIN.NPP.SQ', 'FIN.NPP.YTD'),
    ('FIN.NPDEDT.SQ', 'FIN.NPDEDT.YTD'),
    ('FIN.OCF.SQ', 'FIN.OCF.YTD'),
]


def load(field_csv):
    rows = list(csv.DictReader(io.open(field_csv, encoding='utf-8-sig')))
    docs = defaultdict(lambda: {'fields': defaultdict(list), 'meta': {}})
    for r in rows:
        d = docs[r['document_id']]
        d['meta'] = {'security_id': r['security_id'], 'stock_code': r['stock_code'],
                     'slot_id': r['slot_id'], 'period_label': r['period_label']}
        d['fields'][r['field_id']].append(r)
    return docs


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def check_doc(doc_id, d):
    out = {'document_id': doc_id, **d['meta']}
    # 1) 分季度加总
    for sq, ytd in PAIRS:
        sq_rows = [r for r in d['fields'].get(sq, []) if r['extract_status'] == 'EXTRACTED']
        ytd_rows = [r for r in d['fields'].get(ytd, []) if r['extract_status'] == 'EXTRACTED']
        tag = sq.split('.')[1].replace('.SQ', '')
        if not ytd_rows:
            out[f'sum_{tag}'] = 'NO_YTD'
            continue
        if len(sq_rows) < 4:
            out[f'sum_{tag}'] = 'INCOMPLETE_QUARTERS'
            continue
        sq_vals = [num(r['value_cny']) for r in sq_rows]
        if any(v is None for v in sq_vals):
            out[f'sum_{tag}'] = 'UNPARSED'
            continue
        total = sum(sq_vals)
        base = num(ytd_rows[0]['value_cny'])
        if base is None:
            out[f'sum_{tag}'] = 'UNPARSED'
            continue
        diff = total - base
        tol = max(1000.0, abs(base) * 5e-4)
        out[f'sum_{tag}'] = 'MATCH' if abs(diff) <= tol else f'MISMATCH({diff:,.2f})'

    # 2) 单位一致性（只比金额字段；重述标记等非金额字段的单位是 NOT_APPLICABLE，不参与）
    units = {r['unit_raw'] for fid, rs in d['fields'].items()
             if fid.startswith('FIN.') and fid != 'FIN.RESTATEMENT'
             for r in rs if r.get('unit_raw') not in ('', 'UNKNOWN', None, 'NOT_APPLICABLE')}
    out['units_seen'] = '|'.join(sorted(units))
    out['unit_consistent'] = 'YES' if len(units) <= 1 else 'NO'

    # 3) 资产总计 ≥ 应收账款 + 存货（弱约束）
    def get(fid):
        rs = [r for r in d['fields'].get(fid, []) if r['extract_status'] == 'EXTRACTED']
        return num(rs[0]['value_cny']) if rs else None

    ta, ar, inv, ca = get('FIN.ASSET.INSTANT'), get('FIN.AR.INSTANT'), \
        get('FIN.INV.INSTANT'), get('FIN.CONTRACTASSET.INSTANT')
    if ta is None or ar is None:
        out['balance_sanity'] = 'SKIP'
    else:
        s = (ar or 0) + (inv or 0) + (ca or 0)
        out['balance_sanity'] = 'OK' if s <= ta * 1.0001 else 'VIOLATION'
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fields', required=True)
    ap.add_argument('--tag', default='')
    args = ap.parse_args()

    docs = load(args.fields)
    rows = [check_doc(k, v) for k, v in docs.items()]
    rows.sort(key=lambda x: (x.get('slot_id', ''), x.get('security_id', '')))

    hdr = ['document_id', 'security_id', 'stock_code', 'slot_id', 'period_label',
           'sum_REV', 'sum_NPP', 'sum_NPDEDT', 'sum_OCF',
           'units_seen', 'unit_consistent', 'balance_sanity']
    path = OUT / f'field_quality_check{args.tag}.csv'
    with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=hdr, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)

    def tally(key):
        c = defaultdict(int)
        for r in rows:
            v = str(r.get(key, ''))
            c['MATCH' if v == 'MATCH' else ('MISMATCH' if v.startswith('MISMATCH')
                                            else v)] += 1
        return dict(c)

    summary = {
        'documents': len(rows),
        'sum_check': {k: tally(f'sum_{k}') for k in ('REV', 'NPP', 'NPDEDT', 'OCF')},
        'unit_consistent': dict((k, sum(1 for r in rows if r['unit_consistent'] == k))
                                for k in ('YES', 'NO')),
        'balance_sanity': dict((k, sum(1 for r in rows if r['balance_sanity'] == k))
                               for k in ('OK', 'VIOLATION', 'SKIP')),
    }
    json.dump(summary, io.open(OUT / f'field_quality_summary{args.tag}.json', 'w',
                               encoding='utf-8'), ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f'[A03] wrote {path.name}')


if __name__ == '__main__':
    main()
