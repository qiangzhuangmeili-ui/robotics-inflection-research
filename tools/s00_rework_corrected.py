"""S00 返工：对 6 个「已采原版但更正全文已落盘」的槽重抽更正版，并逐字段比对。

阻断项 4：S00 原来直接用台账 document_id 抽，未接 A04 版本链，
6 个槽存在更正版全文却仍采用原版。本脚本只重抽这 6 份（不重跑全池），
输出 corrected 版字段 + 原版/更正版逐字段差异，供标准化阶段做版本采用。

用法：python tools/s00_rework_corrected.py
"""
import csv
import io
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import a03_financial_field_extractor as A03  # noqa: E402

OUT = ROOT / 'runs/issues/S00/rework'
CHAIN = ROOT / 'runs/issues/A04/rework/correction_chain_audit.csv'
INDEX = ROOT / 'runs/collection/collection_index.csv'


def load_index():
    return {(r['slot_id'], r['security_id']): r
            for r in csv.DictReader(io.open(INDEX, encoding='utf-8-sig'))}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    idx = load_index()
    chain = list(csv.DictReader(io.open(CHAIN, encoding='utf-8-sig')))

    todo = []
    for c in chain:
        key = (c['slot_id'], c['security_id'])
        row = idx.get(key)
        if not row:
            continue
        if c['corrected_present'] != 'True':
            continue
        if row['document_id'] != c['original_id']:
            continue  # 台账已采用更正版，无需处理
        code = c['security_id'].split(':')[1]
        cpath = ROOT / 'sources/collection/originals' / code / c['slot_id'] / f"{c['corrected_id']}.pdf"
        opath = ROOT / 'sources/collection/originals' / code / c['slot_id'] / f"{c['original_id']}.pdf"
        todo.append({
            'security_id': c['security_id'], 'stock_code': code, 'slot_id': c['slot_id'],
            'period_label': row['period_label'],
            'original_id': c['original_id'], 'corrected_id': c['corrected_id'],
            'notice_id': c['notice_id'],
            'corrected_path': str(cpath), 'original_path': str(opath),
            'corrected_exists': cpath.exists(), 'original_exists': opath.exists(),
        })

    print(f'[S00-rework] slots needing corrected version: {len(todo)}', flush=True)
    results = []
    for t in todo:
        rec = dict(t)
        if not t['corrected_exists']:
            rec['error'] = 'CORRECTED_FILE_MISSING'
            results.append(rec)
            continue
        task_c = {'document_id': t['corrected_id'], 'security_id': t['security_id'],
                  'stock_code': t['stock_code'], 'slot_id': t['slot_id'],
                  'period_label': t['period_label'], 'path': t['corrected_path']}
        task_o = dict(task_c, document_id=t['original_id'], path=t['original_path'])
        rc = A03.extract_one(task_c)
        ro = A03.extract_one(task_o) if t['original_exists'] else None
        rec['corrected_fields'] = {(f['field_id'], f['note']): f for f in rc.get('fields', [])}
        rec['original_fields'] = {(f['field_id'], f['note']): f for f in (ro or {}).get('fields', [])}
        rec['corrected_xcheck'] = rc.get('crosscheck')
        rec['corrected_diag'] = {k: rc.get(k) for k in
                                 ('n_pages', 'text_chars', 'parse_error', 'unit_bs', 'unit_is', 'unit_cf')}
        results.append(rec)
        print(f"  {t['security_id']} {t['slot_id']}: corrected={t['corrected_id']} "
              f"fields={len(rec['corrected_fields'])} xcheck={A03.xcheck_verdict(rc.get('crosscheck', {}))}",
              flush=True)

    # 逐字段差异
    diff_rows = []
    for rec in results:
        if 'corrected_fields' not in rec:
            continue
        cf, of = rec['corrected_fields'], rec['original_fields']
        keys = sorted(set(cf) | set(of))
        for k in keys:
            a = of.get(k)
            b = cf.get(k)
            va = (a or {}).get('value_cny', '')
            vb = (b or {}).get('value_cny', '')
            sa = (a or {}).get('extract_status', 'MISSING')
            sb = (b or {}).get('extract_status', 'MISSING')
            same = (va == vb and sa == sb)
            diff_rows.append({
                'security_id': rec['security_id'], 'slot_id': rec['slot_id'],
                'field_id': k[0], 'note': k[1],
                'original_document_id': rec['original_id'],
                'corrected_document_id': rec['corrected_id'],
                'original_value': va, 'corrected_value': vb,
                'original_status': sa, 'corrected_status': sb,
                'same': 'YES' if same else 'NO',
                'original_page': (a or {}).get('page', ''),
                'corrected_page': (b or {}).get('page', ''),
            })

    with io.open(OUT / 'corrected_version_fields.csv', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=A03.FIELDS_HEADER)
        w.writeheader()
        for rec in results:
            for k, row in rec.get('corrected_fields', {}).items():
                w.writerow(row)

    with io.open(OUT / 'corrected_vs_original_diff.csv', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(diff_rows[0].keys()) if diff_rows else
                           ['security_id', 'slot_id', 'field_id'])
        w.writeheader()
        w.writerows(diff_rows)

    n_diff = sum(1 for r in diff_rows if r['same'] == 'NO')
    summary = {
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'slots_checked': len(results),
        'slots_with_corrected': len([r for r in results if 'corrected_fields' in r]),
        'field_pairs_compared': len(diff_rows),
        'field_pairs_different': n_diff,
        'items': [{k: r.get(k) for k in ('security_id', 'slot_id', 'original_id', 'corrected_id',
                                         'notice_id', 'corrected_exists', 'error')}
                  for r in results],
    }
    json.dump(summary, io.open(OUT / 'corrected_version_summary.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=1)[:1500], flush=True)


if __name__ == '__main__':
    main()
