"""A03 收尾：把全量抽取结果转成字段层核销结论。

做四件事，全部可复算：
1. 字段覆盖率：按 field_id × extract_status 统计，区分「抽到了」「该报表没这个科目」「抽取失败」。
2. 交叉校验：三表 vs 年报摘要表（rev/npp/ocf 三源独立排版），一致才算抽对。
3. 恒等式质检：分季度加总 = 全年累计、单位一致、资产 ≥ 应收+存货。
4. 缺口登记：把「抽取失败」和「需复核」的项写进 field_gaps_for_reconcile.csv，供 remaining_gaps 合并。

输出 runs/issues/A03/field_coverage_annual_full.csv、field_gap_register_annual_full.csv、
field_layer_summary.json。
"""
import argparse
import csv
import io
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/issues/A03'

# 不是缺口的终态：抽到了 / 该报表确实没有这个科目 / 非金额字段
OK_STATUS = {'EXTRACTED'}
NEUTRAL_STATUS = {'NOT_IN_STATEMENT', 'BLANK_IN_STATEMENT', 'NOT_APPLICABLE'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fields', default=str(OUT / 'financial_fields_extracted_annual_full.csv'))
    ap.add_argument('--diag', default=str(OUT / 'extraction_diagnostics_annual_full.csv'))
    ap.add_argument('--quality', default=str(OUT / 'field_quality_check_annual_full.csv'))
    args = ap.parse_args()

    rows = list(csv.DictReader(io.open(args.fields, encoding='utf-8-sig')))
    diag = list(csv.DictReader(io.open(args.diag, encoding='utf-8-sig'))) \
        if Path(args.diag).exists() else []
    quality = list(csv.DictReader(io.open(args.quality, encoding='utf-8-sig'))) \
        if Path(args.quality).exists() else []

    # 1) 覆盖率：按 (slot, field) 聚合，季度字段 4 行算一个槽位判定
    # 聚合键必须带 document_id：否则每个 (slot, field) 只剩一个集合，1054 家会被压成 1
    agg = defaultdict(set)
    for r in rows:
        agg[(r['document_id'], r['slot_id'], r['field_id'])].add(r['extract_status'])

    per_field = defaultdict(lambda: Counter())
    per_slot_field = defaultdict(lambda: Counter())
    for (_doc, slot, fid), sts in agg.items():
        if sts & OK_STATUS:
            per_field[fid]['EXTRACTED'] += 1
            per_slot_field[slot]['EXTRACTED'] += 1
        elif sts <= NEUTRAL_STATUS:
            per_field[fid]['NOT_IN_STATEMENT'] += 1
            per_slot_field[slot]['NOT_IN_STATEMENT'] += 1
        else:
            per_field[fid]['FAILED_OR_REVIEW'] += 1
            per_slot_field[slot]['FAILED_OR_REVIEW'] += 1

    cov_path = OUT / 'field_coverage_annual_full.csv'
    with io.open(cov_path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['field_id', 'extracted', 'not_in_statement', 'failed_or_review', 'total', 'extract_rate'])
        for fid in sorted(per_field):
            c = per_field[fid]
            tot = sum(c.values())
            w.writerow([fid, c['EXTRACTED'], c['NOT_IN_STATEMENT'], c['FAILED_OR_REVIEW'], tot,
                        round(c['EXTRACTED'] / tot, 4) if tot else 0])

    # 2) 缺口登记
    gaps = []
    n = 0
    for r in rows:
        if r['extract_status'] in OK_STATUS | NEUTRAL_STATUS:
            continue
        n += 1
        gaps.append({
            'gap_id': f'FLD-{n:05d}',
            'security_id': r['security_id'], 'stock_code': r['stock_code'],
            'slot_id': r['slot_id'], 'period_label': r['period_label'],
            'field_id': r['field_id'], 'status': r['extract_status'],
            'page': r['page'], 'note': (r['note'] or '')[:120],
            'document_id': r['document_id'],
        })
    gap_path = OUT / 'field_gap_register_annual_full.csv'
    with io.open(gap_path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['gap_id', 'security_id', 'stock_code', 'slot_id',
                                          'period_label', 'field_id', 'status', 'page',
                                          'note', 'document_id'])
        w.writeheader()
        w.writerows(gaps)

    # 3) 交叉校验与质检汇总
    xc = Counter(d.get('xcheck_pass', '') for d in diag)
    q_sum = {}
    if quality:
        def tally(key):
            c = Counter()
            for q in quality:
                v = q.get(key, '') or ''
                c['MATCH' if v == 'MATCH' else ('MISMATCH' if v.startswith('MISMATCH') else v)] += 1
            return dict(c)
        q_sum = {
            'sum_REV': tally('sum_REV'), 'sum_NPP': tally('sum_NPP'),
            'sum_NPDEDT': tally('sum_NPDEDT'), 'sum_OCF': tally('sum_OCF'),
            'unit_consistent': dict(Counter(q['unit_consistent'] for q in quality)),
            'balance_sanity': dict(Counter(q['balance_sanity'] for q in quality)),
        }

    errs = Counter(d.get('parse_error') or '' for d in diag)
    summary = {
        'documents': len({r['document_id'] for r in rows}),
        'field_rows': len(rows),
        'slot_field_pairs': len(agg),
        'per_slot': {k: dict(v) for k, v in per_slot_field.items()},
        'per_field': {k: dict(v) for k, v in per_field.items()},
        'crosscheck_documents': dict(xc),
        'quality': q_sum,
        'parse_errors': {k: v for k, v in errs.items() if k},
        'field_gaps': len(gaps),
        'gap_by_status': dict(Counter(g['status'] for g in gaps)),
        'gap_by_field': dict(Counter(g['field_id'] for g in gaps)),
    }
    json.dump(summary, io.open(OUT / 'field_layer_summary.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=1)[:4000])
    print(f'[A03] wrote {cov_path.name} {gap_path.name} field_layer_summary.json')


if __name__ == '__main__':
    main()
