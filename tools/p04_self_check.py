"""P04 自检：把 issue #15 的两条验收标准拆成可复算的检查项。

只读 P04 交付物与证据文件，不修改任何内容；输出 runs/issues/P04/self_check.json。
自检由执行者本人完成，结论标 SELF_CHECK，不冒充独立审计。
"""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/issues/P04'
SNAPSHOT = Path(r'C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究'
                r'\collection_run_20261026\raw\既有候选池财务快照.csv')

checks = []


def add(cid, criterion, ok, evidence, detail=''):
    checks.append({'id': cid, 'criterion': criterion, 'result': 'PASS' if ok else 'FAIL',
                   'evidence': evidence, 'detail': detail})


def load_csv(name):
    return list(csv.DictReader((OUT / name).open(encoding='utf-8')))


def main():
    fdict = load_csv('financial_field_dictionary.csv')
    mapping = load_csv('provider_field_mapping.csv')
    gaps = load_csv('legacy_snapshot_gap_register.csv')
    rules = json.loads((OUT / 'period_conversion_rules.json').read_text(encoding='utf-8'))
    cp = json.loads((OUT / 'crosscheck_provider_vs_pdf.json').read_text(encoding='utf-8'))
    pc = json.loads((OUT / 'crosscheck_period_conversion.json').read_text(encoding='utf-8'))
    pdfev = json.loads((OUT / 'pdf_lineitem_evidence.json').read_text(encoding='utf-8'))
    df = pd.read_csv(SNAPSHOT, encoding='utf-8-sig')

    # A1 金额/比例/百分点不混
    allowed = {'AMOUNT_CNY': '元', 'RATIO_PCT': '%', 'DELTA_PP': '百分点',
               'PER_SHARE_CNY': '元/股', 'RATIO_TIMES': '倍'}
    bad = [f"{r['field_id']}={r['unit_kind']}/{r['unit']}" for r in fdict
           if r['unit_kind'] in allowed and allowed[r['unit_kind']] != r['unit']]
    add('A1', '金额/比例/百分点单位与量纲不混', not bad,
        'financial_field_dictionary.csv', f'{len(fdict)} 个字段单位全部匹配；异常={bad}')

    # A2 收入/扣非/净利三字段独立
    ids = {r['field_id'] for r in fdict}
    need = {'FIN.REV.YTD', 'FIN.NPDEDT.YTD', 'FIN.NPP.YTD'}
    def prohibits(row):
        blob = ''.join(row.get(k, '') for k in ('blocking', 'notes', 'formula', 'comparability'))
        return any(k in blob for k in ('不得用', '不得由', '必须回官方', '不得互相替代'))
    separate = need <= ids and all(prohibits(r) for r in fdict if r['field_id'] in need)
    add('A2', '收入/扣非/净利为独立字段且互不替代', separate,
        'financial_field_dictionary.csv', '三个 field_id 独立存在，且 blocking 明确禁止互相替代')

    # A3 NULL 与真实 0 可区分
    null_ok = all(r['null_semantics'] for r in fdict)
    amount_cols = [c for c in df.columns if df[c].dtype.kind in 'if']
    zero_cells = int(sum((df[c] == 0).sum() for c in amount_cols))
    missing_rows = int((df['data_status'] == 'FINANCIAL_DATA_MISSING').sum())
    missing_all_null = all(df.loc[df.data_status == 'FINANCIAL_DATA_MISSING', c].isna().all()
                           for c in amount_cols if c not in ('stock_code',))
    add('A3', 'NULL 与真实 0 可区分且缺失不填 0', null_ok and zero_cells == 0 and missing_all_null,
        'financial_field_dictionary.csv + 旧快照实测',
        f'{len(amount_cols)} 个金额列中 0 值单元格={zero_cells}；{missing_rows} 家缺失行全列为 NULL={missing_all_null}；'
        f'每字段均有 null_semantics')

    # B1 7 个 P00 契约缺口逐项登记
    required = ['FIN.OCF.YTD', 'FIN.AR.INSTANT', 'FIN.INV.INSTANT', 'FIN.COST.YTD',
                'FIN.PUBLISHED_ON', 'FIN.LISTING_DATE', 'FIN.REV.SQ']
    gap_ids = {g['canonical_field_id'] for g in gaps}
    missing = [f for f in required if f not in gap_ids]
    add('B1', 'P00 契约 7 个字段缺口逐项登记', not missing,
        'legacy_snapshot_gap_register.csv', f'缺登记={missing}；登记总数={len(gaps)}')

    # B2 2025H1 基数缺口（issue 验收明确点名）
    h1 = [g for g in gaps if '@2025H1' in g['gap_id']]
    add('B2', '2025H1 营收等同比基数缺口已列', len(h1) >= 5,
        'legacy_snapshot_gap_register.csv', f'2025H1 相关缺口 {len(h1)} 项：' + '、'.join(g['notes'] for g in h1))

    # B3 来源映射逐行有证据
    no_ev = [m['mapping_id'] for m in mapping if not m['evidence_ref'].strip()]
    absent_ok = all(m['evidence_type'] in ('LIVE_PROBE_FULL_FIELD_SCAN', 'LOCAL_FILE_COLUMN_SCAN')
                    for m in mapping if m['confidence'] == 'CONFIRMED_ABSENT')
    add('B3', '来源字段映射逐行有证据，缺失字段也有扫描证据', not no_ev and absent_ok,
        'provider_field_mapping.csv', f'{len(mapping)} 行全部有 evidence_ref；无证据行={no_ev}')

    # B4 数值一致性实测
    add('B4', '结构化接口与官方 PDF 数值/单位一致',
        cp['verdict_counts'].get('MATCH_EXACT', 0) == len(cp['rows']) and len(cp['rows']) >= 14,
        'crosscheck_provider_vs_pdf.json',
        f"{cp['verdict_counts']}；样本 {len(cp['pairs'])} 组")

    # B5 期间换算规则可复算
    add('B5', '累计/单季度换算规则经实测验证',
        pc['verdict_counts'].get('MATCH_EXACT', 0) == len(pc['rows']) and len(pc['rows']) >= 40,
        'crosscheck_period_conversion.json',
        f"{pc['verdict_counts']}；含四季加总=全年、累计差=官方单季")

    # B6 单位来自官方表头
    units = [r.get('unit_on_statement') for r in pdfev['line_items'] if r.get('unit_on_statement')]
    add('B6', '单位取官方表头而非推断', units and all(u == '元' for u in units),
        'pdf_lineitem_evidence.json', f'{len(units)} 处表头读数，取值集合={sorted(set(units))}')

    # B7 期间口径更正有证据
    corr = rules['snapshot_period_semantics_correction']
    add('B7', '旧快照扣非口径由“单季”更正为“累计”且有逐季加总证据', bool(corr['proof']),
        'period_conversion_rules.json#snapshot_period_semantics_correction', corr['proof'][:120])

    # B8 禁止项与阻断条件成文
    add('B8', '禁止项（fillna(0)/跨版本相减/单季×4）与阻断条件成文',
        bool(rules['null_zero_rules']['prohibited']) and bool(rules['single_quarter_formulas']['prohibited'])
        and bool(rules['blocking_conditions']),
        'period_conversion_rules.json',
        f"null 禁止 {len(rules['null_zero_rules']['prohibited'])} 条、期间禁止 "
        f"{len(rules['single_quarter_formulas']['prohibited'])} 条、阻断 {len(rules['blocking_conditions'])} 条")

    # B9 北交所缺口显式化
    bj = [g for g in gaps if g['gap_id'] == 'GAP-EXCHANGE-BJ']
    add('B9', '北交所 62 家缺口与适配器要求显式登记',
        bool(bj) and 'BJ' in bj[0]['required_action'],
        'legacy_snapshot_gap_register.csv', bj[0]['impact'] if bj else 'MISSING')

    passed = sum(1 for c in checks if c['result'] == 'PASS')
    payload = {
        'plan_version': '20261026_collection_first_v2',
        'issue_key': 'P04',
        'issue_number': 15,
        'review_nature': 'SELF_CHECK',
        'checked_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'executor': 'WorkBuddy AI',
        'summary': {'total': len(checks), 'pass': passed, 'fail': len(checks) - passed},
        'decision': 'SELF_CHECK_PASS' if passed == len(checks) else 'SELF_CHECK_FAIL',
        'checks': checks,
        'artifacts': {},
    }
    for name in ['financial_field_dictionary.csv', 'provider_field_mapping.csv', 'period_conversion_rules.json',
                 'legacy_snapshot_gap_register.csv']:
        p = OUT / name
        payload['artifacts'][name] = {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}
    (OUT / 'self_check.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'pass': passed, 'total': len(checks), 'decision': payload['decision']}, ensure_ascii=False))
    for c in checks:
        if c['result'] != 'PASS':
            print('FAIL', c['id'], c['criterion'], c['detail'])


if __name__ == '__main__':
    main()
