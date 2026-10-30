"""S02 v8：以 s00_v8（= v7 + 74 格扣非 + 126 格扣非单季）为输入，重算全池 12 指标。

指标公式/阈值/规则内容一律不动，只更新输入指纹。
"""
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research")
OUT = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'tools'))
import s02_calculate as S          # noqa: E402
import l0_classify as L            # noqa: E402

V7_S02 = ROOT / 'runs/issues/S02/remediation_20261029/collect_q3_2026/s02_v7_guarded/all_pool_metrics.csv'
NP = OUT / 's00_v8.csv'
GZ = OUT / 's00_v8.csv.gz'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read(p):
    return list(csv.DictReader(open(p, encoding='utf-8-sig', newline='')))


def write(p, rows):
    with open(p, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def main():
    patch = json.loads((OUT / 's00_v8_patch_summary.json').read_text(encoding='utf-8'))
    manifest = dict(
        version='S00_M07_NPDEDT_REPAIR_V8_20261030',
        built_from=patch['source'], built_from_sha256=patch['source_sha256'],
        patch=dict(npdedt_added=patch['npdedt_added'], npdedt_updated=patch['npdedt_updated'],
                   sq_added=patch['sq_added'], sq_by_status=patch['sq_by_status']),
        scope='仅补 FIN.NPDEDT.YTD 与其单季派生；其余字段、重述判定、更正版采用沿用 v7',
        rows=patch['rows_v8'], sha256=patch['v8_sha256'])
    mp = OUT / 's00_v8_manifest.json'
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')

    rules = json.loads((ROOT / 'runs/issues/S01/screen_rules_v2.json').read_text(encoding='utf-8'))
    base_rules = json.loads(json.dumps(rules))
    fps = [GZ, mp, ROOT / 'data/company_master.csv']
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
    S.s01.NORMALIZED = NP
    original_add = S.add

    def add(cid, item, ok, detail, blocking=True, result_override=None):
        if cid == 'P01':
            item = '新输入版本指纹固定，指标公式沿用冻结 S01 v2'
        if cid == 'Q16':
            detail['note'] = ('S00 已覆盖 12 槽；此清单是抽取盲区、口径待核或原 HOLD 的剩余落点，'
                              '不能解释为没有改善。')
        if cid in ('Q13', 'Q14') and not ok:
            return original_add(cid, '与历史 S01 快照的差异（本轮已修复输入，不要求计数不变）',
                                False, detail, False)
        return original_add(cid, item, ok, detail, blocking, result_override)

    S.add = add
    code = S.main()
    assert code == 0, 'S02 blocking checks failed'

    cp = S.S02 / 'company_metric_summary.csv'
    companies = read(cp)
    for r in companies:
        r['l0_evaluability'] = L.classify({s: int(r[col]) for s, col in L.COUNT_COLUMNS.items()})[0]
    write(cp, companies)

    # 并表 HOLD 覆盖（沿用 v7 口径）
    mp2 = S.S02 / 'all_pool_metrics.csv'
    metrics = read(mp2)
    scope_codes = {'002083', '301348'}
    guarded = 0
    for r in metrics:
        if r['stock_code'] in scope_codes and r['metric_status'] == 'OK' \
                and r['metric_id'] not in ('M08', 'M12'):
            r['metric_status'] = 'HOLD'
            r['quality_flags'] = 'Q01_SCOPE_CHANGE'
            guarded += 1
    write(mp2, metrics)

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
        npdedt_added=patch['npdedt_added'], sq_added=patch['sq_added'],
        metric_changes=len(md),
        metric_companies=len({d['security_id'] for d in md}),
        metric_delta_by_metric=dict(Counter(d['metric_id'] for d in md)),
        metric_delta_by_status={f'{k[0]}->{k[1]}': v for k, v in
                                Counter((d['old_status'], d['new_status']) for d in md).items()},
        scope_guard_rows=guarded,
        status_counts=dict(Counter(r['metric_status'] for r in metrics)),
        l0_counts=dict(Counter(r['l0_evaluability'] for r in companies)),
    )
    (OUT / 'rebuild_v8_summary.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
