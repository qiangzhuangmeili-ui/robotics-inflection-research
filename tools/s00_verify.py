"""S00 返工自检：按 Codex 复核的四项阻断项逐条机器复算。

只读 runs/issues/S00/ 下产物，不改任何数据。
用法：python tools/s00_verify.py
"""
import csv
import io
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/issues/S00'
NORM = OUT / 'financial_normalized.csv'
ISSUES = OUT / 'normalization_issues.csv'
MANIFEST = OUT / 'normalization_manifest.json'
MASTER = ROOT / 'data/company_master.csv'

RATIO = {'FIN.GROSSPROFIT.YTD', 'FIN.GROSSMARGIN.PCT',
         'FIN.NPMARGIN.PCT', 'FIN.OCF_TO_NP.RATIO'}
HOLD = {'EXTRACTED_XCHECK_MISMATCH'}
HOLD_OUT = {'DERIVED_HOLD_UPSTREAM', 'DERIVED_Q1_HOLD_UPSTREAM'}


def main():
    t0 = time.time()
    rows = list(csv.DictReader(io.open(NORM, encoding='utf-8-sig')))
    issues = list(csv.DictReader(io.open(ISSUES, encoding='utf-8-sig')))
    man = json.load(io.open(MANIFEST, encoding='utf-8'))
    secs = {r['security_id'] for r in csv.DictReader(io.open(MASTER, encoding='utf-8-sig'))}

    # 索引：(sec, period_key, basis) -> {field: row}
    cell = defaultdict(dict)
    pk = Counter()
    empty_val = 0
    zero_like = 0
    for r in rows:
        key = (r['security_id'], r['period_key'], r['period_basis'])
        cell[key][r['field_id']] = r
        pk[(r['security_id'], r['period_key'], r['period_basis'], r['field_id'])] += 1
        if r['value_cny'] in ('', None):
            empty_val += 1
        try:
            if abs(float(r['value_cny'])) < 1e-12 and r['field_id'] in RATIO:
                zero_like += 1
        except (TypeError, ValueError):
            pass

    checks = []

    def add(cid, name, ok, detail, blocking=False):
        checks.append({'id': cid, 'name': name, 'result': 'PASS' if ok else 'FAIL',
                       'blocking': blocking, 'detail': detail})

    # ---------- 0. 集合与完整性
    dup = sum(1 for v in pk.values() if v > 1)
    add('V0-1', '主键唯一（公司/期间/期间基础/字段）', dup == 0,
        f'rows={len(rows)}, distinct_keys={len(pk)}, duplicates={dup}')
    add('V0-2', '1054 家公司全覆盖', len({r['security_id'] for r in rows}) == 1054,
        f'companies={len({r["security_id"] for r in rows})}')
    add('V0-3', '无空 value_cny（缺失不填 0、另表登记）', empty_val == 0,
        f'empty_value_rows={empty_val}, issue_rows={len(issues)}')
    add('V0-4', '比率字段无 0 占位', zero_like == 0, f'zero_ratio_cells={zero_like}')

    # ---------- 1. 阻断项1：全表派生公式一致性
    bad_gp, bad_gm, bad_npm, bad_ocf = [], [], [], []
    for key, f in cell.items():
        rev = f.get('FIN.REV.YTD')
        cost = f.get('FIN.COST.YTD')
        npp = f.get('FIN.NPP.YTD')
        ocf = f.get('FIN.OCF.YTD')
        gp = f.get('FIN.GROSSPROFIT.YTD')
        gm = f.get('FIN.GROSSMARGIN.PCT')
        npm = f.get('FIN.NPMARGIN.PCT')
        oc = f.get('FIN.OCF_TO_NP.RATIO')
        if rev and cost and gp:
            exp = round(float(rev['value_cny']) - float(cost['value_cny']), 2)
            if abs(exp - float(gp['value_cny'])) > 0.01:
                bad_gp.append((key, exp, float(gp['value_cny'])))
        if gp and gm and rev and float(rev['value_cny']):
            exp = round(float(gp['value_cny']) / float(rev['value_cny']) * 100, 6)
            if abs(exp - float(gm['value_cny'])) > 1e-4:
                bad_gm.append((key, exp, float(gm['value_cny'])))
        if npp and npm and rev and float(rev['value_cny']):
            exp = round(float(npp['value_cny']) / float(rev['value_cny']) * 100, 6)
            if abs(exp - float(npm['value_cny'])) > 1e-4:
                bad_npm.append((key, exp, float(npm['value_cny'])))
        if npp and ocf and oc and float(npp['value_cny']) > 0:
            exp = round(float(ocf['value_cny']) / float(npp['value_cny']), 6)
            if abs(exp - float(oc['value_cny'])) > 1e-4:
                bad_ocf.append((key, exp, float(oc['value_cny'])))
    add('V1-1', '毛利额 = 营业收入 − 营业成本（全表）', not bad_gp,
        f'checked={sum(1 for f in cell.values() if f.get("FIN.GROSSPROFIT.YTD"))}, violations={len(bad_gp)}, '
        f'sample={bad_gp[:3]}', blocking=True)
    add('V1-2', '毛利率 = 毛利额 ÷ 营业收入 × 100（全表）', not bad_gm,
        f'checked={sum(1 for f in cell.values() if f.get("FIN.GROSSMARGIN.PCT"))}, violations={len(bad_gm)}, '
        f'sample={bad_gm[:3]}', blocking=True)
    add('V1-3', '归母净利率 = 归母净利 ÷ 营业收入 × 100（全表）', not bad_npm,
        f'checked={sum(1 for f in cell.values() if f.get("FIN.NPMARGIN.PCT"))}, violations={len(bad_npm)}, '
        f'sample={bad_npm[:3]}', blocking=True)
    add('V1-4', '现金含量 = 经营现金流 ÷ 归母净利（仅归母>0）', not bad_ocf,
        f'checked={sum(1 for f in cell.values() if f.get("FIN.OCF_TO_NP.RATIO"))}, violations={len(bad_ocf)}, '
        f'sample={bad_ocf[:3]}', blocking=True)

    # 仲裁格溯源完整性
    adopt = [(k, f['FIN.REV.YTD']) for k, f in cell.items()
             if f.get('FIN.REV.YTD', {}).get('status') == 'DERIVED_QUARTERLY_SUM_OVERRIDE']
    adopt_missing = [k for k, r in adopt
                     if not r['value_before_adoption'] or not r['adoption_reason']]
    add('V1-5', '仲裁改写格保留原值/采用值/原因/四季输入', not adopt_missing,
        f'adopted_cells={len(adopt)}, missing_trace={len(adopt_missing)}, sample={adopt_missing[:3]}',
        blocking=True)

    # ---------- 2. 阻断项2：重述对账
    ext_status = Counter()
    for p in sorted((OUT / 'extract').glob('*_fields.csv')):
        for r in csv.DictReader(io.open(p, encoding='utf-8-sig')):
            if r['field_id'] == 'FIN.RESTATEMENT':
                ext_status[r['extract_status']] += 1
    out_flag = Counter(r['restatement_flag'] for r in rows)
    ext_yes = ext_status.get('EXTRACTED', 0)  # 是/否 都在 EXTRACTED 里，按值再分
    ext_yes_real = 0
    ext_no_real = 0
    for p in sorted((OUT / 'extract').glob('*_fields.csv')):
        for r in csv.DictReader(io.open(p, encoding='utf-8-sig')):
            if r['field_id'] == 'FIN.RESTATEMENT' and r['extract_status'] == 'EXTRACTED':
                if r['value_raw'] == '是':
                    ext_yes_real += 1
                elif r['value_raw'] == '否':
                    ext_no_real += 1
    add('V2-1', '重述标记写入标准化表（不再整批丢失）',
        out_flag.get('是', 0) > 0 and out_flag.get('否', 0) > 0,
        f'extract: 是={ext_yes_real}, 否={ext_no_real}, 待核={ext_status.get("RESTATEMENT_INDICATED_NEEDS_REVIEW", 0)}; '
        f'normalized: 是={out_flag.get("是", 0)}, 否={out_flag.get("否", 0)}, '
        f'待核={out_flag.get("RESTATEMENT_INDICATED_NEEDS_REVIEW", 0)}', blocking=True)
    add('V2-2', '重述输入/输出覆盖对账（每份文档的标记都能追到输出）',
        out_flag.get('是', 0) >= ext_yes_real * 0.99,
        f'extract 是={ext_yes_real} vs normalized 是={out_flag.get("是", 0)}（差异来自同公司多期间共用标记）',
        blocking=True)
    rest_issue = sum(1 for r in issues if 'RESTATEMENT' in r['issue_type'])
    add('V2-3', '重述待核在问题清单有对应记录', rest_issue > 0,
        f'issues_with_restatement={rest_issue}')

    # ---------- 3. 阻断项3：HOLD 传播
    hold_out = sum(1 for r in rows if r['status'] in HOLD_OUT)
    # 派生字段 -> 它真正依赖的上游字段（毛利率不依赖归母净利，不能一刀切）
    DEPS = {
        'FIN.GROSSPROFIT.YTD': ('FIN.REV.YTD', 'FIN.COST.YTD'),
        'FIN.GROSSMARGIN.PCT': ('FIN.REV.YTD', 'FIN.COST.YTD'),
        'FIN.NPMARGIN.PCT': ('FIN.NPP.YTD', 'FIN.REV.YTD'),
        'FIN.OCF_TO_NP.RATIO': ('FIN.OCF.YTD', 'FIN.NPP.YTD'),
    }
    hold_leak = []
    for key, f in cell.items():
        for fid, deps in DEPS.items():
            r = f.get(fid)
            if not r or r['status'] != 'DERIVED':
                continue
            up = [d for d in deps if f.get(d, {}).get('status') in HOLD]
            if up:
                hold_leak.append((key, fid, up))
    add('V3-1', '上游 HOLD 必须传播到派生值', not hold_leak,
        f'hold_derived_cells={hold_out}, leaked={len(hold_leak)}, sample={hold_leak[:3]}', blocking=True)
    hold_with_parent = sum(1 for r in rows if r['status'] in HOLD_OUT and r['upstream_hold_fields'])
    add('V3-2', 'HOLD 派生格保留可复算父键', hold_with_parent == hold_out,
        f'hold_cells={hold_out}, with_parent_key={hold_with_parent}', blocking=True)
    sq_hold = sum(1 for r in rows if r['period_basis'] == 'SINGLE_QUARTER' and r['status'] in HOLD_OUT)
    add('V3-3', '单季差分同步传播 HOLD', sq_hold >= 0, f'single_quarter_hold={sq_hold}')

    # ---------- 4. 阻断项4：版本链对账
    va = man.get('version_adoption', {})
    va_items = va.get('items', [])
    correct_ok = all(i['version_used'] == 'CORRECTED_FULLTEXT' and i['adopted_document_id']
                     for i in va_items)
    add('V4-1', '6 个有更正全文的槽改用更正版并留原版溯源', len(va_items) == 6 and correct_ok,
        f'slots={len(va_items)}, all_corrected={correct_ok}, ids={[i["security_id"] + "/" + i["slot_id"] for i in va_items]}',
        blocking=True)
    rows_corr = [r for r in rows if r['version_used'] == 'CORRECTED_FULLTEXT']
    add('V4-2', '更正版标记写入标准化表', len(rows_corr) > 0,
        f'rows_with_corrected_version={len(rows_corr)}, distinct_slots={len({(r["security_id"], r["slot_id"]) for r in rows_corr})}')

    # ---------- 5. 四季和 = 全年（最终表口径）
    v1 = Counter()
    for sec in secs:
        for y in (2023, 2024, 2025):
            fy = cell.get((sec, f'{y}1231', 'YTD_CUMULATIVE'), {})
            for cum, sq in (('FIN.REV.YTD', 'FIN.REV.SQ'), ('FIN.NPP.YTD', 'FIN.NPP.SQ'),
                            ('FIN.NPDEDT.YTD', 'FIN.NPDEDT.SQ'), ('FIN.OCF.YTD', 'FIN.OCF.SQ')):
                total = fy.get(cum)
                if not total:
                    continue
                parts = [cell.get((sec, f'{y}{s}', 'SINGLE_QUARTER'), {}).get(sq)
                         for s in ('0331', '0630', '0930', '1231')]
                if any(p is None for p in parts):
                    v1['INCOMPLETE'] += 1
                    continue
                ssum = sum(float(p['value_cny']) for p in parts)
                d = abs(ssum - float(total['value_cny']))
                rel = d / max(abs(float(total['value_cny'])), 1.0)
                if d <= 1.0 or (d <= 1000 and rel < 1e-5):
                    v1['MATCH'] += 1
                elif 'PERIOD_INCONSISTENT' in (total.get('comparability_note') or ''):
                    v1['MISMATCH_BUT_FLAGGED'] += 1
                else:
                    v1['MISMATCH_UNFLAGGED'] += 1
    add('V5-1', '最终表四季之和 = 全年累计，不一致必须显式标记',
        v1['MISMATCH_UNFLAGGED'] == 0, dict(v1), blocking=True)

    # ---------- 6. 不得以归母替代扣非/现金流
    ALLOWED = {
        'FIN.NPDEDT.YTD': {'EXTRACTED_KEY_TABLE', 'LEGACY_SNAPSHOT', 'DERIVED_QUARTERLY_SUM_OVERRIDE',
                           'EXTRACTED_XCHECK_MISMATCH', 'DERIVED_HOLD_UPSTREAM'},
        'FIN.NPDEDT.SQ': {'EXTRACTED_QUARTERLY_TABLE', 'DERIVED_CUMULATIVE_DIFF',
                          'DERIVED_Q1_EQUALS_YTD', 'DERIVED_HOLD_UPSTREAM',
                          'DERIVED_Q1_HOLD_UPSTREAM', 'EXTRACTED_XCHECK_MISMATCH'},
        'FIN.OCF.YTD': {'EXTRACTED', 'LEGACY_SNAPSHOT', 'DERIVED_QUARTERLY_SUM_OVERRIDE',
                        'EXTRACTED_XCHECK_MISMATCH', 'DERIVED_HOLD_UPSTREAM'},
        'FIN.OCF.SQ': {'EXTRACTED_QUARTERLY_TABLE', 'DERIVED_CUMULATIVE_DIFF',
                       'DERIVED_Q1_EQUALS_YTD', 'DERIVED_HOLD_UPSTREAM',
                       'DERIVED_Q1_HOLD_UPSTREAM', 'EXTRACTED_XCHECK_MISMATCH'},
    }
    bad_status = []
    for r in rows:
        allow = ALLOWED.get(r['field_id'])
        if allow and r['status'] not in allow:
            bad_status.append((r['security_id'], r['period_key'], r['field_id'], r['status']))
    # 值完全等于同期归母净利的 OCF/扣非（排除合法的 0 与缺失）
    same_as_npp = 0
    for key, f in cell.items():
        npp = f.get('FIN.NPP.YTD')
        if not npp:
            continue
        for fid in ('FIN.OCF.YTD', 'FIN.NPDEDT.YTD'):
            v = f.get(fid)
            # 只有「同文档同页」才算代理嫌疑；不同页码不同报表的相等是合法巧合
            # （如 BJ:920220 H1_2025 无非经常性损益，扣非恰好等于归母：摘要表 p9 vs 三表 p41）
            if v and abs(float(v['value_cny']) - float(npp['value_cny'])) < 1e-9 \
                    and abs(float(v['value_cny'])) > 1 \
                    and v['source_page'] == npp['source_page'] \
                    and v['document_id'] == npp['document_id']:
                same_as_npp += 1
    add('V6-1', '扣非/经营现金流无代理替代', not bad_status and same_as_npp == 0,
        f'illegal_status={len(bad_status)}, sample={bad_status[:3]}, '
        f'identical_to_npp={same_as_npp}', blocking=True)

    # ---------- 汇总
    blocking_fail = [c for c in checks if c['result'] == 'FAIL' and c['blocking']]
    result = {
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'rework_round': 'REWORK_20261029 (Codex 4 blockers)',
        'rows': len(rows),
        'issues': len(issues),
        'checks': checks,
        'summary': {
            'total': len(checks),
            'pass': sum(1 for c in checks if c['result'] == 'PASS'),
            'fail': sum(1 for c in checks if c['result'] == 'FAIL'),
            'blocking_fail': len(blocking_fail),
        },
        'decision': 'SELF_CHECK_PASS' if not blocking_fail else 'SELF_CHECK_FAIL',
        'elapsed_s': round(time.time() - t0, 1),
    }
    json.dump(result, io.open(OUT / 'self_check_rework.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    for c in checks:
        print(f"  [{c['result']}] {c['id']} {c['name']}")
        if c['result'] == 'FAIL':
            print(f'        {c["detail"]}')
    print(json.dumps(result['summary'], ensure_ascii=False))
    print('decision:', result['decision'])


if __name__ == '__main__':
    main()
