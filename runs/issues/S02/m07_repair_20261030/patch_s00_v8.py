"""在 s00_v7 上做外科式补丁：只补 74 格扣非累计，并重算依赖它的扣非单季。

不动任何其他字段——v7 的重述判定、OCR 恢复、更正版采用都在 v7 里，重建会全部丢掉
（实测重建会带出 17,168 处 restatement_flag 回退）。

用法：python patch_s00_v8.py
"""
import csv
import gzip
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research")
HERE = Path(__file__).parent
V7 = ROOT / 'runs/issues/S02/remediation_20261029/collect_q3_2026/s00_v7.csv'
SLOT_PERIOD = {'q1_2026': '20260331', 'h1_2026': '20260630', 'q3_2026': '20260930'}
PERIOD_META = {
    '20260331': dict(period_key='20260331', period_type='Q1', period_label='Q1_2026',
                     period_start='2026-01-01', period_end='2026-03-31', fiscal_year='2026',
                     period_source='COLLECTED_2026_SLOT', slot_id='q1_2026'),
    '20260630': dict(period_key='20260630', period_type='H1', period_label='H1_2026',
                     period_start='2026-01-01', period_end='2026-06-30', fiscal_year='2026',
                     period_source='COLLECTED_2026_SLOT', slot_id='h1_2026'),
    '20260930': dict(period_key='20260930', period_type='Q3', period_label='Q3_2026',
                     period_start='2026-01-01', period_end='2026-09-30', fiscal_year='2026',
                     period_source='COLLECTED_2026_SLOT', slot_id='q3_2026'),
}
SLOT_ORDER = {'q1_2026': 1, 'h1_2026': 2, 'q3_2026': 3}
PERIOD_SLOT = {v: k for k, v in SLOT_PERIOD.items()}
FIELDS = ['security_id', 'stock_code', 'stock_name', 'period_key', 'period_type', 'period_label',
          'period_start', 'period_end', 'fiscal_year', 'period_basis', 'period_source', 'slot_id',
          'field_id', 'field_name_cn', 'value_raw', 'unit_raw', 'unit_scale', 'value_cny', 'status',
          'status_reason', 'source_kind', 'document_id', 'source_page', 'evidence_label',
          'published_on', 'collected_at', 'pit_status', 'as_of', 'currency',
          'consolidation_scope', 'listing_date', 'is_pre_listing', 'restatement_flag',
          'low_base_flag', 'comparability_note', 'upstream_hold_fields', 'value_before_adoption',
          'adoption_reason', 'quarterly_inputs', 'version_used', 'original_document_id']


def read(p):
    return list(csv.DictReader(open(p, encoding='utf-8-sig', newline='')))


def write(p, rows, header=FIELDS):
    with open(p, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=header, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def main():
    rows = read(V7)
    header = list(rows[0].keys())
    idx = {(r['security_id'], r['period_key'], r['field_id']): r for r in rows}
    overrides = json.loads((HERE / 'npdedt_override_rows.json').read_text(encoding='utf-8'))

    # ---- 1. 扣非累计
    changed, added = [], []
    for key, ov in overrides.items():
        sec, slot = key.split('|')
        period = SLOT_PERIOD[slot]
        k = (sec, period, 'FIN.NPDEDT.YTD')
        if k in idx:
            r = idx[k]
            old = (r['value_cny'], r['status'])
            r.update(value_raw=ov['value_raw'], unit_raw=ov['unit_raw'] or '元',
                     unit_scale=str(ov['unit_scale'] or 1), value_cny=f"{ov['value_cny']}",
                     status='EXTRACTED_KEY_TABLE', status_reason='',
                     source_kind=r['source_kind'] or 'PDF_STATEMENT',
                     document_id=ov['document_id'], source_page=str(ov['page']),
                     evidence_label=ov['evidence_label'])
            changed.append(dict(security_id=sec, period_key=period, field_id='FIN.NPDEDT.YTD',
                                old_value=old[0], new_value=r['value_cny'],
                                old_status=old[1], new_status=r['status']))
        else:
            # 整期无任何行时（000856 2026Q1 是图片版），只能从本公司其他期克隆元数据，
            # 再按目标期改写期间字段；数值仍来自 ov（已按原页核对）。
            base = idx.get((sec, period, 'FIN.REV.YTD'))
            meta = None
            if base is None:
                base = next((v for (s2, p2, f2), v in idx.items()
                             if s2 == sec and f2 == 'FIN.REV.YTD'), None)
                assert base, f'缺少可克隆模板行 {sec} {period}'
                meta = PERIOD_META[period]
            r = {k2: base.get(k2, '') for k2 in header}
            r.update(field_id='FIN.NPDEDT.YTD', field_name_cn='扣非归母净利润（累计）',
                     value_raw=ov['value_raw'], unit_raw=ov['unit_raw'] or '元',
                     unit_scale=str(ov['unit_scale'] or 1), value_cny=f"{ov['value_cny']}",
                     status='EXTRACTED_KEY_TABLE', status_reason='',
                     source_kind=base.get('source_kind') or 'PDF_STATEMENT',
                     document_id=ov['document_id'], source_page=str(ov['page']),
                     evidence_label=ov['evidence_label'], period_basis='YTD_CUMULATIVE',
                     period_type=base['period_type'], period_label=base['period_label'])
            if meta:
                r.update(meta)
            rows.append(r)
            idx[k] = r
            added.append(dict(security_id=sec, period_key=period, field_id='FIN.NPDEDT.YTD',
                              new_value=r['value_cny'], new_status=r['status']))

    # ---- 2. 扣非单季（只补缺失，不覆盖季报官方单季表）
    targets = {k.split('|')[0] for k in overrides}
    sq_changed = []
    for sec in sorted(targets):
        for year in ('2026',):
            ytd = {p: idx.get((sec, p, 'FIN.NPDEDT.YTD')) for p in
                   (f'{year}0331', f'{year}0630', f'{year}0930')}
            sq = {p: idx.get((sec, p, 'FIN.NPDEDT.SQ')) for p in
                  (f'{year}0331', f'{year}0630', f'{year}0930')}
            # Q1 单季 = Q1 累计
            if sq[f'{year}0331'] is None and ytd[f'{year}0331'] and ytd[f'{year}0331']['value_cny']:
                hi = ytd[f'{year}0331']
                r = {k2: hi.get(k2, '') for k2 in header}
                r.update(field_id='FIN.NPDEDT.SQ', field_name_cn='扣非归母净利润（单季）',
                         period_basis='SINGLE_QUARTER', status='DERIVED_Q1_EQUALS_YTD',
                         status_reason='', source_kind=hi.get('source_kind') or 'PDF_STATEMENT',
                         evidence_label='Q1累计即单季', value_raw=hi['value_raw'],
                         unit_raw='元', unit_scale='1', value_cny=hi['value_cny'])
                rows.append(r)
                idx[(sec, f'{year}0331', 'FIN.NPDEDT.SQ')] = r
                sq_changed.append(dict(security_id=sec, period_key=f'{year}0331',
                                       new_value=r['value_cny'], status=r['status']))
                sq[f'{year}0331'] = r
            # H1 单季 = H1 累计 − Q1 累计；9M 单季 = 9M 累计 − H1 累计
            for p_hi, p_lo, ptype, plabel in ((f'{year}0630', f'{year}0331', 'Q2', f'Q2_{year}'),
                                              (f'{year}0930', f'{year}0630', 'Q3', f'Q3_{year}')):
                if sq[p_hi] is not None:
                    continue
                hi, lo = ytd[p_hi], ytd[p_lo]
                if not hi or not lo:
                    continue
                if not hi['value_cny'] or not lo['value_cny']:
                    continue
                val = round(float(hi['value_cny']) - float(lo['value_cny']), 2)
                tmpl = (idx.get((sec, p_hi, 'FIN.NPP.SQ')) or idx.get((sec, p_hi, 'FIN.REV.SQ'))
                        or idx.get((sec, p_hi, 'FIN.NPDEDT.YTD')))
                assert tmpl, f'缺少单季模板行 {sec} {p_hi}'
                r = {k2: tmpl.get(k2, '') for k2 in header}
                r.update(field_id='FIN.NPDEDT.SQ', field_name_cn='扣非归母净利润（单季）',
                         period_type=ptype, period_label=plabel, period_basis='SINGLE_QUARTER',
                         value_raw='', unit_raw='元', unit_scale='1', value_cny=f'{val}',
                         status='DERIVED_CUMULATIVE_DIFF', status_reason='',
                         source_kind='DERIVED_DIFF', document_id=hi['document_id'],
                         source_page=hi['source_page'],
                         evidence_label=f"{hi['slot_id']}−{lo['slot_id']}",
                         published_on=hi['published_on'], pit_status=hi['pit_status'],
                         restatement_flag=hi['restatement_flag'],
                         version_used=hi['version_used'])
                rows.append(r)
                idx[(sec, p_hi, 'FIN.NPDEDT.SQ')] = r
                sq_changed.append(dict(security_id=sec, period_key=p_hi,
                                       new_value=r['value_cny'], status=r['status']))

    out = HERE / 's00_v8.csv'
    write(out, rows, header)
    with (HERE / 's00_v8.csv.gz').open('wb') as raw:
        with gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as g:
            g.write(out.read_bytes())

    summary = dict(source=str(V7.relative_to(ROOT)).replace('\\', '/'),
                   source_sha256=hashlib.sha256(V7.read_bytes()).hexdigest(),
                   rows_v7=len(read(V7)), rows_v8=len(rows),
                   npdedt_updated=len(changed), npdedt_added=len(added),
                   sq_added=len(sq_changed),
                   sq_by_status=dict(Counter(x['status'] for x in sq_changed)),
                   v8_sha256=hashlib.sha256(out.read_bytes()).hexdigest())
    (HERE / 's00_v8_patch_summary.json').write_text(
        json.dumps(dict(summary, npdedt_changes=changed + added, sq_changes=sq_changed),
                   ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
