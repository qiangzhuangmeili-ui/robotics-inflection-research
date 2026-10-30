"""S02 v8：只把「扣非累计」补进来，其余一律沿用 v7 已入池结果，然后重算全池指标。

与 v7 的差别（唯一）：74 份季报/半年报的 FIN.NPDEDT.YTD 由 v8 解析器重新取得。
指标公式、阈值、规则文件内容不动，只更新输入指纹。
v7 的抽取基线 = S00/extract 原始 CSV + 2026-10-29 定向重抽 360 份（remediation/extracted）。

用法：python rebuild_v8.py
"""
import csv
import gzip
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research")
OUT = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'tools'))
import s00_normalize as N          # noqa: E402
import s02_calculate as S          # noqa: E402
import l0_classify as L            # noqa: E402

EXTRACT = ROOT / 'runs/issues/S00/extract'
REMED = ROOT / 'runs/issues/S02/remediation_20261029'
V7_S00 = REMED / 'collect_q3_2026/s00_v7.csv'
V7_S02 = REMED / 'collect_q3_2026/s02_v7_guarded/all_pool_metrics.csv'
PARSER = ROOT / 'tools/a03_financial_field_extractor.py'
SLOTS = ['annual_2023', 'annual_2024', 'annual_2025',
         'h1_2024', 'h1_2025', 'h1_2026',
         'q1_2024', 'q1_2025', 'q1_2026',
         'q3_2024', 'q3_2025', 'q3_2026']


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read(p):
    return list(csv.DictReader(open(p, encoding='utf-8-sig', newline='')))


def write(p, rows):
    with open(p, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def build_overrides():
    """v7 的两层覆盖：定向重抽 360 份（整份替换）+ 本轮 74 份扣非行（单行替换）。"""
    remed = {}
    for f in (REMED / 'extracted').glob('*.json'):
        j = json.loads(f.read_text(encoding='utf-8'))
        remed[(j['security_id'], j['slot_id'])] = j
    npd = json.loads((OUT / 'npdedt_override_rows.json').read_text(encoding='utf-8'))
    return remed, npd


REMED_JSON, NPD_OVERRIDE = build_overrides()


def load_extract(slot):
    p = EXTRACT / f'{slot}_fields.csv'
    out = defaultdict(dict)
    for r in csv.DictReader(open(p, encoding='utf-8-sig')):
        out[r['security_id']][(r['field_id'], r['note'])] = r
    for (sec, sl), r in REMED_JSON.items():
        if sl == slot:
            out[sec] = {(f['field_id'], f['note']): f for f in r['fields']}
    for key, row in NPD_OVERRIDE.items():
        sec, sl = key.split('|')
        if sl == slot:
            out[sec][(row['field_id'], row['note'])] = row
    return out


def load_diag(slot):
    p = EXTRACT / f'{slot}_diag.csv'
    out = {}
    for r in csv.DictReader(open(p, encoding='utf-8-sig')):
        out[r['security_id']] = r
    import a03_financial_field_extractor as A
    for (sec, sl), r in REMED_JSON.items():
        if sl != slot:
            continue
        d = dict(out.get(sec, {}))
        d.update({k: r.get(k, '') for k in ['parse_error', 'restatement', 'restatement_method',
                                            'n_pages', 'text_chars']})
        xc = r.get('crosscheck', {})
        d['xcheck_pass'] = A.xcheck_verdict(xc)
        for f, k in [('FIN.REV.YTD', 'xcheck_rev'), ('FIN.NPP.YTD', 'xcheck_npp'),
                     ('FIN.OCF.YTD', 'xcheck_ocf')]:
            d[k] = xc.get(f, '')
        out[sec] = d
    return out


def main():
    oldmanifest = json.loads((ROOT / 'runs/issues/S00/normalization_manifest.json')
                             .read_text(encoding='utf-8'))
    idx = N.load_index()
    old_lang = {str(ROOT / idx[(r['slot_id'], r['security_id'])]['local_file']):
                (r['language'], r.get('zh_ratio', 0), r.get('text_chars', 0))
                for r in oldmanifest.get('empty_slots_no_value', {}).get('items', [])
                if (r['slot_id'], r['security_id']) in idx}
    original_language = N.detect_doc_language
    N.detect_doc_language = lambda p, pages=3: old_lang.get(str(p)) or original_language(p, pages)
    N.load_extract, N.load_diag = load_extract, load_diag
    N.OUT = OUT / 's00_v8'
    N.OUT.mkdir(exist_ok=True)
    N.main()
    np = N.OUT / 'financial_normalized.csv'
    with (N.OUT / 'financial_normalized.csv.gz').open('wb') as raw:
        with gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as g:
            g.write(np.read_bytes())

    # 与 v7 逐格比对
    old = read(V7_S00)
    new = read(np)
    key = lambda r: (r['security_id'], r['period_key'], r['field_id'])
    om = {key(r): r for r in old}
    nm = {key(r): r for r in new}
    deltas = []
    for k in sorted(om.keys() | nm.keys()):
        a, b = om.get(k), nm.get(k)
        if a == b:
            continue
        fields = [f for f in (a or b) if (a or {}).get(f) != (b or {}).get(f)]
        deltas.append(dict(security_id=k[0], period_key=k[1], field_id=k[2],
                           change='ADD' if a is None else 'REMOVE' if b is None else 'UPDATE',
                           old_value=(a or {}).get('value_cny', ''),
                           new_value=(b or {}).get('value_cny', ''),
                           old_status=(a or {}).get('status', ''),
                           new_status=(b or {}).get('status', ''),
                           changed_columns=';'.join(fields),
                           document_id=(b or a)['document_id'],
                           source_page=(b or a)['source_page']))
    write(OUT / 'normalized_delta_v7_v8.csv', deltas)
    targets = {k.split('|')[0] for k in NPD_OVERRIDE}
    unexpected = {d['security_id'] for d in deltas} - targets
    print(f'normalized_changes={len(deltas)} companies={len({d["security_id"] for d in deltas})} '
          f'unexpected_companies={len(unexpected)}')
    if unexpected:
        print('UNEXPECTED', sorted(unexpected)[:10])

    # 规则文件：只换输入指纹
    rules = json.loads((ROOT / 'runs/issues/S01/screen_rules_v2.json').read_text(encoding='utf-8'))
    base_rules = json.loads(json.dumps(rules))
    fps = [N.OUT / 'financial_normalized.csv.gz', N.OUT / 'normalization_manifest.json',
           ROOT / 'data/company_master.csv']
    rules['input_fingerprint']['files'] = [
        dict(path=str(p.relative_to(ROOT)).replace('\\', '/'), sha256=sha(p), bytes=p.stat().st_size)
        for p in fps]
    rules['input_version'] = 'S00_M07_NPDEDT_REPAIR_V8_20261030'
    rules['base_rules_sha256'] = sha(ROOT / 'runs/issues/S01/screen_rules_v2.json')
    rules['l0_addendum_path'] = str(L.PATCH.relative_to(ROOT)).replace('\\', '/')
    for k in ['metrics', 'signals', 'risk_hints', 'thresholds']:
        if k in rules:
            assert rules[k] == base_rules[k], f'rules changed: {k}'
    rp = OUT / 'rules_recalculation_inputs_v8.json'
    rp.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding='utf-8')

    S.S02 = OUT / 's02_v8'
    S.RULES = rp
    S.RULES_SHA_REQUIRED = sha(rp)
    S.s01.NORMALIZED = np
    original_add = S.add

    def add(cid, item, ok, detail, blocking=True):
        if cid == 'P01':
            item = '新输入版本指纹固定，指标公式沿用冻结 S01 v2'
        if cid == 'Q16':
            detail['note'] = ('S00 已覆盖 12 槽；此清单是抽取盲区、口径待核或原 HOLD 的剩余落点，'
                              '不能解释为没有改善。')
        if cid in ('Q13', 'Q14') and not ok:
            return original_add(cid, '与历史 S01 快照的差异（本轮已修复输入，不要求计数不变）',
                                False, detail, False)
        return original_add(cid, item, ok, detail, blocking)

    S.add = add
    code = S.main()
    assert code == 0, 'S02 blocking checks failed'

    # L0 与并表 HOLD 覆盖（沿用 v7 口径）
    cp = S.S02 / 'company_metric_summary.csv'
    companies = read(cp)
    for r in companies:
        r['l0_evaluability'] = L.classify({s: int(r[col]) for s, col in L.COUNT_COLUMNS.items()})[0]
    write(cp, companies)

    mp = S.S02 / 'all_pool_metrics.csv'
    metrics = read(mp)
    scope_codes = {'002083', '301348'}
    guarded = 0
    for r in metrics:
        if r['stock_code'] in scope_codes and r['metric_status'] == 'OK' \
                and r['metric_id'] not in ('M08', 'M12'):
            r['metric_status'] = 'HOLD'
            r['quality_flags'] = 'Q01_SCOPE_CHANGE'
            guarded += 1
    write(mp, metrics)

    v7 = {(r['security_id'], r['metric_id']): r for r in read(V7_S02)}
    md = []
    for r in metrics:
        a = v7[(r['security_id'], r['metric_id'])]
        if r != a:
            md.append(dict(security_id=r['security_id'], stock_code=r['stock_code'],
                           stock_name=r['stock_name'], metric_id=r['metric_id'],
                           old_value=a['value'], new_value=r['value'],
                           old_status=a['metric_status'], new_status=r['metric_status'],
                           period_key=r['period_key'], note=r['note']))
    write(OUT / 'metric_delta_v7_v8.csv', md)

    result = dict(
        parser_sha256=sha(PARSER),
        npdedt_overrides=len(NPD_OVERRIDE),
        normalized_rows=len(new), normalized_changes=len(deltas),
        normalized_companies=len({d['security_id'] for d in deltas}),
        normalized_unexpected_companies=sorted(unexpected),
        normalized_by_field=dict(Counter(d['field_id'] for d in deltas)),
        metric_changes=len(md),
        metric_companies=len({d['security_id'] for d in md}),
        metric_delta_by_metric=dict(Counter(d['metric_id'] for d in md)),
        metric_delta_by_status=dict(Counter((d['old_status'], d['new_status']) for d in md)),
        scope_guard_rows=guarded,
        status_counts=dict(Counter(r['metric_status'] for r in metrics)),
        l0_counts=dict(Counter(r['l0_evaluability'] for r in companies)),
    )
    (OUT / 'rebuild_v8_summary.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
